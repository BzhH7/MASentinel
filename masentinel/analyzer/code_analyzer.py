from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Callable

from masentinel.schema import AgentInfo, MessageEdge, ToolInfo
from masentinel.utils import read_text, shorten


AGENT_CLASS_NAMES = {
    "AssistantAgent",
    "UserProxyAgent",
    "ConversableAgent",
    "GPTAssistantAgent",
    "GroupChatManager",
}

ProgressFn = Callable[[str], None]

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "output",
    "outputs",
    "site-packages",
    "venv",
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _last_name(node: ast.AST) -> str:
    return _call_name(node).split(".")[-1]


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _var_name(target: ast.AST) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Subscript):
        return _var_name(target.value)
    return None


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self, root_path: str | Path, progress: ProgressFn | None = None) -> None:
        self.root_path = Path(root_path)
        self.progress = progress
        self.agents_by_var: dict[str, AgentInfo] = {}
        self.agents_by_name: dict[str, AgentInfo] = {}
        self.tools_by_name: dict[str, ToolInfo] = {}
        self.edges: set[MessageEdge] = set()
        self.raw_notes: dict[str, Any] = {"warnings": [], "files": [], "functions": []}
        self.current_file: str = ""
        self.class_depth = 0

    def analyze(self) -> dict[str, Any]:
        if not self.root_path.exists():
            self.raw_notes["warnings"].append(f"root_path does not exist: {self.root_path}")
            return self._result()
        self._progress(f"code analyzer: discovering Python files under {self.root_path}")
        py_files = list(self._iter_python_files())
        self._progress(f"code analyzer: discovered {len(py_files)} Python files")
        for index, path in enumerate(py_files, start=1):
            self.current_file = str(path)
            self.raw_notes["files"].append(str(path))
            text = read_text(path)
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                self.raw_notes["warnings"].append(f"SyntaxError in {path}: {exc}")
                continue
            self.visit(tree)
            if index == 1 or index == len(py_files) or index % 25 == 0:
                self._progress(f"code analyzer: parsed {index}/{len(py_files)} files")
        self._attach_edges_from_group_managers()
        self._progress(
            "code analyzer: completed "
            f"agents={len(self.agents_by_name)} tools={len(self.tools_by_name)} edges={len(self.edges)}"
        )
        return self._result()

    def _iter_python_files(self) -> list[Path]:
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root_path):
            dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS and not name.startswith(".ipynb_checkpoints"))
            for filename in sorted(filenames):
                if filename.endswith(".py"):
                    files.append(Path(dirpath) / filename)
        return files

    def _result(self) -> dict[str, Any]:
        return {
            "agents": list(self.agents_by_name.values()),
            "tools": list(self.tools_by_name.values()),
            "message_edges": sorted(self.edges, key=lambda x: (x.source, x.target, x.evidence or "")),
            "raw_notes": self.raw_notes,
        }

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._record_function_note(node)
        if self.class_depth == 0 and self._looks_like_tool_function(node.name):
            self._record_function_tool(node)
        self._record_decorated_tool(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._record_function_note(node)
        if self.class_depth == 0 and self._looks_like_tool_function(node.name):
            self._record_function_tool(node)
        self._record_decorated_tool(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.class_depth += 1
        try:
            self.generic_visit(node)
        finally:
            self.class_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> Any:
        if isinstance(node.value, ast.Call):
            class_name = _last_name(node.value.func)
            targets = [_var_name(t) for t in node.targets]
            var = next((x for x in targets if x), None)
            if class_name in AGENT_CLASS_NAMES:
                self._record_agent(node.value, var, class_name)
            if class_name == "GroupChat":
                self._record_groupchat_edges(node.value)
            if var and class_name == "GroupChatManager":
                self.raw_notes.setdefault("group_managers", {})[var] = _safe_unparse(node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        func_name = _last_name(node.func)
        full_name = _call_name(node.func)
        if func_name in AGENT_CLASS_NAMES and _keyword(node, "name") is not None:
            self._record_agent(node, None, func_name)
        if func_name in {"register_function", "register_for_llm", "register_for_execution"}:
            self._record_registration(node)
        if func_name == "GroupChat":
            self._record_groupchat_edges(node)
        if func_name == "initiate_chat":
            self._record_initiate_chat_edge(node)
        if func_name == "last_message":
            self._record_callsite(node, "last_message", full_name)
        if func_name in {"UserProxyAgent", "GroupChat", "GroupChatManager", "AssistantAgent", "AgentOrchestrator"}:
            self._record_callsite(node, func_name, full_name)
        if func_name == "AgentOrchestrator" and self._call_has_empty_mapping(node):
            self.raw_notes.setdefault("autogen_wiring_risks", []).append(
                {
                    "file": self.current_file,
                    "line": str(getattr(node, "lineno", "")),
                    "risk": "AgentOrchestrator initialized with an empty mapping or no agents.",
                    "call": _safe_unparse(node),
                }
            )
        if full_name.endswith(("register_for_llm", "register_for_execution")):
            self._record_callsite(node, func_name, full_name)
        self.generic_visit(node)

    def _record_agent(self, call: ast.Call, var: str | None, class_name: str) -> None:
        name = _literal(_keyword(call, "name"))
        if not isinstance(name, str) or not name:
            name = var or f"{class_name}_{len(self.agents_by_name) + 1}"
        system_message = _literal(_keyword(call, "system_message"))
        description = _literal(_keyword(call, "description"))
        existing = self.agents_by_name.get(name)
        info = existing or AgentInfo(name=name)
        info.var_name = info.var_name or var
        info.class_name = info.class_name or class_name
        info.system_message = info.system_message or (system_message if isinstance(system_message, str) else None)
        info.description = info.description or (description if isinstance(description, str) else None)
        tools = self._extract_function_map_names(call) + self._extract_tool_list_names(call)
        for tool in tools:
            if tool not in info.tools:
                info.tools.append(tool)
        self.agents_by_name[name] = info
        if var:
            self.agents_by_var[var] = info

    def _record_function_tool(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        signature = f"{node.name}({_safe_unparse(node.args)})"
        params = [{"name": arg.arg, "annotation": _safe_unparse(arg.annotation) if arg.annotation else None} for arg in node.args.args]
        self.tools_by_name.setdefault(
            node.name,
            ToolInfo(
                name=node.name,
                function_name=node.name,
                signature=signature,
                docstring=ast.get_docstring(node),
                parameters=params,
                source_file=self.current_file,
            ),
        )

    def _record_function_note(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.raw_notes.setdefault("functions", []).append(
            {
                "name": node.name,
                "source_file": self.current_file,
                "line": str(getattr(node, "lineno", "")),
                "in_class": self.class_depth > 0,
                "docstring": ast.get_docstring(node),
            }
        )

    def _record_callsite(self, node: ast.Call, kind: str, full_name: str) -> None:
        self.raw_notes.setdefault("call_sites", []).append(
            {
                "kind": kind,
                "call": full_name,
                "source_file": self.current_file,
                "line": str(getattr(node, "lineno", "")),
                "snippet": shorten(_safe_unparse(node), 240),
            }
        )

    def _call_has_empty_mapping(self, call: ast.Call) -> bool:
        candidates = list(call.args)
        candidates.extend(kw.value for kw in call.keywords if kw.arg in {"agents", "agent_map", "agent_configs"} or kw.arg is None)
        if not candidates:
            return True
        for item in candidates:
            if isinstance(item, ast.Dict) and not item.keys:
                return True
            if isinstance(item, (ast.List, ast.Tuple)) and not item.elts:
                return True
        return False

    def _looks_like_tool_function(self, name: str) -> bool:
        lowered = name.lower()
        if lowered.startswith("_") or lowered in {"main", "emit"}:
            return False
        return lowered.endswith("_tool") or "tool" in lowered

    def _record_decorated_tool(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for deco in node.decorator_list:
            deco_name = _call_name(deco.func if isinstance(deco, ast.Call) else deco)
            if deco_name.endswith(("register_for_llm", "register_for_execution")):
                self.tools_by_name.setdefault(node.name, ToolInfo(name=node.name, function_name=node.name, source_file=self.current_file))

    def _extract_function_map_names(self, call: ast.Call) -> list[str]:
        names: list[str] = []
        node = _keyword(call, "function_map")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                key_value = _literal(key) if key else None
                if isinstance(key_value, str):
                    names.append(key_value)
                    if key_value not in self.tools_by_name:
                        self.tools_by_name[key_value] = ToolInfo(name=key_value, function_name=_last_name(value), source_file=self.current_file)
        return names

    def _extract_tool_list_names(self, call: ast.Call) -> list[str]:
        names: list[str] = []
        node = _keyword(call, "tools")
        if isinstance(node, (ast.List, ast.Tuple)):
            for item in node.elts:
                name = _literal(item)
                if isinstance(name, str):
                    names.append(name)
                else:
                    rendered = _last_name(item)
                    if rendered:
                        names.append(rendered)
        return names

    def _record_registration(self, call: ast.Call) -> None:
        owner_var = None
        if isinstance(call.func, ast.Attribute):
            owner_var = _var_name(call.func.value)
        tool_names = self._extract_function_map_names(call)
        explicit_name = _literal(_keyword(call, "name"))
        if isinstance(explicit_name, str):
            tool_names.append(explicit_name)
            self.tools_by_name.setdefault(explicit_name, ToolInfo(name=explicit_name, source_file=self.current_file))
        if not tool_names and call.args:
            rendered = _last_name(call.args[0])
            if rendered:
                tool_names.append(rendered)
        if owner_var and owner_var in self.agents_by_var:
            agent = self.agents_by_var[owner_var]
            for tool in tool_names:
                if tool and tool not in agent.tools:
                    agent.tools.append(tool)

    def _record_groupchat_edges(self, call: ast.Call) -> None:
        agents_node = _keyword(call, "agents")
        names: list[str] = []
        if isinstance(agents_node, (ast.List, ast.Tuple)):
            for item in agents_node.elts:
                var = _var_name(item)
                if var and var in self.agents_by_var:
                    names.append(self.agents_by_var[var].name)
                elif var:
                    names.append(var)
        for source in names:
            for target in names:
                if source != target:
                    self.edges.add(MessageEdge(source, target, "GroupChat potential route"))

    def _record_initiate_chat_edge(self, call: ast.Call) -> None:
        sender = None
        if isinstance(call.func, ast.Attribute):
            sender_var = _var_name(call.func.value)
            sender = self.agents_by_var.get(sender_var).name if sender_var in self.agents_by_var else sender_var
        receiver = None
        if call.args:
            receiver_var = _var_name(call.args[0])
            receiver = self.agents_by_var.get(receiver_var).name if receiver_var in self.agents_by_var else receiver_var
        if sender and receiver:
            self.edges.add(MessageEdge(sender, receiver, "initiate_chat"))

    def _attach_edges_from_group_managers(self) -> None:
        for agent in self.agents_by_name.values():
            if agent.tools:
                self.raw_notes.setdefault("agent_tool_links", {})[agent.name] = list(agent.tools)

    def _progress(self, message: str) -> None:
        if self.progress:
            self.progress(message)


def analyze_code(root_path: str | Path, progress: ProgressFn | None = None) -> dict[str, Any]:
    return CodeAnalyzer(root_path, progress=progress).analyze()
