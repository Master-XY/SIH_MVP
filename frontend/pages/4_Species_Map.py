import os
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from frontend import backend_client

st.set_page_config(page_title="Species / Occurrences", layout="wide")

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
@st.cache_data(ttl=60)
def load_occurrences(limit=500, date_from=None, date_to=None):
    try:
        occ = backend_client.fetch_occurrences(limit=limit, date_from=date_from, date_to=date_to)
    except Exception as e:
        st.warning("Could not fetch occurrences: " + str(e))
        return pd.DataFrame()

    df = pd.DataFrame(occ)

    # Normalize lat/lon
    if "decimalLatitude" in df.columns:
        df = df.rename(columns={"decimalLatitude": "lat", "decimalLongitude": "lon"})
    elif "latitude" in df.columns:
        df = df.rename(columns={"latitude": "lat", "longitude": "lon"})

    if "lat" in df.columns:
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    if "lon" in df.columns:
        df["lon"] = pd.to_numeric(df["lon"], errors="coerce")

    return df

# ------------------------
# UI: Filters
# ------------------------
st.title("📍 Species occurrences (OBIS)")
st.write("Data from backend or local DB.")

left, right = st.columns([1.5, 1])
with left:
    limit = st.number_input("Max records", value=500, min_value=10, max_value=5000, step=10)
    date_from = st.date_input("From date", value=(datetime.utcnow() - timedelta(days=365)).date())
    date_to = st.date_input("To date", value=datetime.utcnow().date())
    if st.button("Load occurrences"):
        load_occurrences.clear()
        st.experimental_rerun()

with right:
    search_name = st.text_input("Filter species (contains)", value="")

# Load
df = load_occurrences(limit=limit, date_from=str(date_from), date_to=str(date_to))

if search_name and "scientificName" in df.columns:
    df = df[df["scientificName"].str.contains(search_name, case=False, na=False)]

st.markdown(f"**Records loaded:** {len(df)}")

# ------------------------
# Top species chart + CSV export
# ------------------------
if not df.empty and "scientificName" in df.columns:
    top = df["scientificName"].value_counts().nlargest(12)
    top_df = top.reset_index().rename(columns={"index":"scientificName","scientificName":"count"})
    import plotly.express as px
    st.subheader("Top species")
    fig = px.bar(top_df, x="count", y="scientificName", orientation="h", height=350)
    st.plotly_chart(fig, use_container_width=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Export CSV", data=csv, file_name="occurrences_export.csv", mime="text/csv")

# ------------------------
# Map
# ------------------------
st.markdown("### Map")
if not df.empty and {"lat","lon"}.issubset(df.columns):
    map_df = df.dropna(subset=["lat","lon"])
    if FOLIUM:
        center = [map_df["lat"].mean(), map_df["lon"].mean()]
        m = folium.Map(location=center, zoom_start=4, tiles="cartodbpositron")
        HeatMap(map_df[["lat","lon"]].values.tolist(), radius=15, blur=10).add_to(m)
        mc = MarkerCluster().add_to(m)
        for _, r in map_df.iterrows():
            popup = f"<b>{r.get('scientificName','-')}</b><br>{r.get('eventDate','-')}<br>{r.get('datasetID','-')}<br>ID: {r.get('occurrenceID','-')}"
            folium.Marker(location=[r["lat"], r["lon"]], popup=popup).add_to(mc)
        st_folium(m, width=900, height=450)
    else:
        st.map(map_df.rename(columns={"lat":"latitude","lon":"longitude"}))
else:
    st.info("No geolocated records to show.")

# ------------------------
# Table + provenance view
# ------------------------
st.markdown("### Records table")
st.dataframe(df.head(100))
