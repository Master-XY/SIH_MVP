# frontend/pages/3_alerts.py
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict
from io import BytesIO

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from frontend import backend_client

import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# ----------------------------
# Synthetic fallback alerts
# ----------------------------
def synthetic_alerts() -> List[Dict]:
    now = datetime.utcnow().isoformat()
    return [
        {"id": 1, "type": "SST anomaly", "status": "active", "message": "SST +2.1°C above climatology",
         "time": now, "lat": 16.5, "lon": 72.3, "sst": None, "chl": None},
        {"id": 2, "type": "HAB-like", "status": "resolved", "message": "Chl spike observed",
         "time": now, "lat": 18.7, "lon": 82.1, "sst": None, "chl": None},
    ]

# ----------------------------
# Fetch alerts
# ----------------------------
@st.cache_data(ttl=120)
def fetch_alerts() -> List[Dict]:
    try:
        res = backend_client.fetch_alerts(limit=50)
    except Exception as e:
        st.error(f"Failed to fetch alerts: {e}")
        res = None

    if not res:
        return synthetic_alerts()
    if isinstance(res, dict) and "alerts" in res:
        return res["alerts"]
    if isinstance(res, list):
        return res
    return []

# ----------------------------
# Download PDF
# ----------------------------
def download_alert_pdf(alert_id: int) -> BytesIO:
    try:
        pdf_bytes = backend_client.download_alert_pdf_bytes(alert_id)
    except Exception as e:
        st.error(f"Failed to download PDF: {e}")
        pdf_bytes = None

    if pdf_bytes:
        return BytesIO(pdf_bytes)
    return None

# ----------------------------
# Send notification
# ----------------------------
def send_alert_notification(alert_id: int, channels: List[str], targets: Dict):
    try:
        res = backend_client.send_notify(alert_id, channels, targets)
    except Exception as e:
        st.error(f"Notification failed: {e}")
        res = {"error": str(e)}
    return res

# ----------------------------
# Map creation
# ----------------------------
def create_map(alerts: List[Dict], center=(9.9, 76.6), zoom_start: int = 5):
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="cartodbpositron")
    cluster = MarkerCluster().add_to(m)

    for a in alerts:
        lat, lon = a.get("lat"), a.get("lon")
        if lat is None or lon is None:
            continue
        popup_html = f"<b>{a.get('type')}</b><br>Status: {a.get('status')}<br>Message: {a.get('message')}"
        folium.Marker([lat, lon], popup=popup_html).add_to(cluster)
    return m

# ----------------------------
# Page UI
# ----------------------------
st.set_page_config(page_title="Alerts", layout="wide")
st.title("Anomaly Alerts")

alerts = fetch_alerts()
st.subheader("Active Alerts List")
for a in alerts:
    st.markdown(f"**{a.get('type')}** ({a.get('status')}) - {a.get('message')}")
    pdf_file = download_alert_pdf(a["id"])
    if pdf_file:
        st.download_button(f"Download PDF for alert {a['id']}", pdf_file, file_name=f"alert_{a['id']}.pdf")
    if st.button(f"Send notification for alert {a['id']}", key=f"notify_{a['id']}"):
        res = send_alert_notification(a["id"], channels=["email"], targets={"admin": "admin@example.com"})
        st.write(res)

st.subheader("Alerts Map")
map_obj = create_map(alerts)
st_folium(map_obj, width=800, height=500)
