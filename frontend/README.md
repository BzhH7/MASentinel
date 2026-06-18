# MASentinel-X Frontend

面向智能体应用的自动化测试与缺陷管理平台前端。当前版本默认连接 `backend/main.py` 暴露的真实 REST API，读取 `outputs/<system_id>/` 下已经生成好的 MASentinel 测试数据。

## 启动顺序

必须先在仓库根目录启动后端：

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 18777
```

再启动前端：

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

浏览器打开：

```text
http://127.0.0.1:5173/
```

前端 Vite 代理默认把 `/api` 转发到 `http://127.0.0.1:18777`。如果你想换后端端口，在 `frontend/.env.local` 中设置：

```env
VITE_PROXY_TARGET=http://127.0.0.1:你的端口
```

## 默认演示数据

前端默认使用：

```text
system1_iterative_coding
```

作为首屏演示项目。也可以在项目、缺陷、报告等页面切换到后端扫描到的其他 `outputs/<system_id>/profile.json` 项目。

## 实时运行目标

`system1_iterative_coding`、`system2_research_agents`、`system3_financial_analysis` 默认用于展示仓库里已有的历史输出。如果要点击“创建运行任务”实时跑，建议使用内置的：

```text
toy_autogen_system
```

它指向仓库内 `examples/toy_autogen_system`，不依赖额外下载的目标项目。历史项目如果没有对应目标源码目录，后端会在启动前返回路径预检错误，而不是继续执行到 Trace 里才显示 Windows 目录异常。

## Mock 开关

默认走真实接口。只有显式设置下面变量时才启用前端 mock：

```env
VITE_USE_MOCK=true
```

未创建 `.env` 时不会回退假数据，会直接请求后端接口。

## 已接入的真实只读展示

- Dashboard：由 `GET /api/projects`、`GET /api/runs/{run_id}`、`GET /api/runs/{run_id}/results`、`GET /api/runs/{run_id}/coverage`、`GET /api/bugs?project_id=xxx` 在前端聚合生成。
- 项目管理：读取 `GET /api/projects` 和 `GET /api/projects/{system_id}`。
- 测试用例：读取 `GET /api/projects/{system_id}/testcases`。
- 测试运行：点击创建运行任务会调用 `POST /api/runs` 启动 MASentinel 后端实时任务，并轮询 `GET /api/jobs/{job_id}` 展示进度日志；完成后读取 `GET /api/runs/{run_id}` 和 `GET /api/runs/{run_id}/results` 刷新真实输出。
- Trace：必须选择具体 `case_id`，调用 `GET /api/runs/{run_id}/trace?case_id=xxx`。
- 缺陷管理：调用 `GET /api/bugs?project_id=xxx`，拖拽状态调用 `PUT /api/bugs/{bug_id}` 更新后端内存状态。
- 报告：调用 `GET /api/reports/{system_id}` 和 `GET /api/reports/{system_id}/file/{filename}` 预览真实 `report.html`、`dashboard.html`、Markdown 报告。

## 目前仍是占位的按钮

后端当前没有对应接口，所以这些按钮保留 UI，但点击会提示：

```text
演示版本：当前展示的是已完成的真实测试数据，该操作未接入实时执行
```

占位按钮包括：新建项目、保存项目、分析项目、自动生成用例、保存测试用例、导出报告。
