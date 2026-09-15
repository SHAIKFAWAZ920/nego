from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

raw_db_url = settings.DATABASE_URL.strip() if (settings.DATABASE_URL and settings.DATABASE_URL.strip()) else ""
db_url = raw_db_url or "sqlite:///./negotiation.db"

# Handle PostgreSQL connection string prefixes (e.g., Supabase postgres:// -> postgresql://)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# SQLite specific arguments (check_same_thread=False for multi-threaded FastAPI requests)
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

