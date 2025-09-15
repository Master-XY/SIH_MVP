# backend/app/inference.py
import os, random
from pathlib import Path

MODEL_DIR = os.getenv("SIH_MODEL_DIR", "data/models")
Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = os.getenv("SIH_UPLOAD_DIR", "data/uploads")
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

def save_upload(file_obj, filename: str) -> str:
    out_path = Path(UPLOAD_DIR) / filename
    with open(out_path, "wb") as f:
        f.write(file_obj.read())
    return str(out_path)

def predict_otolith_stub(filepath: str):
    labels = [
        "Thunnus albacares (Yellowfin Tuna)",
        "Sardinella longiceps (Oil Sardine)",
        "Katsuwonus pelamis (Skipjack Tuna)",
        "Rastrelliger kanagurta (Indian Mackerel)"
    ]
    pred = random.choice(labels)
    confidence = float(round(random.uniform(0.6, 0.98), 4))
    explain = {"gradcam": None, "nearest_examples": []}
    return {"species": pred, "confidence": confidence, "explainability": explain}
