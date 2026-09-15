from pathlib import Path
from pydantic import BaseModel

class Settings(BaseModel):
    PROJECT_NAME: str = "TRACE — AI-Powered CI/CD Log Intelligence Platform"
    PROJECT_VERSION: str = "1.0.0-REVIEW1"
    API_V1_STR: str = "/api/v1"
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DATA_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
    MODELS_CACHE_DIR: Path = DATA_DIR / "models_cache"
    SQLITE_DB_PATH: Path = DATA_DIR / "trace_review1.db"

    # ML Configuration
    BASELINE_MODEL_PATH: Path = MODELS_CACHE_DIR / "baseline_rf.joblib"
    BASELINE_VECTORIZER_PATH: Path = MODELS_CACHE_DIR / "baseline_tfidf.joblib"
    
    # Categories genuinely present and supported in authentic corpus
    FAILURE_CATEGORIES: list[str] = [
        "STORAGE_AND_IO_ERROR",
        "DATABASE_AND_CACHE_TIMEOUT",
        "NETWORK_DEPENDENCY_FAILURE",
        "MESSAGE_BROKER_FAILURE",
        "RESOURCE_EXHAUSTION_CRASH",
        "AUTHENTICATION_SECURITY_ERROR",
        "TEST_ASSERTION_FAILURE",
        "PLUGIN_DESCRIPTOR_RESOLUTION_ERROR",
        "INTERNAL_APPLICATION_LOGIC_ERROR",
        "ENVIRONMENT_AND_PIPELINE_ERROR"
    ]

settings = Settings()

# Ensure directories exist
settings.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
