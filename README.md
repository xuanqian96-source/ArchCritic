# ArchCritic

一个用于建筑设计课评图辅助的原型系统。  
现在已经能完成最基础的演示流程：录入项目内容、提交方案、生成一份结构化评图结果，并在网页中直接展示。

## 项目功能简介

- 录入项目名称、建筑类型、提交人和设计说明。
- 自动创建项目和方案提交记录。
- 返回一份演示评图结果，包含总分、摘要、重点问题、建议和分项判断。
- 页面可直接看到后端状态和最近项目列表。

## 技术架构

- 后端使用 FastAPI 提供接口。
- 数据保存在 SQLite 中，先满足 P0 基础验证。
- 前端使用 React + Vite 提供可视化验证页面。
- 评图结果目前由演示模型生成，后续再替换为真实多 Agent 和 RAG 能力。

## 本地运行方法

### 后端

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
test -d .venv || python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 `http://127.0.0.1:5173` 就能看到验证页面。

## 部署方法和命令

当前阶段以本地开发验证为主，还没有正式部署脚本。  
如需打包前端，可执行：

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend
npm run build
```

## 测试方法和常用命令

### 后端测试

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
./.venv/bin/pytest
```

### 前端测试

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend
npm run test -- --run
```

## 搜索记录

- 本阶段没有为 ArchCritic 的实现方案进行外部搜索，主要基于现有开发计划和仓库状态继续推进。

## 已完成功能列表

- 后端健康检查接口。
- SQLite 数据模型和基础数据库初始化。
- 项目创建与列表接口。
- 方案提交接口。
- 演示评图结果接口。
- 可视化前端验证界面。
- 后端与前端基础测试。

## 待办事项

- 接入真实单 Agent Prompt 和输出解析。
- 把演示评图结果替换成真实模型返回。
- 增加图像上传、知识库和多 Agent 协作流程。
