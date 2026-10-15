"""Incident Graph Dataset Builder for TRACE Stage 3 (GraphSAGE).

Constructs reproducible, leakage-resistant graph datasets from authentic
incident records. Each incident is a node; edges represent distributed trace
correlations, temporal/service co-occurrence, and semantic evidence similarity.
Learned feature preprocessors are strictly fit on the training split only.
"""

import re
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import torch
from torch_geometric.data import Data
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder
from app.core.config import settings
from app.core.security import SecretMasker
from app.parsers.regex_parser import LogParserEngine

class IncidentGraphBuilder:
    """
    Deterministic Graph Builder for Incident Node Classification.
    Constructs node features from Sentence-BERT embeddings + structured log attributes,
    and constructs edges from shared trace IDs, service co-occurrence, and semantic similarity.
    """

    def __init__(
        self,
        semantic_threshold: float = 0.85,
        max_semantic_neighbors: int = 4,
        temporal_window_lines: int = 150
    ):
        self.semantic_threshold = semantic_threshold
        self.max_semantic_neighbors = max_semantic_neighbors
        self.temporal_window_lines = temporal_window_lines

        self.label_encoder = LabelEncoder()
        self.cat_encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
        self.num_scaler = StandardScaler()
        self.is_preprocessor_fitted: bool = False
        self.classes_: List[str] = []
        self.feature_dimension: int = 0

    @staticmethod
    def extract_structured_attributes(row: Union[pd.Series, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract structured operational attributes from an incident row or log text snippet safely.
        Handles missing values, unparsed lines, and sparse metadata.
        """
        text = str(row.get("text") or row.get("evidence_text") or row.get("raw_text") or "")
        source_file = str(row.get("source_file") or "unknown")
        start_line = int(row.get("start_line") or 0)
        end_line = int(row.get("end_line") or start_line)
        line_span = max(1, end_line - start_line + 1)

        # Parse first relevant log line
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        entry = LogParserEngine.parse_line(first_line)

        # Extract attributes from LogEntry or regex fallback
        severity = entry.level or "UNKNOWN"
        service = entry.service or "unknown"
        trace_id = entry.trace_id
        status_code = entry.status_code
        latency_ms = entry.latency_ms

        # Fallback regex extraction if LogParserEngine left them None
        if not trace_id:
            m_trace = re.search(r"\b(?:trace_id|trace)=([^\s,]+)", text)
            if m_trace:
                trace_id = m_trace.group(1)
        if not trace_id:
            m_req = re.search(r"\brequest_id=([^\s,]+)", text)
            if m_req:
                trace_id = m_req.group(1)

        if status_code is None:
            m_stat = re.search(r"\bstatus(?:_code)?=(\d{3})\b", text)
            if m_stat:
                status_code = int(m_stat.group(1))

        if latency_ms is None:
            m_lat = re.search(r"\blatency_ms=(\d+(?:\.\d+)?)\b", text)
            if m_lat:
                latency_ms = float(m_lat.group(1))

        # Normalize service
        if service.startswith("[") and service.endswith("]"):
            service = service[1:-1]

        return {
            "source_file": source_file,
            "start_line": start_line,
            "end_line": end_line,
            "line_span": line_span,
            "severity": severity,
            "service": service,
            "status_code": str(status_code) if status_code else "none",
            "latency_ms": float(latency_ms) if latency_ms is not None else 0.0,
            "trace_id": trace_id
        }

    def fit_preprocessor(self, train_df: pd.DataFrame) -> None:
        """
        Fit the structured categorical and numerical encoders strictly on training data.
        Zero test or validation distribution information is leaked into the preprocessor.
        """
        cat_data = []
        num_data = []

        for _, row in train_df.iterrows():
            attr = self.extract_structured_attributes(row)
            cat_data.append([attr["severity"], attr["service"], attr["status_code"]])
            num_data.append([
                np.log1p(max(0.0, attr["latency_ms"])),
                np.log1p(max(1.0, float(attr["line_span"])))
            ])

        self.cat_encoder.fit(cat_data)
        self.num_scaler.fit(num_data)

        if "failure_category" in train_df.columns:
            self.label_encoder.fit(train_df["failure_category"].astype(str))
            self.classes_ = [str(c) for c in self.label_encoder.classes_]

        self.is_preprocessor_fitted = True

    def transform_structured_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform tabular metadata into scaled, one-hot continuous features.
        """
        if not self.is_preprocessor_fitted:
            raise RuntimeError("Preprocessor must be fit on training data before transform.")

        cat_data = []
        num_data = []

        for _, row in df.iterrows():
            attr = self.extract_structured_attributes(row)
            cat_data.append([attr["severity"], attr["service"], attr["status_code"]])
            num_data.append([
                np.log1p(max(0.0, attr["latency_ms"])),
                np.log1p(max(1.0, float(attr["line_span"])))
            ])

        cat_feat = self.cat_encoder.transform(cat_data)
        num_feat = self.num_scaler.transform(num_data)
        return np.hstack([cat_feat, num_feat]).astype(np.float32)

    def build_node_features(
        self,
        df: pd.DataFrame,
        embeddings: np.ndarray
    ) -> torch.Tensor:
        """
        Combine 384-D dense Sentence-BERT embeddings with tabular structured features.
        Returns a float32 PyTorch tensor of shape (N, 384 + D_struct).
        """
        struct_feat = self.transform_structured_features(df)
        combined = np.hstack([embeddings, struct_feat]).astype(np.float32)
        self.feature_dimension = combined.shape[1]
        return torch.tensor(combined, dtype=torch.float32)

    def build_edges(
        self,
        df: pd.DataFrame,
        embeddings: np.ndarray,
        train_only_indices: Optional[set] = None
    ) -> torch.Tensor:
        """
        Construct meaningful, multi-relational edges without fabricating relationships:
        1. Shared trace/request identifier (direct distributed transaction causality).
        2. Service + temporal proximity within the same build/source file.
        3. High cosine semantic similarity (top-k neighbors with similarity >= threshold).
        4. Self-loops (ensures ego-feature retention).

        If train_only_indices is provided, only connects edges where both nodes are in the set.
        """
        n = len(df)
        edges = set()

        # Always add self-loops
        for i in range(n):
            if train_only_indices is None or i in train_only_indices:
                edges.add((i, i))

        # Extract operational attributes for all nodes
        attrs = [self.extract_structured_attributes(df.iloc[i]) for i in range(n)]

        # 1. Distributed Trace / Request Correlation
        trace_map: Dict[str, List[int]] = {}
        for i, a in enumerate(attrs):
            tid = a["trace_id"]
            if tid:
                trace_map.setdefault(tid, []).append(i)

        for tid, node_ids in trace_map.items():
            if len(node_ids) > 1:
                for idx_a in range(len(node_ids)):
                    for idx_b in range(idx_a + 1, len(node_ids)):
                        u, v = node_ids[idx_a], node_ids[idx_b]
                        if train_only_indices is None or (u in train_only_indices and v in train_only_indices):
                            edges.add((u, v))
                            edges.add((v, u))

        # 2. Service & Temporal Co-occurrence (same file, same service, start line delta <= window)
        for i in range(n):
            for j in range(i + 1, n):
                if train_only_indices and (i not in train_only_indices or j not in train_only_indices):
                    continue
                a_i, a_j = attrs[i], attrs[j]
                if (a_i["source_file"] != "unknown" and 
                    a_i["source_file"] == a_j["source_file"] and
                    a_i["service"] != "unknown" and
                    a_i["service"] == a_j["service"] and
                    abs(a_i["start_line"] - a_j["start_line"]) <= self.temporal_window_lines):
                    edges.add((i, j))
                    edges.add((j, i))

        # 3. Semantic Evidence Cosine Similarity
        # Normalize embeddings to unit vectors
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized_emb = embeddings / norms
        sim_matrix = np.dot(normalized_emb, normalized_emb.T)

        for i in range(n):
            if train_only_indices and i not in train_only_indices:
                continue
            sims = sim_matrix[i].copy()
            sims[i] = -1.0  # mask self
            eligible = np.where(sims >= self.semantic_threshold)[0]
            if len(eligible) > 0:
                # Select top-k highest similarity neighbors
                top_k = eligible[np.argsort(sims[eligible])[::-1][:self.max_semantic_neighbors]]
                for j in top_k:
                    if train_only_indices is None or j in train_only_indices:
                        edges.add((i, int(j)))
                        edges.add((int(j), i))

        if not edges:
            # Fallback self-loops
            for i in range(n):
                edges.add((i, i))

        edge_list = sorted(list(edges))
        src = [e[0] for e in edge_list]
        dst = [e[1] for e in edge_list]
        return torch.tensor([src, dst], dtype=torch.long)

    def build_dataset(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        test_df: pd.DataFrame,
        embedder: Any
    ) -> Tuple[Data, Dict[str, Any]]:
        """
        Build a complete, leakage-resistant PyG Data object with train_mask, val_mask, and test_mask.
        Learned preprocessors are strictly fit on train_df only.
        """
        # 1. Fit preprocessor on training data only
        self.fit_preprocessor(train_df)

        # 2. Extract S-BERT embeddings
        all_df = pd.concat([train_df, val_df, test_df], ignore_index=True)
        texts = all_df["text"].tolist()

        if hasattr(embedder, "encode"):
            embeddings = embedder.encode(texts, batch_size=32, normalize_embeddings=True)
        else:
            # Mock or callable embedder for tests
            embeddings = embedder(texts)

        # 3. Construct Node Features
        x = self.build_node_features(all_df, embeddings)

        # 4. Construct Edges
        edge_index = self.build_edges(all_df, embeddings)

        # 5. Encode Labels
        y_str = all_df["failure_category"].astype(str).tolist()
        y = torch.tensor(self.label_encoder.transform(y_str), dtype=torch.long)

        # 6. Create Masks
        n_train = len(train_df)
        n_val = len(val_df)
        n_test = len(test_df)
        n_total = len(all_df)

        train_mask = torch.zeros(n_total, dtype=torch.bool)
        val_mask = torch.zeros(n_total, dtype=torch.bool)
        test_mask = torch.zeros(n_total, dtype=torch.bool)

        train_mask[:n_train] = True
        val_mask[n_train:n_train + n_val] = True
        test_mask[n_train + n_val:] = True

        data = Data(
            x=x,
            edge_index=edge_index,
            y=y,
            train_mask=train_mask,
            val_mask=val_mask,
            test_mask=test_mask
        )

        metadata = {
            "num_nodes": n_total,
            "num_edges": edge_index.shape[1],
            "feature_dim": x.shape[1],
            "num_classes": len(self.classes_),
            "classes": self.classes_,
            "train_count": n_train,
            "val_count": n_val,
            "test_count": n_test
        }

        return data, metadata
