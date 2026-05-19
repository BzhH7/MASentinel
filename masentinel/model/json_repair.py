from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str) -> dict[str, Any]:
    text = _escape_control_chars_in_strings(_strip_code_fence(text.strip()))
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    for candidate in _json_object_candidates(text):
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def _strip_code_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def _json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    starts = [index for index, char in enumerate(text) if char == "{"]
    for start in starts:
        depth = 0
        stack: list[str] = []
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
                stack.append("}")
            elif char == "[":
                stack.append("]")
            elif char == "}":
                depth -= 1
                if stack and stack[-1] == "}":
                    stack.pop()
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
            elif char == "]" and stack and stack[-1] == "]":
                stack.pop()
        if stack or in_string:
            candidates.append(_complete_partial_json(text[start:], stack, in_string, escape))
    if not candidates:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            candidates.append(match.group(0))
    return candidates


def _complete_partial_json(text: str, stack: list[str], in_string: bool, escape: bool) -> str:
    candidate = text.rstrip()
    if escape:
        candidate = candidate[:-1]
    if in_string:
        candidate += '"'
    candidate = re.sub(r",\s*$", "", candidate)
    while stack:
        closer = stack.pop()
        candidate = re.sub(r",\s*$", "", candidate)
        candidate += closer
    return candidate


def _escape_control_chars_in_strings(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for char in text:
        if escape:
            out.append(char)
            escape = False
            continue
        if char == "\\":
            out.append(char)
            escape = True
            continue
        if char == '"':
            out.append(char)
            in_string = not in_string
            continue
        if in_string and char == "\n":
            out.append("\\n")
        elif in_string and char == "\r":
            out.append("\\r")
        elif in_string and char == "\t":
            out.append("\\t")
        else:
            out.append(char)
    return "".join(out)
