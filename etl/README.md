# ETL folder - adapters & flows

This folder contains adapter templates and a simple Prefect flow to run them.

## Purpose
- Provide ready-to-run code to fetch occurrences (OBIS), SST (ERDDAP), PFZ advisories (INCOIS), and an AIS streamer skeleton.
- Provide QC/provenance helpers.
- Prefect flow (etl_flow_prefect.py) orchestrates tasks.

---

## Files
- `qc_provenance.py` - common provenance/qc helpers.
- `adapters/obis_adapter.py` - OBIS fetch + push_to_backend_csv.
- `adapters/erddap_sst_adapter.py` - ERDDAP SST fetch (requires `erddapy`).
- `adapters/incois_pfz_scraper.py` - simple PFZ scraper (heuristic).
- `adapters/ais_streamer.py` - AIS websocket skeleton.
- `flows/etl_flow_prefect.py` - Prefect flow to run adapter tasks.

---

## Quick setup (local)
1. Activate your venv:
   ```bash
   .venv\Scripts\activate   # Windows
   source .venv/bin/activate  # Linux/Mac
