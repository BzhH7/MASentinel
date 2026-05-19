# MASentinel

MASentinel 是一个面向 AutoGen 多智能体系统的语义覆盖驱动自动化测试框架。它从代码和文档中抽取 agent、tool、requirement 和 message edge，按 “自动生成测例 -> 自动执行并判定 -> 自动诊断并报告” 三阶段运行，生成 requirement、coverage-guided、property-boundary、fuzz、tool-failure、metamorphic、regression 测试用例；运行阶段用 subprocess 隔离执行目标系统并采集 trace；诊断阶段使用规则 oracle 判断应用层和 AutoGen 集成层故障；最后输出覆盖率、故障报告和总览页面。

## 赛题对应关系

- 自动解析代码和文档：`masentinel/analyzer/`
- 自动生成测试用例：`masentinel/generator/`
- 自动运行测试：`masentinel/runner/`
- 自动诊断故障：`masentinel/oracle/`、`masentinel/diagnosis/`
- 语义覆盖率：`masentinel/metrics/coverage.py`
- Markdown/HTML 报告：`masentinel/reporter/`
- 三个系统一键流程：`run_all.py`

MASentinel 不把“大模型回答风格不好”“模型知识不准确”或模型服务鉴权/限流/超时直接判定为目标软件故障。`faults.json` 只保留可通过修改被测系统代码、工具注册/参数逻辑、提示模板、AutoGen 配置或框架适配缓解的应用层与 AutoGen 框架层问题；环境、测试框架和模型服务问题会写入 `non_target_issues.json` 作为解释依据，不计入目标故障数。

## 安装

轻量开发/单测环境：

```bash
cd MASentinel
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

完整运行三个目标 AutoGen 系统建议使用运行环境依赖。若本机默认 Python 过新导致老版 AutoGen/LangChain 不兼容，可使用 Python 3.9/3.11/3.12 单独创建运行环境：

```bash
cd MASentinel
python3 -m venv .venv-runtime
source .venv-runtime/bin/activate
python -m pip install \
  -i http://nexus.sii.shaipower.online/repository/pypi/simple \
  --trusted-host nexus.sii.shaipower.online \
  -r requirements-runtime.txt
```

验证：

```bash
python -m pytest -q
```

## 可选：启动 qwen/vLLM

命题 PDF 的模型分工是：

- 被测多智能体系统：`DeepSeek V4 flash (API)` 或 `qwen2.5-coder:7b (本地部署)`
- 自动化测试方案：`DeepSeek V4 pro (API)`

因此 `configs/*.yaml` 中分成两组配置：

- `testing_*`：MASentinel 自己用于文档需求抽取、可选 LLM judge 等，默认 `ds-v4-pro`
- `target_*`：传给被测 AutoGen 系统运行，默认 `ds-v4-flash`

运行被测系统时，MASentinel 不要求修改被测源码，而是在子进程环境中注入：

```text
OPENAI_API_KEY
OPENAI_BASE_URL
OPENAI_API_BASE
OAI_CONFIG_LIST
MAS_MODEL_NAME
MAS_TARGET_MESSAGE
```

同时通过 `runtime_patches/sitecustomize.py` 在启动时兼容常见 AutoGen/OpenAI 写法：写死的 OpenAI model 会被替换为 `target_model`，`GPTAssistantAgent` 可降级为普通 `AssistantAgent`，Docker、代码执行和人工输入也可由配置关闭。对于把任务硬编码到 `initiate_chat(message=...)` 的样例，可用 `run.message_template` 由 MASentinel 在运行时注入 `MAS_TARGET_MESSAGE` 并覆盖启动消息，不需要修改被测源码。`model_usage.json` 只统计 MASentinel 测试 agent 的调用；被测系统子进程侧的模型注入和 stdout/stderr 证据会单独写入 `target_model_usage.json`。

为避免“测试系统没适配好”被误算成被测系统缺陷，运行器会从 AutoGen stdout 中补充解析 `agent -> agent` 消息边，并通过 runtime patch 捕获 `initiate_chat/send/receive` 生成 `MAS_TRACE`。如果某个 case 没观测到有效 agent workflow，oracle 会把它归为 `TARGET_WORKFLOW_NOT_OBSERVED` 等 test-harness 问题并排除出应用层/AutoGen 框架故障。生成用例默认还会按 `testing.max_case_input_chars` 控制输入长度，防止超长 fuzz prompt 把 LLM 系统卡在启动阶段。

为了减少慢网关上的重复等待，静态 profile 阶段默认不调用模型抽取文档需求，而是先用启发式解析 README；agentic 流程后续仍会调用 `RequirementAnalystAgent` 做语义需求分析。确实需要在静态分析阶段也调用 pro，可显式开启：

```yaml
analyzer:
  doc_model_enabled: true
```

DeepSeek V4 pro 如果偶发超时，可以在 `configs/system*.yaml` 里调整：

```yaml
model:
  testing_timeout_seconds: 90
  testing_retries: 3
```

`testing_retries: 3` 表示失败后最多重试 3 次；如果仍失败，MASentinel 会记录 fallback，不中断整体评测。

如果 DeepSeek 网关支持“思考模式”或 reasoning 参数，MASentinel 测试 agent 可以通过额外请求体显式开启。不同 OpenAI-compatible 网关字段名不完全一致，因此默认不开启，可按接口文档选择一种方式：

```bash
export MAS_MODEL_EXTRA_BODY_JSON='{"enable_thinking":true}'
# 或者
export MAS_MODEL_EXTRA_BODY_JSON='{"reasoning_effort":"high"}'
```

也可以在 Boyue/DeepSeek 启动脚本上临时传入：

```bash
python scripts/run_with_boyue_api.py --config configs/all_systems.yaml --enable-thinking
python scripts/run_with_boyue_api.py --config configs/all_systems.yaml --reasoning-effort high
```

该参数只作用于 MASentinel 内部的 `testing_*` agent 调用；被测系统仍按题目要求注入 `target_model`，默认使用 flash 或本地 qwen。

建议设置两个环境变量，不要把密钥写进配置文件：

```bash
export INF_API_KEY_PRO="..."
export INF_API_KEY_FLASH="..."
```

如果本地有根目录的 `api.md`，也可以让 MASentinel 在运行进程内读取并映射密钥，不会打印密钥：

```bash
python scripts/run_with_api_md.py --config configs/all_systems.yaml --test-model ds-v4-pro
```

`run_with_api_md.py` 同时支持题目原始 `curl` 写法和新的 OpenAI SDK 写法，例如：

```python
from openai import OpenAI
client = OpenAI(
    base_url="https://apicz.boyuerichdata.com/v1/",
    api_key="sk-..."
)
```

如果使用新的 Boyue OpenAI-compatible 接口，建议优先把密钥放到环境变量，避免写入文件：

```bash
export BOYUE_API_KEY="..."
python scripts/run_with_boyue_api.py --config configs/all_systems.yaml
```

如果看到 `HTTP 401 Unauthorized: Invalid token`，说明接口已经收到请求但拒绝了 token。请确认 `BOYUE_API_KEY` 不是示例里的 `sk-...`/`sk-令牌` 占位符，并且当前 shell 里没有被旧值覆盖：

```bash
unset BOYUE_API_KEY
export BOYUE_API_KEY="真实 sk token"
python scripts/run_with_boyue_api.py --config configs/all_systems.yaml
```

默认会使用 `deepseek-v4-pro` 作为 MASentinel 测试 agent 模型，`deepseek-v4-flash` 注入给被测系统；如果该接口只开放 pro，可以临时指定：

```bash
python scripts/run_with_boyue_api.py --config configs/all_systems.yaml --target-model deepseek-v4-pro
```

如果题目提供的 API 网关较慢，也可以临时切到官方 DeepSeek API。注意官方 API 的模型名与题目网关不同，使用 `deepseek-v4-pro` / `deepseek-v4-flash`，不要混用 `ds-v4-pro`：

```bash
export DEEPSEEK_API_KEY="..."
python scripts/run_with_deepseek_official.py --config configs/all_systems.yaml
```

如果需要改为本地 qwen/vLLM 运行被测系统，可启动 OpenAI-compatible 服务：

```bash
MODEL_PATH=Qwen/Qwen2.5-Coder-7B-Instruct PORT=8001 scripts/start_qwen_h200.sh
```

核心框架不依赖 vLLM；没有模型服务时会自动使用确定性启发式和模板生成。

## 配置三个系统

配置位于 `configs/`：

- `system1.yaml`：`AutoGen_IterativeCoding-main`
- `system2.yaml`：`research-agents-3.0-main`
- `system3.yaml`：`autogen-financial-analysis-main`
- `all_systems.yaml`：串联运行三个系统
- `toy.yaml`：不依赖 AutoGen 的最小演示系统

每个系统配置包含：

- `root_path`：系统源码目录
- `doc_path`：README 或需求文档
- `entrypoint`：入口文件
- `run.command`：subprocess 命令
- `run.input_mode`：`stdin`、`argv` 或 `interactive`
- `run.timeout_seconds`：单 case 超时
- `testing.num_cases`：生成用例数

交互式程序可以使用 `run.input_mode: interactive`，runner 会读取 stdout 中的 prompt 并按配置自动应答：

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

Agentic 模式还会调用 `InteractionAdapterAgent` 分析入口代码中的 `input(...)` 和现有配置，生成 `interaction_adapter.json`。模型只允许建议 prompt-response 规则、case 级隔离目录和风险说明；最终执行仍由 runner 的确定性校验层控制。

对于命令行参数型系统，可在 `run.command` 中使用 `{input}`、`{safe_case_id}`、`{stock_symbol}` 等模板变量。例如金融分析系统会把每条 case 映射成不同股票代码：

```yaml
run:
  command: "python main.py analyze {stock_symbol}"
  input_mode: argv
```

## 一键运行

运行 toy 闭环：

```bash
scripts/run_demo.sh
```

运行 toy 的内部多智能体测试流程：

```bash
python -m masentinel.cli run-agentic \
  --config configs/toy.yaml \
  --out outputs/toy_agentic \
  --test-model ds-v4-pro
```

运行三个目标系统：

```bash
python run_all.py --config configs/all_systems.yaml --agentic --no-human
```

`run-agentic` 默认禁止人工介入，并在 `run_manifest.json` 中记录 `human_intervention_allowed: false`。如果目标系统请求 `input()` 或 AutoGen human input，runner 会记录 `HUMAN_INPUT_REQUESTED`。

也可以分步运行：

```bash
python -m masentinel.cli analyze --config configs/system1.yaml --out outputs/system1/profile.json
python -m masentinel.cli generate --profile outputs/system1/profile.json --num-cases 40 --out outputs/system1/testcases.json
python -m masentinel.cli run --config configs/system1.yaml --testcases outputs/system1/testcases.json --out outputs/system1/runs
python -m masentinel.cli diagnose --profile outputs/system1/profile.json --testcases outputs/system1/testcases.json --traces outputs/system1/runs/traces --out outputs/system1/faults.json
python -m masentinel.cli report --profile outputs/system1/profile.json --testcases outputs/system1/testcases.json --traces outputs/system1/runs/traces --faults outputs/system1/faults.json --out outputs/system1/report
```

## 输出文件

```text
outputs/
  index.html
  summary.md
  system1_iterative_coding/
    agent_trace.jsonl
    model_usage.json
    target_model_usage.json
    agentic_summary.json
    run_manifest.json
    profile.json
    semantic_graph.json
    testcases.generated.json
    testcases.validated.json
    testcases.frozen.sha256
    testcases.json
    testcases.executed.json
    runs/
      run_summary.json
      traces/
    oracle_results.json
    non_target_issues.json
    test_harness_issues.json
    faults.json
    fault_groups.json
    false_positive_audit.json
    coverage.json
    trace_graph.json
    dashboard.html
    patch_suggestions.md
    flaky_report.json
    report.md
    report.html
    fault_report.md
    coverage.md
```

## 覆盖率指标

- Agent Coverage：已访问 agent / 识别出的 agent
- Tool Coverage：已调用 tool / 识别出的 tool
- Message Edge Coverage：已观测消息边 / profile 中的消息边
- Requirement Coverage：有至少一条 case 覆盖的 requirement / requirements
- State Coverage：覆盖预定义状态，如 empty input、tool failure、termination、runtime exception
- Fault Mode Coverage：覆盖预定义故障模式，如 tool schema mismatch、missing tool call、message routing error
- MASCov：加权综合覆盖率

```text
MASCov =
0.18 * AgentCoverage
+ 0.18 * ToolCoverage
+ 0.16 * MessageEdgeCoverage
+ 0.16 * RequirementCoverage
+ 0.16 * StateCoverage
+ 0.16 * FaultModeCoverage
```

## 故障类型

规则 oracle 当前检测：

- `RUNTIME_EXCEPTION`
- `TIMEOUT`
- `NON_TERMINATION`
- `MISSING_AGENT`
- `MISSING_TOOL_CALL`
- `FORBIDDEN_TOOL_CALL`
- `MISSING_MESSAGE_EDGE`
- `OUTPUT_EMPTY`
- `OUTPUT_SCHEMA_VIOLATION`
- `REPETITIVE_LOOP`
- `TOOL_SCHEMA_MISMATCH`
- `TOOL_HALLUCINATION`
- `HUMAN_INPUT_REQUESTED`
- `METAMORPHIC_RELATION_VIOLATION`

诊断器只把应用层和 AutoGen 框架层问题写入 `faults.json`，并输出 root cause、suggested fix 和复现命令。模型服务、环境和测试框架问题会进入 `non_target_issues.json`，用于说明为什么未计入目标故障。

## 当前限制

- 完整运行三个目标 AutoGen 系统建议使用 Python 3.9/3.11/3.12 环境；Python 3.13 下部分 AutoGen/金融依赖可能没有兼容 wheel 或版本声明。
- 对任意第三方系统，默认能稳定采集 stdout/stderr、进程状态和 `MAS_TRACE:` 显式事件；更细的 AutoGen send/receive/tool trace 需要在目标进程里导入可选 monkey patch。
- AST 解析采用保守启发式，GroupChat 会生成潜在路由边，部分 missing edge 会标记为 suspected false positive。
- MASentinel 会通过配置和 runtime patch 注入目标模型、API key、stdin、非交互模式和离线/mock 数据源，尽量先让被测系统进入真实 agent workflow；仍缺失的外部服务、模型网关鉴权/限流/超时会记录为 non-target issue，而不会计入应用/框架故障。
- Agentic 模式会优先调用 DeepSeek V4 pro；API 不可用时会 fallback 到确定性工具，并在 `agent_trace.jsonl` 与 `model_usage.json` 中明确记录 fallback。被测系统侧默认注入 DeepSeek V4 flash，证据见 `target_model_usage.json` 与 `runs/run_summary.json`。
