"""
Streamlit dashboard for SIH_MVP (frontend/streamlit_app.py)

Features:
- Modular pages: Home (map + timeseries), Otolith Classifier, eDNA upload, Alerts, API Test
- Attempts to call backend at BACKEND_API; if unavailable, falls back to synthetic data
- Map implemented with folium + streamlit-folium
- Timeseries via Plotly
- Otolith upload uses requests.post to backend; shows confidence & placeholder Grad-CAM
- Designed to be extended: provenance panels, QC flags, API hooks are present as functions

Environment variables:
- SIH_BACKEND_URL  e.g. "http://localhost:8000/api/v1"
- MAPBOX_TOKEN     optional (used for tile layer if provided)

Save as frontend/streamlit_app.py
"""
import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import requests
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)

# ------------------------
# Backend Helper Functions
# ------------------------
BACKEND_URL = "http://127.0.0.1:8000/api/v1"

def call_backend_get(endpoint: str, params: dict = None):
    url = f"{BACKEND_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.write(f"⚠️ Backend GET {url} failed: {e}")
        logging.error(f"Backend GET {url} failed: {e}")
        return None

@st.cache_data
def get_occurrences_from_backend(bbox=None, date_from=None, date_to=None):
    params = {}
    if bbox: params["bbox"] = bbox
    if date_from: params["date_from"] = date_from
    if date_to: params["date_to"] = date_to
    return call_backend_get("/occurrences", params=params)

def fetch_occurrences_or_fallback(bbox=None, date_from=None, date_to=None):
    data = get_occurrences_from_backend(bbox, date_from, date_to)
    if not data:
        # fallback: demo CSV
        try:
            df = pd.read_csv("data/demo_occurrences.csv")
        except:
            df = pd.DataFrame({
                "scientificName": ["Sardinella longiceps", "Thunnus albacares"],
                "decimalLatitude": [15.3, 10.2],
                "decimalLongitude": [73.8, 75.5],
                "eventDate": [str(datetime.today().date()), str(datetime.today().date())]
            })
        return df
    return pd.DataFrame(data)

# ------------------------
# Page Definitions
# ------------------------
def page_home():
    st.title("🌊 SIH MVP Dashboard")
    st.write("Welcome to the unified ocean + biodiversity monitoring platform.")

    # Map
    st.subheader("Occurrences Map (Demo Data)")
    df = fetch_occurrences_or_fallback()
    m = folium.Map(location=[12.5, 77.5], zoom_start=5)
    marker_cluster = MarkerCluster().add_to(m)
    for _, row in df.iterrows():
        folium.Marker(
            location=[row["decimalLatitude"], row["decimalLongitude"]],
            popup=row["scientificName"]
        ).add_to(marker_cluster)
    st_folium(m, width=700, height=450)

    # Time-series placeholder
    st.subheader("Time-Series (placeholder)")
    chart_data = pd.DataFrame({
        "date": pd.date_range(datetime.today(), periods=10).date,
        "SST": [28 + i*0.1 for i in range(10)]
    })
    st.line_chart(chart_data.set_index("date"))

def page_edna():
    st.title("🧬 eDNA Module (Stub)")
    st.write("Here you will upload ASV/OTU tables, view detections, and explore sample metadata.")
    # Placeholder chart
    df = pd.DataFrame({
        "Species": ["Species A", "Species B", "Species C"],
        "Reads": [1200, 800, 450]
    })
    st.bar_chart(df.set_index("Species"))

def page_otoliths():
    st.title("🐟 Otolith Classifier (Stub)")
    st.write("Upload otolith images here for species prediction with explainability.")
    uploaded = st.file_uploader("Upload an otolith image", type=["jpg", "png"])
    if uploaded:
        st.image(uploaded, caption="Uploaded Otolith", width=300)
        st.write("Predicted Species: **Thunnus albacares (Yellowfin Tuna)**")
        st.write("Confidence: 87%")
        st.write("Grad-CAM & nearest examples will appear here (future).")

def page_ocean_data():
    st.title("🌐 Oceanographic Data (Stub)")
    st.write("Satellite SST, chlorophyll, and buoy data visualizations.")
    # Placeholder
    df = pd.DataFrame({
        "date": pd.date_range(datetime.today(), periods=7).date,
        "SST": [27.8, 28.0, 28.2, 28.1, 27.9, 28.3, 28.4],
        "Chlorophyll": [0.5, 0.55, 0.52, 0.6, 0.58, 0.62, 0.65]
    })
    st.line_chart(df.set_index("date"))

def page_about():
    st.title("ℹ️ About")
    st.write("""
    This MVP integrates biodiversity (Darwin Core), eDNA (MIxS), and oceanographic (NetCDF/CF) data.
    Features:
    - Unified ingestion pipeline with provenance
    - Otolith classifier with explainability
    - Anomaly-based HAB/PFZ alerts
    - REST API for external access
    """)

# ------------------------
# Main Navigation
# ------------------------
def main():
    st.sidebar.title("Navigation")
    pages = {
        "Home": page_home,
        "eDNA": page_edna,
        "Otoliths": page_otoliths,
        "Ocean Data": page_ocean_data,
        "About": page_about
    }
    choice = st.sidebar.radio("Go to", list(pages.keys()))
    pages[choice]()

if __name__ == "__main__":
    main()

