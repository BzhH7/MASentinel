# MASentinel-X

面向智能体应用的自动化测试与缺陷管理平台前端演示项目。

## 技术栈

- Vue 3 + TypeScript + Vite
- Element Plus
- ECharts / vue-echarts
- Pinia
- Vue Router

## 运行

```bash
npm install
npm run dev -- --port 5173
```

浏览器打开：

```text
http://127.0.0.1:5173/
```

## Mock / 后端模式

默认连接 MASentinel Python 后端：

```env
VITE_USE_MOCK=false
VITE_API_BASE=/api
```

启动后端：

```bash
cd ..
python -m uvicorn backend.main:app --reload --port 8000
```

如需切回纯前端 mock 演示模式：

```env
VITE_USE_MOCK=true
```
