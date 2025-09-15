# etl/adapters/erddap_sst_adapter.py
from erddapy import ERDDAP
import pandas as pd
from datetime import date
import logging

def fetch_oisst_timeseries(erddap_server: str, dataset_id: str, minlat, maxlat, minlon, maxlon, start=None, end=None):
    """
    Uses erddapy to fetch SST time series over a bbox and time window.
    erddap_server e.g. 'https://www.ncei.noaa.gov/erddap'
    dataset_id example: 'ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon' (server-specific). :contentReference[oaicite:8]{index=8}
    """
    e = ERDDAP(server=erddap_server)
    e.dataset_id = dataset_id
    # constraints: ERDDAP expects variable names and constraints - server/dataset specific
    start = start or (date.today() - pd.Timedelta(days=30)).isoformat()
    end = end or date.today().isoformat()
    # 'time' variable and lat/lon variable names depend on dataset; common names are 'time','latitude','longitude'
    e.constraints = {
        "time": f"{start}/{end}",
        "latitude": f"{minlat}:{maxlat}",
        "longitude": f"{minlon}:{maxlon}"
    }
    # choose the variable(s) to retrieve (commonly 'sst' or 'temp')
    # often one must consult dataset metadata to set variables
    e.variables = ["sst"]
    try:
        df = e.to_pandas(index_col="time", parse_dates=True)
        return df
    except Exception as exc:
        logging.error("erddap fetch error: %s", exc)
        return None
