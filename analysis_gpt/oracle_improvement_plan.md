# MASentinel Improvement Plan

## 1. Test Case Generator Improvements

Add tests that target code/config contracts, not only natural-language success paths.

### system_1: iterative coding

| Case | user_input | Expected behavior | Assertions |
|---|---|---|---|
| Code fence variants | Ask for a one-line Python script, with mocked coder output using ``` without language and ```py. | Valid fenced Python source is saved without corruption. | Saved script compiles, first code token is preserved, no fence markers remain. |
| Partial resume state | Pre-create `MasterPlan.txt` and `script_v1.py`, omit `comments_v1.log`, then continue the project. | System resumes from latest script or reports incomplete state. | Coder prompt includes script_v1.py, existing file is not silently overwritten. |
| Artifact schema | Run one complete iteration. | Review artifact matches profile/docs. | Generated filename matches expected `comments_v1.txt` or profile declares `.log`. |
| Unsafe project name | Enter `../escaped_project` as project name. | Input is rejected. | No write occurs outside `IterCode_Projects`. |

### system_2: research agents

| Case | user_input | Expected behavior | Assertions |
|---|---|---|---|
| Airtable view URL | Use a URL with base, table, view, and more than 100 records. | Tool reads exactly the view and follows pagination. | Trace has view parameter, offset loop, and expected record count. |
| Search API failure | Run with invalid SERPER key. | Tool returns structured error and workflow stops or retries explicitly. | HTTP status and error body captured; raw error text is not treated as search result. |
| Browserless failure | Run with invalid Browserless token. | Tool returns structured error, not `None`. | Trace records tool error result and downstream agent does not continue as if content exists. |
| Multi-record round budget | Use five company records. | All records are searched and updated or work is batched in a tool. | Termination reason is completion, not `max_round`. |

### system_3: financial analysis

| Case | user_input | Expected behavior | Assertions |
|---|---|---|---|
| Simple handoff | `python simple_autogen/main.py analyze AAPL --output out.json` | Downstream agents receive substantive prior analysis. | No forwarded prompt contains only `TERMINATE`; final advice does not claim missing data when data exists. |
| Partial financial rows | Mock financials with revenue and net income but no total debt. | Available metrics are computed; unavailable metrics are null/flagged. | Revenue/profit margin nonzero; missing row recorded. |
| Risk sign convention | Mock price series with known drawdown. | VaR and drawdown match documented sign convention. | Positive magnitudes unless explicitly labeled signed. |
| Documented enterprise entrypoint | `python -m src.main analyze AAPL` | Imports and initialization succeed or fail with controlled dependency/config message. | No class/method/constructor mismatch. |
| Documented CLI commands | `python -m src.main interactive` and `python -m src.main portfolio ...` | Documented commands are accepted and dispatched. | Parser help lists the commands; dispatcher branches are reachable. |
| Enterprise AutoGen wiring | Run `src.main analyze` with mocked dependencies. | Enterprise agents are created and orchestrated. | AgentOrchestrator has non-empty agents; trace contains data, financial, risk, and recommendation agent messages. |

## 2. Runner / Trace Improvements

Record enough structure to diagnose AutoGen routing and application-tool contracts.

Required trace additions:

- Command context: exact command, cwd, env overrides, timeout, input template, parsed arguments, exit code, stdout/stderr tail.
- Message envelope: sender name, receiver name, role, content hash, full content path, turn index, conversation id, and whether the message was assistant output, user proxy auto-reply, tool result, or termination marker.
- `last_message()` provenance: when code reads `agent.last_message()`, record which sender produced the returned message. This would catch system_3 forwarding `TERMINATE`.
- Tool call envelope: tool name, registered caller/executor, schema, arguments, result, status, exception type, HTTP status code if applicable, duration, and whether the result was structured.
- Speaker selection: candidate speakers, selected speaker, raw selector output, validation error if any, allowed/disallowed transition rule, retry count.
- Termination: exact termination condition hit, max_round exhaustion, timeout, human_input_requested, or explicit `TERMINATE`.
- Filesystem effects: files created/modified under expected roots and any writes outside configured project directories.
- External API mocks: request URL, query params such as Airtable `view` and `offset`, page count, and fixture identity.

Implementation direction:

- Wrap AutoGen agent `send`, `receive`, tool execution, and group-chat speaker selection hooks in one normalized event collector.
- Store large message/tool bodies as sidecar files and put hashes plus short previews in JSON traces.
- Add a per-test `expected_mode` field such as `interactive`, `unattended`, or `cli-only`; human-input or timeout rules should use that mode.

## 3. Oracle Improvements

### New rules to add

| Rule | Target | Failure condition |
|---|---|---|
| Markdown code persistence | system_1 | Saved Python differs structurally from coder code block or fails compilation after valid fenced output. |
| Resume-state consistency | system_1 | Existing script version is ignored when continuing a project. |
| Artifact schema conformance | system_1 | Generated artifact names differ from docs/profile without an explicit override. |
| Safe project root | system_1 | Any user-controlled project name resolves outside the configured root. |
| Airtable URL semantics | system_2 | View id from URL is ignored, or pagination stops before all records. |
| Structured tool errors | system_2 | Tool returns raw HTTP error text, `None`, or untyped exception for external API failure. |
| Scalable turn budget | system_2 | Required record count implies more tool actions than `max_round` permits. |
| Message-handoff integrity | system_3 | Downstream agent prompt receives only `TERMINATE`, empty content, or an auto-reply instead of prior assistant analysis. |
| Partial metric preservation | system_3 | One missing financial row zeros unrelated available metrics. |
| Risk sign convention | system_3 | VaR/drawdown sign conflicts with documented/report convention. |
| Documented entrypoint conformance | system_3 | README command fails from import, constructor, parser, or nonexistent method mismatch. |
| AutoGen wiring conformance | system_3 | Documented agent workflow initializes an empty orchestrator or bypasses agents entirely. |

### Assertions to relax

- Missing `write_settled_plan` should not be asserted until the trace shows a valid complete plan and manager approval.
- Missing arbitrary group-chat edges, such as `director->research_manager`, should not be a failure unless the edge is part of a declared workflow invariant.
- Timeout should be treated as a symptom unless linked to a specific prior event: human input request, speaker-selection loop, max_round exhaustion, or unhandled exception.
- Missing data-provider/tool registration should not be concluded if data was collected outside agents and later lost during message handoff.

### Assertions to strengthen

- Require report IDs to include the triggering input, exact command, minimal trace slice, and code/config location when available.
- For tool-related failures, require tool args and tool results, not only absence/presence of a tool call.
- For framework failures, require speaker transition evidence and termination reason.
- For output-format failures, compare docs/profile expected artifacts against actual filesystem output.

## 4. Diagnoser Improvements

Diagnose from symptom to code/config through a small causal checklist.

Recommended diagnosis flow:

1. Classify failure mode from trace: human input, speaker selection, timeout, tool error, message handoff, output artifact, CLI/runtime error.
2. Locate the nearest deterministic source:
   - human input: `UserProxyAgent` config.
   - speaker loop: `GroupChat` manager/speaker selection config.
   - missing tool behavior: registration map, tool schema, caller/executor pair, tool args/result.
   - wrong downstream content: message provenance and `last_message()` call sites.
   - CLI failure: parser, imports, constructor signatures, documented commands.
3. Check whether the model had a fair contract:
   - If required data/tool/schema was unavailable, classify code/framework.
   - If prompts and tools were correct but answer quality varies, classify as model-output uncertainty, not system defect.
4. Use static evidence before final root cause:
   - grep the reported function/class/method.
   - verify the line exists and the called method exists.
   - match trace agent names to configured agents.
   - match docs/profile expected output to code-generated output.
5. Deduplicate by root cause:
   - speaker-selection loops and timeouts from the same trace should cluster under the routing defect.
   - downstream missing-data messages in system_3 should cluster under message-handoff if collected data was present earlier.

Concrete diagnoser changes:

- Add a "root-cause confidence" field with values `code_evidence`, `trace_only`, `oracle_assumption`, and `uncertain`.
- Add a "not model fault because" field to each failure report.
- Add code-location extraction for common AutoGen APIs: `UserProxyAgent`, `GroupChat`, `GroupChatManager`, `register_for_llm`, `register_for_execution`, `function_map`, `speaker_selection_method`, `is_termination_msg`, and `max_round`.
- Compare target config entrypoint against README entrypoint. If MASentinel tests a simplified entrypoint, label enterprise README defects as out-of-scope rather than silently missing them.
- For partial failures, preserve both symptom and corrected root cause. Example: system_3 should read "downstream agents report missing data because prior analysis was forwarded as TERMINATE", not "data collection tool registration missing".

