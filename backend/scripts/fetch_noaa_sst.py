# backend/scripts/fetch_noaa_sst.py
import xarray as xr
import pandas as pd
from datetime import datetime, timedelta
from backend.app.db import SessionLocal, engine
from backend.app import models

def fetch_and_store(days: int = 3):
    """
    Fetch last `days` of NOAA OISST data, store daily mean SST in Measurement.
    """
    base_url = "https://www.ncei.noaa.gov/thredds-ocean/dodsC/OisstBase/NetCDF/AVHRR"
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)

    # NOAA OISST daily dataset
    url = "https://www.ncei.noaa.gov/thredds/dodsC/OisstBase/NetCDF/AVHRR/oisst-avhrr-v02r01.202309.nc"  
    # NOTE: Replace with correct monthly file (each file contains 1 month of daily grids)

    ds = xr.open_dataset(url)

    db = SessionLocal()
    for t in pd.date_range(start, end):
        try:
            # Select one day
            sst_day = ds['sst'].sel(time=t.strftime("%Y-%m-%d"))
            # Subset India Ocean approx box
            sst_box = sst_day.sel(lat=slice(-20, 30), lon=slice(40, 100))
            mean_val = float(sst_box.mean().values)
            
            m = models.Measurement(
                timestamp=pd.to_datetime(t),
                sst=round(mean_val, 2),
                chl=None
            )
            db.add(m)
            print(f"Stored SST {t.date()} = {mean_val:.2f}")
        except Exception as e:
            print("skip", t, e)
            continue
    db.commit()
    db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    fetch_and_store(5)  # fetch last 5 days
