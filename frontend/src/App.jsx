/* 演示验证页面，负责收集输入并展示后端返回的评图结果。 */

import { startTransition, useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const initialForm = {
  name: "",
  buildingType: "",
  ownerName: "",
  designStage: "concept",
  description: "",
};

function buildUrl(path) {
  /* 拼接接口地址，避免不同环境下重复写前缀。 */
  return `${API_BASE_URL}${path}`;
}

async function requestJson(path, options = {}) {
  /* 统一处理前端请求与错误提示。 */
  const response = await fetch(buildUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "请求失败，请稍后重试。");
  }
  return data;
}

function App() {
  /* 管理页面表单、服务状态和评图结果。 */
  const [form, setForm] = useState(initialForm);
  const [healthText, setHealthText] = useState("检查中");
  const [projects, setProjects] = useState([]);
  const [report, setReport] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    /* 页面打开时先加载服务状态和已有项目。 */
    let active = true;

    async function loadOverview() {
      try {
        const [health, recentProjects] = await Promise.all([
          requestJson("/health", { headers: {} }),
          requestJson("/api/projects"),
        ]);
        if (!active) {
          return;
        }
        startTransition(() => {
          setHealthText(health.status === "ok" ? "在线" : "异常");
          setProjects(recentProjects);
        });
      } catch (error) {
        if (!active) {
          return;
        }
        startTransition(() => {
          setHealthText("离线");
          setErrorMessage(error.message || "暂时无法连接后端服务。");
        });
      }
    }

    loadOverview();
    return () => {
      active = false;
    };
  }, []);

  function updateField(field, value) {
    /* 更新单个表单字段。 */
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleSubmit(event) {
    /* 依次创建项目、提交方案，并拉取演示评图结果。 */
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage("");

    try {
      const project = await requestJson("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          building_type: form.buildingType,
          owner_name: form.ownerName,
        }),
      });

      const submission = await requestJson("/api/submissions", {
        method: "POST",
        body: JSON.stringify({
          project_id: project.id,
          title: `${form.name} - 演示提交`,
          design_stage: form.designStage,
          description: form.description,
          image_urls: [],
        }),
      });

      const evaluation = await requestJson(
        `/api/submissions/${submission.id}/evaluate-demo`,
        {
          method: "POST",
          body: JSON.stringify({}),
        }
      );

      startTransition(() => {
        setProjects((current) => [project, ...current].slice(0, 6));
        setReport(evaluation);
      });
    } catch (error) {
      setErrorMessage(error.message || "生成演示评图时出错。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-shell">
      <section className="hero-panel">
        <p className="eyebrow">ArchCritic P0 Visual Check</p>
        <h1>评图系统演示验证台</h1>
        <p className="hero-copy">
          这里先用演示数据把整个流程跑通。你输入一段项目说明，页面会自动完成创建项目、提交方案和生成评图结果。
        </p>
        <div className="status-strip">
          <div className="status-card">
            <span>后端状态</span>
            <strong>{healthText}</strong>
          </div>
          <div className="status-card">
            <span>最近项目数</span>
            <strong>{projects.length}</strong>
          </div>
          <div className="status-card">
            <span>当前模式</span>
            <strong>演示评图</strong>
          </div>
        </div>
      </section>

      <main className="workspace">
        <section className="panel form-panel">
          <div className="panel-heading">
            <h2>提交演示内容</h2>
            <p>先把表单填完整，再点击按钮生成结果。</p>
          </div>

          <form className="critic-form" onSubmit={handleSubmit}>
            <label>
              <span>项目名称</span>
              <input
                aria-label="项目名称"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="例如：城市阅读展亭"
                required
              />
            </label>

            <label>
              <span>建筑类型</span>
              <input
                aria-label="建筑类型"
                value={form.buildingType}
                onChange={(event) => updateField("buildingType", event.target.value)}
                placeholder="例如：小型公共建筑"
                required
              />
            </label>

            <label>
              <span>提交人</span>
              <input
                aria-label="提交人"
                value={form.ownerName}
                onChange={(event) => updateField("ownerName", event.target.value)}
                placeholder="例如：学生甲"
                required
              />
            </label>

            <label>
              <span>设计阶段</span>
              <select
                value={form.designStage}
                onChange={(event) => updateField("designStage", event.target.value)}
              >
                <option value="concept">概念阶段</option>
                <option value="scheme">方案阶段</option>
                <option value="drawing">图纸阶段</option>
              </select>
            </label>

            <label>
              <span>设计说明</span>
              <textarea
                aria-label="设计说明"
                value={form.description}
                onChange={(event) => updateField("description", event.target.value)}
                placeholder="输入一段用于演示验证的方案说明。"
                rows="7"
                required
              />
            </label>

            <button type="submit" disabled={submitting}>
              {submitting ? "生成中..." : "生成演示评图"}
            </button>
          </form>

          {errorMessage ? <p className="error-box">{errorMessage}</p> : null}

          <div className="recent-projects">
            <div className="panel-heading compact">
              <h3>最近项目</h3>
            </div>
            {projects.length === 0 ? (
              <p className="muted-text">还没有项目记录，先试一次提交。</p>
            ) : (
              <ul>
                {projects.map((project) => (
                  <li key={project.id}>
                    <strong>{project.name}</strong>
                    <span>{project.building_type}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="panel result-panel">
          <div className="panel-heading">
            <h2>演示评图结果</h2>
            <p>这里会展示后端返回的汇总结果和分项判断。</p>
          </div>

          {report ? (
            <div className="result-layout">
              <article className="score-board">
                <div>
                  <span className="score-label">总分</span>
                  <strong className="score-value">{report.overall_score}</strong>
                </div>
                <div className="grade-pill">等级 {report.grade}</div>
              </article>

              <article className="summary-card">
                <h3>总评摘要</h3>
                <p>{report.summary}</p>
              </article>

              <div className="tag-columns">
                <section>
                  <h3>需要优先处理</h3>
                  <ul>
                    {report.must_fix.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>

                <section>
                  <h3>建议继续优化</h3>
                  <ul>
                    {report.should_improve.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>

                <section>
                  <h3>当前优势</h3>
                  <ul>
                    {report.strengths.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              </div>

              <section className="agent-list">
                <h3>分项判断</h3>
                <div className="agent-grid">
                  {report.agent_evaluations.map((item) => (
                    <article className="agent-card" key={`${item.agent_type}-${item.dimension}`}>
                      <div className="agent-topline">
                        <h4>{item.dimension}</h4>
                        <span>{item.score}</span>
                      </div>
                      <p>{item.summary}</p>
                      <div className="agent-notes">
                        <strong>亮点</strong>
                        <p>{item.strengths.join(" ")}</p>
                      </div>
                      <div className="agent-notes">
                        <strong>问题</strong>
                        <p>{item.issues.join(" ")}</p>
                      </div>
                      <div className="agent-notes">
                        <strong>建议</strong>
                        <p>{item.suggestions.join(" ")}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : (
            <div className="empty-state">
              <p>还没有生成结果。填完左侧表单后，这里会出现一份完整的演示评图报告。</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
