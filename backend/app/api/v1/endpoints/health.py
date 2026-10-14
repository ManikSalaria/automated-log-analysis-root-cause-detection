from datetime import datetime
from fastapi import APIRouter
from app.core.config import settings
from app.core.database import get_connection
from app.ml.baseline.tfidf_rf import BaselineTfidfRandomForest

router = APIRouter()
baseline_model = BaselineTfidfRandomForest()

@router.get("/health")
def get_system_health():
    """
    Returns live system status, SQLite database stats, and model status.
    """
    model_loaded = baseline_model.load()
    
    db_stats = {
        "connected": False,
        "source_files_count": 0,
        "parsed_events_count": 0,
        "incidents_count": 0,
        "jenkins_builds_count": 0
    }

    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM source_files;")
        db_stats["source_files_count"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM parsed_events;")
        db_stats["parsed_events_count"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM incidents;")
        db_stats["incidents_count"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM jenkins_builds;")
        db_stats["jenkins_builds_count"] = c.fetchone()[0]
        db_stats["connected"] = True
        conn.close()
    except Exception:
        db_stats["connected"] = False

    return {
        "status": "HEALTHY" if db_stats["connected"] and model_loaded else "DEGRADED",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "active_model": {
            "name": "Academic Baseline (TF-IDF + Random Forest)",
            "loaded": model_loaded,
            "feature_dimension": len(baseline_model.vectorizer.vocabulary_) if model_loaded else 0,
            "classes_count": len(baseline_model.classes_) if model_loaded else 0
        },
        "database": db_stats
    }
