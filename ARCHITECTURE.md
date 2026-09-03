# ArchCritic 架构说明

## 文件与模块职责

### 后端

- `backend/app/main.py`：后端入口，初始化数据库、中间件和接口；用户上传目录不再作为公开静态目录。
- `backend/app/config.py`：统一读取数据库、上传目录、模型、跨域、登录 Cookie 等配置。
- `backend/app/database.py`：创建数据库连接，并为已有 SQLite 数据库补齐账户、任务书和报告字段。
- `backend/app/models.py`：定义用户、登录会话、问题反馈、项目、提交、图纸、任务书、Agent 结果、报告，以及知识助手会话与消息等数据表。
- `backend/app/schemas.py`：定义前后端接口的数据格式和输入校验规则。
- `backend/app/routers/auth.py`：提供本地注册、登录、退出、当前用户、个人资料和密码修改接口。
- `backend/app/routers/feedback.py`：校验当前登录用户，并把问题反馈保存到数据库供后台处理。
- `backend/app/routers/assets.py`：登录后校验文件归属，再返回用户上传的图纸或任务书。
- `backend/app/routers/projects.py`：负责当前账户的项目创建、列表、单次摘要、详情、历史和删除。
- `backend/app/routers/submissions.py`：提交接口门面，组合下列按职责拆分的路由文件。
- `backend/app/routers/submission_crud.py`：负责提交草稿、继承、任务书上传和基础资料读取。
- `backend/app/routers/submission_stream.py`：负责真实模型流式评图、阶段事件和模型图纸准备。
- `backend/app/routers/submission_reports.py`：负责工作台快照、报告、知识依据、追问、导出和评图辅助接口。
- `backend/app/services/report_pdf.py`：用嵌入中文字体的矢量文字生成多页报告；专项标题与分数直接显示，四项具体小分横排，反馈以颜色、留白和分割线区分。
- `backend/app/routers/submission_report_data.py`：负责报告的保存、读取和接口结构转换。
- `backend/app/routers/submission_common.py`：保存提交路由共用的模型选择、暂停和错误处理规则。
- `backend/app/routers/files.py`：负责图纸修改、单张删除和批量删除，并校验账户归属。
- `backend/app/routers/knowledge_library.py`：提供知识库目录、单卡详情、不提前暴露答案的知识测试与逐题判定、按需 WebP 缩略图，以及账户隔离的流式知识助手和历史会话接口。
- `backend/app/services/knowledge_quiz.py`、`backend/app/knowledge_quiz_schemas.py`：只负责知识测试的五类题目构造、题目与答案要点清理、答案保护、简答要点匹配和提交结构，不参与知识库浏览、知识助手或评图。
- `frontend-v1-replica/src/pages/knowledgeQuiz.tsx`：负责按难度随机抽取 5 题、自由切题、即时反馈、中途退出总结及浏览器本地错题集；不保存后端答题历史。
- `frontend-v1-replica/src/components/baseComponents.tsx`、`helpComponents.tsx`、`accountComponents.tsx`：通用提示卡、新手指引和账户/帮助弹窗使用页面最外层遮罩，避免受 1536 设计画布缩放限制。
- `backend/app/knowledge_assistant_schemas.py`：定义 4 种知识助手工具、提问上下文、推荐结果、引用和历史会话的数据格式。
- `backend/app/services/knowledge_taxonomy.py`：统一七类知识主题、Agent 对应关系和知识卡自测题抽取规则。
- `backend/app/services/auth.py`：提供密码哈希、会话令牌和项目/提交归属校验。
- `backend/app/services/taskbooks.py`：抽取 PDF、DOCX、TXT 任务书正文，整理课程要求，并按阶段、年级和任务书重点生成评分权重。
- `backend/app/services/taskbook_rules.py`：把任务书条目标为强制、弹性、选配、参考或说明，并分配核对专项与证据方式。
- `backend/app/services/uploads.py`：安全解析和删除本地上传文件，防止路径越界和误删共享文件。
- `backend/app/services/drawing_preprocess.py`：保留原图并限量识别合成图中的独立分区，为模型生成可失败回退的辅助裁切输入。
- `backend/app/services/submission_cleanup.py`：集中删除一次提交的关联数据和不再被引用的物理文件。
- `backend/app/services/knowledge_library.py`：读取最终版知识卡和案例卡；目录只解析文字、图片引用数量和首图地址，浏览器接近卡片时才生成并在内存缓存 WebP 缩略图，单卡详情再解析全部对应图片。
- `backend/app/services/knowledge_assistant.py`：合并浏览目录和治理字段，标准化面积等检索条件，召回候选卡片并调用默认真实模型；模型只能返回候选编号，后端会再次过滤不存在的编号，并在面向用户的回答中分离正文与卡片链接。
- `backend/app/services/report_assistant.py`：为报告追问组合当前报告、近期对话、任务书、全部可用图纸和知识候选；流式提取回答并校验知识链接，仅在图纸证据确认原判断错误时同步修订报告、反馈、专项评价和具体小分。
- `backend/app/agents/function_agent.py`：构建模型图文上下文，包含任务书正文、动态权重、知识依据和全部可用图纸。
- `backend/app/agents/function_agent_report.py`：校验功能 Agent 输出并转换为统一报告结构。
- `backend/app/agents/scheme_review.py`：按概念、方案、图纸三个阶段的白名单顺序执行专项 Agent 和综合评审 Agent，并按任务书权重计算总分。
- `backend/app/agents/prompts/visual_score_calibration_v1.py`：定义实验性视觉校准提示词，要求最终 Agent 先判低、中、高档，再引用最近锚点确定总分。
- `backend/app/agents/evidence_review.py`、`prompts/evidence_agents_v2.py`：研究模式下要求模型只返回事实、来源、置信度、任务书状态和 0—4 级判断，再转换为旧报告兼容结构。
- `backend/app/agents/evidence_inventory.py`：研究模式下唯一直接读取全部图纸的事实层，为图纸分配 D 编号、为事实分配 E 编号，并记录可读性、矛盾和信息边界。
- `backend/app/agents/taskbook_compliance.py`：只使用共享事实独立核对任务书强制/弹性条款，不识图、不输出总分，漏报或证据不足时保守记为不确定。
- `backend/app/knowledge_selection.py`：按阶段、Agent 和评价维度分发知识依据，生成稳定 K 编号；研究正式链路只接受已经真实人工批准的内容。
- `backend/app/scoring/`：负责等级到专项分的固定映射、任务书符合度、分数区间和小样本单调教师校准。
- `backend/app/agents/prompts/function_agent_v1.py`：保存功能与流线 Agent 的提示词和输出要求。
- `backend/app/agents/prompts/scheme_agents_v1.py`：保存场地、形式、结构、设计概念、图面表达和综合评审 Agent 的规则与评分项。
- `backend/app/benchmarking/dataset.py`：把私有 Markdown 标注解析为匿名模型输入和人工标准答案；旧六样本仍是同根目录的历史格式。
- `backend/app/benchmarking/preprocess.py`：读取课程任务书，把 PDF 图纸逐页转为受尺寸控制的高清图片。
- `backend/app/benchmarking/runner.py`：保留历史六样本的多 Agent 运行和同进程语义裁判，只用于复现旧实验。
- `backend/app/benchmarking/anonymize.py`：清除论文实验图纸中的身份文字和图片元数据，并保存人工视觉复核记录。
- `backend/app/benchmarking/paper_experiment_prompts.py`：定义 C0 直接评审与 C1 结构化提示词增强单模型评审的冻结提示和输出结构。
- `backend/app/benchmarking/paper_experiment.py`：准备九样本匿名输入与私有答案，生成中档留一法锚点，并执行和冻结 C0—C3 四个条件。
- `backend/app/benchmarking/paper_experiment_analysis.py`：校验作者逐条核对决定，计算教师分数误差、问题严格精确率、召回率、F1 和暂停闸门。
- `backend/app/benchmarking/visual_anchor_experiment.py`：生成匿名视觉锚点集，并复用冻结 C2 专项结果执行三案例总分校准测试。
- `backend/app/benchmarking/blind_protocol.py`：新正式评测流程，把无答案输入包、一次性盲跑、结果哈希冻结和冻结后独立裁判拆为不同进程。
- `backend/app/benchmarking/asset_audit.py`、`asset_audit_report.py`：只读盘点样本、授权、知识卡、案例和媒体权限，生成不含教师分或标注答案的缺口报告。
- `backend/app/benchmarking/asset_content_validation.py`：严格核对内容字段、来源关联、媒体许可、审核人和逐条证据；分别统计“结构合格草稿”“具备深度证据草稿”和“正式验收内容”，防止用空槽位或未经复核的草稿凑数量。
- `backend/app/benchmarking/baseline_snapshot.py`：记录评分相关代码、提示词、运行配置和历史总体指标的冻结指纹，不接触单份教师答案。
- `backend/app/scoring/visual_anchors.py`：校验视觉锚点清单、图片文件、分档覆盖和指纹，并整理最终 Agent 使用的锚点上下文。
- `backend/app/benchmarking/knowledge_governance.py`：建立来源、媒体、案例、知识卡和问答治理清单；只初始化缺失文件，不覆盖人工审核结果。
- `backend/app/benchmarking/content_review.py`：导出 150 条内容与固定任务复核表，锁定输入哈希；只有完整人工决定和显式确认才能回写，AI 不能自行批准。
- `backend/app/benchmarking/content_evaluation.py`：验证并执行 20 个案例检索和 20 个问题联动固定任务，分别使用前五相关数和知识—案例联合覆盖率验收。
- `../ArchCritic相关资料/知识库最终版/.archcritic/长程Goal治理/`：保存来源台账、逐图媒体许可、100 张知识卡和 50 份案例机器记录；隐藏目录不进入 Obsidian 图谱，候选内容与人工批准后的正式内容分开计数。
- `backend/app/benchmarking/metrics.py`：计算教师分 MAE、RMSE、偏差、相关性、人工区间和语义指标。
- `backend/app/benchmarking/research.py`、`charts.py`：导出 CSV、JSON、SVG 图表、论文数据报告和工作总结。
- `backend/app/benchmarking/calibration.py`、`evidence_report.py`：固定四份校准与两份盲测划分，拟合校准器并导出新版科研数据包。
- `backend/scripts/benchmark_review.py`：提供历史基准复现，以及新盲测输入包、盲跑冻结和独立裁判命令入口。
- `backend/scripts/paper_experiment.py`：提供九样本四条件论文实验的准备、运行、本地核对、统计、暂停闸门和状态查询入口。
- `backend/scripts/build_paper_experiment_report.py`：从四组冻结指标生成论文 CSV、Markdown 结果报告和 SVG/PDF/PNG 图表。
- `backend/scripts/goal_asset_audit.py`：生成长程 Goal 阶段 0—2 机器盘点和人类可读缺口报告。
- `backend/scripts/knowledge_content_review.py`：导出、校验和回写人工内容复核表，回写必须显式确认全部决定来自人工。
- `backend/scripts/content_evaluation_status.py`：盘点 40 个固定检索/联动任务，并在全部人工批准后执行本地检索验收。
- `backend/scripts/initialize_knowledge_governance.py`：初始化公共建筑内容治理工作区。
- `backend/app/wiki.py`：检索 Obsidian 知识卡片，整理为模型可引用、前端可显示的依据和图片。
- `backend/app/governed_wiki.py`：把人工批准的结构化知识卡和案例转换为检索条目；优先读取 `.archcritic/长程Goal治理` 并兼容旧 `99维护记录`，案例必须同时通过来源、证据和逐图许可检查，并保留图片署名。
- `backend/app/llm/`：封装演示模式、千问百炼调用和百炼临时图纸地址；`dashscope_client.py` 是评图与助手共用的百炼兼容传输层。

### 前端

- `frontend-v1-replica/src/App.tsx`：处理官网、登录页和受保护功能页的路由切换。
- `frontend-v1-replica/src/pagesAuth.tsx`：提供与现有视觉一致的双栏注册登录页。
- `frontend-v1-replica/src/state/auth.tsx`、`src/api/auth.ts`：管理当前本地账户和登录接口；注册成功后通过 `src/state/onboarding.ts` 排队一次首次工作台指引，普通登录不触发。
- `frontend-v1-replica/src/state/workspace.tsx`：组合项目工作区状态，通过单次快照和版本化缓存保持报告、图纸与历史一致；文件动作和公共转换已拆到 `workspaceFileActions.ts`、`workspaceShared.ts`。
- `frontend-v1-replica/src/pagesFlow.tsx`：流程页面门面；项目信息、阶段选择、上传图纸和评图工作台分别位于 `src/pages/flow*.tsx`。
- `frontend-v1-replica/src/pagesResults.tsx`：结果页面门面；报告、历史、公共报告组件和历史数据处理位于 `src/pages/report*.tsx`、`historyPage.tsx`。
- `frontend-v1-replica/src/pages/reportPage.tsx`、`reportAssistant.tsx`、`reportShared.tsx`、`reportKnowledgeCard.tsx`：分别组织报告评分与反馈布局、可跨报告与知识页延续的流式 AI 助手、公共数据转换，以及反馈弹窗内的完整知识卡阅读；`state/reportKnowledgeContext.ts` 保存本次报告推荐的来源与整组引用。
- `frontend-v1-replica/src/pages/knowledgePage.tsx`、`knowledgeAssistant.tsx`、`knowledgeQuiz.tsx`、`src/styles/knowledge.css`、`src/api/knowledge.ts`：展示知识总览、深度阅读和按难度测试，提供五类题型、逐题答案、结果汇总、本地进度恢复、搜索、关联跳转、流式助手、四类工具、历史会话及可恢复浏览状态的 AI 推荐结果。
- `frontend-v1-replica/src/components.tsx`：公共组件门面；基础组件、侧栏、账户弹窗与帮助中心位于 `src/components/`，帮助文章内容由 `src/data/helpContent.ts` 统一提供。
- `frontend-v1-replica/src/styles.css`、`src/styles/report.css`：分别保存通用样式和报告相关样式。
- `frontend-v1-replica/vite.config.ts`：固定本地开发端口 `4173`，并使用轮询保证 WSL 挂载盘热更新。
- `DESIGN.md`：记录新版前端视觉规范、组件规则和字号层级。

### 部署

- `deploy/archcritic-backend.service`：以独立 `archcritic` 系统账户运行 FastAPI，只监听 `127.0.0.1:8000`。
- `deploy/archcritic-web.service`、`deploy/nginx-http.conf`：备案期从 8080 提供前端静态文件，并把接口和知识库图片转发到后端。
- `deploy/Caddyfile`：备案完成后为 `api.archcritic.cn` 提供 HTTPS 入口，并使用 RSA 2048 证书兼容旧手机和内嵌浏览器。
- `deploy/backend.env.example`：定义服务器数据库、上传目录、知识库、模型和 Cookie 配置，不保存真实密钥。
- `edgeone.json`、`frontend-v1-replica/.env.production`：定义 EdgeOne Pages 的前端构建、单页路由回退和 `archcritic.cn` 使用的正式 API 地址。

## 模块之间的调用关系

1. 官网“体验产品”进入受保护页面；未登录时 `App.tsx` 转到注册登录页，后端通过 HttpOnly Cookie 识别当前账户。
2. 前端工作区创建当前账户的项目和提交，上传图纸与任务书；接口先校验项目归属，再保存到 SQLite 和本地上传目录。
3. 任务书上传时立即抽取正文。开始评图时，`taskbooks.py` 生成动态权重，`taskbook_rules.py` 同时生成可审计的强制、弹性、选配和参考规则。
4. `drawing_preprocess.py` 先保留全部原图，再为数量较少且存在贯穿留白的合成平面或技术图生成限量辅助裁切；`function_agent.py` 随后把项目资料、设计说明、任务书正文、权重、知识依据和图纸组合成可追溯的模型上下文。
5. `scheme_review.py` 根据阶段过滤 Agent：概念阶段执行场地、形式、概念；方案阶段执行功能、场地、形式、结构；图纸阶段执行图面表达、功能、场地、形式、结构，最后按需执行综合评审。
6. 默认 `legacy_v1` 沿用原专项分；显式启用 `evidence_v2` 时，先生成共享事实清单，各专项 Agent 只读文本证据判等级，再由独立层核对任务书，`scoring/` 固定换算专项分、符合度、校准分和区间。两种模式都写入兼容的 `agent_evaluations`。
7. 流式接口通过 SSE 返回读取资料、准备模型、各 Agent 和保存报告的真实进度；前端只根据后端事件和报告数据渲染。
8. 报告页和历史页读取持久化结果。报告知识卡按 `library_item_id` 调用知识库详情接口，与知识库阅读页共用完整正文和图片，只有接口失败时才回退到当次快照；下载时由 `report_pdf.py` 生成包含总分、专项评分、具体小分和反馈的矢量 PDF，不写入关联知识卡。没有报告时显示未完成状态，不构造设计稿示例分数。
9. 图纸、任务书和历史报告始终按当前用户查询；删除文件、提交或项目时，只清理不再被其他继承版本引用的物理文件。
10. 历史六样本仍由 `preprocess.py`、`runner.py`、`research.py` 和 `evidence_report.py` 复现；新正式实验先由 `asset_audit.py` 检查资产，再由 `blind_protocol.py` 仅复制匿名输入，核对模型、提示词、任务书、校准文件和代码指纹后盲跑并冻结结果，最后在独立进程解封私有答案。
11. 九样本论文实验由 `paper_experiment.py` 生成不含分数和人工问题的匿名包；C0—C3 读取同一输入并分别冻结。中档提示只使用排除当前案例后的汇总锚点。冻结后，`paper_experiment_analysis.py` 才在本地读取私有答案和作者逐条核对决定，外部模型不接触私有答案。
12. 实验性视觉锚点链路只在五个专项 Agent 完成后运行：最终评分 Agent 同时读取当前图纸、专项结论和匿名锚点图，输出档位、最近锚点、比较依据与总分；教师测试分数只在结果冻结后用于本地误差分析。
13. `knowledge_governance.py` 为来源、媒体、案例、知识卡和问答分配稳定编号；案例分析还要在 `evidence_register` 中逐项记录来源、页面位置和“官方事实/学科推断”。草稿可以统计整理进度，但只有来源、许可、学科复核和审核状态全部通过时才进入正式验收计数。
14. 知识助手收到问题后先从最终版目录和治理 JSON 提取候选，再把候选编号与必要摘要交给默认模型；后端流式转发回答、过滤虚构编号并保存会话，前端只用通过校验的推荐结果改变当前知识库列表。当前卡片问答保留扩展文字但不返回推荐链接。评图从同一目录选取候选，并把实际使用内容保存为不可变报告快照。
15. 报告助手先持久化用户问题，再使用独立数据库会话在线程中准备图纸并调用模型，通过 SSE 逐步返回正文；页面暂停只停止当前接收，后台仍完成并保存回答。知识推荐保存整组引用和报告来源，知识页复用同一个报告助手与对话，只有新一轮推荐完成后才更新结果。图纸复核先确认本轮争议的图纸证据：原判断正确时不修改；确认错误时限幅调整分数，并同步清理或改写总评、四类反馈、专项结论和具体小分理由，最后写入报告审计记录。
16. 账户帮助入口与首页共用操作指引和常见问题内容；问题反馈通过受保护接口绑定当前用户并写入 `feedback` 表，退出操作在确认后才删除登录会话。

## 关键设计决定和原因

- 备案期入口固定使用 8080，且 Nginx 使用独立配置和 systemd 服务，原因是服务器现有游戏已经占用 80 和 3000，部署 ArchCritic 不得接管或重启原服务。
- 服务器后端只监听回环地址，外部请求统一经网页网关进入；数据库、上传文件和知识库放在 `/var/lib/archcritic/`，原因是限制直接暴露并避免代码更新覆盖用户数据。
- HTTPS Cookie 只在备案完成、正式 HTTPS 生效后开启；备案期 HTTP 使用 `SameSite=Lax` 且关闭 Secure，原因是浏览器在纯 HTTP 下不会发送 Secure Cookie。
- 用户界面始终按可直接交付的产品状态呈现，不暴露内容治理、审批进度或内部状态标签；模型不确定性只通过统一的中性使用提示表达。治理字段和检索准入门槛仍保留在后端，继续服务内容审计和正式评图。
- 当前产品只保留百炼运行入口：评图、专项 Agent、综合评审和报告生成固定使用 `dashscope/qwen3.8-max`；知识库助手与报告辅助助手固定使用 `dashscope/qwen3.7-plus`。前端不提供模型切换，旧草稿中的其他模型值恢复时直接回落到 `qwen3.8-max`，助手请求不再携带模型参数。
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
- 自动拆图只使用本地图像分区、保留原图、限制最终模型图片数量并允许失败回退，原因是提高密集图纸可读性时不能额外增加一次识图模型调用，也不能扩大报告 JSON 或明显挤占 285 秒评图预算。
- 首页一次读取所有项目的轻量版本摘要，完整工作台按悬停、聚焦或点击读取单次快照，原因是减少重复请求而不是把首页等待简单推迟到项目详情页。
- 每次报告保存任务书和知识库快照，原因是历史报告必须保留生成当时的评分口径与依据，不能随资料更新而改变。
- 知识助手采用“本地召回、模型解释、后端校验”而不是让模型直接遍历文件，原因是 150 张卡片规模下更快、更可控，也能阻止虚构编号；普通问答和当前卡片问答不改变列表，推荐工具使用独立结果状态并保存原总览快照。
- 报告追问采用“问题先入库、模型后台执行、页面重新读取”的恢复方式，原因是用户切换页面或暂停前端展示时，已经发出的提问不应丢失，也不能让一次较慢的多模态调用占住知识库请求。
- 报告正文优先展示四项具体小分和反馈要点，关联知识在同一弹窗完整阅读，连续对话收纳为悬浮遮罩助手；提示卡统一挂到页面最外层并使用全屏遮罩，避免画布缩放或父容器宽度造成遮罩边缘留白。
- 新正式基准不再使用旧 `.prepared` 同根目录作为“物理隔离”证据；只有通过 `blind_protocol.py` 生成的无答案输入包、不接收答案路径的评图进程、冻结哈希和独立裁判进程才可用于盲测声明。
- 九样本论文实验是内部基准而非外部盲测；教师分数和人工问题清单与模型输入物理分离，语义核对采用作者本地逐条决定，不虚构独立教师裁判，也不向外部模型发送私有答案。
- 视觉锚点只用于最终总分尺度定位，不作为专项问题答案；三案例测试没有改善 MAE 或高中低排序，因此该能力保持实验性，不进入产品默认评分链路。
- 技术失败续跑必须保持模型、提示词、任务书、校准文件、评分代码和样本编号全部不变，并在任何模型上传或调用前完成核对，原因是断点恢复不能成为更换口径或挑选结果的入口。
- 第二轮课程分档锚点在开发集上产生过校准，生产默认已恢复第一轮评分标尺；第二轮规则仅作为科研快照保留，原因是不能把总体 MAE 变差的实验设置直接上线。
- 证据优先架构保留为完整研究模式，但产品默认仍为 `legacy_v1`：两份独立盲测 MAE 仅由 12.90 降至 12.00，且高低样本同为 85.4、排序失败；直接上线会给低分学生错误预期。
