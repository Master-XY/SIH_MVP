# backend/scripts/seed_measurements.py
import pandas as pd
from backend.app.db import SessionLocal, engine
from backend.app import models
from datetime import datetime, timedelta
import random

def seed(n=120):
    db = SessionLocal()
    models.Base.metadata.create_all(bind=engine)
    start = datetime.utcnow() - timedelta(days=n)
    for i in range(n):
        t = start + timedelta(days=i)
        # demo seasonal SST + noise
        sst = 27 + 1.2 * (random.random()-0.5) + 0.8 * ( (i/30) % 2 )
        chl = 0.3 + 0.1*(random.random())
        m = models.Measurement(sst=round(sst,2), chl=round(chl,3))
        db.add(m)
    db.commit()
    db.close()
    print("Seeded", n, "measurements")

if __name__ == "__main__":
    seed()
