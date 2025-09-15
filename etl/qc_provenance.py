# etl/qc_provenance.py
"""
QC and provenance helpers for ETL adapters.
Provides:
- make_provenance(source_name, raw_ref, transform_version)
- record_hash(record)
- qc_checks_occurrence(record)
"""
import hashlib
import json
import datetime
import logging

logger = logging.getLogger("qc_provenance")


def make_provenance(source_name: str, raw_ref: str, transform_version: str = "v0.1"):
    """Return a small provenance dict describing the fetch/transform."""
    return {
        "source_name": source_name,
        "fetch_time": datetime.datetime.utcnow().isoformat(),
        "raw_ref": raw_ref,
        "transform_version": transform_version,
    }


def record_hash(record: dict) -> str:
    """Return a stable hash for a record (useful as occurrenceID fallback)."""
    s = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def qc_checks_occurrence(rec: dict):
    """
    Basic QC checks for an occurrence-like record.
    Returns a list of QC flags (empty==OK).
    """
    flags = []
    # coordinates
    try:
        lat = float(rec.get("decimalLatitude") or rec.get("lat") or 0)
        lon = float(rec.get("decimalLongitude") or rec.get("lon") or 0)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            flags.append("bad_coords")
    except Exception:
        flags.append("missing_coords")

    # date
    if rec.get("eventDate") or rec.get("date"):
        d = rec.get("eventDate") or rec.get("date")
        try:
            # try ISO parse
            datetime.datetime.fromisoformat(d)
        except Exception:
            # fallback: we accept it but flag it
            flags.append("bad_date_format")
    else:
        flags.append("missing_date")

    # basic domain checks (extend later)
    # example: check unrealistic depth / temperature ranges here

    if flags:
        logger.debug("QC flags for record: %s", flags)
    return flags
