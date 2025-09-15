# etl/flows/etl_flow_prefect.py
"""
A small Prefect flow that runs adapters and pushes to backend.
This works with Prefect 2.x. For quick runs you can execute:
    python etl/flows/etl_flow_prefect.py
which will run the underlying tasks as normal functions (no Prefect server required).
"""
import os
import logging
from prefect import flow, task
from datetime import datetime

logger = logging.getLogger("etl_flow")
logging.basicConfig(level=logging.INFO)

# Adapter imports (local relative)
from etl.adapters.obis_adapter import fetch_obis, push_to_backend_csv
from etl.adapters.erddap_sst_adapter import fetch_oisst_timeseries
from etl.adapters.incois_pfz_scraper import fetch_pfzs

BACKEND = os.getenv("SIH_BACKEND_URL", "http://127.0.0.1:8000/api/v1")

@task
def obis_task(bbox: str = None, size: int = 200):
    logger.info("Running OBIS task (bbox=%s size=%s)", bbox, size)
    params = {}
    if bbox:
        params["bbox"] = bbox
    recs = fetch_obis(params=params, size=size)
    res = push_to_backend_csv(recs, backend_base=BACKEND)
    logger.info("OBIS push result: %s", res)
    return res

@task
def incois_task():
    logger.info("Running INCOIS PFZ scraper")
    res = fetch_pfzs()
    logger.info("INCOIS PFZ result: %s", res.get("raw")[:200] if res else "<none>")
    # Optionally POST to backend alerts endpoint here
    try:
        import requests
        url = BACKEND.rstrip("/") + "/alerts"
        payload = {"source": "incois_pfz", "raw": res.get("raw", "")}
        # backend might not accept arbitrary payload; skip POST by default
        # r = requests.post(url, json=payload, timeout=10)
    except Exception:
        pass
    return res

@task
def erddap_sst_task():
    logger.info("Running ERDDAP SST task (demo)")
    # Example server/dataset; adjust to dataset available on server
    server = os.getenv("ERDDAP_SERVER", "https://www.ncei.noaa.gov/erddap")
    dataset = os.getenv("ERDDAP_SST_DS", "")  # user must configure
    if not dataset:
        logger.warning("No ERDDAP dataset configured; skipping SST fetch")
        return None
    df = fetch_oisst_timeseries(server, dataset, minlat=6, maxlat=24, minlon=66, maxlon=92)
    if df is not None:
        outpath = f"data/erddap_sst_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.csv"
        df.to_csv(outpath)
        logger.info("Saved ERDDAP SST to %s", outpath)
    return True

@flow
def etl_master(run_obis: bool = True, run_erddap: bool = False, run_incois: bool = True):
    logger.info("Starting ETL master flow")
    results = {}
    if run_obis:
        results["obis"] = obis_task.submit(bbox=os.getenv("ETL_BBOX", "66,6,92,24"), size=int(os.getenv("ETL_OBIS_SIZE", "200"))).result()
    if run_incois:
        results["incois"] = incois_task.submit().result()
    if run_erddap:
        results["erddap"] = erddap_sst_task.submit().result()
    return results

if __name__ == "__main__":
    print("Running ETL master flow locally")
    res = etl_master()
    print("Done:", res)

