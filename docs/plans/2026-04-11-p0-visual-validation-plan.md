# ArchCritic P0 Visual Validation Implementation Plan

> **Execution:** REQUIRED SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补全 ArchCritic 的 P0 基础设施，并提供一个可视化前端验证界面。

**Architecture:** 后端继续使用 FastAPI 和 SQLite，先提供项目、提交和演示评图接口。前端使用 React + Vite，直接调用后端接口显示结果，先用演示数据跑通完整闭环。

**Tech Stack:** Python 3.10 + FastAPI + SQLAlchemy + SQLite + pytest | React 18 + Vite

---

### Task 1: 后端数据层与测试

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/test_database.py`

先写失败测试，再补数据库初始化、基础模型和数据结构。

### Task 2: 后端业务接口与演示评图

**Files:**
- Create: `backend/app/routers/projects.py`
- Create: `backend/app/routers/submissions.py`
- Create: `backend/app/llm/base.py`
- Create: `backend/app/llm/client.py`
- Create: `backend/app/llm/openai_client.py`
- Create: `backend/tests/test_projects.py`
- Create: `backend/tests/test_submissions.py`
- Create: `backend/tests/test_llm.py`

先让测试失败，再补项目创建、提交方案、生成演示评图结果的接口。

### Task 3: 前端界面与联调

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/styles.css`

先补页面结构，再接后端接口，最后验证浏览器可看到完整结果。

### Task 4: 文档与收尾验证

**Files:**
- Create: `CONTEXT.md`
- Create: `ARCHITECTURE.md`
- Modify: `README.md`

更新当前进度、运行方法和模块关系，最后运行后后端与前端验证命令。
