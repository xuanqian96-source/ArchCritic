# ArchCritic 架构说明

## 文件与模块职责

### 后端

- `backend/app/main.py`：后端入口，初始化数据库、中间件和接口；用户上传目录不再作为公开静态目录。
- `backend/app/config.py`：统一读取数据库、上传目录、模型、跨域、登录 Cookie 等配置。
- `backend/app/database.py`：创建数据库连接，并为已有 SQLite 数据库补齐账户、任务书和报告字段。
- `backend/app/models.py`：定义用户、登录会话、项目、提交、图纸、任务书、Agent 结果、报告和知识依据等数据表。
- `backend/app/schemas.py`：定义前后端接口的数据格式和输入校验规则。
- `backend/app/routers/auth.py`：提供本地注册、登录、退出、当前用户、个人资料和密码修改接口。
- `backend/app/routers/assets.py`：登录后校验文件归属，再返回用户上传的图纸或任务书。
- `backend/app/routers/projects.py`：负责当前账户的项目创建、列表、详情、历史和删除。
- `backend/app/routers/submissions.py`：提交接口门面，组合下列按职责拆分的路由文件。
- `backend/app/routers/submission_crud.py`：负责提交草稿、继承、任务书上传和基础资料读取。
- `backend/app/routers/submission_stream.py`：负责真实模型流式评图、阶段事件和模型图纸准备。
- `backend/app/routers/submission_reports.py`：负责报告、知识依据、追问、导出和评图辅助接口。
- `backend/app/routers/submission_report_data.py`：负责报告的保存、读取和接口结构转换。
- `backend/app/routers/submission_common.py`：保存提交路由共用的模型选择、暂停和错误处理规则。
- `backend/app/routers/files.py`：负责图纸修改、单张删除和批量删除，并校验账户归属。
- `backend/app/services/auth.py`：提供密码哈希、会话令牌和项目/提交归属校验。
- `backend/app/services/taskbooks.py`：抽取 PDF、DOCX、TXT 任务书正文，整理课程要求，并按阶段、年级和任务书重点生成评分权重。
- `backend/app/services/taskbook_rules.py`：把任务书条目标为强制、弹性、选配、参考或说明，并分配核对专项与证据方式。
- `backend/app/services/uploads.py`：安全解析和删除本地上传文件，防止路径越界和误删共享文件。
- `backend/app/services/submission_cleanup.py`：集中删除一次提交的关联数据和不再被引用的物理文件。
- `backend/app/agents/function_agent.py`：构建模型图文上下文，包含任务书正文、动态权重、知识依据和全部可用图纸。
- `backend/app/agents/function_agent_report.py`：校验功能 Agent 输出并转换为统一报告结构。
- `backend/app/agents/scheme_review.py`：按概念、方案、图纸三个阶段的白名单顺序执行专项 Agent 和综合评审 Agent，并按任务书权重计算总分。
- `backend/app/agents/evidence_review.py`、`prompts/evidence_agents_v2.py`：研究模式下要求模型只返回事实、来源、置信度、任务书状态和 0—4 级判断，再转换为旧报告兼容结构。
- `backend/app/scoring/`：负责等级到专项分的固定映射、任务书符合度、分数区间和小样本单调教师校准。
- `backend/app/agents/prompts/function_agent_v1.py`：保存功能与流线 Agent 的提示词和输出要求。
- `backend/app/agents/prompts/scheme_agents_v1.py`：保存场地、形式、结构、设计概念、图面表达和综合评审 Agent 的规则与评分项。
- `backend/app/benchmarking/dataset.py`：把私有 Markdown 标注解析为匿名模型输入和人工标准答案；旧六样本仍是同根目录的历史格式。
- `backend/app/benchmarking/preprocess.py`：读取课程任务书，把 PDF 图纸逐页转为受尺寸控制的高清图片。
- `backend/app/benchmarking/runner.py`：保留历史六样本的多 Agent 运行和同进程语义裁判，只用于复现旧实验。
- `backend/app/benchmarking/blind_protocol.py`：新正式评测流程，把无答案输入包、一次性盲跑、结果哈希冻结和冻结后独立裁判拆为不同进程。
- `backend/app/benchmarking/asset_audit.py`、`asset_audit_report.py`：只读盘点样本、授权、知识卡、案例和媒体权限，生成不含教师分或标注答案的缺口报告。
- `backend/app/benchmarking/asset_content_validation.py`：严格核对内容字段、来源关联、媒体许可、审核人和逐条证据；分别统计“结构合格草稿”“具备深度证据草稿”和“正式验收内容”，防止用空槽位或未经复核的草稿凑数量。
- `backend/app/benchmarking/baseline_snapshot.py`：记录评分相关代码、提示词、运行配置和历史总体指标的冻结指纹，不接触单份教师答案。
- `backend/app/benchmarking/knowledge_governance.py`：建立来源、媒体、案例、知识卡和问答治理清单；只初始化缺失文件，不覆盖人工审核结果。
- `backend/app/benchmarking/content_review.py`：导出 150 条内容与固定任务复核表，锁定输入哈希；只有完整人工决定和显式确认才能回写，AI 不能自行批准。
- `backend/app/benchmarking/content_evaluation.py`：验证并执行 20 个案例检索和 20 个问题联动固定任务，分别使用前五相关数和知识—案例联合覆盖率验收。
- `../知识库测试版/99维护记录/长程Goal治理/`：保存来源台账、逐图媒体许可、60 张知识卡草稿、30 道固定问答、20 份案例证据草稿和 40 个固定检索/联动任务；候选内容与人工批准后的正式内容分开计数。
- `backend/app/benchmarking/metrics.py`：计算教师分 MAE、RMSE、偏差、相关性、人工区间和语义指标。
- `backend/app/benchmarking/research.py`、`charts.py`：导出 CSV、JSON、SVG 图表、论文数据报告和工作总结。
- `backend/app/benchmarking/calibration.py`、`evidence_report.py`：固定四份校准与两份盲测划分，拟合校准器并导出新版科研数据包。
- `backend/scripts/benchmark_review.py`：提供历史基准复现，以及新盲测输入包、盲跑冻结和独立裁判命令入口。
- `backend/scripts/goal_asset_audit.py`：生成长程 Goal 阶段 0—2 机器盘点和人类可读缺口报告。
- `backend/scripts/knowledge_content_review.py`：导出、校验和回写人工内容复核表，回写必须显式确认全部决定来自人工。
- `backend/scripts/content_evaluation_status.py`：盘点 40 个固定检索/联动任务，并在全部人工批准后执行本地检索验收。
- `backend/scripts/initialize_knowledge_governance.py`：初始化公共建筑内容治理工作区。
- `backend/app/wiki.py`：检索 Obsidian 知识卡片，整理为模型可引用、前端可显示的依据和图片。
- `backend/app/governed_wiki.py`：把人工批准的结构化知识卡和案例转换为检索条目；案例必须同时通过来源、证据和逐图许可检查，并保留图片署名。
- `backend/app/llm/`：统一封装演示、OpenAI、千问百炼和 Gemini 模型调用，以及百炼临时图纸地址。

### 前端

- `frontend-v1-replica/src/App.tsx`：处理官网、登录页和受保护功能页的路由切换。
- `frontend-v1-replica/src/pagesAuth.tsx`：提供与现有视觉一致的双栏注册登录页。
- `frontend-v1-replica/src/state/auth.tsx`、`src/api/auth.ts`：管理当前本地账户和登录接口。
- `frontend-v1-replica/src/state/workspace.tsx`：组合项目工作区状态；文件动作和公共转换已拆到 `workspaceFileActions.ts`、`workspaceShared.ts`。
- `frontend-v1-replica/src/pagesFlow.tsx`：流程页面门面；项目信息、阶段选择、上传图纸和评图工作台分别位于 `src/pages/flow*.tsx`。
- `frontend-v1-replica/src/pagesResults.tsx`：结果页面门面；报告、历史、公共报告组件和历史数据处理位于 `src/pages/report*.tsx`、`historyPage.tsx`。
- `frontend-v1-replica/src/components.tsx`：公共组件门面；基础组件、侧栏和账户弹窗位于 `src/components/`。
- `frontend-v1-replica/src/styles.css`、`src/styles/report.css`：分别保存通用样式和报告相关样式。
- `frontend-v1-replica/vite.config.ts`：固定本地开发端口 `4173`，并使用轮询保证 WSL 挂载盘热更新。
- `DESIGN.md`：记录新版前端视觉规范、组件规则和字号层级。

## 模块之间的调用关系

1. 官网“体验产品”进入受保护页面；未登录时 `App.tsx` 转到注册登录页，后端通过 HttpOnly Cookie 识别当前账户。
2. 前端工作区创建当前账户的项目和提交，上传图纸与任务书；接口先校验项目归属，再保存到 SQLite 和本地上传目录。
3. 任务书上传时立即抽取正文。开始评图时，`taskbooks.py` 生成动态权重，`taskbook_rules.py` 同时生成可审计的强制、弹性、选配和参考规则。
4. `function_agent.py` 把项目资料、设计说明、任务书正文、权重、知识库依据和图纸组合成一次可追溯的模型上下文。
5. `scheme_review.py` 根据阶段过滤 Agent：概念阶段执行场地、形式、概念；方案阶段执行功能、场地、形式、结构；图纸阶段执行图面表达、功能、场地、形式、结构，最后按需执行综合评审。
6. 默认 `legacy_v1` 沿用原专项分；显式启用 `evidence_v2` 时，模型只判证据与等级，`scoring/` 固定换算专项分、任务书符合度、校准分和区间。两种模式都写入兼容的 `agent_evaluations`。
7. 流式接口通过 SSE 返回读取资料、准备模型、各 Agent 和保存报告的真实进度；前端只根据后端事件和报告数据渲染。
8. 报告页和历史页读取持久化结果。没有报告时显示未完成状态，不构造设计稿示例分数。
9. 图纸、任务书和历史报告始终按当前用户查询；删除文件、提交或项目时，只清理不再被其他继承版本引用的物理文件。
10. 历史六样本仍由 `preprocess.py`、`runner.py`、`research.py` 和 `evidence_report.py` 复现；新正式实验先由 `asset_audit.py` 检查资产，再由 `blind_protocol.py` 仅复制匿名输入，核对模型、提示词、任务书、校准文件和代码指纹后盲跑并冻结结果，最后在独立进程解封私有答案。
11. `knowledge_governance.py` 为来源、媒体、案例、知识卡和问答分配稳定编号；案例分析还要在 `evidence_register` 中逐项记录来源、页面位置和“官方事实/学科推断”。草稿可以统计整理进度，但只有来源、许可、学科复核和审核状态全部通过时才进入正式验收计数。

## 关键设计决定和原因

- 当前账户、项目和文件继续保存在本机 SQLite 与上传目录中，原因是本阶段先完成真实的单机闭环；上云时再迁移到正式数据库和对象存储。
- 密码采用 PBKDF2-SHA256 加随机盐，数据库只保存会话令牌哈希，原因是即使本地开发也不应保存明文密码和登录令牌。
- 首个正式注册账户接管升级前没有账户归属的历史项目，原因是保留已有测试数据；之后注册的账户严格隔离。
- 用户上传目录由受保护接口读取，原因是项目接口隔离后，公开静态文件仍会造成跨账户访问漏洞。
- 任务书权重由可复核的本地规则计算，再把正文和权重交给模型，原因是只在提示词中说“参考任务书”无法保证最终总分真正改变，也不利于历史追溯。
- 任务书明确写明某专项不要求或不计分时显著降低该项权重；低年级且未提出结构要求时降低结构权重，原因是评分必须贴近课程真实目标。
- 概念、方案、图纸共用一套阶段编排器和统一报告结构，差异通过阶段 Agent 白名单与专项提示词表达，原因是这样能避免三套流程产生冲突代码。
- 综合评审只汇总专项结果，总分由后端按保存的动态权重计算，原因是避免综合模型忽略任务书或重复改变评分口径。
- 报告页取消硬编码演示兜底，原因是占位数据会被误认为真实结果；开发用 `mock` 模式仍保留为显式测试能力。
- 提交、流程、报告、工作区、侧栏和样式均按职责拆分，当前业务代码单文件不超过 500 行，原因是后续新增 Agent 和云端能力时更容易定位与验证改动。
- 阶段化多 Agent 总预算保持 285 秒，原因是需要兼顾多模型顺序评审和前端可接受的等待时间。
- 百炼图纸采用临时 OSS URL 并缓存过期时间，原因是建筑图纸体积较大，base64 直传更容易超时。
- 每次报告保存任务书和知识库快照，原因是历史报告必须保留生成当时的评分口径与依据，不能随资料更新而改变。
- 新正式基准不再使用旧 `.prepared` 同根目录作为“物理隔离”证据；只有通过 `blind_protocol.py` 生成的无答案输入包、不接收答案路径的评图进程、冻结哈希和独立裁判进程才可用于盲测声明。
- 技术失败续跑必须保持模型、提示词、任务书、校准文件、评分代码和样本编号全部不变，并在任何模型上传或调用前完成核对，原因是断点恢复不能成为更换口径或挑选结果的入口。
- 第二轮课程分档锚点在开发集上产生过校准，生产默认已恢复第一轮评分标尺；第二轮规则仅作为科研快照保留，原因是不能把总体 MAE 变差的实验设置直接上线。
- 证据优先架构保留为完整研究模式，但产品默认仍为 `legacy_v1`：两份独立盲测 MAE 仅由 12.90 降至 12.00，且高低样本同为 85.4、排序失败；直接上线会给低分学生错误预期。
