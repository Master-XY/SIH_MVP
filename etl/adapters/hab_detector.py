import xarray as xr
import numpy as np
import pandas as pd

def compute_anomaly(current_file, climatology_file, thresh=2.0):
    """
    current_file: NetCDF with recent SST/chlorophyll
    climatology_file: NetCDF with long-term climatology
    """
    cur = xr.open_dataset(current_file)
    clim = xr.open_dataset(climatology_file)

    # assume variable 'sst' in both datasets
    cur_sst = cur['sst'].mean(dim='time')
    clim_mean = clim['sst'].mean(dim='time')
    clim_std = clim['sst'].std(dim='time')

    anomaly = (cur_sst - clim_mean) / clim_std
    mask = anomaly.where(anomaly > thresh)

    hotspots = mask.to_dataframe().dropna()
    return hotspots.reset_index()

def generate_alert(hotspots_df):
    if hotspots_df.empty:
        return {"status": "no_alerts"}
    # Simplified: just take bbox of hotspot
    minlat, maxlat = hotspots_df['lat'].min(), hotspots_df['lat'].max()
    minlon, maxlon = hotspots_df['lon'].min(), hotspots_df['lon'].max()
    return {
        "status": "alert",
        "type": "SST anomaly",
        "bbox": [float(minlon), float(minlat), float(maxlon), float(maxlat)],
        "explanation": "SST anomaly > 2σ detected, possible HAB/anoxia"
    }
