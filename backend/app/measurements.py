# backend/app/measurements.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from .db import get_db
from . import models
import pandas as pd
import io
import xarray as xr
from datetime import datetime
from fastapi import Query

router = APIRouter(tags=["measurements"], prefix="/measurements")

@router.get("/recent")
def get_recent_measurements(limit: int = Query(200), db: Session = Depends(get_db)):
    """
    Return latest measurements (SST, Chl) up to `limit` records
    """
    rows = db.query(models.Measurement).order_by(models.Measurement.id.desc()).limit(limit).all()
    out = []
    for r in rows:
        out.append({
            "sst": r.sst,
            "chl": r.chl,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "lat": r.lat,
            "lon": r.lon
        })
    return out

@router.post("/load_csv")
async def load_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Accept CSV with columns: timestamp (opt), sst, chl, lat, lon
    """
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    inserted = 0
    for _, r in df.iterrows():
        try:
            sst = float(r.get("sst") or r.get("SST"))
            chl = float(r.get("chl") or r.get("Chl") or r.get("chlorophyll", 0.0))
            lat = r.get("lat") or r.get("latitude") or None
            lon = r.get("lon") or r.get("longitude") or None
            ts = r.get("timestamp") or r.get("time") or None
            if ts:
                try:
                    ts = datetime.fromisoformat(str(ts))
                except Exception:
                    ts = None
            meas = models.Measurement(sst=sst, chl=chl, lat=str(lat) if lat else None, lon=str(lon) if lon else None)
            db.add(meas)
            inserted += 1
        except Exception:
            continue
    db.commit()
    return {"status": "ok", "inserted": inserted}


@router.post("/load_netcdf")
async def load_netcdf(file: UploadFile = File(...), var_sst: str = "sst", var_chl: str = None, db: Session = Depends(get_db)):
    """
    Accept a NetCDF file, extract a timeseries (mean over spatial domain) for sst and chl.
    var_sst/var_chl: variable names in nc file.
    """
    content = await file.read()
    try:
        # xarray can open from bytes via BytesIO + open_dataset
        ds = xr.open_dataset(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"NetCDF open error: {e}")

    # reduce in time/space to produce records
    if "time" in ds.dims:
        times = ds["time"].values
        records = []
        for t in times:
            try:
                sst_val = float(ds[var_sst].sel(time=t).mean().values)
            except Exception:
                sst_val = None
            chl_val = None
            if var_chl and var_chl in ds:
                try:
                    chl_val = float(ds[var_chl].sel(time=t).mean().values)
                except Exception:
                    chl_val = None
            rec = {"time": pd.to_datetime(str(t)).isoformat(), "sst": sst_val, "chl": chl_val}
            records.append(rec)
    else:
        # single snapshot
        try:
            sst_val = float(ds[var_sst].mean().values)
        except Exception:
            sst_val = None
        chl_val = None
        if var_chl and var_chl in ds:
            try:
                chl_val = float(ds[var_chl].mean().values)
            except Exception:
                chl_val = None
        records = [{"time": datetime.utcnow().isoformat(), "sst": sst_val, "chl": chl_val}]

    inserted = 0
    for r in records:
        if r["sst"] is None and r["chl"] is None:
            continue
        meas = models.Measurement(sst=r["sst"], chl=r["chl"], lat=None, lon=None)
        db.add(meas)
        inserted += 1
    db.commit()
    return {"status": "ok", "inserted": inserted, "sample": records[:3]}
