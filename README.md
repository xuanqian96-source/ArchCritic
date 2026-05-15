# ArchCritic

一个用于建筑设计课评图辅助的原型系统。  
现在已经能完成最基础的后端演示流程，并已把原来的 ArchCritic Demo 单文件界面作为本地前端入口。

## 项目功能简介

- 录入项目名称、建筑类型、提交人、年级和设计说明。
- 选择设计阶段后，点击“开始 AI 评图”会创建项目和方案提交记录。
- 点击图纸上传区可以选择本地图片，并按总平面图、一层平面、分析图、效果图分类查看；开始评图后，已选图纸会保存到后端。
- 自动创建项目和方案提交记录。
- 返回一份评图结果，包含总分、摘要、重点问题、建议和分项判断，并动态更新右侧报告；配置 OpenAI 或阿里云百炼后会调用真实功能与流线 Agent。
- 使用阿里云百炼时，系统会先把本地图纸上传为模型可读取的临时 `oss://` URL，再调用 `qwen3.6-plus`，避免 base64 直传图片导致超时。
- 右侧 AI 对话区支持流式显示模型生成过程，评图完成后同步更新报告区。
- 从 `wiki-test/wiki` 读取测试知识库依据，显示在“知识库追溯”区域。
- 底部历史版本和多 Agent 状态会根据后端返回结果更新。
- 页面可直接看到与早期演示 HTML 一致的三栏评图工作台界面。

## 技术架构

- 后端使用 FastAPI 提供接口。
- 项目、提交、图纸记录和报告数据保存在 SQLite 中，上传图片保存在本地 `uploads` 文件夹。
- 测试知识库依据从项目外层的 `wiki-test/wiki` 读取，后续可替换为正式知识库或检索服务。
- 前端使用 Vite 启动本地页面，目前入口已替换为原 ArchCritic Demo 的静态工作台界面。
- 评图结果支持三种模式：`mock` 用于本地演示，`openai` 和 `dashscope` 会调用真实功能与流线 Agent，读取设计说明、上传图纸和 Wiki 依据。
- 百炼真实评图不再把图片作为 base64 直接传给模型，而是使用百炼临时 OSS 文件 URL；数据库会缓存临时 URL 和过期时间，减少重复上传。

## 本地运行方法

### 后端

```bash
cd /mnt/e/claude/论文/ArchCritic/backend
test -d .venv || python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如需启用真实 GPT 评图，请在 `backend/.env` 中配置：

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=你的 OpenAI API Key
```

如需启用阿里云百炼评图，请在 `backend/.env` 中配置：

```env
LLM_PROVIDER=dashscope
LLM_MODEL=qwen3.6-plus
DASHSCOPE_API_KEY=你的百炼 API Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 前端

```bash
cd /mnt/e/claude/论文/ArchCritic/frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 `http://127.0.0.1:5173` 就能看到与 ArchCritic Demo 一致的本地前端界面。

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
npm run test
```

当前前端为静态页面，暂无完整自动化测试；本阶段以构建检查和关键交互检查为主。

## 搜索记录

- 本阶段没有为 ArchCritic 的实现方案进行外部搜索，主要基于现有开发计划和仓库状态继续推进。

## 已完成功能列表

- 后端健康检查接口。
- SQLite 数据模型和基础数据库初始化。
- 项目创建与列表接口。
- 方案提交接口。
- 年级字段保存。
- 图纸上传、图纸列表和静态图片访问。
- 单个项目详情、项目提交历史、单次提交详情和报告查询接口。
- Wiki 测试知识库依据读取接口。
- 演示评图结果接口；配置 OpenAI 或阿里云百炼后同一接口会调用真实功能与流线 Agent。
- 功能与流线 Agent v1：按功能满足、功能分区、流线分析、平面丰富性四项评分，并要求模型标注图纸识别不确定内容。
- 百炼临时 OSS 图纸链路：上传本地图纸获得模型可访问 URL，解决 base64 图片直传导致的超时问题。
- 右侧 AI 对话流式输出：新增流式评图接口，前端能实时看到模型生成内容，并在结束后渲染报告。
- ArchCritic Demo 静态工作台界面已接入本地前端入口。
- 左侧项目信息、设计阶段选择、本地图片上传、中间图纸查看、后端保存、右侧报告动态渲染、历史版本和知识库追溯已具备前端交互。
- Demo 后端产品设计文档：`docs/plans/2026-05-12-demo-backend-product-design.md`。
- 后端与前端基础测试。

## 待办事项

- 继续用更多真实学生图纸验收百炼模型的图纸识别和建筑学评价稳定性。
- 增加更完整的知识库检索和多 Agent 协作流程。
- 后续生产部署时，把百炼临时 OSS 换成正式对象存储和更稳定的文件缓存策略。
