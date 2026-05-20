from __future__ import annotations

from masentinel.generator.patterns.base import base_metadata, has_any, limited, profile_text
from masentinel.schema import SystemProfile, TestCase, TestOracleSpec


class DataInvariantPattern:
    name = "data_invariant"
    case_type = "data_invariant"
    fault_modes = ["partial_metric_zeroed", "numeric_sign_convention_error"]

    def applicable(self, profile: SystemProfile) -> bool:
        text = profile_text(profile)
        return has_any(
            text,
            (
                "pandas",
                "dataframe",
                "financials",
                "balance sheet",
                "income statement",
                "stock",
                "ticker",
                "yfinance",
                "finance",
                "financial",
                "risk",
                "returns",
                "drawdown",
                "sharpe",
                "var_95",
                "value at risk",
                "total revenue",
                "net income",
                "财务",
                "股票",
                "风险",
            ),
        )

    def instantiate(self, profile: SystemProfile, budget: int | None = None) -> list[TestCase]:
        cases = [
            TestCase(
                case_id=f"{profile.system_id}_DATAINV_001",
                system_id=profile.system_id,
                case_type=self.case_type,
                objective="Available financial metrics should be preserved when one optional row is missing.",
                input="Analyze a mocked ticker where Total Revenue and Net Income exist but Total Debt is missing.",
                oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=30),
                metadata={
                    **base_metadata("partial_data_invariant", "profile contains financial/dataframe metric calculations", "partial_metric_zeroed"),
                    "fixture": {
                        "mock_data_fixture": "partial_financial_rows",
                        "financials": {"Total Revenue": 1000, "Net Income": 100, "Total Debt": None},
                    },
                    "stock_symbol": "AAPL",
                    "assertions": ["available_metrics_nonzero", "missing_metric_null_or_unavailable", "missing_row_recorded"],
                },
            ),
            TestCase(
                case_id=f"{profile.system_id}_DATAINV_002",
                system_id=profile.system_id,
                case_type=self.case_type,
                objective="Risk metrics should follow the documented numeric sign convention.",
                input="Analyze a mocked price series with known drawdown and negative 5th percentile daily return.",
                oracle=TestOracleSpec(must_terminate=True, must_not_crash=True, max_turns=30),
                metadata={
                    **base_metadata("numeric_sign_convention", "profile contains risk/return/drawdown calculations", "numeric_sign_convention_error", "medium"),
                    "fixture": {"mock_price_fixture": "known_drawdown"},
                    "stock_symbol": "AAPL",
                    "assertions": ["var_95_nonnegative_if_magnitude", "max_drawdown_nonnegative_if_magnitude"],
                },
            ),
        ]
        return limited(cases, budget)
