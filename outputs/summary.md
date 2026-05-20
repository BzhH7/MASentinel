# MASentinel Summary

> Cases 表示生成测例数；Proc Passed/Failed 表示最终实际执行测例的进程结果；Oracle Passed/Failed 采用目标故障口径，已排除 model provider、外部依赖、test harness、non-target 和 soft budget 等非目标问题。

| System | Cases | Proc Passed | Proc Failed | Oracle Passed | Oracle Failed | AgentCov | ToolCov | EdgeCov | ReqIntent | ReqVerified | ContractCov | EffWorkflow | TraceComplete | EvidenceRate | MASCov | Confirmed Primary Root Causes | Derived Symptoms | Root Groups | Suspected FP | Non-target Excluded | Harness Excluded |
|--------|-------|-------------|-------------|---------------|---------------|----------|---------|---------|-----------|-------------|-------------|-------------|---------------|--------------|--------|-------------------------------|------------------|-------------|--------------|---------------------|------------------|
| system1_iterative_coding | 28 | 20 | 4 | 20 | 8 | 1.00 | 1.00 | 0.71 | 0.38 | 0.25 | 0.50 | 0.92 | 1.00 | 0.55 | 0.71 | 6 | 3 | 8 | 5 | 11 | 11 |
| system2_research_agents | 36 | 25 | 7 | 28 | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.42 | 1.00 | 0.67 | 0.88 | 0.83 | 5 | 1 | 7 | 3 | 13 | 13 |
| system3_financial_analysis | 36 | 31 | 1 | 26 | 10 | 0.36 | N/A | 0.36 | 1.00 | 1.00 | 0.50 | 0.97 | 1.00 | 0.90 | 0.56 | 6 | 2 | 8 | 3 | 23 | 16 |
