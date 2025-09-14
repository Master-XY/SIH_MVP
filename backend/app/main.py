from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI(
    title="SIH MVP API",
    version="0.1.0",
    description="Backend API for SIH MVP (occurrences, otolith classifier, alerts)"
)

# Allow frontend + local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "SIH MVP API running"}

@app.get("/api/v1/occurrences")
def get_occurrences(
    bbox: List[float] = Query(None, description="Bounding box [minLon, minLat, maxLon, maxLat]"),
    date_from: str = Query(None),
    date_to: str = Query(None)
):
    # TODO: query DB for real data
    return {"bbox": bbox, "date_from": date_from, "date_to": date_to, "data": []}

@app.post("/api/v1/otoliths/predict")
def predict_otolith(file: UploadFile = File(...)):
    # TODO: load ML model + return prediction
    return {"species": "Sardinella longiceps", "confidence": 0.85, "explainability_refs": []}

@app.get("/api/v1/alerts")
def get_alerts():
    # TODO: pull from alerts DB
    return {"alerts": [{"id": 1, "type": "SST anomaly", "status": "demo"}]}

@app.post("/api/v1/subscribe")
def subscribe(phone: str):
    # TODO: integrate Twilio
    return {"status": "subscribed", "phone": phone}

@app.get("/api/v1/download")
def download(dataset: str, format: str = "csv"):
    # TODO: stream CSV/NetCDF
    return {"dataset": dataset, "format": format, "url": "/path/to/download"}