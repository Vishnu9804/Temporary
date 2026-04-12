from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Create the SQLAlchemy Engine
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# Create a SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for the ORM models
Base = declarative_base()

# Dependency to get the DB session in your routers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()