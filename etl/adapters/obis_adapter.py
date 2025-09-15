# etl/adapters/obis_adapter.py
import requests, csv, tempfile, os
from typing import Dict, Any, List
from etl.qc_provenance import make_provenance, qc_checks_occurrence, record_hash

OBIS_BASE = "https://api.obis.org/v3/occurrence"

def fetch_obis(params: Dict[str,Any]=None, size:int=1000) -> List[Dict]:
    """
    Generic OBIS fetch. Pass OBIS params (scientificName, bbox, size, etc).
    Example: params={'scientificName':'Sardinella','size':500}
    See OBIS API docs for param list. :contentReference[oaicite:5]{index=5}
    """
    params = params or {}
    params.setdefault("size", size)
    r = requests.get(OBIS_BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    # OBIS may return list or dict — attempt to extract records
    if isinstance(data, dict):
        for k in ("results","data","features"):
            if k in data:
                return data[k]
        # fallback: return dict wrapped
        return [data]
    return data

def push_to_backend_csv(records: List[Dict], backend_base: str):
    if not records:
        return {"status":"no_records"}
    # write to temp CSV with Darwin Core subset
    fields = ["occurrenceID","scientificName","eventDate","decimalLatitude","decimalLongitude","datasetID","qc_flag"]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    tmp.close()
    with open(tmp.name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            out = {
                "occurrenceID": r.get("occurrenceID") or r.get("id") or record_hash(r),
                "scientificName": r.get("scientificName") or r.get("scientificname") or r.get("scientific_name"),
                "eventDate": r.get("eventDate") or r.get("date"),
                "decimalLatitude": r.get("decimalLatitude") or r.get("lat") or "",
                "decimalLongitude": r.get("decimalLongitude") or r.get("lon") or "",
                "datasetID": r.get("datasetID") or r.get("datasetid") or "",
                "qc_flag": ",".join(qc_checks_occurrence(r)) or "ok"
            }
            w.writerow(out)
    files = {"file": (os.path.basename(tmp.name), open(tmp.name,"rb"), "text/csv")}
    url = backend_base.rstrip("/") + "/occurrences/load"
    resp = requests.post(url, files=files, timeout=60)
    # cleanup
    try:
        os.remove(tmp.name)
    except Exception:
        pass
    return resp.json() if resp.ok else {"error": str(resp.text)}
