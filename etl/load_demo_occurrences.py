# etl/load_demo_occurrences.py
import requests
import os
from pathlib import Path

BACKEND = os.getenv("SIH_BACKEND_URL", "http://127.0.0.1:8000/api/v1")
CSV_PATH = Path("data/demo_occurrences.csv")

def load_to_backend():
    url = f"{BACKEND}/occurrences/load"
    with open(CSV_PATH, "rb") as f:
        files = {"file": (CSV_PATH.name, f, "text/csv")}
        r = requests.post(url, files=files, timeout=30)
        print("Status:", r.status_code, r.text)

if __name__ == "__main__":
    load_to_backend()
