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
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict

import streamlit as st
import pandas as pd
import numpy as np
import requests
from PIL import Image, ImageDraw

import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import plotly.express as px

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

# Generic backend callers with error handling and logging
def backend_get(path: str, params: dict = None, timeout: float = 8.0) -> Optional[dict]:
    url = BACKEND_API().rstrip("/") + "/" + path.lstrip("/")
    try:
        r = requests.get(url, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"Backend GET failed: {url} — {e}")
        logger.error("Backend GET failed: %s — %s", url, e)
        return None

def backend_post(path: str, files=None, data=None, json_data=None, timeout: float = 20.0) -> Optional[dict]:
    url = BACKEND_API().rstrip("/") + "/" + path.lstrip("/")
    try:
        r = requests.post(url, files=files, data=data, json=json_data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"Backend POST failed: {url} — {e}")
        logger.error("Backend POST failed: %s — %s", url, e)
        return None

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
    """Try backend, otherwise return synthetic DataFrame."""
    params = {}
    if bbox:
        params["bbox"] = bbox
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    res = backend_get("/occurrences", params=params)
    if res is None:
        return synthetic_occurrences()
    # backend may return list or dict
    if isinstance(res, list):
        df = pd.DataFrame(res)
    elif isinstance(res, dict) and "data" in res:
        df = pd.DataFrame(res["data"])
    else:
        df = pd.DataFrame([res])
    # Normalize column names
    # expected: decimalLatitude, decimalLongitude
    if "decimalLatitude" not in df.columns and "lat" in df.columns:
        df = df.rename(columns={"lat": "decimalLatitude", "lon": "decimalLongitude"})
    return df

@st.cache_data(ttl=120)
def fetch_alerts() -> List[Dict]:
    res = backend_get("/alerts")
    if res is None:
        return synthetic_alerts()
    if isinstance(res, dict) and "alerts" in res:
        return res["alerts"]
    if isinstance(res, list):
        return res
    return []

# ----------------------------
# Helper UI pieces
# ----------------------------
def create_map(df: pd.DataFrame, center=(20.0, 80.0), zoom_start: int = 5, popup_fields: Optional[List[str]] = None):
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="cartodbpositron")
    token = st.session_state.get("MAPBOX_TOKEN", "")
    if token:
        folium.TileLayer(
            tiles=f"https://api.mapbox.com/styles/v1/mapbox/light-v10/tiles/{{z}}/{{x}}/{{y}}?access_token={token}",
            attr="Mapbox", name="Mapbox", control=True, overlay=False).add_to(m)
    cluster = MarkerCluster().add_to(m)
    popup_fields = popup_fields or ["scientificName", "eventDate", "datasetID", "qc_flag"]
    for _, row in df.iterrows():
        try:
            lat = float(row["decimalLatitude"])
            lon = float(row["decimalLongitude"])
        except Exception:
            continue
        popup_html = "<div>"
        for f in popup_fields:
            if f in row:
                popup_html += f"<b>{f}:</b> {row.get(f,'-')}<br/>"
        popup_html += "</div>"
        folium.Marker([lat, lon], popup=popup_html).add_to(cluster)
    return m

def show_provenance(df: pd.DataFrame, index: int):
    if index < 0 or index >= len(df):
        st.write("No record selected")
        return
    rec = df.iloc[index]
    st.subheader("Provenance & QC")
    prov = rec.get("provenance", None)
    if pd.isna(prov) or not prov:
        st.write("No provenance metadata available.")
    else:
        if isinstance(prov, str):
            try:
                prov_obj = json.loads(prov)
            except Exception:
                prov_obj = {"info": prov}
        else:
            prov_obj = prov
        st.json(prov_obj)
    st.write("QC flag:", rec.get("qc_flag", "unset"))
    st.write("Full record:")
    st.json(rec.to_dict())

# ----------------------------
# Page Implementations
# ----------------------------
# Replace the old `page_home()` entirely with this
def page_home():
    st.header("Home — Overview")
    
    # --------------------------
    # Backend settings expander
    # --------------------------
    with st.expander("Backend settings (quick)"):
        st.text_input(
            "Backend base (SIH_BACKEND_URL)",
            value=st.session_state.get("SIH_BACKEND_URL", DEFAULT_BACKEND),
            key="SIH_BACKEND_URL_input"
        )
        if st.button("Save Backend URL"):
            set_setting("SIH_BACKEND_URL", st.session_state["SIH_BACKEND_URL_input"])
            st.success("Backend URL updated for this session.")

    # --------------------------
    # Top metrics
    # --------------------------
    col1, col2, col3 = st.columns(3)
    
    try:
        occ_all = backend_get("/occurrences?limit=1000") or []
        total_occ = len(occ_all) if isinstance(occ_all, list) else (len(occ_all.get("results", [])) if isinstance(occ_all, dict) else 0)
    except Exception:
        total_occ = 0
    col1.metric("Occurrences (sample)", total_occ)
    
    try:
        meas = backend_get("/measurements/recent?limit=200")
        if meas and isinstance(meas, dict):
            meas_list = meas.get("measurements", [])
        elif isinstance(meas, list):
            meas_list = meas
        else:
            meas_list = []
        sst_latest = meas_list[0]["sst"] if meas_list else None
    except Exception:
        meas_list = []
        sst_latest = None
    col2.metric("Latest SST (°C)", sst_latest or "-")
    
    try:
        alerts_resp = backend_get("/alerts")
        alerts_list = alerts_resp.get("alerts") if isinstance(alerts_resp, dict) else (alerts_resp or [])
        active = sum(1 for a in (alerts_list if isinstance(alerts_list, list) else []) if str(a.get("status","")).lower()=="active")
    except Exception:
        active = 0
    col3.metric("Active alerts", active)
    
    st.markdown("---")
    
    # --------------------------
    # SST timeseries
    # --------------------------
    st.subheader("SST timeseries (recent)")
    import plotly.express as px
    if meas_list:
        dfm = pd.DataFrame(meas_list)
        if "timestamp" in dfm.columns:
            dfm["ts"] = pd.to_datetime(dfm["timestamp"])
        elif "created_at" in dfm.columns:
            dfm["ts"] = pd.to_datetime(dfm["created_at"])
        else:
            dfm["ts"] = pd.date_range(end=pd.Timestamp.now(), periods=len(dfm))
        dfm = dfm.sort_values("ts")
        dfm["sst_roll"] = dfm["sst"].astype(float).rolling(7, min_periods=1).mean()
        fig = px.line(dfm, x="ts", y=["sst","sst_roll"], labels={"value":"SST (°C)","ts":"time"}, title="Recent SST (from backend)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No measurement timeseries available. Use 'Live' mode on Alerts page or run the seed / ingestion scripts.")
    
    st.markdown("---")
    
    # --------------------------
    # Occurrences map + summary + CSV
    # --------------------------
    st.subheader("Occurrences map & summary")
    left, right = st.columns((2,1))
    
    with left:
        bbox = st.text_input("BBox (minLon,minLat,maxLon,maxLat) — optional", "")
        date_from = st.date_input("From date", value=date.today() - timedelta(days=365))
        date_to = st.date_input("To date", value=date.today())
        load_btn = st.button("Load occurrences")
        
        if load_btn:
            df = fetch_occurrences(
                bbox=bbox if bbox.strip() else None, 
                date_from=str(date_from), 
                date_to=str(date_to)
            )
            st.session_state["last_occurrences"] = df.to_dict(orient="records")
        
        df = pd.DataFrame(st.session_state.get("last_occurrences", [])) if st.session_state.get("last_occurrences") else fetch_occurrences()
        st.write(f"Showing {len(df)} records")
        
        if not df.empty:
            center = (df["decimalLatitude"].mean(), df["decimalLongitude"].mean())
        else:
            center = (20.0, 80.0)
        
        m = create_map(df, center=center, zoom_start=5)
        st_folium(m, width=800, height=500)
        
        # Provenance selection
        if not df.empty:
            idx = st.number_input("Select record index to view provenance", min_value=0, max_value=len(df)-1, value=0)
            show_provenance(df, int(idx))
    
    with right:
        st.subheader("Top species")
        if not df.empty and "scientificName" in df.columns:
            top = df["scientificName"].value_counts().nlargest(5)
            for s, cnt in top.items():
                st.write(f"- {s}: {cnt}")
        
        st.subheader("Quick actions")
        if st.button("Download occurrences CSV"):
            if not df.empty:
                buf = io.StringIO()
                df.to_csv(buf, index=False)
                st.download_button("Download CSV", buf.getvalue(), file_name="occurrences.csv", mime="text/csv")
            else:
                st.info("No data to download.")


def page_otoliths():
    st.header("Otolith / Species Classifier")
    st.write("Upload otolith images to get model predictions (demo).")
    upload_col, info_col = st.columns((1, 2))
    uploaded = upload_col.file_uploader("Upload otolith image (jpg/png)", type=["jpg", "jpeg", "png"])
    if uploaded:
        try:
            image = Image.open(uploaded).convert("RGB")
        except Exception as e:
            st.error(f"Cannot open image: {e}")
            return
        info_col.image(image, caption="Uploaded image", use_column_width=True)

        if upload_col.button("Predict (backend)"):
            # prepare multipart upload
            files = {"file": (uploaded.name, uploaded, "image/jpeg")}
            resp = backend_post("/otoliths/predict", files=files)
            if resp:
                species = resp.get("predicted_species") or resp.get("species") or resp.get("scientificName", "unknown")
                confidence = resp.get("confidence") or resp.get("confidence_pct") or resp.get("score")
                st.success(f"Predicted: **{species}**")
                if confidence is not None:
                    st.write(f"Confidence: **{confidence}**")
                # explainability
                explain = resp.get("explainability", None) or resp.get("explainability_refs", None)
                if explain:
                    st.write("Explainability provided by backend:")
                    st.write(explain)
                else:
                    st.info("No explainability returned. Showing placeholder Grad-CAM.")
                    # create translucent overlay placeholder
                    overlay = Image.new("RGBA", image.size, (255, 0, 0, 40))
                    gradcam = Image.alpha_composite(image.convert("RGBA"), overlay)
                    st.image(gradcam, caption="Grad-CAM placeholder", use_column_width=True)
            else:
                st.info("Backend not reachable — running local demo prediction.")
                # local demo prediction
                species = np.random.choice(["Sardinella longiceps", "Thunnus albacares", "Rastrelliger kanagurta"])
                conf = round(float(np.random.uniform(0.65, 0.96)), 2)
                st.success(f"Predicted (demo): **{species}**")
                st.write(f"Confidence: **{conf}**")
                overlay = Image.new("RGBA", image.size, (255, 0, 0, 40))
                gradcam = Image.alpha_composite(image.convert("RGBA"), overlay)
                st.image(gradcam, caption="Grad-CAM placeholder", use_column_width=True)

        # Correction / feedback form (human-in-loop)
        st.subheader("Is the prediction wrong? Provide correction")
        with st.form("otolith_feedback"):
            corrected = st.text_input("Correct species name (leave blank if ok)")
            notes = st.text_area("Notes (e.g. why incorrect, quality issues)")
            submitted = st.form_submit_button("Send feedback")
            if submitted:
                payload = {"corrected_species": corrected, "notes": notes}
                # try to POST to backend feedback endpoint (optional)
                resp = backend_post("/otoliths/feedback", json_data=payload)
                if resp:
                    st.success("Feedback saved to backend.")
                else:
                    # store in local session for demo
                    lst = st.session_state.get("otolith_feedback_local", [])
                    lst.append({"time": datetime.utcnow().isoformat(), **payload})
                    st.session_state["otolith_feedback_local"] = lst
                    st.info("Feedback stored locally for demo.")

def page_edna():
    st.header("eDNA — ASV / OTU table upload")
    st.write("Upload a CSV with columns like sampleID, taxon, count. Also accepts MIxS metadata with sample info.")
    uploaded = st.file_uploader("Upload ASV/OTU CSV", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            st.subheader("Preview")
            st.dataframe(df.head(50))
            if {"taxon", "count"}.issubset(set(df.columns)):
                summary = df.groupby("taxon")["count"].sum().reset_index().sort_values("count", ascending=False)
                st.subheader("Top taxa (by reads)")
                st.dataframe(summary.head(20))
            # Show sample locations if columns present
            if {"latitude", "longitude"}.issubset(set(df.columns)):
                coords = df.rename(columns={"latitude": "decimalLatitude", "longitude": "decimalLongitude"})
                m = create_map(coords, center=(coords["decimalLatitude"].mean(), coords["decimalLongitude"].mean()))
                st_folium(m, width=800, height=400)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
    else:
        st.info("No file uploaded. You can create a simple CSV with 'taxon,count' columns for testing.")

def page_ocean_data():
    st.header("Ocean Data — Timeseries & NetCDF (placeholder)")
    st.write("This page will visualise SST/chlorophyll. For now, we show demo timeseries and a hint for local NetCDF loading.")
    days = pd.date_range(end=date.today(), periods=30)
    sst = 27.5 + np.sin(np.linspace(0, 6, len(days))) * 0.6 + np.random.normal(0, 0.15, len(days))
    chl = 0.4 + np.cos(np.linspace(0, 4, len(days))) * 0.08 + np.random.normal(0, 0.02, len(days))
    df = pd.DataFrame({"date": days, "SST": sst, "Chlorophyll": chl})
    fig = px.line(df, x="date", y=["SST", "Chlorophyll"], title="Demo ocean timeseries")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Load local NetCDF (example stub)")
    nc_file = st.file_uploader("Upload NetCDF (.nc) for demo plotting (optional)", type=["nc"])
    if nc_file:
        st.info("NetCDF uploaded — parsing is not implemented in this demo stub. Will parse variables and plot timeseries in future.")

def page_alerts():
    st.header("Alerts & Advisory Panel")
    alerts = fetch_alerts()
    st.write(f"{len(alerts)} alerts (real or synthetic).")
    cols = st.columns(2)
    with cols[0]:
        for a in alerts:
            with st.expander(f"Alert #{a.get('id')} — {a.get('type')} ({a.get('status')})"):
                st.write("Message:", a.get("message", "-"))
                st.write("Time:", a.get("time", "-"))
                st.write("Location:", f"{a.get('lat','-')}, {a.get('lon','-')}")
                st.json(a)
                if st.button(f"Export advisory PDF (alert {a.get('id')})"):
                    st.info("PDF advisory generation implemented on backend in future. For now, demo only.")
    with cols[1]:
        st.subheader("Alerts map")
        df_alerts = pd.DataFrame(alerts)
        if not df_alerts.empty and {"lat", "lon"}.issubset(df_alerts.columns):
            m = folium.Map(location=(df_alerts["lat"].mean(), df_alerts["lon"].mean()), zoom_start=5)
            for _, r in df_alerts.iterrows():
                color = "red" if r.get("status") == "active" else "orange"
                folium.CircleMarker(location=[r["lat"], r["lon"]], radius=8, color=color, fill=True, fillOpacity=0.7, popup=r.get("message","")).add_to(m)
            st_folium(m, width=600, height=400)
        else:
            st.write("No geolocated alerts to show.")

    st.subheader("Subscribe for alerts")
    with st.form("subscribe_form"):
        phone = st.text_input("Phone (E.164 format, e.g. +91XXXXXXXXXX)")
        email = st.text_input("Email (optional)")
        sub = st.form_submit_button("Subscribe")
        if sub:
            payload = {"phone": phone, "email": email}
            resp = backend_post("/subscribe", json_data=payload)
            if resp:
                st.success("Subscribed (backend saved).")
            else:
                # local demo store
                subs = st.session_state.get("local_subscribers", [])
                subs.append(payload)
                st.session_state["local_subscribers"] = subs
                st.info("Subscription saved locally for demo.")

def page_api_test():
    st.header("API Test & Tools")
    base = BACKEND_API().rstrip("/api/v1")
    st.write("Backend base:", base)
    if st.button("Check backend /health"):
        res = backend_get("/health")
        st.write(res)
    if st.button("List occurrences (raw)"):
        res = backend_get("/occurrences")
        st.write(res or "No response")
    if st.button("Open OpenAPI docs"):
        st.write(f"Open your browser: {base}/docs")

def page_settings():
    st.header("Settings")
    st.text_input("Backend API (full path including /api/v1)", key="SIH_BACKEND_URL_input", value=st.session_state.get("SIH_BACKEND_URL", DEFAULT_BACKEND))
    st.text_input("Mapbox token (optional)", key="MAPBOX_TOKEN_input", value=st.session_state.get("MAPBOX_TOKEN", DEFAULT_MAPBOX))
    if st.button("Save settings (session)"):
        set_setting("SIH_BACKEND_URL", st.session_state["SIH_BACKEND_URL_input"])
        set_setting("MAPBOX_TOKEN", st.session_state["MAPBOX_TOKEN_input"])
        st.success("Settings saved for current session. To persist across restarts, add to .env or export env vars.")
    st.markdown("**Note:** This saves settings in session only. For persistent config, add `SIH_BACKEND_URL` and `MAPBOX_TOKEN` to a `.env` file or export them in your environment.")

def page_about():
    st.header("About SIH MVP")
    st.markdown("""
    **SIH MVP frontend** — demo dashboard for Smart India Hackathon prototype.
    - Built with Streamlit, Folium, Plotly.
    - Backend: FastAPI (separate service).
    - Data standards: Darwin Core (occurrences), MIxS (eDNA), NetCDF/CF (gridded).
    """)
    st.markdown("Developer tips: keep backend running and update `Settings` to point to your API during testing.")

# ----------------------------
# Router
# ----------------------------
def main():
    st.sidebar.title("SIH MVP")
    page = st.sidebar.radio("Navigate", ["Home", "Otoliths", "eDNA", "Ocean Data", "Alerts", "API Test", "Settings", "About"])
    # show quick backend status
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        st.sidebar.write("Backend:")
        if backend_get("/health") is not None:
            st.sidebar.success("Connected")
        else:
            st.sidebar.error("No connection (using demo data)")

    if page == "Home":
        page_home()
    elif page == "Otoliths":
        page_otoliths()
    elif page == "eDNA":
        page_edna()
    elif page == "Ocean Data":
        page_ocean_data()
    elif page == "Alerts":
        page_alerts()
    elif page == "API Test":
        page_api_test()
    elif page == "Settings":
        page_settings()
    elif page == "About":
        page_about()

if __name__ == "__main__":
    main()

