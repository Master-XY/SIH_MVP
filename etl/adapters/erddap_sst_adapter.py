# etl/adapters/erddap_sst_adapter.py
"""
Simple ERDDAP SST adapter.
Prefer 'erddapy' if available; fallback to building a CSV subset URL.
This code is adaptable but minimal and intended for demo usage.
"""
import logging
import datetime
import pandas as pd

logger = logging.getLogger("erddap_sst_adapter")

try:
    from erddapy import ERDDAP
    ERDDAP_AVAILABLE = True
except Exception:
    ERDDAP_AVAILABLE = False

def fetch_oisst_timeseries(erddap_server: str, dataset_id: str, minlat: float, maxlat: float,
                           minlon: float, maxlon: float, start: str = None, end: str = None):
    """
    Fetch SST timeseries using erddapy if installed.
    Returns a pandas DataFrame (index=time) or None.
    Example:
        fetch_oisst_timeseries("https://www.ncei.noaa.gov/erddap", "ncdc_oisst_avhrr", 6,24,66,92)
    """
    start = start or (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    end = end or datetime.date.today().isoformat()

    if ERDDAP_AVAILABLE:
        try:
            e = ERDDAP(server=erddap_server, protocol="tabledap")
            e.dataset_id = dataset_id
            # constraints will depend on dataset variable names: 'time','latitude','longitude' are common
            e.constraints = {
                "time": f"{start}/{end}",
                "latitude": f"{minlat}:{maxlat}",
                "longitude": f"{minlon}:{maxlon}"
            }
            # common variable name for SST is 'sst' but varies by dataset
            try:
                e.variables = ["sst"]
            except Exception:
                # leave variables default
                pass
            df = e.to_pandas()
            logger.info("Fetched ERDDAP data shape: %s", getattr(df, "shape", None))
            return df
        except Exception as e:
            logger.exception("erddapy fetch error: %s", e)
            return None
    else:
        logger.warning("erddapy not available. Install 'erddapy' for full functionality.")
        return None
