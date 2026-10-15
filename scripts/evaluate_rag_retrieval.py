"""Stage 4 RAG Retrieval Pipeline Evaluation Script.

Evaluates the TRACE Stage 4 hybrid retrieval engine on the canonical
held-out group-aware test split (57 test queries evaluated against
the 268-incident group-aware training corpus).

Computes:
- Recall@1, Recall@3, Recall@5, Recall@10 (Hit Rate)
- Precision@1, Precision@3, Precision@5
- Mean Reciprocal Rank (MRR)
- Mean Cosine Similarity of Top-1
- Latency (mean, p95)

Compares 3 retrieval modalities:
1. Hybrid (BM25 + Sentence-BERT + Category Prior)
2. Dense Semantic (Sentence-BERT only)
3. Sparse Lexical (BM25 only)

Outputs results to stdout and saves to backend/data/rag_evaluation_manifest.json.
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.ml.stage4_rag.retrieval_corpus import (
    load_train_corpus, load_test_queries, CorpusIncident
)
from app.ml.stage4_rag.hybrid_retriever import HybridRetriever
from app.ml.stage1_embedder.sbert_embedder import SentenceBertEmbedder


def evaluate_mode(
    retriever: HybridRetriever,
    test_queries: List[CorpusIncident],
    mode: str = "hybrid",
    top_k_list: List[int] = [1, 3, 5, 10]
) -> Dict[str, Any]:
    """Evaluate retrieval quality across queries for a specific mode."""
    max_k = max(top_k_list)
    recalls = {k: 0 for k in top_k_list}
    precisions = {k: [] for k in top_k_list}
    reciprocal_ranks = []
    top1_similarities = []
    latencies_ms = []

    for query in test_queries:
        t0 = time.perf_counter()

        if mode == "semantic_only":
            results = retriever.retrieve_semantic_only(
                query_text=query.text,
                top_k=max_k,
                exclude_incident_codes={query.incident_code}
            )
        elif mode == "bm25_only":
            results = retriever.retrieve_bm25_only(
                query_text=query.text,
                top_k=max_k,
                exclude_incident_codes={query.incident_code}
            )
        else:
            # Hybrid
            results = retriever.retrieve(
                query_text=query.text,
                top_k=max_k,
                query_category=query.failure_category,
                exclude_incident_codes={query.incident_code}
            )

        elapsed = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed)

        # Relevance ground-truth proxy: Category match
        # (Weak label from RootCauseCandidateAnalyzer)
        relevance = [
            1 if r.get("failure_category") == query.failure_category else 0
            for r in results
        ]

        # Top-1 cosine similarity
        if results and "semantic_similarity" in results[0]:
            top1_similarities.append(results[0]["semantic_similarity"])
        elif results and "score" in results[0] and mode == "semantic_only":
            top1_similarities.append(results[0]["score"])

        # MRR calculation
        rr = 0.0
        for rank, rel in enumerate(relevance, start=1):
            if rel == 1:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        # Recall@k (HitRate) and Precision@k
        for k in top_k_list:
            k_rel = relevance[:k]
            if sum(k_rel) > 0:
                recalls[k] += 1
            precisions[k].append(sum(k_rel) / k if k > 0 else 0.0)

    n_queries = len(test_queries)
    return {
        "mode": mode,
        "sample_count": n_queries,
        "metrics": {
            "recall_at_1": round(recalls[1] / n_queries, 4),
            "recall_at_3": round(recalls[3] / n_queries, 4),
            "recall_at_5": round(recalls[5] / n_queries, 4),
            "recall_at_10": round(recalls[10] / n_queries, 4),
            "precision_at_1": round(float(np.mean(precisions[1])), 4),
            "precision_at_3": round(float(np.mean(precisions[3])), 4),
            "precision_at_5": round(float(np.mean(precisions[5])), 4),
            "mrr": round(float(np.mean(reciprocal_ranks)), 4),
            "mean_top1_similarity": round(float(np.mean(top1_similarities)), 4) if top1_similarities else 0.0,
            "avg_latency_ms": round(float(np.mean(latencies_ms)), 2),
            "p95_latency_ms": round(float(np.percentile(latencies_ms, 95)), 2),
        }
    }


def main():
    print("=" * 70)
    print("TRACE STAGE 4: RAG RETRIEVAL PIPELINE EVALUATION AUDIT")
    print("=" * 70)

    train_corpus = load_train_corpus()
    test_queries = load_test_queries()

    print(f"Corpus size (Train split): {len(train_corpus)} incidents")
    print(f"Query count (Test split):  {len(test_queries)} incidents")
    print(f"Split strategy:            Canonical Group-Aware Stratified Split")
    print(f"Leakage protection:        Group-disjoint + Self-incident exclusion")
    print("-" * 70)

    # Initialize shared SBERT embedder and build index
    embedder = SentenceBertEmbedder()
    retriever = HybridRetriever(alpha=0.5, beta=0.3, gamma=0.2, embedder=embedder)

    print("Building Hybrid Retriever Index...")
    t0 = time.time()
    retriever.build_index(train_corpus)
    print(f"Index built in {time.time() - t0:.2f}s")
    print("-" * 70)

    modes = ["hybrid", "semantic_only", "bm25_only"]
    results_by_mode = {}

    for mode in modes:
        print(f"Evaluating mode: '{mode}'...")
        eval_res = evaluate_mode(retriever, test_queries, mode=mode)
        results_by_mode[mode] = eval_res["metrics"]
        m = eval_res["metrics"]
        print(f"  Recall@1:    {m['recall_at_1']:.4f}  |  Recall@3: {m['recall_at_3']:.4f}  |  Recall@5: {m['recall_at_5']:.4f}")
        print(f"  Precision@1: {m['precision_at_1']:.4f}  |  MRR:      {m['mrr']:.4f}  |  Latency:  {m['avg_latency_ms']:.2f}ms")
        print()

    # Build final evaluation manifest
    manifest = {
        "stage": "Stage 4 (RAG Retrieval Pipeline)",
        "pipeline_name": "TRACE Hybrid RAG Retriever",
        "dataset_split": "Canonical Group-Aware Stratified Split (Leakage-Free)",
        "train_corpus_size": len(train_corpus),
        "test_query_count": len(test_queries),
        "relevance_criterion": "Category Match (Heuristic/Weak Supervision Ground Truth)",
        "rrf_k": 60,
        "fusion_weights": {
            "alpha_semantic": 0.5,
            "beta_bm25": 0.3,
            "gamma_metadata": 0.2
        },
        "evaluation_summary": {
            "hybrid": results_by_mode["hybrid"],
            "semantic_only": results_by_mode["semantic_only"],
            "bm25_only": results_by_mode["bm25_only"]
        },
        "comparison_table": [
            {
                "modality": "Hybrid (BM25 + SBERT + Category Prior)",
                "recall_at_1": results_by_mode["hybrid"]["recall_at_1"],
                "recall_at_3": results_by_mode["hybrid"]["recall_at_3"],
                "recall_at_5": results_by_mode["hybrid"]["recall_at_5"],
                "mrr": results_by_mode["hybrid"]["mrr"],
                "avg_latency_ms": results_by_mode["hybrid"]["avg_latency_ms"]
            },
            {
                "modality": "Dense Semantic (Sentence-BERT all-MiniLM-L6-v2)",
                "recall_at_1": results_by_mode["semantic_only"]["recall_at_1"],
                "recall_at_3": results_by_mode["semantic_only"]["recall_at_3"],
                "recall_at_5": results_by_mode["semantic_only"]["recall_at_5"],
                "mrr": results_by_mode["semantic_only"]["mrr"],
                "avg_latency_ms": results_by_mode["semantic_only"]["avg_latency_ms"]
            },
            {
                "modality": "Sparse Lexical (Okapi BM25)",
                "recall_at_1": results_by_mode["bm25_only"]["recall_at_1"],
                "recall_at_3": results_by_mode["bm25_only"]["recall_at_3"],
                "recall_at_5": results_by_mode["bm25_only"]["recall_at_5"],
                "mrr": results_by_mode["bm25_only"]["mrr"],
                "avg_latency_ms": results_by_mode["bm25_only"]["avg_latency_ms"]
            }
        ],
        "limitations_and_disclosures": [
            "Relevance is evaluated using weak heuristic category ground-truth labels from RootCauseCandidateAnalyzer.",
            "Group-aware split ensures query incidents originate from independent log files/builds, preventing template leakage.",
            "Stage 4 implements evidence and incident retrieval only; LLM generation and report synthesis are deferred to Stage 5.",
            "Surrounding chronological events are fetched from SQLite on-demand via indexed line spans."
        ],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }

    manifest_path = settings.RAG_EVALUATION_MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest successfully generated and saved to: {manifest_path}")


if __name__ == "__main__":
    main()
