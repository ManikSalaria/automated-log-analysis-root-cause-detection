"""GraphSAGE Neural Network Architecture for TRACE Stage 3.

Implements inductive Graph Sample and Aggregate (GraphSAGE) using
PyTorch Geometric's SAGEConv for multi-class incident root-cause classification.
"""

from typing import Optional, List
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv

class GraphSAGEClassifier(nn.Module):
    """
    Multi-layer GraphSAGE Node Classification Network.
    Aggregates neighborhood structural and semantic representations
    for root-cause failure classification.
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int = 128,
        out_channels: int = 10,
        num_layers: int = 2,
        dropout: float = 0.2,
        aggr: str = "mean"
    ):
        super().__init__()
        self.in_channels = in_channels
        self.hidden_channels = hidden_channels
        self.out_channels = out_channels
        self.num_layers = num_layers
        self.dropout = dropout
        self.aggr = aggr

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()

        if num_layers == 1:
            self.convs.append(SAGEConv(in_channels, hidden_channels, aggr=aggr))
            self.norms.append(nn.LayerNorm(hidden_channels))
        else:
            # Input GraphSAGE layer
            self.convs.append(SAGEConv(in_channels, hidden_channels, aggr=aggr))
            self.norms.append(nn.LayerNorm(hidden_channels))

            # Intermediate GraphSAGE layers
            for _ in range(num_layers - 2):
                self.convs.append(SAGEConv(hidden_channels, hidden_channels, aggr=aggr))
                self.norms.append(nn.LayerNorm(hidden_channels))

            # Final GraphSAGE layer before head
            self.convs.append(SAGEConv(hidden_channels, hidden_channels, aggr=aggr))
            self.norms.append(nn.LayerNorm(hidden_channels))

        # Linear classification head
        self.classifier = nn.Linear(hidden_channels, out_channels)

        self._reset_parameters()

    def _reset_parameters(self):
        for conv in self.convs:
            conv.reset_parameters()
        for norm in self.norms:
            norm.reset_parameters()
        nn.init.xavier_uniform_(self.classifier.weight)
        if self.classifier.bias is not None:
            nn.init.zeros_(self.classifier.bias)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """
        Forward propagation through SAGEConv layers with LayerNorm, ReLU, and Dropout.
        Returns raw class logits of shape (N, out_channels).
        """
        for conv, norm in zip(self.convs, self.norms):
            x = conv(x, edge_index)
            x = norm(x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)

        logits = self.classifier(x)
        return logits

    def predict_proba(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """
        Computes softmax class probability distribution.
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x, edge_index)
            return F.softmax(logits, dim=-1)
