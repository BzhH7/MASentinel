from masentinel.reporter.project_report import collect_project_evidence, render_project_report, render_system_fault_report
from masentinel.utils import write_json


def test_project_report_contains_required_competition_sections(tmp_path) -> None:
    system_dir = tmp_path / "system_demo"
    write_json(
        system_dir / "coverage.json",
        {
            "agent_coverage": 1.0,
            "tool_coverage": 0.5,
            "message_edge_coverage": 0.25,
            "requirement_coverage": 0.75,
            "state_coverage": 0.5,
            "fault_mode_coverage": 0.5,
            "mascov": 0.6,
        },
    )
    write_json(
        system_dir / "faults.json",
        [
            {
                "fault_id": "F1",
                "case_id": "C1",
                "layer": "application",
                "fault_type": "Missing Tool Call",
                "severity": "medium",
                "confidence": 0.8,
                "summary": "Expected tool was not called.",
                "suspected_false_positive": False,
            }
        ],
    )

    evidence = collect_project_evidence(tmp_path, [])
    report = render_project_report(evidence, {"system_analyses": [], "next_steps": ["继续改进 trace 采集。"]})

    assert "## 算法代码与说明文档" in report
    assert "## 方案设计" in report
    assert "## 测试覆盖率指标设计" in report
    assert "## 三个多智能体系统测试覆盖率与结果汇总" in report
    assert "## 故障报告" in report
    assert "## 效果分析" in report
    assert "## 下一步改进计划" in report
    assert f"`{tmp_path}/`" in report
    assert "system_demo" in report
    assert "system_demo/故障报告.md" in report


def test_system_fault_report_is_per_target_system(tmp_path) -> None:
    system_dir = tmp_path / "system_demo"
    write_json(system_dir / "coverage.json", {"mascov": 0.6})
    write_json(
        system_dir / "faults.json",
        [
            {
                "fault_id": "F1",
                "case_id": "C1",
                "layer": "application",
                "fault_type": "Missing Tool Call",
                "severity": "medium",
                "confidence": 0.8,
                "summary": "Expected tool was not called.",
                "suggested_fix": "Register the tool.",
                "suspected_false_positive": False,
            }
        ],
    )
    evidence = collect_project_evidence(tmp_path, [])
    report = render_system_fault_report(evidence["systems"][0], {})

    assert "# MASentinel 故障报告：system_demo" in report
    assert "## 覆盖率" in report
    assert "#### 真实故障 / 确认主根因" in report
    assert "F1" in report
