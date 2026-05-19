from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from masentinel.utils import dataclass_to_dict, read_text, utc_now_iso, write_json


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_bytes(json.dumps(dataclass_to_dict(data), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def hash_file(path: str | Path | None) -> str | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None
    return sha256_bytes(target.read_bytes())


def hash_directory(root: str | Path | None) -> str | None:
    if not root:
        return None
    root_path = Path(root)
    if not root_path.exists():
        return None
    digest = hashlib.sha256()
    for path in sorted(root_path.rglob("*.py")):
        if any(part in {".venv", "venv", "__pycache__", ".git"} for part in path.parts):
            continue
        rel = str(path.relative_to(root_path))
        digest.update(rel.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_run_manifest(config_path: str | Path, config: dict[str, Any], entry_command: str, no_human: bool) -> dict[str, Any]:
    config_text = read_text(config_path)
    return {
        "run_id": f"{config.get('system_id', Path(config_path).stem)}_{utc_now_iso()}",
        "start_time": utc_now_iso(),
        "config_path": str(Path(config_path).resolve()),
        "config_hash": sha256_bytes(config_text.encode("utf-8")),
        "code_snapshot_hash": hash_directory(config.get("root_path")),
        "doc_hash": hash_file(config.get("doc_path")),
        "human_intervention_allowed": not no_human,
        "entry_command": entry_command,
        "python_executable": sys.executable,
        "pid": os.getpid(),
    }


def write_run_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    write_json(path, manifest)
