from fastapi import APIRouter
from app.api.v1.endpoints import (
    ingestion, analysis, classification, 
    incidents, metrics, events, health
)

api_router = APIRouter()
api_router.include_router(ingestion.router, prefix="/ingest", tags=["Log Ingestion"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Incident & Root Cause Analysis"])
api_router.include_router(classification.router, prefix="/classification", tags=["Baseline Classification"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["Incidents Registry"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["Dynamic Evaluation Metrics"])
api_router.include_router(events.router, prefix="/events", tags=["Structured Events"])
api_router.include_router(health.router, prefix="", tags=["Health & Status"])
