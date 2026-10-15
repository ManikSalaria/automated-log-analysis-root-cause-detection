"""TRACE Stage 3 GraphSAGE Pipeline and Model Manager.

Integrates graph dataset construction, PyG GraphSAGE neural network training,
leakage-resistant evaluation, checkpoint serialization, and live inductive inference.
"""

import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import Data
import joblib
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support, confusion_matrix
)
from sklearn.utils.class_weight import compute_class_weight

from app.core.config import settings
from app.core.security import SecretMasker
from app.ml.stage1_embedder.sbert_embedder import SentenceBertEmbedder
from app.ml.stage3_gnn.graph_builder import IncidentGraphBuilder
from app.ml.stage3_gnn.sage_model import GraphSAGEClassifier

class TraceGraphSAGEPipeline:
    """
    End-to-end GraphSAGE pipeline for Stage 3 incident root-cause classification.
    Supports transductive/inductive graph training and live single-incident inference.
    """

    def __init__(
        self,
        hidden_channels: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
        lr: float = 0.005,
        weight_decay: float = 1e-4,
        epochs: int = 150,
        aggr: str = "mean",
        semantic_threshold: float = 0.85,
        random_state: int = 42
    ):
        self.hidden_channels = hidden_channels
        self.num_layers = num_layers
        self.dropout = dropout
        self.lr = lr
        self.weight_decay = weight_decay
        self.epochs = epochs
        self.aggr = aggr
        self.semantic_threshold = semantic_threshold
        self.random_state = random_state

        self.embedder = SentenceBertEmbedder()
        self.graph_builder = IncidentGraphBuilder(semantic_threshold=semantic_threshold)
        self.model: Optional[GraphSAGEClassifier] = None
        self.is_trained: bool = False
        self.classes_: List[str] = []
        self.feature_dimension: int = 0

        # Reference training memory for inductive neighborhood aggregation during single-item inference
        self.ref_embeddings: Optional[np.ndarray] = None
        self.ref_features: Optional[np.ndarray] = None
        self.ref_labels: Optional[List[str]] = None

    def _set_seeds(self):
        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(self.random_state)

    def train(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Train the GraphSAGE model using PyTorch Geometric SAGEConv.
        Learned preprocessors and edge constructions are leakage-free.
        """
        self._set_seeds()
        start_time = time.perf_counter()

        if len(train_df) == 0:
            raise ValueError("Training dataset cannot be empty.")

        # Ensure embedder is loaded
        if not self.embedder.is_loaded:
            self.embedder.load()

        # If test_df not provided, use an empty DataFrame
        if test_df is None:
            test_df = pd.DataFrame(columns=train_df.columns)

        # 1. Build Graph Dataset
        data, metadata = self.graph_builder.build_dataset(
            train_df=train_df,
            val_df=val_df,
            test_df=test_df,
            embedder=self.embedder
        )

        self.feature_dimension = data.x.shape[1]
        self.classes_ = metadata["classes"]
        num_classes = len(self.classes_)

        # 2. Store training reference bank for inductive runtime inference
        train_count = len(train_df)
        self.ref_embeddings = self.embedder.encode(train_df["text"].tolist(), batch_size=32, normalize_embeddings=True)
        self.ref_features = data.x[:train_count].detach().cpu().numpy()
        self.ref_labels = train_df["failure_category"].astype(str).tolist()

        # 3. Instantiate GraphSAGE Network
        self.model = GraphSAGEClassifier(
            in_channels=self.feature_dimension,
            hidden_channels=self.hidden_channels,
            out_channels=num_classes,
            num_layers=self.num_layers,
            dropout=self.dropout,
            aggr=self.aggr
        )

        # Compute balanced class weights for training nodes to address category imbalance
        y_train_np = data.y[data.train_mask].cpu().numpy()
        unique_classes = np.unique(y_train_np)
        weights_arr = compute_class_weight("balanced", classes=unique_classes, y=y_train_np)
        
        weight_tensor = torch.ones(num_classes, dtype=torch.float32)
        for cls_idx, w in zip(unique_classes, weights_arr):
            weight_tensor[cls_idx] = float(w)

        criterion = nn.CrossEntropyLoss(weight=weight_tensor)
        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.lr,
            weight_decay=self.weight_decay
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="max", patience=15, factor=0.5
        )

        best_val_f1 = -1.0
        best_state_dict = None
        best_epoch = 0

        # 4. Training Loop
        for epoch in range(1, self.epochs + 1):
            self.model.train()
            optimizer.zero_grad()

            logits = self.model(data.x, data.edge_index)
            loss = criterion(logits[data.train_mask], data.y[data.train_mask])
            loss.backward()
            optimizer.step()

            # Validation step
            self.model.eval()
            with torch.no_grad():
                val_logits = self.model(data.x, data.edge_index)
                val_preds = val_logits[data.val_mask].argmax(dim=-1).cpu().numpy()
                val_true = data.y[data.val_mask].cpu().numpy()

                val_acc = accuracy_score(val_true, val_preds) if len(val_true) > 0 else 0.0
                val_f1 = precision_recall_fscore_support(
                    val_true, val_preds, average="macro", zero_division=0
                )[2] if len(val_true) > 0 else 0.0

            scheduler.step(val_f1)

            if val_f1 > best_val_f1 or best_state_dict is None:
                best_val_f1 = val_f1
                best_epoch = epoch
                best_state_dict = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}

        # Load best checkpoint
        if best_state_dict is not None:
            self.model.load_state_dict(best_state_dict)

        self.is_trained = True
        train_time = time.perf_counter() - start_time

        return {
            "training_time_sec": round(train_time, 3),
            "epochs_run": self.epochs,
            "best_epoch": best_epoch,
            "best_val_f1": round(best_val_f1 * 100, 2),
            "feature_dimension": self.feature_dimension,
            "num_nodes": data.num_nodes,
            "num_edges": data.edge_index.shape[1],
            "classes_count": len(self.classes_),
            "classes": self.classes_
        }

    def evaluate_graph(self, data: Data, mask: torch.Tensor) -> Dict[str, Any]:
        """
        Evaluate GraphSAGE on a specified partition mask (e.g. data.test_mask).
        Computes accuracy, macro-F1, weighted-F1, per-class breakdown, and confusion matrix.
        """
        if not self.is_trained or self.model is None:
            raise RuntimeError("Model must be trained before evaluation.")

        self.model.eval()
        with torch.no_grad():
            logits = self.model(data.x, data.edge_index)
            probs = F.softmax(logits, dim=-1)

            subset_probs = probs[mask].cpu().numpy()
            subset_preds = logits[mask].argmax(dim=-1).cpu().numpy()
            subset_true = data.y[mask].cpu().numpy()

        acc = float(accuracy_score(subset_true, subset_preds))
        p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
            subset_true, subset_preds, average="macro", zero_division=0
        )
        p_weighted, r_weighted, f1_weighted, _ = precision_recall_fscore_support(
            subset_true, subset_preds, average="weighted", zero_division=0
        )

        # Per-class breakdown
        per_class = {}
        for idx, cls_name in enumerate(self.classes_):
            cls_mask = (subset_true == idx)
            cls_support = int(np.sum(cls_mask))
            if cls_support > 0:
                cls_p, cls_r, cls_f1, _ = precision_recall_fscore_support(
                    subset_true == idx, subset_preds == idx, average="binary", zero_division=0
                )
                per_class[cls_name] = {
                    "precision": round(float(cls_p) * 100, 2),
                    "recall": round(float(cls_r) * 100, 2),
                    "f1": round(float(cls_f1) * 100, 2),
                    "support": cls_support
                }
            else:
                per_class[cls_name] = {
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1": 0.0,
                    "support": 0
                }

        conf_mat = confusion_matrix(subset_true, subset_preds, labels=list(range(len(self.classes_))))

        return {
            "accuracy": round(acc * 100, 2),
            "precision_macro": round(float(p_macro) * 100, 2),
            "recall_macro": round(float(r_macro) * 100, 2),
            "f1_macro": round(float(f1_macro) * 100, 2),
            "f1_weighted": round(float(f1_weighted) * 100, 2),
            "sample_count": len(subset_true),
            "classes": self.classes_,
            "per_class_metrics": per_class,
            "confusion_matrix": conf_mat.tolist()
        }

    def predict(self, text: str) -> Dict[str, Any]:
        """
        Perform live inductive inference on a single log string or failure block.
        Extracts Sentence-BERT embeddings, transforms structured attributes, constructs
        an inference ego-subgraph using reference training neighbors, and returns predictions.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty or whitespace.")

        if not self.is_trained or self.model is None:
            if not self.load():
                raise RuntimeError("TRACE GraphSAGE model is not loaded. Train the model first.")

        start_time = time.perf_counter()

        # 1. Privacy Sanitization
        sanitized = SecretMasker.sanitize(text, mask_ips=True, normalize_identifiers=True)

        # 2. Extract Sentence-BERT dense representation
        if not self.embedder.is_loaded:
            self.embedder.load()

        query_emb = self.embedder.encode(sanitized, normalize_embeddings=True)  # (384,)

        # 3. Extract and scale structured metadata
        dummy_row = {"text": sanitized}
        query_struct = self.graph_builder.transform_structured_features(pd.DataFrame([dummy_row]))[0]  # (D_struct,)
        query_x = np.concatenate([query_emb, query_struct]).astype(np.float32)  # (D_in,)

        # 4. Inductive Neighborhood Construction
        neighbor_info = []
        if self.ref_embeddings is not None and len(self.ref_embeddings) > 0:
            # Pairwise cosine similarity with training incident reference bank
            norms = np.linalg.norm(self.ref_embeddings, axis=1)
            norms[norms == 0] = 1.0
            q_norm = np.linalg.norm(query_emb)
            q_norm = 1.0 if q_norm == 0 else q_norm

            sims = np.dot(self.ref_embeddings, query_emb) / (norms * q_norm)
            eligible_idx = np.where(sims >= self.semantic_threshold)[0]

            if len(eligible_idx) > 0:
                top_k = eligible_idx[np.argsort(sims[eligible_idx])[::-1][:self.graph_builder.max_semantic_neighbors]]
                # Subgraph: node 0 is query, nodes 1..K are reference training neighbors
                sub_features = [query_x]
                edges_list = [(0, 0)]  # self loop for query

                for new_idx, orig_ref_idx in enumerate(top_k, 1):
                    sub_features.append(self.ref_features[orig_ref_idx])
                    edges_list.append((new_idx, new_idx))  # self loop for neighbor
                    edges_list.append((0, new_idx))        # query -> neighbor
                    edges_list.append((new_idx, 0))        # neighbor -> query
                    if self.ref_labels:
                        neighbor_info.append({
                            "neighbor_id": int(orig_ref_idx),
                            "similarity": round(float(sims[orig_ref_idx]), 4),
                            "historical_category": self.ref_labels[orig_ref_idx]
                        })

                sub_x = torch.tensor(np.array(sub_features), dtype=torch.float32)
                src = [e[0] for e in edges_list]
                dst = [e[1] for e in edges_list]
                sub_edge_index = torch.tensor([src, dst], dtype=torch.long)
            else:
                # Standalone node with self-loop
                sub_x = torch.tensor(np.array([query_x]), dtype=torch.float32)
                sub_edge_index = torch.tensor([[0], [0]], dtype=torch.long)
        else:
            sub_x = torch.tensor(np.array([query_x]), dtype=torch.float32)
            sub_edge_index = torch.tensor([[0], [0]], dtype=torch.long)

        # 5. Forward propagation
        self.model.eval()
        with torch.no_grad():
            probs = self.model.predict_proba(sub_x, sub_edge_index)
            query_probs = probs[0].cpu().numpy()

        pred_idx = int(np.argmax(query_probs))
        pred_category = self.classes_[pred_idx]
        confidence = float(query_probs[pred_idx])

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        top_indices = np.argsort(query_probs)[::-1][:4]
        top_probs = {
            self.classes_[idx]: round(float(query_probs[idx]), 4)
            for idx in top_indices
        }

        rationale = (
            f"Predicted by 2-layer GraphSAGE (SAGEConv mean aggregation) over "
            f"{self.feature_dimension}-D hybrid features (384-D S-BERT + structured attributes) "
            f"with {len(neighbor_info)} historical incident neighbor(s) aggregated."
        )

        return {
            "model_name": "TRACE Stage 3 (GraphSAGE)",
            "predicted_category": pred_category,
            "confidence": round(confidence, 4),
            "latency_ms": round(latency_ms, 2),
            "feature_dimension": self.feature_dimension,
            "top_probabilities": top_probs,
            "rationale": rationale,
            "graph_neighbors_aggregated": len(neighbor_info),
            "neighbor_evidence": neighbor_info
        }

    def save(
        self,
        model_path: Optional[Path] = None,
        preprocessor_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None
    ) -> None:
        """Persist model weights, preprocessor artifacts, and training configuration."""
        if not self.is_trained or self.model is None:
            raise RuntimeError("Cannot save an unfitted GraphSAGE model.")

        m_path = model_path or settings.GRAPHSAGE_MODEL_PATH
        p_path = preprocessor_path or settings.GRAPHSAGE_PREPROCESSOR_PATH
        man_path = manifest_path or settings.GRAPHSAGE_MANIFEST_PATH

        m_path.parent.mkdir(parents=True, exist_ok=True)

        # Save PyTorch model state dict
        torch.save({
            "model_state_dict": self.model.state_dict(),
            "in_channels": self.feature_dimension,
            "hidden_channels": self.hidden_channels,
            "out_channels": len(self.classes_),
            "num_layers": self.num_layers,
            "dropout": self.dropout,
            "aggr": self.aggr,
            "classes": self.classes_
        }, m_path)

        # Save preprocessor and reference bank
        preprocessor_bundle = {
            "cat_encoder": self.graph_builder.cat_encoder,
            "num_scaler": self.graph_builder.num_scaler,
            "label_encoder": self.graph_builder.label_encoder,
            "classes": self.classes_,
            "feature_dimension": self.feature_dimension,
            "ref_embeddings": self.ref_embeddings,
            "ref_features": self.ref_features,
            "ref_labels": self.ref_labels
        }
        joblib.dump(preprocessor_bundle, p_path)

        manifest = {
            "model_name": "TRACE Stage 3 (GraphSAGE)",
            "architecture": "GraphSAGE (SAGEConv)",
            "aggregation": self.aggr,
            "num_layers": self.num_layers,
            "hidden_channels": self.hidden_channels,
            "feature_dimension": self.feature_dimension,
            "classes": self.classes_,
            "dropout": self.dropout,
            "learning_rate": self.lr,
            "weight_decay": self.weight_decay,
            "epochs": self.epochs,
            "random_state": self.random_state
        }
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def load(
        self,
        model_path: Optional[Path] = None,
        preprocessor_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None
    ) -> bool:
        """Load persisted GraphSAGE model and preprocessor artifacts from disk."""
        m_path = model_path or settings.GRAPHSAGE_MODEL_PATH
        p_path = preprocessor_path or settings.GRAPHSAGE_PREPROCESSOR_PATH
        man_path = manifest_path or settings.GRAPHSAGE_MANIFEST_PATH

        if not (m_path.exists() and p_path.exists()):
            self.is_trained = False
            return False

        try:
            # Load preprocessor bundle
            bundle = joblib.load(p_path)
            self.graph_builder.cat_encoder = bundle["cat_encoder"]
            self.graph_builder.num_scaler = bundle["num_scaler"]
            self.graph_builder.label_encoder = bundle["label_encoder"]
            self.graph_builder.is_preprocessor_fitted = True
            self.classes_ = bundle["classes"]
            self.feature_dimension = bundle["feature_dimension"]
            self.ref_embeddings = bundle.get("ref_embeddings")
            self.ref_features = bundle.get("ref_features")
            self.ref_labels = bundle.get("ref_labels")

            # Load PyTorch model checkpoint
            checkpoint = torch.load(m_path, map_location="cpu")
            self.model = GraphSAGEClassifier(
                in_channels=checkpoint["in_channels"],
                hidden_channels=checkpoint["hidden_channels"],
                out_channels=checkpoint["out_channels"],
                num_layers=checkpoint["num_layers"],
                dropout=checkpoint.get("dropout", self.dropout),
                aggr=checkpoint.get("aggr", self.aggr)
            )
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.eval()

            if not self.embedder.is_loaded:
                self.embedder.load()

            self.is_trained = True
            return True
        except Exception:
            self.is_trained = False
            return False
