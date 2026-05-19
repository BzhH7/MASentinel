from masentinel.model.json_repair import parse_json_object


def test_parse_json_object_recovers_partial_agent_json() -> None:
    raw = (
        '{ "testcases": [ { "case_id": "SYS_REQ_001", '
        '"case_type": "requirement_positive", '
        '"objective": "Verify planner approval.", '
        '"input": "Manager: \\"We need a calculator app.\\" Planner: \\"I understand. The main challenges ar'
    )

    parsed = parse_json_object(raw)

    assert parsed["testcases"][0]["case_id"] == "SYS_REQ_001"
    assert parsed["testcases"][0]["input"].endswith("ar")


def test_parse_json_object_escapes_newlines_inside_strings() -> None:
    raw = '{"testcases": [{"case_id": "C1", "input": "line1\nline2"}], "confidence": 0.8}'

    parsed = parse_json_object(raw)

    assert parsed["testcases"][0]["input"] == "line1\nline2"
    assert parsed["confidence"] == 0.8
