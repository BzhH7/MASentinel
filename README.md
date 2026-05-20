# MASentinel

MASentinel 是一个面向 AutoGen 类多智能体系统的语义覆盖驱动自动化测试框架。它能够从代码和 README 中抽取 agent、tool、requirement、message edge 和运行入口，自动生成测试用例，隔离执行目标系统，采集 trace，执行 oracle 判定、故障分类、误报审计，并生成 Markdown/HTML/网页化报告。

框架关注可通过修改被测系统代码、工具封装、消息编排、CLI 入口、文件处理逻辑或 AutoGen 配置缓解的软件缺陷。模型服务鉴权失败、外部 API 不可用、限流、网络超时、测试 harness 未触达目标 workflow 等问题会记录为 non-target/test-harness 证据，不计入目标故障数。

## 核心能力

- 代码与文档解析：构建 `SystemProfile`，识别 agent、tool、GroupChat、message edge、CLI、README 命令和文件/数据处理逻辑。
- 通用测试模式生成：覆盖 smoke、无人值守、终止信号、speaker selection、artifact、filesystem、resume、tool API/error、handoff、data invariant、CLI 文档一致性和 AutoGen wiring。
- Agentic planning + 确定性裁决：内部测试 agent 负责需求理解、测试规划、用例设计、诊断解释和报告草稿；ApplicabilityVerifier、oracle、代码证据和 trace 证据负责最终判断。
- 无人值守执行：通过 subprocess 隔离运行目标系统，注入 API 配置、argv/stdin/interactive response、runtime patch 和测试目录。
- 多智能体语义覆盖率：输出 AgentCov、ToolCov、EdgeCov、ReqVerifiedCov、ContractCov、TraceCompleteness、RootCauseEvidenceRate 和综合 MASCov。
- 报告与网页展示：生成每个系统的覆盖率、故障、误报审计、trace graph、dashboard 和项目总报告。

## 目录结构

```text
MASentinel/
  configs/                    # 三套系统与模型配置
  masentinel/
    analyzer/                 # README/源码/profile 构建
    agents/                   # 内部测试 agent
    generator/                # 测试模式选择与测例生成
    oracle/                   # 规则与契约 oracle
    diagnosis/                # 故障分类、去重、归因
    metrics/                  # 覆盖率计算
    runner/                   # subprocess 执行与 trace 采集
    reporter/                 # Markdown/HTML/项目报告
  runtime_patches/            # AutoGen runtime patch
  scripts/                    # API 入口、报告重建、网页生成
  tests/                      # 单元测试
  run_all.py                  # 三系统一键评测入口
```

## 安装

轻量开发和单测环境：

```bash
cd MASentinel
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

完整运行三套目标 AutoGen 系统建议使用运行环境依赖。若本机默认 Python 过新导致老版 AutoGen/LangChain 不兼容，可使用 Python 3.9/3.11/3.12 创建单独环境：

```bash
cd MASentinel
python3 -m venv .venv-runtime
source .venv-runtime/bin/activate
python -m pip install -r requirements-runtime.txt
```

## 模型与 API 配置

MASentinel 将模型分为两类：

- `testing_*`：MASentinel 内部测试 agent 使用，例如需求分析、测例设计、故障解释，默认可使用 `ds-v4-pro` 或 `deepseek-v4-pro`。
- `target_*`：注入给被测 AutoGen 系统运行，默认可使用 `ds-v4-flash`、`deepseek-v4-flash` 或本地 qwen2.5-coder。

建议把密钥放到环境变量，不要写进配置文件：

```bash
export INF_API_KEY_PRO="..."
export INF_API_KEY_FLASH="..."
export BOYUE_API_KEY="..."
export DEEPSEEK_API_KEY="..."
```

Boyue/OpenAI-compatible 网关：

```bash
python scripts/run_with_boyue_api.py \
  --config configs/all_systems.yaml \
  --testing-model deepseek-v4-pro \
  --target-model deepseek-v4-flash
```

官方 DeepSeek API：

```bash
python scripts/run_with_deepseek_official.py \
  --config configs/all_systems.yaml
```

如果接口只开放 pro，可临时把被测系统模型也指定为 pro：

```bash
python scripts/run_with_boyue_api.py \
  --config configs/all_systems.yaml \
  --target-model deepseek-v4-pro
```

如果网关支持 reasoning 或思考模式，可通过额外请求体开启，该参数只作用于 MASentinel 内部 testing agent：

```bash
export MAS_MODEL_EXTRA_BODY_JSON='{"reasoning_effort":"high"}'
# 或
export MAS_MODEL_EXTRA_BODY_JSON='{"enable_thinking":true}'
```

内部 agent API 调用可并行执行，建议从 3 或 4 开始：

```bash
export MAS_AGENT_API_WORKERS=4
```

## 配置被测系统

配置位于 `configs/`：

- `system1.yaml`：`AutoGen_IterativeCoding-main`
- `system2.yaml`：`research-agents-3.0-main`
- `system3.yaml`：`autogen-financial-analysis-main`
- `all_systems.yaml`：串联运行三套系统
- `toy.yaml`：不依赖 AutoGen 的最小演示系统

每个系统配置通常包含：

- `root_path`：被测系统源码目录
- `doc_path`：README 或需求文档
- `entrypoint`：入口文件
- `run.command`：subprocess 命令
- `run.input_mode`：`stdin`、`argv` 或 `interactive`
- `run.timeout_seconds`：单 case 超时
- `testing.num_cases`：目标测例数量

交互式程序可使用 prompt-response 自动应答：

```yaml
run:
  input_mode: interactive
  interaction:
    prompt_responses:
      - trigger: "Selection:"
        response: "1"
        max_count: 1
      - trigger: "What python creation would you like?"
        response: "{input}"
        max_count: 1
```

命令行参数型系统可在 `run.command` 中使用模板变量：

```yaml
run:
  command: "python main.py analyze {stock_symbol}"
  input_mode: argv
```

## 运行

运行 toy 闭环：

```bash
scripts/run_demo.sh
```

运行 toy 的 agentic 测试流程：

```bash
python -m masentinel.cli run-agentic \
  --config configs/toy.yaml \
  --out outputs/toy_agentic \
  --test-model ds-v4-pro
```

运行三套目标系统：

```bash
python run_all.py --config configs/all_systems.yaml --agentic --no-human
```

`run_all.py` 默认会清空每个系统的旧输出目录后再运行，避免 stale traces 或旧 regression cases 混入最终报告。如需保留历史输出和回归池，可加：

```bash
python run_all.py --config configs/all_systems.yaml --agentic --no-human --keep-output
```

分步运行单系统：

```bash
python -m masentinel.cli analyze \
  --config configs/system1.yaml \
  --out outputs/system1/profile.json

python -m masentinel.cli generate \
  --profile outputs/system1/profile.json \
  --num-cases 40 \
  --out outputs/system1/testcases.json

python -m masentinel.cli run \
  --config configs/system1.yaml \
  --testcases outputs/system1/testcases.json \
  --out outputs/system1/runs

python -m masentinel.cli diagnose \
  --profile outputs/system1/profile.json \
  --testcases outputs/system1/testcases.json \
  --traces outputs/system1/runs/traces \
  --out outputs/system1/faults.json

python -m masentinel.cli report \
  --profile outputs/system1/profile.json \
  --testcases outputs/system1/testcases.json \
  --traces outputs/system1/runs/traces \
  --faults outputs/system1/faults.json \
  --out outputs/system1/report
```

## 离线重建报告

如果修改了 oracle、coverage 或 fault classifier，希望不重跑被测系统、只基于已保存 trace 重新计算结果：

```bash
python scripts/rebuild_reports_from_outputs.py \
  --output-dir outputs \
  --project-report
```

该脚本会按当前 `test_plan.json` 过滤 stale case/trace，并写出 `suite_consistency_report.json`。若一致性报告中出现 `missing_selected_contract_patterns`，说明当前测试计划包含已有 trace 尚未覆盖的模式，需要 clean rerun。

也可以只重生成项目总报告：

```bash
python scripts/generate_project_report.py \
  --output-dir outputs \
  --config configs/all_systems.yaml
```

## 输出文件

```text
outputs/
  index.html
  summary.md
  项目报告.md
  project_report.agent.json
  site/index.html
  system1_iterative_coding/
    profile.json
    semantic_graph.json
    system_features.json
    test_plan.json
    testcases.generated.json
    testcases.validated.json
    testcases.executed.json
    runs/run_summary.json
    runs/traces/
    oracle_results.json
    faults.json
    fault_groups.json
    false_positive_audit.json
    non_target_issues.json
    test_harness_issues.json
    coverage.json
    trace_graph.json
    report.md
    report.html
    dashboard.html
    故障报告.md
```

## 最新结果快照

以下为当前最终网页报告口径的三系统汇总结果。`Cases` 表示生成测例数；进程通过/失败统计实际执行结果；Oracle 通过/失败采用目标故障口径，即排除 model provider、外部依赖、test harness、non-target 和 soft budget 等非目标问题后的判定结果。

| System | Cases | Proc Passed | Proc Failed | Oracle Passed | Oracle Failed | AgentCov | ToolCov | EdgeCov | ReqVerified | ContractCov | MASCov | Confirmed Primary Root Causes | Suspected/Partial | Non-target Excluded |
|--------|------:|------------:|------------:|--------------:|--------------:|---------:|--------:|--------:|------------:|------------:|-------:|-------------------------------:|------------------:|--------------------:|
| `system1_iterative_coding` | 28 | 20 | 4 | 20 | 8 | 1.00 | 1.00 | 0.71 | 0.25 | 0.50 | 0.71 | 6 | 5 | 11 |
| `system2_research_agents` | 36 | 25 | 7 | 28 | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 0.42 | 0.83 | 5 | 3 | 13 |
| `system3_financial_analysis` | 36 | 31 | 1 | 26 | 10 | 0.36 | N/A | 0.36 | 1.00 | 0.50 | 0.56 | 6 | 3 | 23 |
| **Total** | **100** | **76** | **12** | **74** | **26** | - | - | - | - | - | - | **17** | **11** | **47** |

## 覆盖率指标

- `AgentCov`：已访问 agent / 识别出的 agent。
- `ToolCov`：已调用 tool / 识别出的 tool；无统一注册工具时记为 N/A。
- `EdgeCov`：已观测消息边 / profile 中必需消息边。
- `ReqIntentCov`：测例设计意图覆盖到的需求比例。
- `ReqVerifiedCov`：至少被一个非阻塞且无目标故障用例有效验证的需求比例。
- `StateCov`：正常、异常、终止、非终止、工具失败、空输入等状态覆盖比例。
- `FaultCov`：已覆盖故障模式占目标故障模式集合的比例。
- `ContractCov`：已实例化并执行的契约 pattern 占适用契约 pattern 的比例。
- `TraceCompleteness`：trace 是否包含关键 agent/tool/message 事件。
- `RootCauseEvidenceRate`：confirmed fault 中具备代码证据或强 trace 证据的比例。
- `MASCov`：由 AgentCov、ToolCov、EdgeCov、ReqIntentCov、StateCov 和 FaultCov 加权得到的综合多智能体语义覆盖率。

MASCov 当前权重：

```text
MASCov =
  0.18 * AgentCov
+ 0.18 * ToolCov
+ 0.16 * EdgeCov
+ 0.16 * ReqIntentCov
+ 0.16 * StateCov
+ 0.16 * FaultCov
```

若某一维度不适用，例如 ToolCov 为 N/A，则该维度从分子和分母中同时剔除，并对剩余权重重新归一化。

## 故障范围

会计入 `faults.json` 的目标问题主要包括：

- 应用层：路径处理、文件产物、schema、resume、CLI 文档一致性、API 参数、分页、数据不变量等问题。
- AutoGen 框架层：human input 阻塞、speaker selection loop、handoff 只传递 TERMINATE、固定 max round 不适配任务规模、orchestrator/agent wiring 缺失等问题。

不会计入目标故障的问题包括：

- 模型服务鉴权失败、限流、网关超时。
- 外部 API 或第三方服务不可用。
- 测试 harness 未成功触达目标 agent/tool/message workflow。
- 纯粹的大模型回答质量、风格或知识准确性问题。

## 常见问题

### `HTTP 401 Unauthorized: Invalid token`

说明接口已经收到请求但拒绝 token。请确认环境变量不是示例占位符，并清理旧值：

```bash
unset BOYUE_API_KEY
export BOYUE_API_KEY="真实 sk token"
python scripts/run_with_boyue_api.py --config configs/all_systems.yaml
```

### DeepSeek V4 pro 偶发超时

可在 `configs/system*.yaml` 中增加超时和重试：

```yaml
model:
  testing_timeout_seconds: 90
  testing_retries: 3
```

如果仍失败，MASentinel 会记录 fallback，不中断整体评测。

### 本地 qwen/vLLM

如需使用本地 qwen2.5-coder 运行被测系统，可启动 OpenAI-compatible 服务：

```bash
MODEL_PATH=Qwen/Qwen2.5-Coder-7B-Instruct \
PORT=8001 \
scripts/start_qwen_h200.sh
```

核心框架不依赖 vLLM；没有模型服务时，部分步骤会自动使用确定性启发式和模板生成。

## 当前限制

- 完整运行三套目标 AutoGen 系统建议使用 Python 3.9/3.11/3.12；Python 3.13 下部分 AutoGen/金融依赖可能没有兼容 wheel 或版本声明。
- AST 和 README 解析采用保守启发式，部分潜在 message edge 需要结合 trace 和 false-positive audit 解读。
- HTTP tool error 若缺少 observed HTTP status 与结构化 tool result/error envelope，只作为 suspected/partial，不计入 confirmed primary root cause。
- runtime patch 能增强 AutoGen send/receive/tool/last_message trace；若目标系统绕开 patch 路径，TraceCompleteness 会下降。
