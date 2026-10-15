"""TRACE Stage 5: LLM-Powered Root Cause Explanation and Evidence-Grounded Remediation.

Combines ML classifier outputs (GraphSAGE, XGBoost, TF-IDF/RF), Stage 4 hybrid RAG
retrieval, stable citation grounding (E1..En), and local LLM instruct models
to generate actionable, advisory root-cause reports.
"""

from app.ml.stage5_llm.synthesis_service import execute_synthesis_pipeline
from app.ml.stage5_llm.providers import get_llm_provider
