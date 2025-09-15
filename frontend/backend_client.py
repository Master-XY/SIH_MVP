# frontend/backend_client.py
import os
from contextlib import contextmanager
from pathlib import Path
import io
import csv

# Import backend models + helpers
from backend.app.db import SessionLocal, Base, engine
from backend.app import models
# import functions we will reuse
from backend.app import alerts as alerts_module
from backend.app import measurements as measurements_module
from backend.app.inference import predict_otolith_stub, save_upload
from backend.app.notifications import send_notifications

# Ensure DB/tables exist
Path(os.environ.get("SIH_DB_PATH", os.path.join(os.getcwd(), "data", "sih.db"))).parent.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)

# Decide local mode: default to local (Streamlit Cloud)
USE_REMOTE = bool(os.environ.get("SIH_BACKEND_URL"))  # if set, will use remote HTTP
REMOTE_BASE = os.environ.get("SIH_BACKEND_URL", "").rstrip("/")

@contextmanager
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Health ----------
def health():
    if USE_REMOTE:
        import requests
        r = requests.get(f"{REMOTE_BASE}/health", timeout=5)
        return r.json()
    return {"status": "ok"}


# ---------- Alerts ----------
def fetch_alerts(limit=50):
    """Return list-of-dicts like the API /alerts"""
    if USE_REMOTE:
        import requests
        r = requests.get(f"{REMOTE_BASE}/alerts", timeout=6)
        try:
            return r.json()
        except Exception:
            return []
    with db_session() as db:
        rows = db.query(models.Alert).order_by(models.Alert.created_at.desc()).limit(limit).all()
        out = []
        for r in rows:
            out.append({
                "id": r.id,
                "type": r.type,
                "status": r.status,
                "message": r.message,
                "lat": r.lat,
                "lon": r.lon,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "notified": bool(r.notified)
            })
        return {"alerts": out} if out else []


def run_detector(payload: dict = None):
    """Call the anomaly detection logic that used to be at POST /alerts/check"""
    payload = payload or {}
    if USE_REMOTE:
        import requests
        r = requests.post(f"{REMOTE_BASE}/alerts/check", json=payload, timeout=10)
        return r.json()
    with db_session() as db:
        # alerts_module.run_check expects (payload, db) signature where db can be passed manually
        return alerts_module.run_check(payload=payload, db=db)


def download_alert_pdf_bytes(alert_id: int):
    """Return advisory PDF bytes or None"""
    if USE_REMOTE:
        import requests
        endpoints = [f"{REMOTE_BASE}/alerts/{alert_id}/pdf", f"{REMOTE_BASE}/alerts/{alert_id}/export_pdf"]
        for url in endpoints:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200 and r.headers.get("content-type","").startswith("application/pdf"):
                    return r.content
            except Exception:
                continue
        return None
    with db_session() as db:
        a = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
        if not a:
            return None
        alert_dict = {
            "id": a.id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "lat": a.lat,
            "lon": a.lon,
            "type": a.type,
            "status": a.status,
            "message": a.message,
        }
        return alerts_module.create_advisory_pdf(alert_dict)


def send_notify(alert_id: int, channels: list, targets: dict):
    """Mock notifications and update DB notified flag"""
    if USE_REMOTE:
        import requests
        r = requests.post(f"{REMOTE_BASE}/alerts/{alert_id}/notify", json={"channels": channels, "targets": targets}, timeout=10)
        try:
            return r.json()
        except Exception:
            return {"error": "notify failed"}
    with db_session() as db:
        a = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
        if not a:
            return {"error": "alert not found"}
        result = send_notifications(a, channels, targets)
        a.notified = True
        a.notifier_info = result
        db.add(a)
        db.commit()
        db.refresh(a)
        return {"sent": result}


# ---------- Occurrences ----------
def fetch_occurrences(limit: int = 1000, date_from: str = None, date_to: str = None):
    if USE_REMOTE:
        import requests
        params = {}
        if limit:
            params["limit"] = limit
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        r = requests.get(f"{REMOTE_BASE}/occurrences", params=params, timeout=8)
        try:
            return r.json()
        except Exception:
            return []
    with db_session() as db:
        q = db.query(models.Occurrence)
        rows = q.limit(limit).all()
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
                "qc_flag": r.qc_flag,
                "raw": r.raw
            })
        return out


def load_occurrences_csv(file_bytes: bytes, filename: str = "uploaded.csv"):
    """Accept bytes of CSV (same behavior as /occurrences/load)"""
    if USE_REMOTE:
        import requests
        files = {"file": (filename, io.BytesIO(file_bytes), "text/csv")}
        r = requests.post(f"{REMOTE_BASE}/occurrences/load", files=files, timeout=60)
        return r.json()
    text = file_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    with db_session() as db:
        count = 0
        for row in reader:
            try:
                occ = models.Occurrence(
                    occurrenceID=row.get("occurrenceID") or f"occ_{count}",
                    scientificName=row.get("scientificName"),
                    eventDate=row.get("eventDate"),
                    decimalLatitude=float(row.get("decimalLatitude") or 0.0),
                    decimalLongitude=float(row.get("decimalLongitude") or 0.0),
                    datasetID=row.get("datasetID", "uploaded_csv"),
                    provenance={"source": filename},
                    qc_flag=row.get("qc_flag","ok"),
                    raw=row
                )
                db.add(occ)
                count += 1
            except Exception:
                continue
        db.commit()
    return {"status": "ok", "inserted": count}


# ---------- Measurements ----------
def get_recent_measurements(limit: int = 200):
    if USE_REMOTE:
        import requests
        r = requests.get(f"{REMOTE_BASE}/measurements/recent", params={"limit": limit}, timeout=8)
        try:
            return r.json()
        except Exception:
            return []
    with db_session() as db:
        rows = db.query(models.Measurement).order_by(models.Measurement.id.desc()).limit(limit).all()
        out = []
        for r in rows:
            out.append({
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "lat": r.lat,
                "lon": r.lon
            })
        return out


# ---------- Otoliths (stub) ----------
def predict_otolith(file_bytes: bytes, filename: str):
    """Use your inference stub locally."""
    if USE_REMOTE:
        import requests
        files = {"file": (filename, io.BytesIO(file_bytes), "image/jpeg")}
        r = requests.post(f"{REMOTE_BASE}/otoliths/predict", files=files, timeout=30)
        try:
            return r.json()
        except Exception:
            return {"error": "predict failed"}
    # Local: write to tmp path then call predict_otolith_stub
    tmp_path = save_upload(io.BytesIO(file_bytes), filename)  # save_upload expects a file-like; see backend.app.inference.save_upload
    return predict_otolith_stub(tmp_path)

# ---------- Demo seeding ----------
def ensure_seeded():
    """Seed the DB with sample measurements if empty (for demo on Streamlit Cloud)."""
    with db_session() as db:
        cnt = db.query(models.Measurement).count()
        if cnt == 0:
            try:
                from backend.scripts.seed_measurements import seed
                seed(120)  # seed with 120 fake records
            except Exception:
                # fallback: insert some manual fake data
                from datetime import datetime, timedelta
                import random
                for i in range(60):
                    t = datetime.utcnow() - timedelta(hours=i)
                    sst = 27 + (random.random() - 0.5)
                    chl = 0.3 + random.random() * 0.1
                    m = models.Measurement(sst=round(sst, 2), chl=round(chl, 3), timestamp=t)
                    db.add(m)
                db.commit()


