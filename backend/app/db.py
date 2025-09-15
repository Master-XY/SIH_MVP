# backend/app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base


DB_PATH = os.getenv("SIH_DB_PATH", "data/sih.db")
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# DB file path
DB_FILE = os.path.join(os.path.dirname(__file__), "alerts.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_FILE}")

# sqlite needs check_same_thread False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Engine + session
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


