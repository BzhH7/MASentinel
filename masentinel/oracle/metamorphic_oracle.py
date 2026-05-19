from __future__ import annotations

from masentinel.schema import RunTrace, TestCase


def check_metamorphic_relation(testcase: TestCase, trace: RunTrace) -> list[str]:
    if testcase.case_type != "metamorphic":
        return []
    if trace.timeout:
        return ["Metamorphic case timed out before relation could be checked."]
    return []
