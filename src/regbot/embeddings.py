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

    Falls back to the local cache when the Hub is unreachable. RegBot is local-first by
    design, so a cached model must keep working without network: ``snapshot_download``
    otherwise raises on a transient Hub failure even though every file is already on disk.
    ``local_files_only`` is passed explicitly so offline behaviour does not depend on Hub
    client version details.

    Env (optional):
    - HF_HUB_DOWNLOAD_TIMEOUT: seconds (default here: 300 if unset; hub default is often 10).
    - REGBOT_HF_ENDPOINT: if set, copied to HF_ENDPOINT (e.g. https://hf-mirror.com for China).
    - HF_HUB_OFFLINE=1: skip the Hub entirely and load from cache.
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

    offline = os.getenv("HF_HUB_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")

    def _download(local_only: bool) -> str:
        return snapshot_download(
            repo_id=model_name,
            ignore_patterns=_HUB_IGNORE_PATTERNS,
            local_files_only=local_only,
        )

    if offline:
        return SentenceTransformer(_download(True))

    try:
        path = _download(False)
    except Exception as exc:  # noqa: BLE001 — any Hub/network failure should try the cache
        try:
            path = _download(True)
        except Exception:
            raise RuntimeError(
                f"Could not reach the Hugging Face Hub for '{model_name}' and no complete "
                "copy is cached locally. Connect to the network for the first download, "
                "set REGBOT_HF_ENDPOINT to a mirror, or point REGBOT_EMBEDDING_MODEL at a "
                f"local directory. Original error: {exc}"
            ) from exc
    return SentenceTransformer(path)
