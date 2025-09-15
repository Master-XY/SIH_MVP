# frontend/pages/3_Alerts.py
import os
import io
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta

# try to use folium map if available for nicer markers
try:
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except Exception:
    FOLIUM_AVAILABLE = False

st.set_page_config(page_title="Alerts & Advisories", layout="wide")

BACKEND = os.environ.get("SIH_BACKEND_URL", "http://localhost:8000/api/v1").rstrip("/")

# ----------------------
# Helpers
# ----------------------
@st.cache_data(ttl=30)
def fetch_alerts_from_backend():
    try:
        r = requests.get(f"{BACKEND}/alerts", timeout=6)
        r.raise_for_status()
        payload = r.json()
        # backend may return {"alerts": [...]} or a list
        if isinstance(payload, dict) and "alerts" in payload:
            alerts = payload["alerts"] or []
        elif isinstance(payload, list):
            alerts = payload
        else:
            alerts = payload or []
        return alerts
    except Exception as e:
        st.warning("Could not reach backend; showing no alerts (or fallback).")
        return []


def run_detector(payload: dict = None):
    """Call backend anomaly check (backend should support POST /alerts/check)."""
    try:
        r = requests.post(f"{BACKEND}/alerts/check", json=payload or {}, timeout=10)
        try:
            return r.json()
        except Exception:
            return {"status_code": r.status_code, "text": r.text}
    except Exception as e:
        return {"error": str(e)}


def download_pdf_bytes(alert_id: int):
    """Try the common pdf endpoints. Return bytes or None."""
    endpoints = [f"{BACKEND}/alerts/{alert_id}/pdf", f"{BACKEND}/alerts/{alert_id}/export_pdf"]
    for url in endpoints:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and r.headers.get("content-type","").startswith("application/pdf"):
                return r.content
        except Exception:
            pass
    return None


def send_notify(alert_id: int, channels: list, targets: dict):
    try:
        r = requests.post(f"{BACKEND}/alerts/{alert_id}/notify", json={"channels": channels, "targets": targets}, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        # handle trailing Z
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
        st.write("")  # spacer
        # quick simulation controls
        with st.expander("Run anomaly detector (simulate)"):
            sim_sst = st.number_input("SST (°C) — optional", value=None, step=0.1, format="%.2f", key="sim_sst")
            sim_chl = st.number_input("Chlorophyll — optional", value=None, step=0.01, format="%.2f", key="sim_chl")
            sim_lat = st.text_input("Lat (optional)", value="12.9", key="sim_lat")
            sim_lon = st.text_input("Lon (optional)", value="77.6", key="sim_lon")
            if st.button("Run detector now", key="run_detector"):
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
                # refresh alerts cache
                fetch_alerts_from_backend.clear()
    with c3:
        if st.button("Export alerts CSV"):
            alerts_list = fetch_alerts_from_backend()
            df = geodf_from_alerts(alerts_list)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", data=csv, file_name="alerts_export.csv", mime="text/csv")
    with c4:
        st.write("Backend:")
        st.caption(BACKEND)

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

# Filters
with st.expander("Filters"):
    st.write("Narrow displayed alerts")
    st_cols = st.columns([2, 2, 3])
    types = sorted(df_alerts["type"].dropna().unique().tolist()) if not df_alerts.empty else []
    status_vals = ["All"] + sorted(df_alerts["status"].dropna().unique().tolist()) if not df_alerts.empty else ["All"]
    sel_type = st_cols[0].multiselect("Type", options=types, default=types)
    sel_status = st_cols[1].selectbox("Status", options=status_vals, index=0 if "All" in status_vals else 0)
    default_from = date.today() - timedelta(days=30)
    drange = st_cols[2].date_input("Date range", value=(default_from, date.today()))
    # apply filters
    df_display = df_alerts.copy()
    if sel_type:
        df_display = df_display[df_display["type"].isin(sel_type)]
    if sel_status and sel_status != "All":
        df_display = df_display[df_display["status"] == sel_status]
    try:
        dt_from = datetime.combine(drange[0], datetime.min.time())
        dt_to = datetime.combine(drange[1], datetime.max.time())
        df_display["created_dt"] = df_display["created_at"].apply(parse_iso)
        df_display = df_display[df_display["created_dt"].dropna().index.intersection(df_display.index)]
        df_display = df_display[(df_display["created_dt"] >= dt_from) & (df_display["created_dt"] <= dt_to)]
    except Exception:
        pass

# Map
st.markdown("### Map — Alert locations")
if not df_display.empty and df_display[["lat", "lon"]].notnull().any().any():
    if FOLIUM_AVAILABLE:
        center = [df_display["lat"].dropna().mean(), df_display["lon"].dropna().mean()]
        m = folium.Map(location=center, zoom_start=6, tiles="cartodbpositron")
        mc = MarkerCluster().add_to(m)
        for _, r in df_display.iterrows():
            if pd.notna(r["lat"]) and pd.notna(r["lon"]):
                color = "red" if str(r.get("status","")).lower() == "active" else "orange"
                popup = f"<b>{r.get('type')}</b><br/>{r.get('message')}<br/>SST: {r.get('sst')} Chl: {r.get('chl')}"
                folium.CircleMarker([r["lat"], r["lon"]], radius=7, color=color, fill=True, fillOpacity=0.7, popup=popup).add_to(mc)
        st_folium(m, width=900, height=400)
    else:
        # fall back to st.map
        map_df = df_display.dropna(subset=["lat","lon"])[["lat","lon"]].rename(columns={"lat":"latitude","lon":"longitude"})
        st.map(map_df)
else:
    st.info("No geolocated alerts to map (or no alerts match filters).")

# Alert cards
st.markdown("### Alert list")
if df_display.empty:
    st.info("No alerts match the selected filters.")
else:
    for _, row in df_display.sort_values("created_dt", ascending=False).iterrows():
        with st.container():
            cols = st.columns([6, 2])
            status = str(row.get("status", "")).lower()
            if status == "active":
                badge = "🔴 Active"
            elif status in ("resolved", "closed"):
                badge = "🟢 Resolved"
            else:
                badge = "🟠 " + (row.get("status") or "unknown")

            header_md = f"**Alert #{int(row['id'])} — {row.get('type','-')}**  \n{badge}  •  {row.get('created_at','-')}"
            cols[0].markdown(header_md)
            cols[1].markdown(f"**SST:** {row.get('sst','-')} °C  \n**Chl:** {row.get('chl','-')}")

            st.write(row.get("message", "-"))

            action_cols = st.columns([1, 1, 2, 2])
            # Download PDF
            if action_cols[0].button("📄 Download PDF", key=f"pdf_{row['id']}"):
                pdf_bytes = download_pdf_bytes(int(row["id"]))
                if pdf_bytes:
                    action_cols[0].download_button("Save PDF", data=pdf_bytes, file_name=f"advisory_{row['id']}.pdf", mime="application/pdf")
                else:
                    st.warning("PDF not available for this alert.")

            # Quick details / map link
            if action_cols[1].button("📍 Center on map", key=f"center_{row['id']}"):
                # set session state so map could re-center (not implemented fully here)
                st.experimental_set_query_params(alert=row["id"])
                st.info("Map centered (query param set).")

            # Notify panel
            with action_cols[2].expander("🔔 Send demo notification"):
                channels = st.multiselect("Channels", options=["sms", "telegram", "email"], key=f"chn_{row['id']}")
                sms = st.text_input("SMS number", value="+911234567890", key=f"sms_{row['id']}")
                tg = st.text_input("Telegram chat id", value="demo_chat", key=f"tg_{row['id']}")
                mail = st.text_input("Email", value="demo@example.com", key=f"mail_{row['id']}")
                if st.button("Send", key=f"send_{row['id']}"):
                    targets = {"sms": sms, "telegram": tg, "email": mail}
                    resp = send_notify(int(row["id"]), channels, targets)
                    st.json(resp)
                    # refresh cache so notified flag shows next time
                    fetch_alerts_from_backend.clear()

            # Small spacer
            st.markdown("---")
