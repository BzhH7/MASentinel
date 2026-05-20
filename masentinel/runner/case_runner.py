from __future__ import annotations

import json
import os
import pty
import re
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from masentinel.instrumentation.trace_recorder import TraceRecorder
from masentinel.runner.filesystem_monitor import FilesystemMonitor
from masentinel.runner.system_adapter import build_command, build_env, render_case_template, target_model_context
from masentinel.schema import RunTrace, TestCase, TraceEvent
from masentinel.utils import ensure_dir, shorten, write_json


TRACE_PREFIX = "MAS_TRACE:"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
AUTOGEN_MESSAGE_RE = re.compile(r"^([A-Za-z_][\w.-]*)\s+\(to\s+([A-Za-z_][\w.-]*)\):\s*$")


class CaseRunner:
    def __init__(self, config: dict[str, Any], traces_dir: str | Path) -> None:
        self.config = config
        self.traces_dir = ensure_dir(traces_dir)

    def run_case(self, testcase: TestCase) -> RunTrace:
        trace_path = str(self.traces_dir / f"{testcase.case_id}.json")
        recorder = TraceRecorder(testcase.case_id, testcase.system_id)
        command = build_command(self.config, testcase)
        run_cfg = self.config.get("run", {}) or {}
        cwd = run_cfg.get("working_dir") or self.config.get("root_path") or "."
        timeout_seconds = int((testcase.metadata or {}).get("timeout_seconds") or run_cfg.get("timeout_seconds", 120))
        input_mode = run_cfg.get("input_mode", "stdin")
        env = build_env(self.config, testcase, trace_path)
        isolated_cleanup = self._prepare_isolated_paths(run_cfg, cwd, testcase)
        fixture_setup = self._prepare_case_fixture(cwd, testcase)
        fs_monitor = self._filesystem_monitor(cwd, testcase)
        fs_monitor.snapshot_before()
        stdout = ""
        stderr = ""
        returncode = None
        timeout = False
        human_input_requested = False
        interaction_responses: list[dict[str, str]] = []
        recorder.events.append(
            TraceEvent(
                type="process_start",
                timestamp=time.time(),
                content=" ".join(command),
                metadata={"cwd": str(cwd), "case_id": testcase.case_id, "isolated_cleanup": isolated_cleanup},
            )
        )
        try:
            case_input = self._case_input(testcase)
            if input_mode == "interactive":
                stdout, stderr, returncode, timeout, interaction_responses = self._run_interactive(
                    command=command,
                    cwd=cwd,
                    env=env,
                    timeout_seconds=timeout_seconds,
                    testcase=testcase,
                    case_input=case_input,
                )
            else:
                stdin_payload = None
                if input_mode == "stdin":
                    stdin_payload = case_input if case_input.endswith("\n") else case_input + "\n"
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    input=stdin_payload,
                    timeout=timeout_seconds,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
                returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timeout = True
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="ignore")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="ignore")
            returncode = None
            recorder.record_exception("TimeoutExpired", f"Timed out after {timeout_seconds}s")
        except Exception as exc:
            stderr = str(exc)
            returncode = -1
            recorder.record_exception(exc.__class__.__name__, str(exc))
        filesystem_effects = fs_monitor.snapshot_after()
        for event in self._events_from_stdout(stdout):
            recorder.events.append(event)
        for response in interaction_responses:
            recorder.events.append(
                TraceEvent(
                    type="interactive_response",
                    timestamp=time.time(),
                    content=response.get("response", ""),
                    metadata={
                        "trigger": response.get("trigger", ""),
                        "case_id": testcase.case_id,
                    },
                )
            )
        human_input_requested = self._detect_human_input_requested(stdout, stderr, recorder.events)
        if human_input_requested:
            recorder.events.append(
                TraceEvent(
                    type="human_input_requested",
                    timestamp=time.time(),
                    content="Target system requested human input during a no-human MASentinel run.",
                    metadata={"case_id": testcase.case_id, "no_human": True},
                )
            )
        turn_count = max(recorder.turn_count, self._message_turn_count(recorder.events))
        recorder.turn_count = turn_count
        status = "timeout" if timeout else ("failed" if human_input_requested or returncode != 0 else "passed")
        terminated = bool(returncode == 0 and not timeout and not human_input_requested)
        final_output = self._final_output(stdout, stderr)
        trace = recorder.finalize(
            status=status,
            terminated=terminated,
            timeout=timeout,
            final_output=final_output,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            metadata={
                "command": command,
                "cwd": str(cwd),
                "timeout_seconds": timeout_seconds,
                "input_mode": input_mode,
                "stdin_template_used": bool(run_cfg.get("stdin_template")),
                "isolated_cleanup": isolated_cleanup,
                "case_fixture": fixture_setup,
                "filesystem_effects": filesystem_effects,
                "interaction_responses": interaction_responses,
                "no_human": (self.config.get("run", {}) or {}).get("no_human", True),
                "human_input_requested": human_input_requested,
                **target_model_context(self.config),
            },
        )
        write_json(trace_path, trace)
        return trace

    def _prepare_case_fixture(self, cwd: str | Path, testcase: TestCase) -> dict[str, Any]:
        metadata = testcase.metadata if isinstance(testcase.metadata, dict) else {}
        fixture = metadata.get("fixture") if isinstance(metadata.get("fixture"), dict) else {}
        created: list[str] = []
        omitted: list[str] = []
        skipped: list[dict[str, str]] = []
        if not fixture:
            return {"created_files": created, "omitted_files": omitted, "skipped": skipped}
        cwd_path = Path(cwd).resolve()
        root_template = str(fixture.get("root") or ".")
        root = Path(render_case_template(root_template, testcase))
        if not root.is_absolute():
            root = cwd_path / root
        root = root.resolve()
        if not self._path_inside(root, cwd_path):
            return {"created_files": created, "omitted_files": omitted, "skipped": [{"path": str(root), "reason": "fixture_root_outside_cwd"}]}
        for rel_path, content in (fixture.get("create_files") or {}).items():
            target = (root / str(rel_path)).resolve()
            if not self._path_inside(target, root):
                skipped.append({"path": str(target), "reason": "fixture_file_outside_root"})
                continue
            ensure_dir(target.parent)
            target.write_text(str(content), encoding="utf-8")
            created.append(str(target))
        for rel_path in fixture.get("omit_files") or []:
            target = (root / str(rel_path)).resolve()
            omitted.append(str(target))
            if self._path_inside(target, root) and target.exists():
                target.unlink()
        return {"root": str(root), "created_files": created, "omitted_files": omitted, "skipped": skipped}

    def _filesystem_monitor(self, cwd: str | Path, testcase: TestCase) -> FilesystemMonitor:
        cwd_path = Path(cwd).resolve()
        run_cfg = self.config.get("run", {}) or {}
        allowed_templates = run_cfg.get("filesystem_allowed_roots") or []
        if isinstance(allowed_templates, str):
            allowed_templates = [allowed_templates]
        metadata = testcase.metadata if isinstance(testcase.metadata, dict) else {}
        if not allowed_templates and metadata.get("generic_pattern") == "safe_project_root":
            for key, value in (run_cfg.get("env", {}) or {}).items():
                if "PROJECT_DIR" in str(key).upper():
                    allowed_templates.append(str(value))
        allowed_roots: list[Path] = []
        for item in allowed_templates:
            rendered = render_case_template(str(item), testcase)
            path = Path(rendered)
            allowed_roots.append((cwd_path / path).resolve() if not path.is_absolute() else path.resolve())
        if not allowed_roots:
            allowed_roots = [cwd_path]
        watch_roots = [cwd_path]
        return FilesystemMonitor(allowed_roots=allowed_roots, watch_roots=watch_roots)

    def _path_inside(self, path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _run_interactive(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str],
        timeout_seconds: int,
        testcase: TestCase,
        case_input: str,
    ) -> tuple[str, str, int | None, bool, list[dict[str, str]]]:
        if os.name != "posix":
            stdin_payload = case_input if case_input.endswith("\n") else case_input + "\n"
            completed = subprocess.run(
                command,
                cwd=cwd,
                input=stdin_payload,
                timeout=timeout_seconds,
                env=env,
                capture_output=True,
                text=True,
            )
            return completed.stdout or "", completed.stderr or "", completed.returncode, False, []

        run_cfg = self.config.get("run", {}) or {}
        interaction_cfg = run_cfg.get("interaction", {}) or {}
        rules = list(interaction_cfg.get("prompt_responses", []) or interaction_cfg.get("startup_responses", []) or [])
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        chunks: list[str] = []
        responses: list[dict[str, str]] = []
        sent_counts = [0 for _ in rules]
        deadline = time.time() + timeout_seconds
        timed_out = False
        try:
            while True:
                if time.time() > deadline:
                    timed_out = True
                    process.kill()
                    break
                readable, _, _ = select.select([master_fd], [], [], 0.1)
                if readable:
                    try:
                        data = os.read(master_fd, 4096)
                    except OSError:
                        data = b""
                    if data:
                        chunks.append(data.decode("utf-8", errors="ignore"))
                        self._send_matching_interactive_responses(master_fd, rules, sent_counts, "".join(chunks), testcase, responses)
                if process.poll() is not None:
                    while True:
                        readable, _, _ = select.select([master_fd], [], [], 0)
                        if not readable:
                            break
                        try:
                            data = os.read(master_fd, 4096)
                        except OSError:
                            break
                        if not data:
                            break
                        chunks.append(data.decode("utf-8", errors="ignore"))
                    break
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass
            if timed_out:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            else:
                process.wait()
        return "".join(chunks), "", process.returncode, timed_out, responses

    def _send_matching_interactive_responses(
        self,
        master_fd: int,
        rules: list[Any],
        sent_counts: list[int],
        output: str,
        testcase: TestCase,
        responses: list[dict[str, str]],
    ) -> None:
        import re

        tail = output[-4000:]
        for index, raw_rule in enumerate(rules):
            if not isinstance(raw_rule, dict):
                continue
            trigger = str(raw_rule.get("trigger", ""))
            if not trigger:
                continue
            max_count = int(raw_rule.get("max_count", 1 if raw_rule.get("once", True) else 1000) or 1)
            if sent_counts[index] >= max_count:
                continue
            matched = bool(re.search(trigger, tail, re.DOTALL)) if raw_rule.get("regex") else trigger in tail
            if not matched:
                continue
            response = render_case_template(str(raw_rule.get("response", "")), testcase)
            os.write(master_fd, (response + "\n").encode("utf-8"))
            sent_counts[index] += 1
            responses.append({"trigger": trigger, "response": response})

    def _message_turn_count(self, events: list[TraceEvent]) -> int:
        explicit_turns = [int(event.turn) for event in events if event.type == "message" and event.turn]
        seen: set[tuple[str, str, str]] = set()
        for event in events:
            if event.type != "message":
                continue
            content = (event.content or "").strip()
            fingerprint = (event.sender or "", event.receiver or "", content[:1000])
            seen.add(fingerprint)
        return max(max(explicit_turns, default=0), len(seen))

    def _case_input(self, testcase: TestCase) -> str:
        run_cfg = self.config.get("run", {}) or {}
        stdin_template = run_cfg.get("stdin_template")
        if stdin_template:
            return render_case_template(str(stdin_template), testcase)
        if testcase.input_sequence:
            return "\n".join(str(item.get("content", "")) for item in testcase.input_sequence if item.get("content")).strip()
        return testcase.input

    def _prepare_isolated_paths(self, run_cfg: dict[str, Any], cwd: str | Path, testcase: TestCase) -> list[dict[str, str]]:
        if not run_cfg.get("clean_isolated_paths_before_case", False):
            return []
        paths = run_cfg.get("isolated_paths", []) or []
        if isinstance(paths, str):
            paths = [paths]
        cwd_path = Path(cwd).resolve()
        results: list[dict[str, str]] = []
        for item in paths:
            rendered = render_case_template(str(item), testcase)
            target = Path(rendered)
            if not target.is_absolute():
                target = cwd_path / target
            try:
                resolved = target.resolve()
                if not self._is_safe_isolated_path(resolved, cwd_path):
                    results.append({"path": str(resolved), "status": "skipped_unsafe"})
                    continue
                if resolved.exists():
                    shutil.rmtree(resolved)
                    results.append({"path": str(resolved), "status": "removed"})
                else:
                    results.append({"path": str(resolved), "status": "already_absent"})
            except Exception as exc:
                results.append({"path": str(target), "status": "error", "error": str(exc)})
        return results

    def _is_safe_isolated_path(self, path: Path, cwd: Path) -> bool:
        try:
            path.relative_to(cwd)
        except ValueError:
            return False
        if path == cwd:
            return False
        return any(part.startswith(".masentinel") for part in path.parts)

    def _events_from_stdout(self, stdout: str) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        for line in stdout.splitlines():
            clean_line = ANSI_RE.sub("", line).strip()
            if clean_line.startswith(TRACE_PREFIX):
                payload = clean_line[len(TRACE_PREFIX) :].strip()
                try:
                    data = json.loads(payload)
                    data.setdefault("timestamp", time.time())
                    events.append(TraceEvent(**data))
                except Exception:
                    events.append(TraceEvent(type="trace_parse_error", timestamp=time.time(), content=shorten(clean_line, 300)))
                continue
            match = AUTOGEN_MESSAGE_RE.match(clean_line)
            if match:
                events.append(
                    TraceEvent(
                        type="message",
                        timestamp=time.time(),
                        sender=match.group(1),
                        receiver=match.group(2),
                        content="AutoGen stdout message boundary",
                        metadata={"source": "autogen_stdout"},
                    )
                )
        return events

    def _detect_human_input_requested(self, stdout: str, stderr: str, events: list[TraceEvent]) -> bool:
        for event in events:
            if event.type == "human_input_requested":
                return True
            mode = str(event.metadata.get("human_input_mode", "")).upper()
            if mode in {"ALWAYS", "TERMINATE"}:
                return True
        text = f"{stdout}\n{stderr}".lower()
        markers = [
            "eoferror",
            "press enter",
            "waiting for human",
            "human input",
            "manual input",
            "user input requested",
        ]
        return any(marker in text for marker in markers)

    def _final_output(self, stdout: str, stderr: str) -> str:
        text = stdout.strip() or stderr.strip()
        if not text:
            return ""
        lines = [line for line in text.splitlines() if not line.startswith(TRACE_PREFIX)]
        return "\n".join(lines[-20:]).strip()
