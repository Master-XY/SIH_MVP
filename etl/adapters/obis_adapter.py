# etl/adapters/obis_adapter.py
"""
OBIS adapter: fetch occurrence records from OBIS and push to backend ingestion CSV endpoint.

Usage (example):
    from etl.adapters.obis_adapter import fetch_obis, push_to_backend_csv
    recs = fetch_obis({'scientificName': 'Sardinella', 'size': 200})
    push_to_backend_csv(recs, backend_base="http://127.0.0.1:8000/api/v1")
"""
import requests
import csv
import tempfile
import os
import time
import logging
from typing import Dict, Any, List

from etl.qc_provenance import make_provenance, qc_checks_occurrence, record_hash

logger = logging.getLogger("obis_adapter")
OBIS_BASE = "https://api.obis.org/v3/occurrence"


def fetch_obis(params: Dict[str, Any] = None, size: int = 500, max_pages: int = 10, page_size: int = 500) -> List[Dict]:
    """
    Fetch records from OBIS using simple paging.
    - params: dict of OBIS query params (scientificName, bbox, etc.)
    - size: total desired records
    - max_pages: safety cap
    - page_size: page size per request (OBIS supports larger sizes; keep moderate)
    Returns list of raw OBIS records (dicts) or empty list on failure.
    """
    params = params.copy() if params else {}
    results = []
    offset = 0
    total_wanted = size
    page = 0
    while len(results) < total_wanted and page < max_pages:
        try:
            params.update({"size": min(page_size, total_wanted - len(results)), "offset": offset})
            r = requests.get(OBIS_BASE, params=params, timeout=30)
            r.raise_for_status()
            payload = r.json()
            # OBIS v3 often returns 'results'
            page_records = payload.get("results") or payload.get("data") or payload.get("features") or payload
            if isinstance(page_records, dict):
                # maybe top-level structure; attempt to extract list fields
                for k in ("results", "data", "features"):
                    if k in page_records:
                        page_records = page_records[k]
                        break
            if not page_records:
                break
            if isinstance(page_records, list):
                results.extend(page_records)
            else:
                # single record
                results.append(page_records)
            # prepare next page
            offset += params["size"]
            page += 1
            time.sleep(0.2)  # be polite
        except Exception as e:
            logger.exception("OBIS fetch error: %s", e)
            break
    logger.info("Fetched %d OBIS records", len(results))
    return results


def push_to_backend_csv(records: List[Dict], backend_base: str = "http://127.0.0.1:8000/api/v1"):
    """
    Convert records to a Darwin Core subset CSV and POST to backend /occurrences/load
    Returns backend response JSON or raises on error.
    """
    if not records:
        return {"status": "no_records"}

    fields = ["occurrenceID", "scientificName", "eventDate", "decimalLatitude", "decimalLongitude", "datasetID", "qc_flag"]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    tmp.close()
    try:
        with open(tmp.name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in records:
                out = {
                    "occurrenceID": r.get("occurrenceID") or r.get("id") or record_hash(r),
                    "scientificName": r.get("scientificName") or r.get("scientificname") or r.get("scientific_name") or "",
                    "eventDate": r.get("eventDate") or r.get("date") or "",
                    "decimalLatitude": r.get("decimalLatitude") or r.get("lat") or "",
                    "decimalLongitude": r.get("decimalLongitude") or r.get("lon") or "",
                    "datasetID": r.get("datasetID") or r.get("datasetid") or "",
                    "qc_flag": ",".join(qc_checks_occurrence(r)) or "ok"
                }
                w.writerow(out)

        files = {"file": (os.path.basename(tmp.name), open(tmp.name, "rb"), "text/csv")}
        url = backend_base.rstrip("/") + "/occurrences/load"
        logger.info("Pushing CSV to backend %s", url)
        resp = requests.post(url, files=files, timeout=120)
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code, "text": resp.text}
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass


if __name__ == "__main__":
    # quick local test (only runs if executed directly)
    print("Running quick OBIS fetch test (1 record)...")
    recs = fetch_obis({"size": 10}, size=10)
    print("Fetched:", len(recs))
