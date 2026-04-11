# ArchCritic 架构说明

## 文件与模块职责

- `backend/app/main.py`：后端入口，负责启动服务、挂载中间件和接口。
- `backend/app/config.py`：读取系统配置。
- `backend/app/database.py`：创建数据库连接和会话。
- `backend/app/models.py`：定义项目、提交、评图结果等数据表。
- `backend/app/schemas.py`：定义接口输入输出格式。
- `backend/app/routers/health.py`：提供健康检查接口。
- `backend/app/routers/projects.py`：负责项目创建和项目列表。
- `backend/app/routers/submissions.py`：负责方案提交和演示评图。
- `backend/app/llm/base.py`：定义模型调用统一接口。
- `backend/app/llm/client.py`：根据配置返回演示模型或真实模型客户端。
- `backend/app/llm/openai_client.py`：封装真实 OpenAI 调用入口。
- `frontend/src/App.jsx`：前端主页面，负责表单、请求和结果展示。
- `frontend/src/main.jsx`：挂载 React 页面。
- `frontend/src/styles.css`：定义界面样式。
- `frontend/src/App.test.jsx`：验证页面可以提交并显示结果。

## 模块之间的调用关系

- 前端页面先请求后端健康检查和项目列表。
- 用户提交表单后，前端依次调用“创建项目”“提交方案”“生成演示评图”三个接口。
- 提交接口把数据写入 SQLite。
- 评图接口调用演示模型客户端生成结构化结果，再写回数据库并返回给前端。

## 关键设计决定和原因

- 当前数据库先使用 SQLite，原因是 P0 目标是先把最小闭环跑通。
- 当前评图先使用演示结果，原因是先验证提交流程和界面展示，不在 P0 阶段追求真实学术评图质量。
- OpenAI 客户端采用延迟导入，原因是避免在演示模式下拖慢应用启动。
- 前端脚本直接调用本地 `node_modules` 中的 Vite 和 Vitest，原因是当前环境下可执行脚本权限不稳定，这种写法更稳。
