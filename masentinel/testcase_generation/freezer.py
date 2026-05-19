from __future__ import annotations

from pathlib import Path
from typing import Any

from masentinel.run_manifest import sha256_json
from masentinel.utils import write_json, write_text


def freeze_testcases(testcases: list[Any], out_dir: str | Path) -> str:
    out_dir = Path(out_dir)
    digest = sha256_json(testcases)
    write_text(out_dir / "testcases.frozen.sha256", digest + "\n")
    return digest


def write_generation_artifacts(generated: list[Any], validated: list[Any], out_dir: str | Path) -> str:
    out_dir = Path(out_dir)
    write_json(out_dir / "testcases.generated.json", generated)
    write_json(out_dir / "testcases.validated.json", validated)
    write_json(out_dir / "testcases.json", validated)
    return freeze_testcases(validated, out_dir)
