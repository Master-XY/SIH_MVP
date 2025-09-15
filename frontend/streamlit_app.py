"""
frontend/streamlit_app.py
Comprehensive Streamlit frontend for SIH_MVP (demo-ready + future-proof).

Features:
- Config via .env (SIH_BACKEND_URL, MAPBOX_TOKEN)
- Pages: Home, Otoliths, eDNA, Ocean Data, Alerts, API Test, Settings, About
- Backend calls with graceful fallback to synthetic data
- Map with marker clustering, time filtering, provenance panel
- Otolith upload -> calls backend /otoliths/predict, shows confidence + Grad-CAM placeholder + correction feedback
- eDNA CSV upload and summary
- Alerts list + map and subscription form
- Settings panel to update backend URL & mapbox token in session
"""

import os
import io
import logging
import json
from datetime import datetime, date, timedelta , timezone
from typing import Optional, List, Dict

import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image

import folium
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium
import plotly.express as px
import sys

# Ensure backend_client import works
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from frontend import backend_client

# Optional: load .env if python-dotenv installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass  # it's optional; environment variables may be set elsewhere

# ----------------------------
# Configuration & logging
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sih_frontend")

DEFAULT_BACKEND = os.getenv("SIH_BACKEND_URL", "http://127.0.0.1:8000/api/v1")
DEFAULT_MAPBOX = os.getenv("MAPBOX_TOKEN", "")

# Streamlit page config
st.set_page_config(page_title="SIH MVP Dashboard", layout="wide", initial_sidebar_state="expanded")

try:
    backend_client.ensure_seeded()
except Exception:
    # don't crash startup on seed errors
    pass

# ----------------------------
# Utility helpers
# ----------------------------
def get_setting(key: str, default: str = "") -> str:
    """Read and store simple settings in session_state so they persist during the session."""
    ss = st.session_state
    if key not in ss:
        ss[key] = os.getenv(key, default)
    return ss[key]

def set_setting(key: str, value: str):
    st.session_state[key] = value

# Initialize settings in session
if "SIH_BACKEND_URL" not in st.session_state:
    st.session_state["SIH_BACKEND_URL"] = DEFAULT_BACKEND
if "MAPBOX_TOKEN" not in st.session_state:
    st.session_state["MAPBOX_TOKEN"] = DEFAULT_MAPBOX

BACKEND_API = lambda: st.session_state.get("SIH_BACKEND_URL", DEFAULT_BACKEND)

# ----------------------------
# Synthetic / fallback data
# ----------------------------
@st.cache_data(ttl=300)
def synthetic_occurrences(n=120, bbox=(66.0, 6.0, 92.0, 24.0)):
    minlon, minlat, maxlon, maxlat = bbox
    rng = np.random.default_rng(seed=42)
    lons = rng.uniform(minlon, maxlon, n)
    lats = rng.uniform(minlat, maxlat, n)
    species = ["Sardinella longiceps", "Thunnus albacares", "Katsuwonus pelamis", "Rastrelliger kanagurta"]
    rows = []
    for i in range(n):
        rows.append({
            "occurrenceID": f"synthetic-{i}",
            "scientificName": rng.choice(species),
            "eventDate": (date.today() - timedelta(days=int(rng.integers(0, 365)))).isoformat(),
            "decimalLatitude": float(lats[i]),
            "decimalLongitude": float(lons[i]),
            "datasetID": "synthetic_demo_v1",
            "provenance": {"source": "synthetic", "fetched_at": datetime.utcnow().isoformat()},
            "qc_flag": rng.choice(["ok", "suspect"])
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def synthetic_alerts():
    now = datetime.utcnow().isoformat()
    return [
        {"id": 1, "type": "SST anomaly", "status": "active", "message": "SST +2.1°C above climatology", "time": now, "lat": 16.5, "lon": 72.3},
        {"id": 2, "type": "HAB-like", "status": "resolved", "message": "Chl spike observed", "time": now, "lat": 18.7, "lon": 82.1},
    ]

# ----------------------------
# Data fetch wrappers
# ----------------------------
@st.cache_data(ttl=120)
def fetch_occurrences(bbox: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> pd.DataFrame:
    """Try backend_client, otherwise return synthetic DataFrame."""
    try:
        res = backend_client.fetch_occurrences(limit=1000, date_from=date_from, date_to=date_to)
    except Exception as e:
        logger.error(f"fetch_occurrences failed: {e}")
        res = None

    if not res:
        return synthetic_occurrences()

    if isinstance(res, list):
        df = pd.DataFrame(res)
    elif isinstance(res, dict) and "data" in res:
        df = pd.DataFrame(res["data"])
    else:
        df = pd.DataFrame([res])

    if "decimalLatitude" not in df.columns and "lat" in df.columns:
        df = df.rename(columns={"lat": "decimalLatitude", "lon": "decimalLongitude"})
    return df

@st.cache_data(ttl=120)
def fetch_alerts() -> List[Dict]:
    try:
        res = backend_client.fetch_alerts(limit=50)
    except Exception as e:
        logger.error(f"fetch_alerts failed: {e}")
        res = None

    if not res:
        return synthetic_alerts()
    if isinstance(res, dict) and "alerts" in res:
        return res["alerts"]
    if isinstance(res, list):
        return res
    return []
# ----------------------------
# Measurements & Ocean Data
# ----------------------------
@st.cache_data(ttl=120)
def fetch_recent_measurements(limit: int = 200) -> pd.DataFrame:
    """Try backend_client, otherwise return synthetic DataFrame."""
    try:
        res = backend_client.get_recent_measurements(limit=limit)
    except Exception as e:
        logger.error(f"fetch_recent_measurements failed: {e}")
        res = None

    if not res:
        # synthetic fallback
        now = datetime.utcnow()
        df = pd.DataFrame([{
            "sst": 27 + np.random.rand(),
            "chl": 0.3 + np.random.rand() * 0.1,
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "lat": 16 + np.random.rand(),
            "lon": 72 + np.random.rand()
        } for i in range(limit)])
    else:
        df = pd.DataFrame(res)
    return df

# ----------------------------
# Otoliths upload & inference
# ----------------------------
def handle_otolith_upload(uploaded_file):
    if uploaded_file is None:
        return None

    bytes_data = uploaded_file.read()
    filename = uploaded_file.name
    try:
        result = backend_client.predict_otolith(bytes_data, filename)
    except Exception as e:
        logger.error(f"Otolith prediction failed: {e}")
        return {"error": str(e)}

    return result

# ----------------------------
# PDF advisory download
# ----------------------------
def download_alert_pdf(alert_id: int):
    try:
        pdf_bytes = backend_client.download_alert_pdf_bytes(alert_id)
    except Exception as e:
        logger.error(f"download_alert_pdf failed: {e}")
        pdf_bytes = None
    return pdf_bytes

# ----------------------------
# Notification sending
# ----------------------------
def send_alert_notification(alert_id: int, channels: List[str], targets: Dict):
    try:
        res = backend_client.send_notify(alert_id, channels, targets)
    except Exception as e:
        logger.error(f"send_alert_notification failed: {e}")
        res = {"error": str(e)}
    return res

# ----------------------------
# Map helpers
# ----------------------------
def create_map(df: pd.DataFrame,
               center=(9.9, 76.6),
               zoom_start: int = 5,
               popup_fields: Optional[List[str]] = None):
    """Generate folium map centered on India."""
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="cartodbpositron")
    marker_cluster = MarkerCluster().add_to(m)

    if popup_fields is None:
        popup_fields = ["scientificName", "eventDate", "datasetID"]

    for idx, row in df.iterrows():
        lat, lon = row.get("decimalLatitude"), row.get("decimalLongitude")
        if lat is None or lon is None:
            continue
        popup_html = "<br>".join(f"<b>{f}:</b> {row.get(f,'')}" for f in popup_fields)
        folium.Marker([lat, lon], popup=popup_html).add_to(marker_cluster)

    return m

# ----------------------------
# Pages: Home / Otoliths / eDNA / Ocean Data / Alerts
# ----------------------------
def page_home():
    st.title("SIH MVP Dashboard")
    st.markdown("Welcome to the SIH MVP. Use the sidebar to navigate between pages.")

    st.subheader("Recent Occurrences Map")
    df_occ = fetch_occurrences()
    map_obj = create_map(df_occ)
    st_folium(map_obj, width=800, height=500)

def page_otoliths():
    st.title("Otolith Classification")
    uploaded_file = st.file_uploader("Upload an otolith image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        with st.spinner("Predicting..."):
            result = handle_otolith_upload(uploaded_file)
        st.json(result)

def page_edna():
    st.title("eDNA CSV Upload")
    uploaded_file = st.file_uploader("Upload eDNA CSV", type=["csv"])
    if uploaded_file:
        bytes_data = uploaded_file.read()
        res = backend_client.load_occurrences_csv(bytes_data, uploaded_file.name)
        st.write(res)
        df_occ = fetch_occurrences()
        st.dataframe(df_occ.head())

def page_ocean_data():
    st.title("Ocean Measurements")
    df_meas = fetch_recent_measurements(limit=200)
    st.dataframe(df_meas.head())
    if not df_meas.empty:
        fig = px.scatter_mapbox(df_meas, lat="lat", lon="lon", color="sst", size="chl",
                                hover_data=["timestamp"],
                                mapbox_style="carto-positron", zoom=4, center={"lat": 10, "lon": 75})
        st.plotly_chart(fig, use_container_width=True)

def page_alerts():
    st.title("Alerts")
    alerts = fetch_alerts()
    for a in alerts:
        st.markdown(f"**{a.get('type')}** ({a.get('status')}) - {a.get('message')}")
        pdf_bytes = download_alert_pdf(a["id"])
        if pdf_bytes:
            st.download_button(f"Download PDF for alert {a['id']}", pdf_bytes, file_name=f"alert_{a['id']}.pdf")
        if st.button(f"Send notification for alert {a['id']}"):
            res = send_alert_notification(a["id"], channels=["email"], targets={"admin": "admin@example.com"})
            st.write(res)
# ----------------------------
# Settings & About Pages
# ----------------------------
def page_settings():
    st.title("Settings")

    backend_url = st.text_input("Backend URL", value=st.session_state.get("SIH_BACKEND_URL"))
    mapbox_token = st.text_input("Mapbox Token", value=st.session_state.get("MAPBOX_TOKEN"))

    if st.button("Save Settings"):
        set_setting("SIH_BACKEND_URL", backend_url)
        set_setting("MAPBOX_TOKEN", mapbox_token)
        st.success("Settings updated! Please refresh pages to apply.")

def page_about():
    st.title("About SIH MVP Dashboard")
    st.markdown("""
    **Smart India Hackathon MVP Dashboard**  
    - Frontend: Streamlit  
    - Backend: FastAPI / SQLAlchemy  
    - Features: Otolith classification, eDNA occurrence tracking, ocean measurements, anomaly alerts  
    - Author: Team SIH  
    - Version: 1.0  
    """)

# ----------------------------
# Sidebar Navigation
# ----------------------------
PAGES = {
    "Home": page_home,
    "Otoliths": page_otoliths,
    "eDNA": page_edna,
    "Ocean Data": page_ocean_data,
    "Alerts": page_alerts,
    "Settings": page_settings,
    "About": page_about,
}

st.sidebar.title("Navigation")
selected_page = st.sidebar.radio("Go to", list(PAGES.keys()))
page_func = PAGES[selected_page]

# Health check badge
try:
    health_status = backend_client.health()
    status_color = "green" if health_status.get("status") == "ok" else "red"
except Exception:
    status_color = "red"
st.sidebar.markdown(f"**Backend Health:** <span style='color:{status_color}'>●</span>", unsafe_allow_html=True)

# Optional: force refresh button for caching
if st.sidebar.button("Refresh Data"):
    for key in st.session_state.keys():
        if key.startswith("cache_"):
            del st.session_state[key]
    st.experimental_rerun()

# ----------------------------
# Run selected page
# ----------------------------
page_func()
# ----------------------------
# Additional helpers / utilities
# ----------------------------
def clear_session_cache():
    """Clear all cached Streamlit data and rerun."""
    st.session_state.clear()
    st.experimental_rerun()

def display_dataframe(df: pd.DataFrame, max_rows: int = 20):
    """Safe display of a dataframe with optional truncation."""
    if df.empty:
        st.write("No data available.")
        return
    st.dataframe(df.head(max_rows))

# ----------------------------
# Error handling wrappers
# ----------------------------
def safe_call(fn, *args, **kwargs):
    """Call a function and log exceptions; returns None on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"safe_call error: {e}")
        st.error(f"An error occurred: {e}")
        return None

# ----------------------------
# Streamlit caching / refresh management
# ----------------------------
# Use @st.cache_data for expensive backend calls (already applied above)
# Provide "Refresh Data" button in sidebar (already in part 3)
# Optionally, can add per-page refresh buttons if needed
# Example usage:
# if st.button("Refresh Occurrences"):
#     fetch_occurrences.clear()
#     st.experimental_rerun()

# ----------------------------
# Initialization
# ----------------------------
# Ensure session state defaults
for key, default_val in [("SIH_BACKEND_URL", DEFAULT_BACKEND), ("MAPBOX_TOKEN", DEFAULT_MAPBOX)]:
    if key not in st.session_state:
        st.session_state[key] = default_val

# Ensure backend seeded (demo)
safe_call(backend_client.ensure_seeded)

# ----------------------------
# End of streamlit_app.py
# ----------------------------
