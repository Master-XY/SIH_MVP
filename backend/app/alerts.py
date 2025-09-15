from fastapi import APIRouter, Response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import random

router = APIRouter(prefix="/alerts", tags=["alerts"])

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
def check_anomaly():
    """Dummy anomaly detector using random values (replace with real SST/chl)."""
    sst = random.uniform(20, 32)
    chl = random.uniform(0.1, 5.0)

    if sst > 30 or chl > 3.0:
        return {
            "id": len(alerts_db) + 1,
            "created_at": datetime.utcnow().isoformat(),
            "sst": round(sst, 2),
            "chl": round(chl, 2),
            "lat": "12.9N",
            "lon": "77.6E",
            "type": "HAB risk",
            "status": "Active",
            "message": f"High SST={sst:.2f}°C and Chl={chl:.2f} mg/m³ → Possible bloom"
        }
    return None


# ---------------- ROUTES ----------------
@router.get("/")
def get_alerts():
    """Return all current alerts."""
    return {"alerts": alerts_db}


@router.post("/check")
def run_check():
    """Run anomaly detection and add new alert if found."""
    anomaly = check_anomaly()
    if anomaly:
        alerts_db.append(anomaly)
        return {"new_alert": anomaly}
    return {"status": "no anomaly"}


@router.get("/{alert_id}/pdf")
def get_alert_pdf(alert_id: int):
    """Generate a PDF advisory for a given alert."""
    alert = next((a for a in alerts_db if a["id"] == alert_id), None)
    if not alert:
        return {"error": "Alert not found"}

    pdf_bytes = create_advisory_pdf(alert)
    return Response(content=pdf_bytes, media_type="application/pdf")
