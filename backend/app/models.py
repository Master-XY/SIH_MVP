# backend/app/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text , Boolean
from sqlalchemy import Table, ForeignKey
from sqlalchemy.sql import func
from .db import Base

class Occurrence(Base):
    __tablename__ = "occurrences"
    id = Column(Integer, primary_key=True, index=True)
    occurrenceID = Column(String, index=True)
    scientificName = Column(String, index=True)
    eventDate = Column(String)
    decimalLatitude = Column(Float)
    decimalLongitude = Column(Float)
    datasetID = Column(String)
    provenance = Column(JSON)
    qc_flag = Column(String, default="ok")
    raw = Column(JSON, default={})

class OtolithFeedback(Base):
    __tablename__ = "otolith_feedback"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    corrected_species = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Subscriber(Base):
    __tablename__ = "subscribers"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=False)
    email = Column(String, unique=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)
    status = Column(String)
    message = Column(Text)
    lat = Column(Float)
    lon = Column(Float)
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # NEW FIELDS
    sst = Column(Float, nullable=True)
    chl = Column(Float, nullable=True)
    notified = Column(Boolean, default=False)

