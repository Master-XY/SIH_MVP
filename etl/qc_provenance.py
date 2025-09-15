# etl/qc_provenance.py
import hashlib, json, datetime
from typing import Dict, Any, List

def make_provenance(source_name: str, raw_ref: str, transform_version: str="v0.1") -> Dict[str, Any]:
    return {
        "source_name": source_name,
        "fetch_time": datetime.datetime.utcnow().isoformat(),
        "raw_ref": raw_ref,          # e.g. URL or objectstore path
        "transform_version": transform_version
    }

def record_hash(record: Dict[str,Any]) -> str:
    s = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def qc_checks_occurrence(rec: Dict[str,Any]) -> List[str]:
    flags = []
    try:
        lat = float(rec.get("decimalLatitude") or rec.get("lat") or 0)
        lon = float(rec.get("decimalLongitude") or rec.get("lon") or 0)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            flags.append("bad_coords")
    except Exception:
        flags.append("missing_coords")

    d = rec.get("eventDate") or rec.get("date") or None
    if d:
        try:
            # accept ISO or common formats
            from dateutil import parser
            parser.parse(d)
        except Exception:
            flags.append("bad_date")
    else:
        flags.append("missing_date")

    # add domain-specific checks later (SST ranges, salinity).
    return flags
