# backend/app/alerts.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime

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
