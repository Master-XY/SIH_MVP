# frontend/pages/4_Species_Map.py
import os
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="Species / Occurrences", layout="wide")
BACKEND = os.environ.get("SIH_BACKEND_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")

# Optional nicer map if available
try:
    import folium
    from folium.plugins import MarkerCluster, HeatMap
    from streamlit_folium import st_folium
    FOLIUM = True
except Exception:
    FOLIUM = False

# ------------------------
# Helpers
# ------------------------
@st.cache_data(ttl=120)
def fetch_occurrences(limit=1000, bbox=None, date_from=None, date_to=None):
    params = {}
    if limit:
        params["limit"] = limit
    if bbox:
        params["bbox"] = bbox
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    try:
        r = requests.get(f"{BACKEND}/occurrences", params=params, timeout=10)
        r.raise_for_status()
        payload = r.json()
        if isinstance(payload, dict) and "data" in payload:
            recs = payload["data"]
        elif isinstance(payload, list):
            recs = payload
        elif isinstance(payload, dict) and "results" in payload:
            recs = payload["results"]
        else:
            recs = payload or []
        return recs
    except Exception as e:
        st.warning("Could not fetch occurrences from backend: " + str(e))
        return []

def normalize_df(recs):
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs)
    # harmonize lat/lon
    for col in ("decimalLatitude","lat","latitude"):
        if col in df.columns:
            df = df.rename(columns={col: "lat"})
            break
    for col in ("decimalLongitude","lon","longitude"):
        if col in df.columns:
            df = df.rename(columns={col: "lon"})
            break
    # parse as float safely
    df["lat"] = df.get("lat").apply(lambda x: float(x) if x is not None else None) if "lat" in df.columns else None
    df["lon"] = df.get("lon").apply(lambda x: float(x) if x is not None else None) if "lon" in df.columns else None
    # harmonize species name
    if "scientificName" not in df.columns and "species" in df.columns:
        df = df.rename(columns={"species":"scientificName"})
    return df

# ------------------------
# UI: Filters
# ------------------------
st.title("📍 Species occurrences (OBIS)")
st.write("Live data from backend `/api/v1/occurrences`. Use filters to narrow the view.")

left, right = st.columns([1.5, 1])
with left:
    limit = st.number_input("Max records", value=500, min_value=10, max_value=5000, step=10)
    bbox = st.text_input("BBox (minLon,minLat,maxLon,maxLat) — optional", value="")
    date_from = st.date_input("From date", value=(datetime.utcnow() - timedelta(days=365)).date())
    date_to = st.date_input("To date", value=datetime.utcnow().date())
    if st.button("Load occurrences"):
        fetch_occurrences.clear()
        st.experimental_rerun()

with right:
    search_name = st.text_input("Filter species (contains)", value="")

# Load
recs = fetch_occurrences(limit=limit, bbox=bbox or None, date_from=str(date_from), date_to=str(date_to))
df = normalize_df(recs)

if search_name:
    df = df[df.get("scientificName","").str.contains(search_name, case=False, na=False)]

st.markdown(f"**Records loaded:** {len(df)}")

# ------------------------
# Top species chart + CSV export
# ------------------------
if not df.empty and "scientificName" in df.columns:
    top = df["scientificName"].value_counts().nlargest(12)
    top.name = "count"
    top_df = top.reset_index().rename(columns={"index":"scientificName"})
    
    st.subheader("Top species")
    c1, c2 = st.columns([2,1])
    with c1:
        import plotly.express as px
        fig = px.bar(
            top_df,
            x="count",
            y="scientificName",
            orientation="h",
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Export CSV", data=csv, file_name="occurrences_export.csv", mime="text/csv")

# ------------------------
# Map
# ------------------------
st.markdown("### Map")
map_df = df.dropna(subset=["lat","lon"])
if map_df.empty:
    st.info("No geolocated records to show for current filters.")
else:
    if FOLIUM:
        # Default center over Africa
        center = [9.9, 76.6]  
        m = folium.Map(location=center, zoom_start=3, tiles="cartodbpositron")

        # Heatmap
        heat_data = map_df[["lat","lon"]].values.tolist()
        if heat_data:
            HeatMap(data=heat_data, radius=15, blur=10).add_to(m)

        # MarkerCluster
        mc = MarkerCluster().add_to(m)
        for _, r in map_df.iterrows():
            popup = f"<b>{r.get('scientificName','-')}</b><br>{r.get('eventDate','-')}<br>{r.get('datasetID','-')}<br>ID: {r.get('occurrenceID','-')}"
            folium.Marker(location=[r["lat"], r["lon"]], popup=popup).add_to(mc)

        st_folium(m, width=900, height=450)
    else:
        map_df2 = map_df.rename(columns={"lat":"latitude","lon":"longitude"})
        st.map(map_df2)

# ------------------------
# Table + provenance view
# ------------------------
st.markdown("### Records table")
st.dataframe(df.head(100))

with st.expander("Show provenance / raw record for a selected occurrence id"):
    occ_id = st.text_input("Type occurrenceID to inspect")
    if occ_id:
        selected = next((r for r in recs if str(r.get("occurrenceID","")) == str(occ_id)), None)
        if selected:
            st.json(selected)
        else:
            st.write("Occurrence ID not found in current set.")
