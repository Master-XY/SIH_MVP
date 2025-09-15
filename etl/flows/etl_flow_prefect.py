# etl/flows/etl_flow_prefect.py
from prefect import flow, task
from etl.adapters.obis_adapter import fetch_obis, push_to_backend_csv
from etl.adapters.erddap_sst_adapter import fetch_oisst_timeseries

BACKEND = "http://127.0.0.1:8000/api/v1"  # override via env

@task
def run_obis_task(bbox=None):
    params = {}
    if bbox:
        params["bbox"] = bbox
    recs = fetch_obis(params=params, size=500)
    res = push_to_backend_csv(recs, backend_base=BACKEND)
    return res

@task
def run_sst_task():
    # example: NOAA ERDDAP server and dataset id (server may vary)
    server = "https://www.ncei.noaa.gov/erddap"
    ds = "ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon"
    df = fetch_oisst_timeseries(server, ds, minlat=6, maxlat=24, minlon=66, maxlon=92)
    # For demo, save to csv and push someplace (object store) or compute anomaly
    if df is not None:
        fn = "/tmp/sst_recent.csv"
        df.to_csv(fn)
    return True

@flow
def etl_master():
    r1 = run_obis_task.submit(bbox="66,6,92,24")
    r2 = run_sst_task.submit()
    return {"obis": r1.result(), "sst": r2.result()}

if __name__ == "__main__":
    etl_master()
