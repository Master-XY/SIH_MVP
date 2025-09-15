import os
import io
import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
import numpy as np
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from frontend import backend_client

# try to use folium map if available for nicer markers
try:
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False

st.set_page_config(page_title="Alerts & Advisories", layout="wide")

# ----------------------
# Helpers
# ----------------------

@st.cache_data(ttl=30)
def fetch_alerts_from_backend():
    try:
        res = backend_client.fetch_alerts(limit=50)
        if isinstance(res, dict) and "alerts" in res:
            return res["alerts"] or []
        elif isinstance(res, list):
            return res
        else:
            return res or []
    except Exception as e:
        st.warning("Could not fetch alerts: " + str(e))
        return []


def synthetic_measurements(n_days: int = 90):
    now = datetime.utcnow()
    dates = [now - timedelta(days=i) for i in range(n_days)]
    dates.reverse()
    sst = 27 + 0.5*np.sin(np.linspace(0, 4*np.pi, n_days)) + np.random.normal(0, 0.3, n_days)
    chl = 0.3 + 0.1*np.sin(np.linspace(0, 2*np.pi, n_days)) + np.random.normal(0, 0.05, n_days)
    return pd.DataFrame({"ts": dates, "sst": sst, "chl": chl})


def run_detector(payload: dict = None):
    try:
        return backend_client.run_detector(payload or {})
    except Exception as e:
        return {"error": str(e)}


def download_pdf_bytes(alert_id: int):
    try:
        return backend_client.download_alert_pdf_bytes(alert_id)
    except Exception:
        return None


def send_notify(alert_id: int, channels: list, targets: dict):
    try:
        return backend_client.send_notify(alert_id, channels, targets)
    except Exception as e:
        return {"error": str(e)}


def parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1]
        return datetime.fromisoformat(dt_str)
    except Exception:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def geodf_from_alerts(alerts):
    rows = []
    for a in alerts:
        try:
            lat = float(a.get("lat") or a.get("latitude") or a.get("decimalLatitude") or None)
            lon = float(a.get("lon") or a.get("longitude") or a.get("decimalLongitude") or None)
        except Exception:
            lat = lon = None
        rows.append({
            "id": a.get("id"),
            "type": a.get("type"),
            "status": a.get("status"),
            "message": a.get("message"),
            "created_at": a.get("created_at") or a.get("time") or a.get("timestamp"),
            "sst": a.get("sst"),
            "chl": a.get("chl"),
            "lat": lat,
            "lon": lon,
            "notified": a.get("notified", False)
        })
    return pd.DataFrame(rows)

# ----------------------
# UI
# ----------------------
st.title("🚨 Alerts & Advisories — Demo")

# Top controls
with st.container():
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        if st.button("🔄 Refresh alerts"):
            fetch_alerts_from_backend.clear()
    with c2:
        with st.expander("Run anomaly detector (simulate)"):
            sim_sst = st.number_input("SST (°C) — optional", value=None, step=0.1, format="%.2f")
            sim_chl = st.number_input("Chlorophyll — optional", value=None, step=0.01, format="%.2f")
            sim_lat = st.text_input("Lat (optional)", value="12.9")
            sim_lon = st.text_input("Lon (optional)", value="77.6")
            if st.button("Run detector now"):
                payload = {}
                if sim_sst not in (None, ""):
                    payload["sst"] = float(sim_sst)
                if sim_chl not in (None, ""):
                    payload["chl"] = float(sim_chl)
                if sim_lat:
                    payload["lat"] = sim_lat
                if sim_lon:
                    payload["lon"] = sim_lon
                res = run_detector(payload)
                st.json(res)
                fetch_alerts_from_backend.clear()
    with c3:
        if st.button("Export alerts CSV"):
            alerts_list = fetch_alerts_from_backend()
            df = geodf_from_alerts(alerts_list)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", data=csv, file_name="alerts_export.csv", mime="text/csv")
    with c4:
        st.caption("Using backend_client")

# Load alerts
alerts_list = fetch_alerts_from_backend()
df_alerts = geodf_from_alerts(alerts_list)

# Metrics
total = len(df_alerts)
active = int(df_alerts["status"].str.lower().eq("active").sum()) if "status" in df_alerts.columns else 0
notified = int(df_alerts["notified"].astype(bool).sum()) if "notified" in df_alerts.columns else 0
colm = st.columns(3)
colm[0].metric("Total alerts", total)
colm[1].metric("Active", active)
colm[2].metric("Notified", notified)

# Map
st.markdown("### Map — Alert locations")
if not df_alerts.empty and df_alerts[["lat", "lon"]].notnull().any().any():
    if FOLIUM_AVAILABLE:
        center = [df_alerts["lat"].dropna().mean(), df_alerts["lon"].dropna().mean()]
        m = folium.Map(location=center, zoom_start=6, tiles="cartodbpositron")
        mc = MarkerCluster().add_to(m)
        for _, r in df_alerts.iterrows():
            if pd.notna(r["lat"]) and pd.notna(r["lon"]):
                color = "red" if str(r.get("status","")).lower() == "active" else "orange"
                popup = f"<b>{r.get('type')}</b><br/>{r.get('message')}<br/>SST: {r.get('sst')} Chl: {r.get('chl')}"
                folium.CircleMarker([r["lat"], r["lon"]], radius=7, color=color, fill=True, fillOpacity=0.7, popup=popup).add_to(mc)
        st_folium(m, width=900, height=400)
    else:
        map_df = df_alerts.dropna(subset=["lat","lon"])[["lat","lon"]].rename(columns={"lat":"latitude","lon":"longitude"})
        st.map(map_df)
else:
    st.info("No geolocated alerts to map (or no alerts match filters).")

# Demo/Live toggle
mode = st.radio("Mode", ["Demo (synthetic)", "Live (backend)"], horizontal=True)
use_demo = (mode == "Demo (synthetic)")

# Fetch measurements
if use_demo:
    df_meas = synthetic_measurements()
else:
    try:
        meas = backend_client.get_recent_measurements(limit=500)
        df_meas = pd.DataFrame(meas)
    except Exception:
        st.warning("Failed to reach backend; using demo data")
        df_meas = synthetic_measurements()

# Plot
if not df_meas.empty:
    df_meas['ts'] = pd.to_datetime(df_meas.get('timestamp'))
    df_meas = df_meas.sort_values('ts')
    df_meas['sst_roll'] = df_meas['sst'].rolling(7, min_periods=1).mean()
    import plotly.express as px
    fig = px.line(df_meas, x='ts', y=['sst','sst_roll'], labels={'value':'SST (°C)','ts':'time'}, title="SST timeseries")
    st.plotly_chart(fig, use_container_width=True)
