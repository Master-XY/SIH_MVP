# backend/app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import uvicorn
import os
from pathlib import Path
import csv
import io

from .db import SessionLocal, engine, Base
from . import models
from .inference import save_upload, predict_otolith_stub
from .alerts import create_advisory_pdf
from . import alerts, models
from . import measurements   # near other relative imports
from .db import SessionLocal, engine, Base
from .db import get_db

# create tables
Base.metadata.create_all(bind=engine)

# Create FastAPI instance
app = FastAPI(title="SIH MVP API", version="1.0")

# Register routers
app.include_router(alerts.router, prefix="/api/v1")

# Root endpoint
@app.get("/")
def root():
    return {"message": "SIH MVP backend is running 🚀"}
app.include_router(alerts.router)

app = FastAPI(title="SIH MVP Backend", version="0.1.0")

app.include_router(measurements.router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}

# Occurrences - return rows from DB
@app.get("/api/v1/occurrences")
def get_occurrences(db: Session = Depends(get_db), bbox: str = None, date_from: str = None, date_to: str = None):
    q = db.query(models.Occurrence)
    # TODO: implement bbox/date filtering properly
    rows = q.limit(1000).all()
    out = []
    for r in rows:
        out.append({
            "occurrenceID": r.occurrenceID,
            "scientificName": r.scientificName,
            "eventDate": r.eventDate,
            "decimalLatitude": r.decimalLatitude,
            "decimalLongitude": r.decimalLongitude,
            "datasetID": r.datasetID,
            "provenance": r.provenance,
            "qc_flag": r.qc_flag
        })
    return out

# Occurrence ingestion: simple CSV ingestion (ETL endpoint)
@app.post("/api/v1/occurrences/load")
def load_occurrences_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Accept a CSV with columns: occurrenceID,scientificName,eventDate,decimalLatitude,decimalLongitude,datasetID"""
    text = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    count = 0
    for row in reader:
        occ = models.Occurrence(
            occurrenceID=row.get("occurrenceID") or f"occ_{count}",
            scientificName=row.get("scientificName"),
            eventDate=row.get("eventDate"),
            decimalLatitude=float(row.get("decimalLatitude") or 0.0),
            decimalLongitude=float(row.get("decimalLongitude") or 0.0),
            datasetID=row.get("datasetID", "uploaded_csv"),
            provenance={"source": file.filename},
            qc_flag=row.get("qc_flag","ok"),
            raw=row
        )
        db.add(occ)
        count += 1
    db.commit()
    return {"status": "ok", "inserted": count}

# Otolith prediction endpoint (uses inference stub)
@app.post("/api/v1/otoliths/predict")
async def otolith_predict(file: UploadFile = File(...)):
    try:
        filename = file.filename
        file.file.seek(0)
        upload_path = save_upload(file.file, filename)
        result = predict_otolith_stub(upload_path)
        return {"filename": filename, "predicted_species": result["species"], "confidence": result["confidence"], "explainability": result["explainability"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Otolith feedback endpoint
@app.post("/api/v1/otoliths/feedback")
def otolith_feedback(corrected_species: str = None, notes: str = None, filename: str = None, db: Session = Depends(get_db)):
    fb = models.OtolithFeedback(filename=filename or "", corrected_species=corrected_species or "", notes=notes or "")
    db.add(fb)
    db.commit()
    return {"status": "ok"}

# Alerts endpoints
@app.get("/api/v1/alerts")
def get_alerts(db: Session = Depends(get_db)):
    rows = db.query(models.Alert).order_by(models.Alert.created_at.desc()).limit(50).all()
    out = []
    for r in rows:
        out.append({"id": r.id, "type": r.type, "status": r.status, "message": r.message, "lat": r.lat, "lon": r.lon, "payload": r.payload, "created_at": r.created_at.isoformat()})
    if not out:
        # return empty list to let frontend fall back to synthetic alerts
        return []
    return {"alerts": out}

@app.get("/api/v1/alerts/{alert_id}/export_pdf")
def export_alert_pdf(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    pdf_bytes = create_advisory_pdf({
        "type": alert.type,
        "status": alert.status,
        "message": alert.message,
        "lat": alert.lat,
        "lon": alert.lon,
        "created_at": alert.created_at.isoformat()
    })
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=advisory_{alert_id}.pdf"})

# Subscribe endpoint
@app.post("/api/v1/subscribe")
def subscribe(phone: str = None, email: str = None, db: Session = Depends(get_db)):
    sub = models.Subscriber(phone=phone or "", email=email or "")
    db.add(sub)
    db.commit()
    return {"status": "ok"}

# Download CSV of occurrences
@app.get("/api/v1/download/occurrences")
def download_occurrences_csv(db: Session = Depends(get_db)):
    rows = db.query(models.Occurrence).limit(10000).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["occurrenceID","scientificName","eventDate","decimalLatitude","decimalLongitude","datasetID"])
    for r in rows:
        writer.writerow([r.occurrenceID, r.scientificName, r.eventDate, r.decimalLatitude, r.decimalLongitude, r.datasetID])
    buf.seek(0)
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=occurrences.csv"})

if __name__ == "__main__":
    print("Run with: uvicorn backend.app.main:app --reload --port 8000")
