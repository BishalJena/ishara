"""Minimal port of the AI4Bharat INCLUDE keypoint transformer for inference.

Vendored from https://github.com/AI4Bharat/INCLUDE (MIT) at revision
df348f4a640060d4d39f02556d9f96851e8c46c7 so that inference does not depend on
xgboost/timm. Architecture, config values and the pretrained state dict keys are
unchanged. One deliberate difference: the upstream forward applies
``F.dropout(p=0.2)`` unconditionally, which randomises predictions even in eval
mode; here it is only applied while training.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import transformers

INPUT_SIZE = 134  # 25 pose + 21 + 21 hand landmarks, x and y each
MAX_FRAMES = 169  # evaluate.py pads/truncates every clip to this length
N_CLASSES = 263
FRAME_W, FRAME_H = 1920, 1080  # training clips were scaled to pixel coords of this size

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
CHECKPOINTS = {
    "large": ("include_no_cnn_transformer_large.pth",
              "https://api.wandb.ai/files/abdur-ai4bharat/include-no-cnn/1nywb73r/augs_transformer.pth"),
    "small": ("include_no_cnn_transformer_small.pth",
              "https://api.wandb.ai/files/abdur-ai4bharat/include-no-cnn/2kuznb3t/augs_transformer.pth"),
}
LABEL_MAP = ARTIFACTS / "INCLUDE" / "label_maps" / "label_map_include.json"


class _Config:
    def __init__(self, size: str):
        assert size in ("small", "large")
        self.input_size = INPUT_SIZE
        self.max_position_embeddings = 256
        self.layer_norm_eps = 1e-12
        self.hidden_dropout_prob = 0.1
        self.hidden_size, self.num_attention_heads, self.num_hidden_layers = (
            (512, 8, 4) if size == "large" else (256, 4, 2)
        )
        self.model_config = transformers.BertConfig(
            hidden_size=self.hidden_size,
            num_attention_heads=self.num_attention_heads,
            num_hidden_layers=self.num_hidden_layers,
            max_position_embeddings=self.max_position_embeddings,
            attn_implementation="eager",
        )


class PositionEmbedding(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.position_embeddings = nn.Embedding(config.max_position_embeddings, config.hidden_size)
        self.LayerNorm = nn.LayerNorm(config.hidden_size, eps=config.layer_norm_eps)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.register_buffer("position_ids", torch.arange(config.max_position_embeddings).expand((1, -1)))

    def forward(self, x):
        pos = self.position_embeddings(self.position_ids[:, : x.size(1)])
        return self.dropout(self.LayerNorm(x + pos))


class Transformer(nn.Module):
    def __init__(self, config, n_classes=N_CLASSES):
        super().__init__()
        self.l1 = nn.Linear(config.input_size, config.hidden_size)
        self.embedding = PositionEmbedding(config)
        self.layers = nn.ModuleList(
            [transformers.BertLayer(config.model_config) for _ in range(config.num_hidden_layers)]
        )
        self.l2 = nn.Linear(config.hidden_size, n_classes)

    def forward(self, x):
        x = self.embedding(self.l1(x))
        for layer in self.layers:
            x = layer(x)[0]
        x = torch.max(x, dim=1).values
        x = F.dropout(x, p=0.2, training=self.training)
        return self.l2(x)


def load_labels(path: Path = LABEL_MAP) -> list[str]:
    label_map = json.loads(path.read_text())
    labels = [None] * len(label_map)
    for name, idx in label_map.items():
        labels[idx] = name
    return labels


def load_model(size: str = "large", device: str | torch.device = "cpu") -> Transformer:
    filename, url = CHECKPOINTS[size]
    path = ARTIFACTS / filename
    if not path.is_file():
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        torch.hub.download_url_to_file(url, str(path), progress=True)
    model = Transformer(_Config(size))
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model"])
    return model.to(device).eval()


def pad_sequence(seq):
    """(T, 134) float array -> (1, MAX_FRAMES, 134) tensor, zero padded or truncated."""
    seq = torch.as_tensor(seq, dtype=torch.float32)
    if seq.shape[0] >= MAX_FRAMES:
        seq = seq[:MAX_FRAMES]
    else:
        seq = F.pad(seq, (0, 0, 0, MAX_FRAMES - seq.shape[0]))
    return seq.unsqueeze(0)


@torch.no_grad()
def predict(model: Transformer, seq, labels: list[str], k: int = 5):
    """Returns list of (label, probability) for the top-k classes."""
    x = pad_sequence(seq).to(next(model.parameters()).device)
    probs = torch.softmax(model(x), dim=-1)[0].cpu()
    top = torch.topk(probs, k)
    return [(labels[i], float(p)) for p, i in zip(top.values, top.indices)]
