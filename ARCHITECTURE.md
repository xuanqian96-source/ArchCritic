# ArchCritic 架构说明

## 文件与模块职责

- `backend/app/main.py`：后端入口，负责启动服务、挂载中间件和接口。
- `backend/app/config.py`：读取系统配置，包括数据库、跨域和上传目录。
- `backend/app/database.py`：创建数据库连接和会话，并为旧 SQLite 数据库补齐新增字段。
- `backend/app/models.py`：定义项目、提交、图纸文件和评图结果等数据表。
- `backend/app/schemas.py`：定义接口输入输出格式。
- `backend/app/wiki.py`：读取 `wiki-test/wiki` 中的测试知识库文件，并整理为前端可显示的依据。
- `backend/app/agents/function_agent.py`：整理提交信息、图纸和 Wiki 依据，调用功能与流线 Agent，并校验模型输出。
- `backend/app/agents/image_payload.py`：在必须使用 base64 兜底时处理模型图片 payload。
- `backend/app/agents/prompts/function_agent_v1.py`：保存功能与流线 Agent v1 的系统提示词、输出结构和用户提示词模板。
- `backend/app/routers/health.py`：提供健康检查接口。
- `backend/app/routers/projects.py`：负责项目创建、项目列表、项目详情和提交历史。
- `backend/app/routers/submissions.py`：负责方案提交、图纸上传、图纸列表、报告查询、Wiki 依据查询和评图调用。
- `backend/app/llm/base.py`：定义模型调用统一接口。
- `backend/app/llm/client.py`：根据配置返回演示模型或真实模型客户端。
- `backend/app/llm/dashscope_files.py`：调用百炼上传策略接口，把本地图纸上传为模型可读取的临时 `oss://` URL。
- `backend/app/llm/openai_client.py`：封装 OpenAI 兼容调用入口，当前支持 OpenAI 和阿里云百炼，并把功能 Agent 结果转换为前端报告结构。
- `frontend/index.html`：当前本地前端入口，承载 ArchCritic Demo 工作台界面、项目信息更新、本地图片上传、后端保存和图纸查看交互。
- `frontend/package.json`：前端运行脚本，当前只保留静态 Vite 页面所需配置。
- `frontend/vite.config.js`：Vite 本地开发配置。
- `docs/plans/2026-05-12-demo-backend-product-design.md`：按当前前端界面梳理后端模块、接口、用户流程和 Demo 开发顺序。

## 模块之间的调用关系

- 左侧表单点击“开始 AI 评图”后，会把项目名称、建筑类型和设计阶段同步到顶部导航，并请求后端创建项目、创建提交、上传图纸和生成演示报告。
- 图纸选择先在浏览器本地预览，开始评图后上传到后端，后端返回 `/uploads/...` 图片地址并继续用于中间图纸区显示。
- 项目、提交、图纸文件和报告接口把数据写入 SQLite；历史版本从同一项目下的提交和报告中读取。
- 评图接口在 `mock` 模式下调用演示模型；在 `openai` 或 `dashscope` 模式下整理提交、图纸和 Wiki 依据，调用功能与流线 Agent，再写回数据库并返回给前端。
- `dashscope` 模式会先把本地图纸上传到百炼临时 OSS，并把 `oss://` URL 缓存在图纸记录中；模型调用时通过 URL 读取图纸，不再使用 base64 直传作为主链路。
- 流式评图接口通过 SSE 把模型输出片段推送给前端，前端右侧 AI 对话区实时追加文本，最终收到报告后再渲染报告视图。
- Wiki 依据接口按设计阶段读取 `wiki-test/wiki/评价维度/...` 下的 Markdown 文件，整理标题、来源类型和摘要后返回前端。

## 关键设计决定和原因

- 当前数据库先使用 SQLite，原因是 P0 目标是先把最小闭环跑通。
- 当前评图先使用演示结果，原因是先验证提交流程和界面展示，不在 P0 阶段追求真实学术评图质量。
- 当前优先把 ArchCritic Demo 作为前端基础，原因是先统一演示界面，再逐步把真实后端接口接回页面。
- 上传文件先保存在本地 `uploads` 目录，原因是当前目标是稳定演示和本地验证，不急于引入对象存储。
- 第二、三步先复用 `wiki-test/wiki` 作为演示知识库，原因是已有测试数据可用，避免重复生成一套临时依据。
- 旧 React 验证页已删除，原因是当前阶段只保留一套前端入口，减少维护混乱。
- OpenAI 客户端采用延迟导入，原因是避免在演示模式下拖慢应用启动。
- OpenAI 客户端禁用系统代理环境变量，原因是当前开发环境代理会导致 SDK 连接 OpenAI API 时被断开。
- 阿里云百炼采用 OpenAI 兼容接口接入，原因是可以复用现有图文输入和功能 Agent 逻辑；图纸图片先上传为百炼临时 OSS URL，原因是 base64 直传在真实测试中多次超时，而 URL 调用能在约十几秒完成图纸识别。
- 右侧 AI 对话采用流式输出，原因是用户需要看到模型正在工作，避免界面长时间停在 90%。
- 第一个真实 Agent 先做功能与流线，原因是它能直接使用现有 Wiki 测试知识库，并且最适合验证“图文输入、结构化输出、前端报告显示”的完整链路。
- 前端脚本直接调用本地 `node_modules` 中的 Vite，原因是当前环境下可执行脚本权限不稳定，这种写法更稳。
