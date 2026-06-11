import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Resolve the project root (Prueba) and place the SQLite DB there
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(BASE_DIR, 'plc_logs.db')

engine = create_engine(f'sqlite:///{DB_PATH}', echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

class CommandLog(Base):
    __tablename__ = "command_log"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    command_type = Column(String, nullable=False)  # e.g., piston1, motor_speed
    sent_value = Column(String, nullable=False)   # store as string for flexibility
    verified_value = Column(String, nullable=True)
    status = Column(String, nullable=False)       # SUCCESS or FAIL
    # New fields for detection events
    category = Column(String, nullable=True)
    confidence = Column(String, nullable=True)

class CameraSettings(Base):
    __tablename__ = "camera_settings"
    id = Column(Integer, primary_key=True, index=True)
    initial_delay = Column(String, default="5.0")  # seconds before turning motor back on
    motor_off_duration = Column(String, default="5.0")
    cat1_duration = Column(String, default="2.0")
    cat2_duration = Column(String, default="3.0")
    cat3_duration = Column(String, default="0.0")
    auto_execute = Column(String, default="1")  # 1=True, 0=False
def init_db():
    """Create tables if they do not exist."""
    Base.metadata.create_all(bind=engine)

from contextlib import contextmanager

@contextmanager
def get_db():
    """Dependency generator for a DB session – callers must close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
