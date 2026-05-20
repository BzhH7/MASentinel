from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from masentinel.generator.patterns.cli_doc_conformance import extract_documented_commands
from masentinel.schema import SystemProfile
from masentinel.utils import read_text


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".cache",
    ".masentinel_autoreply",
    ".masentinel_fixture",
    ".masentinel_projects",
    "outputs",
    "output",
    "site-packages",
    "node_modules",
}


def detect_static_faults(profile: SystemProfile, start_index: int = 1) -> list[dict[str, Any]]:
    """Detect deterministic code/documentation contract defects.

    These rules intentionally look for portable implementation patterns rather
    than benchmark-specific system names or ground-truth IDs.
    """

    corpus = _source_corpus(profile)
    doc_text = read_text(profile.doc_path) if profile.doc_path else ""
    faults: list[dict[str, Any]] = []

    detectors = [
        _markdown_fence_parser_faults,
        _artifact_schema_faults,
        _resume_state_faults,
        _human_input_mode_faults,
        _http_tool_contract_faults,
        _scalable_budget_faults,
        _data_metric_faults,
        _cli_doc_faults,
        _autogen_wiring_faults,
    ]
    for detector in detectors:
        faults.extend(detector(profile, corpus, doc_text))

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for fault in faults:
        key = (str(fault.get("failure_code")), str(fault.get("summary")), str(fault.get("code_locations", []))[:240])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fault)

    prefix = profile.system_id.upper()
    for offset, fault in enumerate(deduped, start=start_index):
        if not fault.get("fault_id"):
            fault["fault_id"] = f"{prefix}_FAULT_{offset:03d}"
        if not fault.get("case_id"):
            fault["case_id"] = f"{profile.system_id}_STATIC_{str(fault.get('failure_code', 'FAULT')).lower()}"
        fault.setdefault("reproduction", {"input": "static code contract analysis", "command": ""})
        fault.setdefault("suspected_false_positive", False)
        fault.setdefault("evidence_strength", 0.72)
        fault.setdefault("root_cause_confidence", "code_evidence")
        fault.setdefault("confirmation_status", "confirmed_fault")
        fault.setdefault("confirmation_source", "deterministic_static_code_evidence")
        fault.setdefault(
            "deterministic_confirmation",
            {
                "confirmed": True,
                "source": "deterministic_static_code_evidence",
                "reason": "static code/documentation pattern with direct source evidence",
                "evidence_strength": fault.get("evidence_strength", 0.72),
                "root_cause_confidence": "code_evidence",
            },
        )
        fault.setdefault(
            "not_model_fault_because",
            "The defect is present in deterministic code, documentation, or framework configuration and can be mitigated without changing model parameters.",
        )
    return deduped


def _markdown_fence_parser_faults(profile: SystemProfile, corpus: list[dict[str, Any]], _doc_text: str) -> list[dict[str, Any]]:
    faults = []
    for source in corpus:
        text = source["text"]
        lowered = text.lower()
        if "replace('`'" not in text and 'replace("`"' not in text:
            continue
        if not re.search(r"\[[^\]]*6\s*:\s*\]", text):
            continue
        if "python" not in lowered and "code" not in lowered:
            continue
        locations = _locations(source, ("replace('`'", 'replace("`"', "[6:"))
        faults.append(
            _fault(
                profile,
                "MARKDOWN_ARTIFACT_CORRUPTION",
                "application",
                "Artifact Persistence Corruption",
                "high",
                "Markdown code fence extraction strips backticks and then slices a fixed prefix, which can corrupt valid unlabeled or short language-tag fences.",
                [
                    "detected backtick stripping plus fixed [6:] slicing",
                    source["path"],
                ],
                "The artifact writer assumes a specific code fence prefix instead of parsing Markdown fences structurally.",
                "Use a Markdown fence parser or regex that extracts the fenced body independent of optional language labels; compile-check Python artifacts before writing.",
                locations,
                confidence=0.9,
                evidence_strength=0.78,
            )
        )
    return faults


def _artifact_schema_faults(profile: SystemProfile, corpus: list[dict[str, Any]], doc_text: str) -> list[dict[str, Any]]:
    faults = []
    documented = _versioned_artifacts(doc_text)
    if not documented:
        return faults
    for source in corpus:
        text = source["text"]
        implemented = _versioned_artifacts(text)
        for base in sorted(set(documented) & set(implemented)):
            doc_exts = documented[base]
            code_exts = implemented[base]
            if doc_exts == code_exts:
                continue
            faults.append(
                _fault(
                    profile,
                    "ARTIFACT_SCHEMA_MISMATCH",
                    "application",
                    "Output Artifact Schema Mismatch",
                    "medium",
                    "Documented versioned artifact extension differs from the implementation's persisted artifact extension.",
                    [
                        f"artifact_family={base}",
                        f"documented_extensions={sorted(doc_exts)}",
                        f"implemented_extensions={sorted(code_exts)}",
                        source["path"],
                    ],
                    "Documentation and artifact persistence code disagree on a versioned artifact schema.",
                    "Align persisted artifact extensions with documentation or update documentation and downstream readers consistently.",
                    _locations(source, (base, "." + next(iter(code_exts)))),
                    confidence=0.84,
                    evidence_strength=0.74,
                )
            )
    return faults


def _resume_state_faults(profile: SystemProfile, corpus: list[dict[str, Any]], _doc_text: str) -> list[dict[str, Any]]:
    faults = []
    for source in corpus:
        text = source["text"]
        lowered = text.lower()
        artifact_bases = set(_versioned_artifacts(text))
        if len(artifact_bases) < 2:
            continue
        if not any(marker in lowered for marker in ("resume", "latest", "does_version", "version_exists", "continue")):
            continue
        for function_name, block in _function_blocks(text):
            block_lower = block.lower()
            if not any(marker in f"{function_name.lower()}\n{block_lower}" for marker in ("resume", "latest", "does_version", "version_exists", "continue")):
                continue
            checked_bases = {base for base in artifact_bases if base.lower() in block_lower}
            missing_bases = artifact_bases - checked_bases
            if checked_bases and missing_bases:
                faults.append(
                    _fault(
                        profile,
                        "RESUME_STATE_INCOMPLETE",
                        "application",
                        "Resume State Inconsistency",
                        "medium",
                        "Resume-state detection checks only part of the versioned artifact family.",
                        [
                            f"checked_artifacts={sorted(checked_bases)}",
                            f"unvalidated_artifacts={sorted(missing_bases)}",
                            source["path"],
                        ],
                        "The resume detector does not discover all versioned artifacts independently.",
                        "Discover latest artifacts per family and resume complete state or report incomplete state explicitly.",
                        _locations(source, tuple(sorted(artifact_bases)) + ("resume", "latest", "does_version")),
                        confidence=0.84,
                        evidence_strength=0.7,
                    )
                )
                break
        else:
            single_checks = [
                base
                for base in artifact_bases
                if re.search(rf"(exists|isfile|glob|path)\([^)]*{re.escape(base)}", lowered)
            ]
            if single_checks and len(set(single_checks)) < len(artifact_bases):
                missing = artifact_bases - set(single_checks)
                faults.append(
                    _fault(
                        profile,
                        "RESUME_STATE_INCOMPLETE",
                        "application",
                        "Resume State Inconsistency",
                        "medium",
                        "Resume-state detection validates only one versioned artifact family.",
                        [
                            f"checked_artifacts={sorted(set(single_checks))}",
                            f"unvalidated_artifacts={sorted(missing)}",
                            source["path"],
                        ],
                        "The resume detector does not discover all versioned artifacts independently.",
                        "Discover latest artifacts per family and resume complete state or report incomplete state explicitly.",
                        _locations(source, tuple(sorted(artifact_bases)) + ("resume", "latest", "does_version")),
                        confidence=0.84,
                        evidence_strength=0.7,
                    )
                )
    return faults


def _human_input_mode_faults(profile: SystemProfile, corpus: list[dict[str, Any]], _doc_text: str) -> list[dict[str, Any]]:
    faults = []
    for source in corpus:
        text = source["text"]
        if re.search(r"human_input_mode\s*=\s*['\"]ALWAYS['\"]", text):
            faults.append(
                _fault(
                    profile,
                    "HUMAN_INPUT_REQUESTED",
                    "autogen_framework",
                    "Human Input Mode Error",
                    "high",
                    "AutoGen user proxy is configured to always request human input in an automated workflow.",
                    ["human_input_mode='ALWAYS'", source["path"]],
                    "The framework configuration is incompatible with unattended automated evaluation.",
                    "Set human_input_mode='NEVER' or provide a deterministic non-blocking input adapter for automated runs.",
                    _locations(source, ("human_input_mode", "UserProxyAgent")),
                    confidence=0.9,
                    evidence_strength=0.76,
                )
            )
    return faults


def _http_tool_contract_faults(profile: SystemProfile, corpus: list[dict[str, Any]], _doc_text: str) -> list[dict[str, Any]]:
    faults = []
    for source in corpus:
        text = source["text"]
        lowered = text.lower()
        if "api.airtable.com" in lowered:
            locations = _locations(source, ("api.airtable.com", "requests.", "offset", "view"))
            if "view" not in lowered:
                faults.append(
                    _fault(
                        profile,
                        "VIEW_PARAMETER_IGNORED",
                        "application",
                        "Tool API Semantics Error",
                        "high",
                        "External table/API tool constructs requests without preserving documented view/filter parameters.",
                        ["Airtable API call found without view/query parameter handling", source["path"]],
                        "The tool wrapper loses semantic URL fields such as view/filter identifiers.",
                        "Parse base/table/view/query fields and pass semantic parameters through to the API request.",
                        locations,
                        confidence=0.88,
                        evidence_strength=0.72,
                    )
                )
            if "offset" not in lowered:
                faults.append(
                    _fault(
                        profile,
                        "PAGINATION_NOT_FOLLOWED",
                        "application",
                        "Tool API Pagination Missing",
                        "high",
                        "External table/API tool does not follow paginated responses.",
                        ["Airtable API call found without offset pagination loop", source["path"]],
                        "The tool wrapper returns only the first page of a paginated API result.",
                        "Iterate response offsets until exhausted and merge all records before returning.",
                        locations,
                        confidence=0.88,
                        evidence_strength=0.72,
                    )
                )
        if "requests" in lowered and ("return response.text" in lowered or "return none" in lowered):
            has_raise_or_envelope = "raise_for_status" in lowered or re.search(r"return\s+\{[^}]*['\"]error['\"]", lowered, re.DOTALL)
            if not has_raise_or_envelope:
                fault = _fault(
                    profile,
                    "TOOL_UNSTRUCTURED_ERROR",
                    "application",
                    "Tool Error Contract Missing",
                    "medium",
                    "HTTP tool can return raw text or None instead of a structured success/error envelope.",
                    ["requests-based tool returns response.text/None without typed error envelope", source["path"]],
                    "The tool wrapper does not normalize HTTP failures into a structured result.",
                    "Check status codes and return typed success/error payloads with status, message, and retryability.",
                    _locations(source, ("return response.text", "return None", "status_code", "requests")),
                    confidence=0.72,
                    evidence_strength=0.5,
                )
                _mark_static_advisory(
                    fault,
                    "Static HTTP wrapper evidence requires an observed failing HTTP status and tool result/error envelope before confirmation.",
                )
                faults.append(fault)
    return faults


def _scalable_budget_faults(profile: SystemProfile, corpus: list[dict[str, Any]], doc_text: str) -> list[dict[str, Any]]:
    faults = []
    combined_doc = doc_text.lower()
    for source in corpus:
        text = source["text"]
        lowered = text.lower()
        match = re.search(r"max_round\s*=\s*(\d+)", text)
        if not match:
            continue
        if not ("groupchat" in lowered and ("record" in lowered or "airtable" in lowered or "companies" in lowered or "company" in combined_doc)):
            continue
        max_round = int(match.group(1))
        faults.append(
            _fault(
                profile,
                "SCALABLE_BUDGET_EXCEEDED",
                "autogen_framework",
                "Scalable Turn Budget Error",
                "medium",
                "GroupChat uses a fixed max_round for work that scales with records/items.",
                [f"max_round={max_round}", source["path"]],
                "The configured conversation budget is fixed while the task workload scales with external records/items.",
                "Scale max_round with record count or move repeated per-record work into deterministic batched tools.",
                _locations(source, ("GroupChat", "max_round", "record", "airtable")),
                confidence=0.82,
                evidence_strength=0.68,
            )
        )
    return faults


def _data_metric_faults(profile: SystemProfile, corpus: list[dict[str, Any]], _doc_text: str) -> list[dict[str, Any]]:
    faults = []
    for source in corpus:
        text = source["text"]
        lowered = text.lower()
        if ".loc[" in text and "except" in lowered and "return metrics" in lowered and ("financial" in lowered or "balance_sheet" in lowered):
            faults.append(
                _fault(
                    profile,
                    "PARTIAL_METRIC_ZEROED",
                    "application",
                    "Data Processing Invariant Violation",
                    "medium",
                    "Financial metric calculation can discard available metrics when one optional row lookup fails.",
                    ["direct .loc row lookups inside broad try/except", source["path"]],
                    "Independent financial metrics are computed in a shared exception scope, so one missing row can zero unrelated outputs.",
                    "Compute each metric independently and represent missing-row-dependent values as null/unavailable.",
                    _locations(source, (".loc[", "except", "return metrics", "financial")),
                    confidence=0.84,
                    evidence_strength=0.7,
                )
            )
        if ("percentile(returns, 5)" in lowered or "quantile(0.05" in lowered) and ("drawdown.min" in lowered or "max_drawdown" in lowered):
            faults.append(
                _fault(
                    profile,
                    "NUMERIC_SIGN_CONVENTION_ERROR",
                    "application",
                    "Data Processing Invariant Violation",
                    "medium",
                    "Risk metrics are returned as negative signed returns where reports commonly expect positive magnitudes.",
                    ["VaR/drawdown assigned from lower-tail/min return expressions", source["path"]],
                    "Risk metric outputs are not normalized to documented/report magnitude semantics.",
                    "Normalize VaR and drawdown outputs to positive magnitudes or label them explicitly as signed returns.",
                    _locations(source, ("percentile", "quantile", "drawdown.min", "max_drawdown", "var_95")),
                    confidence=0.82,
                    evidence_strength=0.68,
                )
            )
    return faults


def _cli_doc_faults(profile: SystemProfile, corpus: list[dict[str, Any]], doc_text: str) -> list[dict[str, Any]]:
    commands = extract_documented_commands(doc_text)
    if not commands:
        return []
    source_text = "\n".join(source["text"] for source in corpus)
    source_lower = source_text.lower()
    faults = []
    for command in commands:
        subcommand = _documented_subcommand(command)
        if not subcommand:
            continue
        if _cli_subcommand_registered(source_lower, subcommand):
            continue
        faults.append(
            _fault(
                profile,
                "DOCUMENTED_CLI_COMMAND_MISSING",
                "application",
                "Documented CLI Command Missing",
                "medium",
                f"Documented CLI command is not implemented by the parser or dispatcher: {command}",
                [f"documented_command={command}", "subcommand parser registration not found in source"],
                "Documentation advertises a CLI subcommand that the implementation does not register.",
                "Add the documented subcommand to the parser/dispatcher or remove/update the documentation.",
                _locations_for_literals(corpus, ("add_parser", "subparsers", "argparse", subcommand)),
                confidence=0.82,
                evidence_strength=0.66,
            )
        )
    return faults


def _autogen_wiring_faults(profile: SystemProfile, _corpus: list[dict[str, Any]], _doc_text: str) -> list[dict[str, Any]]:
    risks = profile.raw_notes.get("autogen_wiring_risks", []) or []
    if not risks:
        return []
    return [
        _fault(
            profile,
            "AUTOGEN_WIRING_MISSING",
            "autogen_framework",
            "Agent Orchestration Wiring Missing",
            "high",
            "Documented AutoGen workflow is initialized with an empty or missing agent mapping.",
            [str(item) for item in risks[:6]],
            "The orchestrator/factory wiring does not create or register the documented collaborating agents.",
            "Create the required agents from the factory and pass a non-empty role-to-agent mapping into the orchestrator.",
            [
                {"file": str(item.get("file", "")), "line": str(item.get("line", "")), "function": "AgentOrchestrator"}
                for item in risks
                if isinstance(item, dict)
            ],
            confidence=0.9,
            evidence_strength=0.76,
        )
    ]


def _fault(
    profile: SystemProfile,
    code: str,
    layer: str,
    fault_type: str,
    severity: str,
    summary: str,
    evidence: list[str],
    root_cause: str,
    suggested_fix: str,
    locations: list[dict[str, str]],
    confidence: float,
    evidence_strength: float,
) -> dict[str, Any]:
    return {
        "fault_id": "",
        "case_id": f"{profile.system_id}_STATIC_{code.lower()}",
        "layer": layer,
        "fault_type": fault_type,
        "failure_code": code,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "evidence": evidence,
        "root_cause": root_cause,
        "suggested_fix": suggested_fix,
        "code_locations": locations[:8],
        "evidence_strength": evidence_strength,
        "root_cause_confidence": "code_evidence",
        "reproduction": {"input": "static code contract analysis", "command": ""},
    }


def _mark_static_advisory(fault: dict[str, Any], reason: str) -> None:
    fault["confirmation_status"] = "suspected_fault"
    fault["confirmation_source"] = "deterministic_static_advisory"
    fault["suspected_false_positive"] = True
    fault["deterministic_confirmation"] = {
        "confirmed": False,
        "source": "deterministic_static_code_evidence",
        "reason": reason,
        "evidence_strength": fault.get("evidence_strength", 0.0),
        "root_cause_confidence": fault.get("root_cause_confidence", "code_evidence"),
    }


def _source_corpus(profile: SystemProfile, max_chars_per_file: int = 200_000) -> list[dict[str, Any]]:
    paths = [Path(item) for item in profile.raw_notes.get("files", []) or []]
    if not paths and profile.entrypoint:
        paths.append(Path(profile.entrypoint))
    if not paths and profile.root_path and (profile.doc_path or profile.entrypoint):
        root = Path(profile.root_path)
        if root.exists():
            paths = sorted(root.rglob("*.py"))
    corpus = []
    for path in paths:
        if _skip_path(path) or not path.exists():
            continue
        text = read_text(path)
        if not text:
            continue
        corpus.append({"path": str(path), "text": text[:max_chars_per_file]})
    return corpus


def _skip_path(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS or part.startswith(".ipynb_checkpoints") for part in path.parts)


def _locations(source: dict[str, Any], markers: tuple[str, ...]) -> list[dict[str, str]]:
    text = str(source.get("text", ""))
    locations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if any(marker.lower() in lowered for marker in markers):
            locations.append({"file": str(source.get("path", "")), "line": str(lineno), "function": ""})
        if len(locations) >= 5:
            break
    return locations


def _locations_for_literals(corpus: list[dict[str, Any]], markers: tuple[str, ...]) -> list[dict[str, str]]:
    locations = []
    for source in corpus:
        locations.extend(_locations(source, markers))
        if locations:
            break
    return locations[:5]


def _documented_subcommand(command: str) -> str | None:
    parts = command.split()
    if len(parts) >= 4 and parts[0].startswith("python") and parts[1] == "-m":
        return parts[3]
    if len(parts) >= 3 and parts[0].startswith("python"):
        return parts[2]
    return None


def _cli_subcommand_registered(source_lower: str, literal: str) -> bool:
    value = re.escape(literal.lower())
    patterns = (
        rf"\.add_parser\(\s*['\"]{value}['\"]",
        rf"add_parser\(\s*['\"]{value}['\"]",
        rf"@[\w.]+\.command\(\s*['\"]{value}['\"]",
        rf"@[\w.]+\.command\([^)]*name\s*=\s*['\"]{value}['\"]",
        rf"typer\.[\w_]+\([^)]*['\"]{value}['\"]",
        rf"choices\s*=\s*\[[^\]]*['\"]{value}['\"]",
        rf"commands\s*=\s*\{{[^}}]*['\"]{value}['\"]",
    )
    return any(re.search(pattern, source_lower, flags=re.DOTALL) for pattern in patterns)


def _versioned_artifacts(text: str) -> dict[str, set[str]]:
    artifacts: dict[str, set[str]] = {}
    for match in re.finditer(r"\b([A-Za-z][\w-]*_v)(?:\*|\d+|n|\{[^}]+\})?\.([A-Za-z0-9]+)\b", text, flags=re.IGNORECASE):
        base = match.group(1).lower()
        ext = match.group(2).lower()
        artifacts.setdefault(base, set()).add(ext)
    return artifacts


def _function_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), text[match.start() : end]))
    return blocks
