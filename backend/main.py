from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_database
from app.api.v1.api import api_router

# Initialize SQLite database schema
init_database()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Automated Log Analysis and Root Cause Detection System using Machine Learning (Review-1 Academic Milestone, Dept. of ISE, NIE Mysore)",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for React frontend (port 3000 / 5173 / localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Review-1 API endpoints under /api/v1
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "milestone": "Review 1 Academic Baseline",
        "institution": "The National Institute of Engineering, Mysore — Dept of ISE",
        "batch": "B9",
        "active_model": "Academic Baseline (TF-IDF + Random Forest)",
        "docs_url": "/docs",
        "health_check": f"{settings.API_V1_STR}/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
