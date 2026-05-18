from __future__ import annotations

import os
from typing import Any

# Skip optional heavy artifacts; PyTorch inference uses model.safetensors + tokenizer only.
_HUB_IGNORE_PATTERNS = [
    "*.onnx",
    "**/*.onnx",
    "openvino*",
    "tf_model*",
    "rust_model*",
    "pytorch_model.bin",
]


def load_sentence_transformer(model_name: str) -> Any:
    """
    Load a SentenceTransformer model with smaller Hub downloads and relaxed timeouts.

    - Hugging Face: snapshot_download(..., ignore_patterns=...) then load from local path,
      avoiding hundreds of MB of ONNX / OpenVINO / duplicate pytorch weights.
    - Local directory: pass-through to SentenceTransformer(path).

    Env (optional):
    - HF_HUB_DOWNLOAD_TIMEOUT: seconds (default here: 300 if unset; hub default is often 10).
    - REGBOT_HF_ENDPOINT: if set, copied to HF_ENDPOINT (e.g. https://hf-mirror.com for China).
    """
    if os.getenv("HF_HUB_DOWNLOAD_TIMEOUT") is None:
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"

    mirror = os.getenv("REGBOT_HF_ENDPOINT", "").strip()
    if mirror:
        os.environ["HF_ENDPOINT"] = mirror

    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer

    expanded = os.path.expanduser(model_name)
    if os.path.isdir(expanded):
        return SentenceTransformer(expanded)

    path = snapshot_download(
        repo_id=model_name,
        ignore_patterns=_HUB_IGNORE_PATTERNS,
    )
    return SentenceTransformer(path)
