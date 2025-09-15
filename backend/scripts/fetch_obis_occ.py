# backend/scripts/fetch_obis_occ.py
import requests
from backend.app.db import SessionLocal, engine
from backend.app import models
from datetime import datetime

def fetch_and_store(limit=50):
    """
    Fetch species occurrences near Kerala coast and store in DB.
    """
    url = "https://api.obis.org/v3/occurrence"
    params = {
        "decimalLatitude": "8,12",   # Kerala coast lat box
        "decimalLongitude": "74,78", # Kerala coast lon box
        "size": limit
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()

    db = SessionLocal()
    inserted = 0
    for rec in data.get("results", []):
        occ = models.Occurrence(
            occurrenceID = str(rec.get("occurrenceID", "")),
            scientificName = rec.get("scientificName", ""),
            eventDate = rec.get("eventDate"),
            decimalLatitude = rec.get("decimalLatitude"),
            decimalLongitude = rec.get("decimalLongitude"),
            datasetID = rec.get("datasetID"),
            provenance = {"source": "OBIS"},
            qc_flag = "ok",
            raw = rec  # store full record JSON
        )
        db.add(occ)
        inserted += 1
    db.commit()
    db.close()
    print(f"Inserted {inserted} OBIS records")

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    fetch_and_store()
