# ArchCritic

一个用于建筑设计课评图辅助的本地系统。
现在使用新版 React 前端和 FastAPI 后端完成从注册登录、提交任务书与图纸、多 Agent 评图到历史报告查看的完整流程。

当前版本：`v0.4.0-research.1`（证据化评图与论文实验工具）。

## 项目功能简介

- 录入项目名称、建筑类型、提交人、年级和设计说明。
- 官网首页点击“体验产品”后，首次使用会进入注册页；之后使用本地账户登录，每个账户只看到自己的项目、图纸和历史报告。
- 选择设计阶段后，系统会自动启用对应 Agent：概念阶段侧重场地、形式与设计概念；方案阶段评审功能、场地、形式与结构；图纸阶段增加图面表达评审。
- 上传 PDF、DOCX 或 TXT 任务书后，后端会提取正文，把具体要求交给每个 Agent，并根据任务书重点、弱化要求和年级调整各项评分占比。
- 点击图纸上传区可以选择多张本地图片，并按总平面图、一层平面、分析图、效果图分类查看；开始评图后，系统保留原图，并为包含多个独立图纸区域的平面或技术图限量生成辅助裁切图。
- 自动创建项目和方案提交记录。
- 返回一份评图结果，包含总分、摘要、重点问题、建议和分项判断，并动态更新右侧报告；当前产品通过阿里云百炼 `qwen3.8-max` 调用对应专项 Agent、综合评审 Agent 并生成最终报告。
- 使用阿里云百炼时，系统会先把本地图纸上传为模型可读取的临时 `oss://` URL，再调用 `qwen3.8-max`，避免 base64 直传图片导致超时。
- 百炼临时图纸上传带有重试机制；流式输出中断时会自动改用非流式结构化评图兜底。
- 本地私有基准集支持一键生成匿名逐页输入、运行真实多 Agent 回归、计算教师分误差与语义指标，并导出 CSV、JSON、SVG 图表和论文报告；私有图纸与结果默认不进入 Git。
- 已实现“共享图纸证据—专项等级评价—独立任务书核对—确定性评分—教师校准”研究架构。已冻结的四份校准、两份盲测未能稳定区分高低样本，因此产品默认仍使用 `legacy_v1`，新链路仅作研究验证。
- 模型评图会读取全部可用图纸，并优先让模型看到平面图，避免只分析第一张图纸导致误判。
- 首页使用一次轻量摘要读取全部项目状态；进入或悬停项目卡片时再读取并复用单次工作台快照，避免随项目数量增加产生大量重复请求。
- 右侧 AI 对话区会显示当前阶段各 Agent 的真实顺序评审进度，评图完成后同步更新报告区。
- 报告页会把当前评分维度拆成四项具体小分，并在右侧集中展示反馈要点。反馈关联卡片会按真实知识库编号读取与知识库详情页相同的完整正文和图片，规范应用卡阅读时隐藏没有可读内容的“原始 PDF”附件章节，接口暂时不可用时才显示评图快照；下载报告会生成包含总分、专项评分、各评价点具体小分和反馈建议的多页 PDF，不附加关联知识卡。PDF 的专项标题与分数直接显示，四项小分横向并列，以留白和细分割线区分；反馈按等级使用轻量颜色提示，不再嵌套卡片。AI 辅助助手提供图纸复核、问题解释和知识推荐，回答按流式逐步显示；生成中仍可编辑下一条问题，暂停后即可发送。知识推荐链接会进入与知识助手一致的推荐总览，并继续显示原报告对话，卡片详情可直接返回报告。只有图纸证据明确证明原判断有误时，图纸复核才会限幅修订分数，同时清理或改写总评、反馈、专项结论和具体小分中的错误判断并保存修订记录；原判断无误时不改报告。
- 当前产品按用途固定分流：评图、各 Agent 与报告生成使用 `qwen3.8-max`，知识库助手和报告辅助助手使用 `qwen3.7-plus`；界面不提供模型切换入口，两个助手也不显示内部模型名称。
- 从 `ArchCritic相关资料/知识库最终版` 检索 Obsidian Wiki 知识依据，评图时只把本次最相关的卡片交给模型；每条依据会带编号并可点击打开居中的知识卡片，案例卡片可显示图片。
- 左侧“知识库”提供独立学习浏览页，可查看 100 张知识卡和 50 张案例卡；知识卡按规范、场地、功能、空间、结构、概念、综合分类，支持搜索、关联跳转和正文图片。知识测试按入门、进阶、研习选择难度，每次随机抽取 5 题，覆盖单选、多选、判断、识图和简答；每题提交后显示答案、解析和判定，答题卡区分对错并允许自由浏览。浏览器本地保存错题及正确答案，中途退出只生成本场得分总结，不保留未完成进度。只有具备明确答案要点的题目会进入测试。建筑知识助手支持真实流式回答、新建与历史会话，进入历史会话时默认定位最新消息，返回知识库后可恢复上次对话位置；工具标签在发送后以轻量紫色图标文字呈现。助手提供案例推荐、知识查询、学习清单和当前卡片问答；当前卡片问答只显示文字回答，其余推荐结果只使用后端校验过的真实卡片编号，并可直接更新知识库卡片列表。学习浏览与评图使用同一套卡片来源，但正式 AI 评图仍遵守人工审核门槛。面向用户的页面按最终交付状态呈现，不展示内容治理或审批流程词；AI 推荐统一使用中性的准确性提示，内部治理字段继续用于检索准入和审计。
- 每次评图会保存当次使用的知识库依据快照，历史报告打开时优先读取快照，避免知识库更新后依据编号和报告内容错位。
- 报告反馈中的 `[K1]`、`[K2]` 等知识编号会显示为可点击引用，用户可以从具体问题直接打开对应知识卡片。
- 专项 Agent 评分支持展开查看，能看到分项分数、评分理由、证据、已确认事实、信息缺口和不确定观察。
- 总分圆圈显示最终综合评审得分，右侧横条只显示专项 Agent，避免综合评审分数重复展示。
- “查看历史版本”会打开已保存提交卡片，点击后可切换回当时的项目信息、图纸和评图报告。
- 底部历史版本和多 Agent 状态会根据后端返回结果更新；评审矩阵和对话区会显示各 Agent 的头像；刷新页面后会自动恢复上次项目、图纸、报告和历史记录。
- 页面可直接看到新版三栏评图工作台界面。
- 已在 `frontend-v1-replica/` 按 Figma“前端 V1”制作 React 新版界面并接回现有 FastAPI 后端；旧版 `frontend/` 已移出仓库，归档到 `../ArchCritic-开发过程历史代码/2026-06-13/frontend-旧版演示前端/`。

## 技术架构

- 后端使用 FastAPI 提供接口。
- 项目、提交、图纸记录和报告数据保存在 SQLite 中，上传图片保存在本地 `uploads` 文件夹。
- 本地密码使用带随机盐的不可逆哈希保存，登录会话使用 HttpOnly Cookie；上传文件必须登录且属于当前账户才能读取。
- 知识库依据从项目外层的 `ArchCritic相关资料/知识库最终版` 检索，该目录可直接用 Obsidian 打开；治理 JSON 位于隐藏的 `.archcritic/长程Goal治理`，不进入关系图谱，后端仍兼容旧目录格式。
- 建筑知识助手先在后端用建筑类型、面积、场地、设计阶段和关键词召回候选，再让默认模型只在候选编号中选择和解释；模型返回后再次校验编号，会话按账户保存在 SQLite。`mock` 模式只用于开发检查，不会伪造助手成功回答。
- 前端使用 Vite 启动本地页面，当前正式入口是 `frontend-v1-replica/`。
- 新版前端位于 `frontend-v1-replica/`，使用 React、TypeScript、Tailwind CSS 和 Vite，已接通项目、图纸、任务书、评图、报告、知识追溯、历史版本和追问。迁移计划见 `docs/plans/2026-05-31-frontend-v1-interaction-and-backend-migration-plan.md`。
- 产品评图统一使用 `dashscope/qwen3.8-max`，会读取设计说明、任务书正文、上传图纸和 Wiki 依据；后端按当前阶段顺序调用专项 Agent，再由综合评审 Agent 输出最终报告。知识库助手和报告辅助助手固定使用 `dashscope/qwen3.7-plus`，不接收前端模型参数。
- 阶段化多 Agent 默认把单次总评审预算控制在 285 秒内，每个专项 Agent 输出事实识别、分项评分、不确定观察和修改建议，综合评审只汇总专项结果。
- 报告会保存本次实际使用的 Agent、任务书摘要和动态评分权重；历史页直接读取真实报告，没有报告时明确显示未完成状态，不使用设计稿占位数据。
- 真实模型评图会先要求模型列出图纸事实，再进行评价；输出结构统一为 `observed_facts + sub_scores`，与设计说明或事实识别冲突的内容会降级为不确定观察，避免错误地进入“必须修改”。
- 前端只在开始评图前展示并提交 `dashscope/qwen3.8-max`；旧草稿保存过的其他模型值在恢复时也会自动回落到该模型。两个助手由后端固定调用 `qwen3.7-plus`。
- 百炼真实评图不再把图片作为 base64 直接传给模型，而是使用百炼临时 OSS 文件 URL；数据库会缓存临时 URL 和过期时间，减少重复上传。
- `backend/app/benchmarking/` 负责基准数据解析、高清拆页、真实模型调用、统计、图表和科研报告；正式新实验使用“无答案盲跑—结果冻结—独立裁判”流程，评图进程不读取教师分或标注答案。
- 九样本论文实验另设 C0 直接评审、C1 结构化提示词增强的单模型评审、C2 多 Agent 和 C3 知识增强多 Agent 四个条件；匿名输入与私有答案分离，模型结果冻结后才按人工标注清单进行本地严格语义核对。
- 产品默认使用 `legacy_v1`；`evidence_v2` 为可显式开启的研究模式。研究模式由模型提供证据和 0—4 级判断，数值分由后端固定规则与本地校准器生成，并随报告保存审计信息。
- `evidence_v2` 先对所有图纸建立统一 E 编号事实清单，各专项 Agent 只能引用该清单；任务书符合度由独立文本层核对，知识引用则保存每个 Agent 实际使用和无效编号记录。

## 本地运行方法

### 后端

```bash
cd /mnt/e/claude/codex/ArchCritic/backend
test -d .venv || python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启用阿里云百炼时，请在 `backend/.env` 中配置：

```env
LLM_PROVIDER=dashscope
LLM_MODEL=qwen3.8-max
LLM_ASSISTANT_MODEL=qwen3.7-plus
DASHSCOPE_API_KEY=你的百炼 API Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SCORING_ARCHITECTURE=legacy_v1
```

需要复现实验证据层时，可临时改为 `SCORING_ARCHITECTURE=evidence_v2`；当前盲测未通过高低分区分验证，不建议直接用于学生正式评分。

任务书支持 TXT、DOCX 和带文字层的 PDF。PDF 解析依赖本机 `pdftotext`；扫描版 PDF 暂未接入 OCR，上传时会明确提示改用可复制文字的版本。旧版 DOC 请先另存为 DOCX。

报告 PDF 使用 ReportLab 生成可选择和复制文字的矢量页面，并通过系统 `fontconfig` 选择、嵌入中文与拉丁字体；本地和服务器需要安装至少一套中文字体。

### 前端

新版 React 前端：

```bash
cd /mnt/e/claude/codex/ArchCritic/frontend-v1-replica
npm run dev
```

打开 `http://127.0.0.1:4173`。新版前端固定使用 `4173` 端口，如果端口被占用会直接报错，不自动换端口。

本项目位于 WSL 的 Windows 挂载盘 `/mnt/e`，Vite 已启用文件轮询监听，避免热更新漏掉文件变更。修改前端后可用下面命令快速确认 `4173` 已返回新源码：

```bash
cd /mnt/e/claude/codex/ArchCritic/frontend-v1-replica
npm run dev:check -- "要检查的样式或文本" "/src/实际修改模块.tsx"
```

旧版演示前端不再放在当前仓库内；历史代码位置为：

```text
/mnt/e/claude/论文/ArchCritic-开发过程历史代码/2026-06-13/frontend-旧版演示前端/
```

## 部署方法和命令

生产部署采用“静态前端 + FastAPI 后端 + 独立网关”的方式：前端构建产物由 Nginx 提供，后端由 systemd 常驻运行，SQLite、上传文件和知识库统一放在 `/var/lib/archcritic/`，不随代码版本覆盖。

备案审核期间，腾讯轻量云使用 `http://app.archcritic.cn:8080` 提供临时访问；该入口不占用服务器原有游戏的 80 和 3000 端口。备案完成后，正式入口使用 EdgeOne Pages 托管的 `https://archcritic.cn`，后端使用轻量云上的 `https://api.archcritic.cn`。

前端正式构建：

```bash
cd /mnt/e/claude/codex/ArchCritic/frontend-v1-replica
npm run build
```

部署文件位于 `deploy/`：

- `archcritic-backend.service`：后端常驻服务，只监听服务器内部的 `127.0.0.1:8000`。
- `archcritic-web.service` 和 `nginx-http.conf`：备案期 HTTP 网页服务，只监听 8080。
- `Caddyfile`：备案完成后的 HTTPS 反向代理配置。
- `backend.env.example`：服务器环境变量模板，真实密钥只填写在服务器 `/etc/archcritic/backend.env`，不得提交到 Git。

EdgeOne Pages 使用根目录 `edgeone.json`，构建目录为 `frontend-v1-replica`，产物目录为 `frontend-v1-replica/dist`，并已配置单页应用回退规则。
正式域名从 HTTP 打开时会在业务代码运行前保留路径并切换到 HTTPS；HTTPS 响应同时通过 HSTS 让浏览器记住安全入口一年，避免再次从 HTTP 页面发起登录或注册。

## 测试方法和常用命令

### 内测注册与百度统计

新注册默认需要内测码；已有账户登录不受影响。服务器只保存码的 SHA-256 摘要，`REGISTRATION_CODE_LIMITS` 配置每个摘要对应的累计注册上限；空字典会暂停新注册。用量存于独立的 `registration_code_usage` 表，与账户创建在同一事务内提交，失败回滚，停用再启用同一码不会重置用量。上线前备份数据库，再由应用正常启动补建此表，不改写原用户。

生成三个码、每码 100 个名额（明文输出请私密保存，不提交 Git）：

```bash
cd /mnt/e/claude/codex/ArchCritic/backend
.venv/bin/python scripts/generate_registration_codes.py --count 3 --limit 100
```

将输出中的 `REGISTRATION_CODE_REQUIRED` 和 `REGISTRATION_CODE_LIMITS` 放入服务器 `/etc/archcritic/backend.env`。合并新增码时保留原码配置；移除某个摘要即可停用该码。只有隔离测试需要时才设置 `REGISTRATION_CODE_REQUIRED=false`；当前注册页面始终提示填写内测码。

百度统计在网页端记录访问。当前站点 ID 与允许统计的域名由 `frontend-v1-replica/site.config.json` 管理；Vite 正式构建将官方加载代码直接插入首页 `<head>`，便于百度安装检测器读取原始 HTML。ID 留空并重新构建发布即可关闭统计；后端 `/api/site/config` 保留兼容，但不再控制新版前端安装。网页异步加载官方脚本，手动记录固定路由，避免 React 单页切换漏报或首页 iframe 重复统计。本地开发、预览域名和 HTTP 跳转页不统计，不主动上报账号、密码、内测码或项目内容。代码可被检测与实际产生访问数据需要分别验证。

知识测试发布必须核对 `/api/knowledge/quiz/answer` 路由及题目 `question_type/options`、难度 `value/count` 字段；只有 `/api/knowledge/quiz` 存在不足以证明新版题库已部署。当前前端会拒绝旧格式并显示更新提示，不缓存旧数据。

### 后端测试

日常开发只运行与本次修改直接相关的一项测试，并限制为 60 秒；脚本会自动使用后端虚拟环境和正确工作目录：

```bash
cd /mnt/e/claude/codex
bash .agents/skills/archcritic-dev-flow/scripts/archcritic-dev.sh after-backend "tests/test_target.py::test_name"
```

只有依赖、数据库结构、认证、公共模型或核心路由发生跨模块变化时，才从后端目录运行完整测试。测试超时后先缩小到单项，不重复运行完整文件。

### 私有评分基准

```bash
cd /mnt/e/claude/codex/ArchCritic/backend
./.venv/bin/python scripts/benchmark_review.py prepare
./.venv/bin/python scripts/benchmark_review.py run --round formal-round1 --provider dashscope --model qwen3.6-plus --workers 2
./.venv/bin/python scripts/benchmark_review.py report --round formal-round1 --model qwen3.6-plus
./.venv/bin/python scripts/benchmark_review.py export --first formal-round1 --second formal-round2
./.venv/bin/python scripts/benchmark_review.py evidence-export
```

上述 `run/report/export` 命令只用于复现 2026-07-17 的历史六样本实验。新开发集、验证集和最终测试必须使用下列严格流程：

```bash
cd /mnt/e/claude/codex/ArchCritic/backend
./.venv/bin/python scripts/goal_asset_audit.py
./.venv/bin/python scripts/benchmark_review.py blind-prepare --source-root ../标注基准集/.prepared --output-root ../标注基准集/.blind-workspace/model-inputs
./.venv/bin/python scripts/benchmark_review.py blind-run --test-id <冻结测试编号> --input-root ../标注基准集/.blind-workspace/model-inputs
./.venv/bin/python scripts/benchmark_review.py blind-judge --results-root <冻结结果目录> --private-answers <私有答案文件> --judgments-root <独立裁判目录>
```

`blind-run` 不接收答案路径；成功结果会写入哈希并冻结，不得因分数不理想重跑。`blind-judge` 只在冻结校验通过后才会读取私有答案。数据字段规范见 `docs/schemas/long-horizon-goal-v1/`。

2026-07-27 九样本四条件论文实验使用下列入口。`prepare`、`run`、`judge-local`、`metrics` 和 `gate` 分阶段执行；已经冻结的正式结果不得覆盖。

```bash
cd /mnt/e/claude/codex/ArchCritic
backend/.venv/bin/python backend/scripts/paper_experiment.py status
backend/.venv/bin/python backend/scripts/build_paper_experiment_report.py
backend/.venv/bin/python -m pytest backend/tests/test_paper_experiment.py backend/tests/test_blind_protocol.py -q
```

内容人工复核与知识专项使用下列命令。`apply` 只有在复核表逐条由真实人工确认后才允许执行；当前不要运行正式 `run`：

```bash
cd /mnt/e/claude/codex/ArchCritic/backend
./.venv/bin/python scripts/knowledge_content_review.py export
./.venv/bin/python scripts/knowledge_content_review.py validate
./.venv/bin/python scripts/knowledge_content_review.py apply --confirm-human-reviewed
./.venv/bin/python scripts/content_evaluation_status.py status
./.venv/bin/python scripts/content_evaluation_status.py run
```

匿名输入、原始结果与论文数据均保存在本地 `标注基准集/`，该目录受 `.gitignore` 保护。

### 前端测试

日常样式、文案和局部交互修改使用快速流程，一次完成基础检查、目标模块热更新和 4173 健康检查：

```bash
cd /mnt/e/claude/codex
bash .agents/skills/archcritic-dev-flow/scripts/archcritic-dev.sh after-frontend "目标标记" "/src/实际修改模块.tsx"
```

类型结构、依赖、构建配置或跨模块核心流程变化时，再额外运行：

```bash
cd /mnt/e/claude/codex/ArchCritic/frontend-v1-replica
npm run typecheck
npm test
npm run build
```

浏览器完整交互验收脚本位于 `backend/scripts/verify_frontend_v1_browser.ps1`。

## 搜索记录

- 2026-09-05 根据百度[自动检查说明](https://trend.baidu.com/web/help/article?id=178)，检查器抓取网页源码，通过 JS 动态安装可能显示未检测。安装方式已改为构建时写入 `<head>`，统计 ID 集中在前端公开配置；不再等待后端接口后才安装脚本，保持单次安装与手动路由 PV。

- 2026-09-05 经用户授权完成 npm 生产依赖扫描：已知漏洞 0 项，不涵盖 Python/开发依赖。百度统计 ID 经用户完整代码核对一致，但本机、服务器及绕缓存请求的官方脚本均返回空内容，采集尚未确认；官方[代码自动检查说明](https://trend.baidu.com/web/help/article?id=178)也提示，通过 JS 动态安装可能在自动检测中显示未检测到代码，因此以实际脚本内容及采集请求为最终依据。

- 2026-09-05 核对百度统计官方[代码部署](https://tongji.baidu.com/web/help/article?id=219)和 [trackPageview](https://tongji.baidu.com/web/help/article?id=235&type=0)：统计脚本必须安装在网页端，单页应用切换使用手动 PV；当前实现关闭自动 PV，由后端公开站点 ID，前端仅发送固定页面路径。网络依赖漏洞扫描因外发元数据审批未通过，未形成漏洞库比对结论。

- 2026-09-03 参考成熟学习平台和设计系统的测验入口做法：入口应明确告诉用户从哪里开始、下一步做什么；可选择卡片需要完整卡片可点击、清晰的悬停状态，并通过文字或图形而非仅靠颜色表达差异。知识测试初始页据此改为“规则摘要 + 三档挑战卡 + 独立错题复习入口”，同时保持 ArchCritic 原有黑白灰与紫色视觉体系。
- 2026-09-02 复核腾讯 EdgeOne Pages 官方当前说明：GitHub 仓库仍可自动构建部署，项目设置可绑定根域名或子域名；自定义域名需要按控制台给出的记录更新 DNS。当前项目继续使用 GitHub `master` 自动部署，并把 `archcritic.cn` 作为正式入口。
- 2026-09-03 复核腾讯 EdgeOne Pages、Caddy TLS 官方说明并实测生产链路：`archcritic.cn` 已通过 EdgeOne 向大陆运营商节点调度，`api.archcritic.cn` 直达广州腾讯云；大陆节点抽测 13/13、后端连续健康检查 12/12，现代浏览器 API、CORS 和账号预检均正常。兼容性对比确认官网支持 RSA，而 API 当前仅提供 ECDSA 证书，RSA-only 客户端握手失败；部署配置已改为 RSA 2048。针对用户网络或边缘节点的瞬时抖动，前端只读请求和登录增加一次短时重试，错误提示不再把网络失败误报为“后端未启动”。
- 2026-09-01 核对阿里云百炼官方模型说明：`qwen3.8-max` 与 `qwen3.7-plus` 均支持文字、图片和结构化输出，继续使用现有百炼兼容接口即可；产品据此把前者固定用于评图和 Agent，后者固定用于两类助手。
- 2026-08-31 核对阿里云百炼官方说明：百炼兼容 Chat Completions 可通过 `extra_body={"enable_search": true}` 开启联网搜索，当前知识卡拓展和报告问题解释继续在千问模式下按需联网检索。
- 2026-08-23 核对腾讯 EdgeOne Makers 官方 `edgeone.json` 与构建指南：仓库根目录配置可以覆盖安装命令、构建命令、Node.js 版本和输出目录；Vite 静态站点必须把输出目录指向实际包含 `index.html` 的 `dist`，单页应用可使用 `/*` 到 `/index.html` 的 SPA 回退。当前项目据此固定使用 Node.js 22.11.0、`npm ci`、`npm run build` 和 `frontend-v1-replica/dist`。

## 已完成功能列表

- 实验性视觉评分锚点：已从同类课程原始图纸建立低 3、中 4、高 4 的匿名锚点集，最终 Agent 可记录档位、最近锚点、比较依据和校准分数；三案例测试未改善 MAE 和分档排序，因此当前不作为产品默认评分。
- 本地账户与数据隔离：支持首次注册、登录、确认退出、修改昵称和密码；账号使用 3–12 位英文字母或数字，昵称支持 1–12 个中英文字符，表单会在离开输入栏时即时提示错误。项目、提交、上传文件、历史报告均按账户隔离，密码不保存明文。
- 账户帮助中心：新账户首次进入工作台时自动展示一次遮罩式分步指引，之后可从帮助菜单手动重看；同时提供真实操作常见问题和可写入后台数据库的问题反馈表单。
- 真实任务书评分：上传时抽取任务书正文，识别课程重点和“不作要求”等弱化条件，结合设计阶段与年级生成动态评分权重，并将依据随历史报告保存。
- 三阶段多 Agent：概念阶段启用场地、形式、概念和综合评审；方案阶段启用功能、场地、形式、结构和综合评审；图纸阶段启用图面表达、功能、场地、形式、结构和综合评审。
- 真实报告展示：报告页和历史页按后端真实维度、分数、任务书权重和 Agent 数据渲染；支持将当前真实结果导出为排版后的多页 PDF，报告缺失或不完整时显示明确状态，不再注入虚构评分。
- 工程化重构：提交接口、评图逻辑、工作区、流程页、报告页、侧栏和样式均已按职责拆分，当前前后端业务代码单文件均不超过 500 行。
- 本地文件生命周期：图纸与任务书必须登录后按所属账户访问；删除项目、版本或文件时会清理不再被其他版本引用的本地文件。
- 新版 React 前端迁移：接通草稿、阶段与 Agent、图纸、任务书、流式评图、暂停、报告详情、知识追溯、历史恢复、项目继承、报告导出和追问；旧版前端已归档到仓库外历史目录。
- 新版项目侧栏：同名项目会归并展示，按提交时间生成 V1、V2 等历史版本；首页和侧栏共用项目状态，切换页面时保留已有卡片。
- 图纸辅助拆分与无缝加载：优先识别合成平面和技术图中的完整分区，原图始终保留且辅助图数量受限；项目摘要、工作台快照和报告缓存使用同一份后端状态。
- 新版资料管理接口：支持图纸类型与说明修改、单张删除、批量删除、任务书上传和继承已有项目最近一次资料。
- 新版浏览器验收脚本：可按真实页面顺序完成保存、提交、评图、报告详情、知识追溯、历史和追问，并保存报告页截图。
- 后端健康检查接口。
- SQLite 数据模型和基础数据库初始化。
- 项目创建与列表接口。
- 方案提交接口。
- 年级字段保存。
- 图纸上传、图纸列表和静态图片访问。
- 单个项目详情、项目提交历史、单次提交详情和报告查询接口。
- Wiki 知识库检索接口：按项目类型、阶段、图纸类型和设计说明筛选相关知识卡片。
- 知识库学习浏览接口：读取最终版 Markdown 目录和单卡详情，目录阶段不扫描全部图片，打开案例后才按正文顺序读取图片。
- 知识库依据快照：保存每次评图实际使用的依据，历史报告不重新匹配新的知识库内容。
- 评图结果接口当前统一调用阿里云百炼千问模型；内部演示模式只用于开发检查。
- 功能与流线 Agent v1：按功能满足、功能分区、流线分析、平面丰富性四项评分，要求模型引用知识卡片编号，并标注图纸识别不确定内容。
- 阶段化多 Agent v1：功能、场地、几何形式、结构、设计概念、图面表达和综合评审 Agent 已接入真实模型，按阶段白名单顺序评审并输出统一报告。
- 前端多 Agent 过程展示：对话区和评审矩阵会显示当前阶段实际 Agent 的头像、调用顺序和完成状态。
- 报告问题知识引用：反馈条目中的知识编号会绑定到本次报告保存的知识库快照，并可直接打开对应知识卡片。
- 专项评分展开卡片：点击除综合评审外的专项评分，可查看分项评分、理由、证据、事实识别和不确定内容。
- 多张高清图纸前端上传：同一图纸类型可保留多张图片，评图时会把可用图纸按顺序发送给模型。
- 功能与流线 Agent v1 的输出格式已统一，先返回图纸事实识别，再返回四项评分和修改建议。
- 百炼临时 OSS 图纸链路：上传本地图纸获得模型可访问 URL，解决 base64 图片直传导致的超时问题。
- 百炼调用稳定性兜底：临时 OSS 上传失败会自动重试，流式输出中断或 JSON 不完整时会尝试非流式结构化评图。
- 右侧 AI 对话流式输出：新增流式评图接口，前端能实时看到模型生成内容，并在结束后渲染报告。
- 固定模型展示：确认提交页和报告助手仅显示当前千问模型，不再提供模型切换控件。
- 知识库追溯卡片：每条知识依据可点击查看与知识库详情页相同的完整 Markdown 正文和图片；旧报告详情读取失败时保留当次快照兜底。
- 历史版本卡片：完成评图后自动进入项目历史，点击“查看历史版本”可查看并切换到旧提交的报告状态。
- 高清图纸上传策略：默认保留原图，只有超过约 12MB 的图纸才缩放到约 4000px 长边，减少小字和线条识别损失。
- 事实识别约束：评图前要求模型先识别楼梯、电梯、卫生间、主入口、车库入口、报告厅和服务台等关键事实，错误的“未看清”结论不会直接进入必须修改。
- 知识库图片展示：案例图片通过只读静态路径展示在知识卡片中。
- 工作台刷新恢复：评图完成后记录最近项目和提交，刷新页面会自动恢复上次报告、图纸和历史版本。
- 新版 React 工作台已接入本地前端入口。
- 左侧项目信息、设计阶段选择、本地图片上传、中间图纸查看、后端保存、右侧报告动态渲染、历史版本和知识库追溯已具备前端交互。
- Demo 后端产品设计文档：`docs/plans/2026-05-12-demo-backend-product-design.md`。
- 新版前端视觉与文字层级设计规范：`DESIGN.md`。
- Obsidian 知识库与模型调用路线文档：`docs/plans/2026-05-19-obsidian-wiki-knowledge-graph-route.md`。
- 新版 React 前端交互与后端迁移计划书：`docs/plans/2026-05-31-frontend-v1-interaction-and-backend-migration-plan.md`。
- 评分可信度与公共建筑知识/案例长程 Goal 任务书：`docs/plans/2026-07-19-archcritic-long-horizon-goal-taskbook.md`。
- 长程 Goal 资产审计与严格盲测：可机器盘点样本、知识卡、案例、来源和授权；空字段、占位内容、未核验来源和未授权媒体不会计数；支持无答案输入包、一次性盲跑、结果哈希冻结、技术失败留痕和冻结后独立裁判。续跑前会同时核对模型、提示词、任务书、校准文件和评分代码指纹。
- 公共建筑内容治理：已核验 1 组 OGL 政府设计指南和 2 本 CC BY-NC 开放教材；20 个候选案例均登记了第一方或公共机构来源并形成逐条证据草稿，其中 18 份具备三类以上证据。新增 9 张案例图片已按 CC0 或 CC BY/CC BY-SA 逐图登记许可与哈希，旧有 89 张未授权图片继续隔离；全部内容仍待建筑学复核，因此正式知识卡、案例和问答计数仍为 0。
- 内容复核与检索验收：已生成 60 张分层知识卡、30 道固定问答、20 个自然语言案例检索任务和 20 个评图问题联动任务，五类问题各 4 个。人工复核包共 150 条，回写前会检查真实复核人、逐条确认和草稿哈希；待分析或待复核内容不会进入模型检索，只有人工批准且媒体许可合格的结构化条目才能激活。
- 后端与前端基础测试。
- 六样本真实评分基准：已接入课程任务书，完成两轮固定千问模型测试；支持提示词指纹、MAE/RMSE/相关性、事实准确率、问题召回率、CSV/JSON 数据和 SVG 论文图表导出。
- 九样本四条件论文实验：完成 36/36 份 `qwen3.6-plus` 报告及冻结、本地严格核对、暂停闸门、CSV/Markdown 汇总和两张论文图；正式结果表明多 Agent 提升问题覆盖，但没有改善教师分数 MAE。
- 证据优先评分研究：任务书要求可区分强制、弹性、选配和参考；Agent 只交付事实、置信度与 0—4 级判断，后端负责固定换算和教师校准。四份校准与两份盲测数据包位于 `标注基准集/测试报告与论文数据/新版证据校准架构/`。

## 待办事项

- 补齐正在制作的中档样本后，冻结当前研究代码，在更大的独立样本上重新验证高、中、低分区分；当前 `evidence_v2` 不升为产品默认。
- 为扫描版任务书补充 OCR，并继续完善向量检索、知识库质量和多 Agent 评价稳定性。
- 上云前补充正式数据库迁移、对象存储、HTTPS Cookie、备份恢复和部署脚本；当前本地账户数据不直接视为生产账户体系。
