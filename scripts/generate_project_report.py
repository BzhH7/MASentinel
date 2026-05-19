from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_api_env(api_doc: Path, target_model: str | None, extra_body_json: str, enable_thinking: bool, reasoning_effort: str) -> None:
    if not api_doc.exists():
        return
    script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(script_dir))
    from run_with_api_md import _extra_body_json, load_api_settings

    env_values, overrides = load_api_settings(api_doc, target_model=target_model)
    os.environ.update(env_values)
    os.environ.update(overrides)
    extra_body_text = _extra_body_json(extra_body_json, enable_thinking, reasoning_effort)
    if extra_body_text:
        os.environ["MAS_MODEL_EXTRA_BODY_JSON"] = extra_body_text
        os.environ["MAS_TESTING_EXTRA_BODY_JSON"] = extra_body_text
    print(
        "[MASentinel][project-report] api settings loaded "
        f"testing_model={os.environ.get('MAS_TESTING_MODEL', 'config')} "
        f"extra_body_keys={','.join(sorted(json.loads(extra_body_text))) if extra_body_text else 'none'}",
        flush=True,
    )


def _first_system_model_config(config_path: Path) -> dict:
    from masentinel.runner.system_adapter import load_system_config
    from masentinel.utils import load_yaml, resolve_path

    all_config = load_yaml(config_path)
    systems = list(all_config.get("systems", []))
    if not systems:
        return {}
    first_path = Path(resolve_path(str(systems[0]), config_path.parent) or systems[0])
    return (load_system_config(first_path).get("model", {}) or {})


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    parser = argparse.ArgumentParser(description="Generate the competition project report from MASentinel outputs.")
    parser.add_argument("--output-dir", default=str(repo_root / "outputs"))
    parser.add_argument("--config", default=str(repo_root / "configs" / "all_systems.yaml"))
    parser.add_argument("--api-doc", default=str(workspace_root / "api.md"))
    parser.add_argument("--test-model", default=None)
    parser.add_argument("--target-model", default=None)
    parser.add_argument("--extra-body-json", default=os.getenv("MAS_MODEL_EXTRA_BODY_JSON", ""))
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"], default="")
    args = parser.parse_args()

    sys.path.insert(0, str(repo_root))
    _load_api_env(Path(args.api_doc), args.target_model, args.extra_body_json, args.enable_thinking, args.reasoning_effort)

    from masentinel.reporter.project_report import write_project_report

    report_path = write_project_report(
        args.output_dir,
        model_config=_first_system_model_config(Path(args.config)),
        test_model=args.test_model,
    )
    print(f"[MASentinel][project-report] generated {report_path}", flush=True)


if __name__ == "__main__":
    main()
