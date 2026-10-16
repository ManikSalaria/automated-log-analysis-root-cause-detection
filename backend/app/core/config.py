import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Automatically load .env from project root or backend directory
_root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
_backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env)
elif _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env)
else:
    load_dotenv()

class Settings(BaseModel):
    PROJECT_NAME: str = "TRACE — AI-Powered CI/CD Log Intelligence Platform"
    PROJECT_VERSION: str = "1.0.0-REVIEW1"
    API_V1_STR: str = "/api/v1"
    ALLOW_RAW_LOG_RETENTION: bool = os.getenv("TRACE_ALLOW_RAW_LOG_RETENTION", "false").lower() in ("true", "1", "yes")
    
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
    XGBOOST_MODEL_PATH: Path = MODELS_CACHE_DIR / "xgboost_classifier.joblib"
    XGBOOST_ENCODER_PATH: Path = MODELS_CACHE_DIR / "xgboost_label_encoder.joblib"
    XGBOOST_MANIFEST_PATH: Path = MODELS_CACHE_DIR / "xgboost_manifest.json"
    GRAPHSAGE_MODEL_PATH: Path = MODELS_CACHE_DIR / "graphsage_model.pt"
    GRAPHSAGE_PREPROCESSOR_PATH: Path = MODELS_CACHE_DIR / "graphsage_preprocessor.joblib"
    GRAPHSAGE_MANIFEST_PATH: Path = MODELS_CACHE_DIR / "graphsage_manifest.json"
    GRAPHSAGE_EVALUATION_PATH: Path = DATA_DIR / "graphsage_evaluation_manifest.json"
    SBERT_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # Stage 4: RAG Retrieval Pipeline
    RAG_CACHE_DIR: Path = MODELS_CACHE_DIR / "rag"
    RAG_CORPUS_EMBEDDINGS_PATH: Path = MODELS_CACHE_DIR / "rag" / "corpus_embeddings.npy"
    RAG_CORPUS_METADATA_PATH: Path = MODELS_CACHE_DIR / "rag" / "corpus_metadata.json"
    RAG_BM25_INDEX_PATH: Path = MODELS_CACHE_DIR / "rag" / "bm25_index.joblib"
    RAG_EVALUATION_MANIFEST_PATH: Path = DATA_DIR / "rag_evaluation_manifest.json"

    # Stage 5: LLM-Powered Root Cause Explanation & Evidence-Grounded Remediation
    TRACE_LLM_PROVIDER: str = os.getenv("TRACE_LLM_PROVIDER", "ollama")
    TRACE_OLLAMA_BASE_URL: str = os.getenv("TRACE_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    TRACE_OLLAMA_MODEL: str = os.getenv("TRACE_OLLAMA_MODEL", "llama3.2:3b")
    TRACE_LLM_TIMEOUT_SEC: float = float(os.getenv("TRACE_LLM_TIMEOUT_SEC", "90.0"))
    TRACE_LLM_MAX_RETRIES: int = int(os.getenv("TRACE_LLM_MAX_RETRIES", "2"))
    TRACE_LLM_MAX_CONTEXT_CHARS: int = int(os.getenv("TRACE_LLM_MAX_CONTEXT_CHARS", "8000"))
    
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
settings.RAG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
