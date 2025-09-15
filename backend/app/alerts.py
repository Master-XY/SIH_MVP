from fastapi import APIRouter, Depends, HTTPException, Response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import random
from sqlalchemy.orm import Session
from .db import get_db
from . import models
from datetime import datetime
import random
import math
from .notifications import send_notifications

router = APIRouter(tags=["alerts"], prefix="/alerts")

# In-memory alert store
alerts_db = []


# ---------------- PDF GENERATOR ----------------
def create_advisory_pdf(alert_record: dict) -> bytes:
    """Return bytes of a simple advisory PDF for an alert."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height - 80, f"Advisory: {alert_record.get('type', 'Alert')}")
    c.setFont("Helvetica", 12)
    c.drawString(40, height - 110, f"Status: {alert_record.get('status','')}")
    c.drawString(40, height - 130, f"Message: {alert_record.get('message','')}")
    c.drawString(40, height - 150, f"Location: {alert_record.get('lat','')}, {alert_record.get('lon','')}")
    c.drawString(40, height - 170, f"Time: {alert_record.get('created_at', datetime.utcnow().isoformat())}")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


# ---------------- ANOMALY DETECTOR ----------------
def compute_zscore(value, values_list):
    if not values_list:
        return None
    mean = sum(values_list) / len(values_list)
    var = sum((x - mean) ** 2 for x in values_list) / len(values_list)
    std = math.sqrt(var)
    if std == 0:
        return None
    return (value - mean) / std


@router.get("/")
def get_alerts(status: str = None, db: Session = Depends(get_db)):
    """List alerts with optional status filter."""
    q = db.query(models.Alert)
    if status:
        q = q.filter(models.Alert.status == status)
    alerts = q.order_by(models.Alert.created_at.desc()).all()
    return {"alerts": [a.__dict__ for a in alerts]}


@router.post("/check")
def run_check(payload: dict = None, db: Session = Depends(get_db)):
    """
    Run anomaly detection.
    Optional payload: {"sst": 29.2, "chl": 1.1, "lat":"12.9N", "lon":"77.6E"}
    """
    payload = payload or {}
    # 1) pick values (from payload or synthetic)
    sst = payload.get("sst") if "sst" in payload else round(random.uniform(20, 32), 2)
    chl = payload.get("chl") if "chl" in payload else round(random.uniform(0.05, 5.0), 2)
    lat = payload.get("lat", payload.get("latitude", "12.9"))
    lon = payload.get("lon", payload.get("longitude", "77.6"))

    # 2) persist measurement
    meas = models.Measurement(sst=sst, chl=chl, lat=str(lat), lon=str(lon))
    db.add(meas)
    db.commit()
    db.refresh(meas)

    # 3) fetch recent history for z-score (last N measurements)
    N = 30
    recent = db.query(models.Measurement).order_by(models.Measurement.timestamp.desc()).limit(N).all()
    sst_history = [m.sst for m in recent if m.sst is not None]
    chl_history = [m.chl for m in recent if m.chl is not None]

    sst_z = compute_zscore(sst, sst_history)
    chl_z = compute_zscore(chl, chl_history)

    # decision rules
    # triggers if z-score strong OR absolute thresholds reached
    z_threshold = 2.0
    triggers = []
    if sst_z is not None and abs(sst_z) >= z_threshold:
        triggers.append(f"SST z={sst_z:.2f}")
    if chl_z is not None and abs(chl_z) >= z_threshold:
        triggers.append(f"Chl z={chl_z:.2f}")
    # absolute thresholds fallback
    if sst > 30.0:
        triggers.append(f"SST too high: {sst}")
    if chl > 3.0:
        triggers.append(f"Chl too high: {chl}")

    if triggers:
        message = " / ".join(triggers) + f" (observed sst={sst}, chl={chl})"
        alert = models.Alert(
            sst=sst,
            chl=chl,
            lat=str(lat),
            lon=str(lon),
            type="HAB risk",
            status="Active",
            message=message,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return {"new_alert": {
            "id": alert.id,
            "created_at": alert.created_at.isoformat(),
            "sst": alert.sst,
            "chl": alert.chl,
            "lat": alert.lat,
            "lon": alert.lon,
            "type": alert.type,
            "status": alert.status,
            "message": alert.message,
        }}
    else:
        return {"status": "no anomaly", "sst": sst, "chl": chl}


@router.get("/{alert_id}/pdf")
def get_alert_pdf(alert_id: int, db: Session = Depends(get_db)):
    """Return advisory PDF bytes for an alert."""
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    # convert to dict for PDF generator
    alert_dict = {
        "id": alert.id,
        "created_at": alert.created_at.isoformat(),
        "sst": alert.sst,
        "chl": alert.chl,
        "lat": alert.lat,
        "lon": alert.lon,
        "type": alert.type,
        "status": alert.status,
        "message": alert.message,
    }
    pdf_bytes = create_advisory_pdf(alert_dict)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.post("/{alert_id}/notify")
def notify_alert(alert_id: int, body: dict = None, db: Session = Depends(get_db)):
    """
    Send (mock) notifications for alert.
    body: {"channels": ["sms","telegram"], "targets": {"sms":"+91123...", "telegram":"chat_id", "email":"a@b"}}
    """
    body = body or {}
    channels = body.get("channels", [])
    targets = body.get("targets", {})

    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    result = send_notifications(alert, channels, targets)
    alert.notified = True
    alert.notifier_info = result
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {"sent": result}


