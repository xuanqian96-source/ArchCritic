// 结果页面：复刻完整评图报告和历史版本对比页。
import { useState } from "react";
import type { PageProps } from "./App";
import { Badge, Button, Card, PageTitle, Sidebar } from "./components";
import { useWorkspace } from "./state/workspace";
import type { AgentEvaluation, SubmissionHistory } from "./types/api";

const fallbackDimensions: AgentEvaluation[] = [
  { agent_type: "function_agent", dimension: "功能与流线", score: 82, summary: "主要问题集中在主入口与公共空间的联系、后勤路径和消防疏散距离校核。建议优先减少人车交叉与局部回折。", strengths: [], issues: [], suggestions: [], details: {} },
  { agent_type: "site_agent", dimension: "场地回应", score: 76, summary: "场地回应具备基础合理性，仍需继续校核周边关系。", strengths: [], issues: [], suggestions: [], details: {} },
  { agent_type: "form_agent", dimension: "几何形式", score: 72, summary: "几何形式表达仍需强化秩序与空间逻辑。", strengths: [], issues: [], suggestions: [], details: {} },
  { agent_type: "structure_agent", dimension: "结构与构造", score: 84, summary: "结构构造总体可行，局部节点仍需复核。", strengths: [], issues: [], suggestions: [], details: {} },
];

// 渲染完整评图报告。
export function ReportPage({ go }: PageProps) {
  const { chatMessages, downloadCurrentReport, draft, report, sendQuestion, startEvaluation } = useWorkspace();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [detailOpen, setDetailOpen] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const dimensions = report?.agent_evaluations.length ? report.agent_evaluations : fallbackDimensions;
  const selected = dimensions[Math.min(selectedIndex, dimensions.length - 1)];
  const traces = report ? [...report.must_fix, ...report.should_improve, ...report.optional_improvements].slice(0, 3) : [
    "消防疏散距离需要复核",
    "公共空间动线仍有绕行",
    "局部节点缺少缓冲",
  ];
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <h1 className="absolute left-[307px] top-[53px] text-[34px] font-bold leading-[44px]">评图报告 {draft.name} <span className="text-[24px] text-[#6b7385]">V1</span></h1>
      <p className="absolute left-[309px] top-[107px] text-[14px] leading-[22px] text-[#53565e]">多维度评分体系</p>
      <div className="font-inter absolute left-[1193px] top-[99px] flex gap-[19px]">
        <Button kind="white" className="w-[116px] font-semibold" onClick={() => { go("processing"); void startEvaluation(); }}>重新生成</Button>
        <Button kind="purple" className="w-[132px] rounded-[12px] font-semibold" onClick={() => go("history")}>历史版本对比</Button>
      </div>
      <Card className="font-inter absolute left-[307px] top-[149px] h-[176px] w-[756px] rounded-[16px]">
        <ScoreRing score={String(Math.round(report?.overall_score ?? 78))} />
        <div className="absolute left-[145px] top-[29px]">
          <h2 className="text-[16px] font-bold">整体评价</h2>
          <p className="mt-2 w-[534px] text-[12px] leading-5 text-[#53565e]">{report?.summary ?? "方案整体完成度较高，功能与流线表现稳定，场地回应具备基础合理性。当前需要优先处理几何形式表达与结构构造定位之间的对应关系。"}</p>
          <b className="mt-1 block text-[12px]">建议先查看“功能与流线”与“结构与构造”的重点问题。</b>
        </div>
        <Button kind="white" className="absolute bottom-[18px] right-[138px] w-[114px]" onClick={() => go("confirm")}>查看项目信息</Button>
        <Button className="absolute bottom-[18px] right-5 w-[102px]" onClick={downloadCurrentReport}>下载报告</Button>
      </Card>
      <section className="font-inter white-panel figma-shadow absolute left-[307px] top-[354px] h-[453px] w-[756px] overflow-hidden rounded-[24px]">
        <h2 className="absolute left-[22px] top-[14px] text-[16px] font-bold">评分维度</h2>
        <span className="absolute left-[98px] top-[17px] text-[11px] text-[#9a9ea7]">点击切换查看对应问题与建议</span>
        <div className="absolute left-[22px] top-[44px] flex gap-[10px]">
          {dimensions.map((item, index) => <button onClick={() => setSelectedIndex(index)} className={`h-[36px] rounded-[10px] px-[16px] text-[12px] font-bold ${index === selectedIndex ? "bg-[#171719] text-white" : "bg-[#fafbfc] text-[#53565e]"}`} key={item.agent_type}>{item.dimension}<span className="ml-10 text-[16px]">{Math.round(item.score)}</span></button>)}
        </div>
        <div className="absolute left-[22px] top-[90px] h-[188px] w-[712px] rounded-[12px] bg-[#171719] px-4 py-[14px] text-white">
          <span className="text-[11px]">当前维度</span>
          <h3 className="mt-3 text-[22px] font-bold">{selected.dimension}</h3>
          <b className="absolute right-[25px] top-[22px] text-[48px] leading-[54px]">{Math.round(selected.score)}</b>
          <p className="mt-3 w-[560px] text-[12px] leading-5">{selected.summary}</p>
          <Button kind="white" className="absolute bottom-4 right-4 h-[34px] w-[106px] text-[12px]" onClick={() => setDetailOpen(true)}>查看详情</Button>
        </div>
        <h3 className="absolute left-[22px] top-[285px] text-[16px] font-bold">知识库追溯</h3>
        <div className="absolute left-[22px] top-[311px] w-[660px] space-y-2">
          {traces.map((text, index) => <TraceRow key={`${text}-${index}`} badge={["必须修改", "重点优化", "建议关注"][index] ?? "建议关注"} text={text} onClick={() => setReferenceOpen(true)} />)}
        </div>
        <div className="absolute right-[24px] top-[313px] h-[104px] w-1 rounded-full bg-[#e8ebef]"><span className="block h-6 w-1 rounded-full bg-[#cbd2dc]" /></div>
      </section>
      <ChatPanel messages={chatMessages} sendQuestion={sendQuestion} />
      {detailOpen && <ReportOverlay title={selected.dimension} subtitle="专项评图详情" onClose={() => setDetailOpen(false)} lines={[...selected.issues, ...selected.suggestions]} fallback={selected.summary} />}
      {referenceOpen && <ReportOverlay title={report?.references[0]?.title ?? "知识库依据"} subtitle="知识库追溯" onClose={() => setReferenceOpen(false)} lines={[report?.references[0]?.display_content || report?.references[0]?.excerpt || "当前条目来自本次报告关联的知识库依据。"]} fallback="" />}
    </div>
  );
}

// 渲染综合得分圆环。
function ScoreRing({ score }: { score: string }) {
  return (
    <div className="absolute left-[22px] top-[27px] h-[98px] w-[98px] rounded-full border-[8px] border-[#efe9ff]" style={{ background: "conic-gradient(#6c4dff 0deg 281deg, transparent 281deg)" }}>
      <div className="absolute left-[8px] top-[8px] flex h-[66px] w-[66px] flex-col items-center justify-center rounded-full bg-white">
        <b className="text-[34px] leading-9 text-[#6c4dff]">{score}</b>
        <span className="text-[10px] text-[#53565e]">综合评分</span>
      </div>
      <span className="absolute left-[13px] top-[86px] flex h-6 w-[52px] items-center justify-center rounded-full border border-[#6c4dff] bg-[#efe9ff] text-[11px] font-bold text-[#6c4dff]">良好</span>
    </div>
  );
}

// 渲染知识库追溯行。
function TraceRow({ badge, text, onClick }: { badge: string; text: string; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className="flex h-[38px] w-full items-center rounded-[10px] bg-[#fafbfc] px-3 text-left text-[12px]">
      <span className="mr-3 rounded-full bg-[#171719] px-3 py-1 text-[10px] font-bold text-white">{badge}</span>
      <b>{text}</b><span className="ml-auto text-[10px] text-[#53565e]">查看</span>
    </button>
  );
}

// 在不改变主页面布局的前提下展示报告详情。
function ReportOverlay({ title, subtitle, lines, fallback, onClose }: { title: string; subtitle: string; lines: string[]; fallback: string; onClose: () => void }) {
  const visibleLines = lines.length ? lines : [fallback];
  return (
    <div className="absolute inset-0 z-20 bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[482px] top-[174px] h-[470px] w-[572px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <p className="text-[12px] text-[#6c4dff]">{subtitle}</p>
        <h2 className="mt-2 text-[24px] font-bold">{title}</h2>
        <div className="mt-6 space-y-3 text-[13px] leading-6 text-[#53565e]">
          {visibleLines.map((line, index) => <p className="rounded-[12px] bg-[#fafbfc] px-4 py-3" key={`${line}-${index}`}>{line}</p>)}
        </div>
        <p className="absolute bottom-6 left-7 text-[11px] text-[#9a9ea7]">点击空白区域关闭</p>
      </section>
    </div>
  );
}

// 渲染报告右侧继续对话区。
function ChatPanel({ messages, sendQuestion }: { messages: { role: "user" | "assistant"; content: string }[]; sendQuestion: (content: string) => Promise<void> }) {
  const [question, setQuestion] = useState("");
  const userMessage = [...messages].reverse().find((item) => item.role === "user")?.content ?? "为什么功能与流线得分相对较高？";
  const assistantMessage = [...messages].reverse().find((item) => item.role === "assistant")?.content ?? "主要原因是功能分区清晰，公共空间与主要入口之间的关系明确。但后勤路径和消防距离仍需要复核，所以当前得分停留在 82。";
  const submit = async (content = question) => {
    if (!content.trim()) return;
    setQuestion("");
    await sendQuestion(content);
  };
  return (
    <section className="font-inter white-panel figma-shadow absolute left-[1089px] top-[149px] h-[658px] w-[371px] overflow-hidden rounded-[22px] px-[22px] py-[20px]">
      <h2 className="text-[18px] font-bold">继续与系统对话</h2>
      <p className="mt-1 text-[12px] text-[#9a9ea7]">追问报告原因、定位问题或生成优化动作</p>
      <div className="mt-7 flex gap-3">
        <img className="h-9 w-9" src="/assets/v1/report-avatar.svg" />
        <p className="w-[276px] rounded-[12px] border border-[#e8ebef] bg-white px-3 py-3 text-[12px] leading-5">报告已生成。我可以继续解释扣分原因、定位图纸问题，或生成下一轮优化动作。</p>
      </div>
      <div className="ml-[30px] mt-2 flex justify-end gap-3">
        <p className="w-[272px] rounded-[12px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-3 text-[12px] leading-5"><b className="block text-[#6b7385]">你的追问</b>{userMessage}</p>
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#171719] text-[12px] font-bold text-white">我</span>
      </div>
      <div className="mt-4 flex gap-3">
        <img className="h-9 w-9" src="/assets/v1/report-avatar.svg" />
        <p className="w-[276px] rounded-[12px] border border-[#d9ceff] bg-[#fbfaff] px-3 py-3 text-[12px] leading-5"><b className="block text-[#6c4dff]">系统回答</b>{assistantMessage}</p>
      </div>
      <b className="mt-3 block text-[12px]">你可以继续追问</b>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-bold">
        <button type="button" className="rounded-full border border-[#e8ebef] px-3 py-2" onClick={() => void submit("生成人口优化方案")}>生成人口优化方案</button>
        <button type="button" className="rounded-full border border-[#e8ebef] px-3 py-2" onClick={() => void submit("解释结构与构造扣分")}>解释结构与构造扣分</button>
        <button type="button" className="rounded-full border border-[#e8ebef] px-3 py-2" onClick={() => void submit("列出必须修改项")}>列出必须修改项</button>
      </div>
      <div className="absolute bottom-6 left-[22px] h-[126px] w-[322px] rounded-[14px] border border-[#e8ebef] bg-[#fafbfc] px-3 py-2 text-[12px] text-[#9a9ea7]">
        <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="继续追问评图进度..." className="h-[62px] w-full resize-none bg-transparent outline-none placeholder:text-[#9a9ea7]" />
        <div className="absolute bottom-2 left-2 h-[27px] w-[222px] rounded-[8px] border border-[#e8ebef] bg-white px-3 py-1.5">模型　<b className="ml-2 text-[#171719]">ArchCritic Pro</b></div>
        <Button className="absolute bottom-2 right-2 h-[27px] w-[55px] px-2 text-[12px]" onClick={() => void submit()}>发送</Button>
      </div>
      <div className="pointer-events-none absolute right-[6px] top-[87px] h-[482px] w-1 rounded-full bg-[rgba(238,240,244,0.96)]">
        <span className="absolute left-0 top-0 h-[169px] w-1 rounded-full bg-[#c9ced8]" />
      </div>
    </section>
  );
}

// 渲染历史版本对比页。
export function HistoryPage({ go }: PageProps) {
  const { history, openSubmission } = useWorkspace();
  const [metric, setMetric] = useState("总得分变化");
  const fallbackHistory: SubmissionHistory[] = [
    { id: 0, title: "V1 初稿", design_stage: "初稿", overall_score: 65 },
    { id: 0, title: "V2 调整", design_stage: "调整", overall_score: 70 },
    { id: 0, title: "V3 优化", design_stage: "优化", overall_score: 76 },
    { id: 0, title: "V4 深化", design_stage: "深化", overall_score: 82 },
    { id: 0, title: "V5 当前", design_stage: "当前", overall_score: 84 },
  ];
  const versions = history.length ? history : fallbackHistory;
  const metricName = metric === "总得分变化" ? "" : metric;
  const values = versions.map((item) => metricName ? item.dimension_scores?.[metricName] ?? item.overall_score ?? 0 : item.overall_score ?? 0);
  const points = values.map((score, index) => {
    const x = versions.length === 1 ? 550 : 54 + index * (994 / (versions.length - 1));
    const y = 400 - (score - 50) * 7;
    return [x, Math.max(32, Math.min(400, y)), score] as const;
  });
  const firstScore = values[0] ?? 0;
  const latestScore = values[values.length - 1] ?? 0;
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} creating />
      <PageTitle title="历史版本对比" subtitle="对比 V2 与 V3 的图纸、评分与修改建议，追踪设计思维演变。" />
      <Button kind="purple" className="absolute right-[75px] top-[100px] w-[132px] rounded-[12px]" onClick={() => go("report")}>返回</Button>
      <Card className="absolute left-[307px] top-[150px] h-[650px] w-[1154px] p-6">
        <h2 className="text-[20px] font-bold">版本评分趋势</h2>
        <p className="mt-1 text-[13px] text-[#6b7280]">按版本迭代顺序从左至右查看评分变化；切换上方指标即可查看不同维度折线。</p>
        <div className="mt-5 flex gap-3">{["总得分变化","功能与流线","场地与回应","几何形式","结构与构造"].map(text => <Button kind={metric === text ? "dark" : "white"} className="h-9" key={text} onClick={() => setMetric(text)}>{text}</Button>)}<div className="ml-auto h-[54px] w-[362px] rounded-[12px] border border-[#e8ebef] bg-white px-5 py-4 text-[13px] text-[#9a9ea7]">当前显示　 <b className="text-[#171719]">{metric}</b>　 <b className="float-right text-[#159447]">V1 → V{versions.length}　{latestScore - firstScore >= 0 ? "+" : ""}{Math.round(latestScore - firstScore)}</b></div></div>
        <div className="relative mt-2 h-[450px]">
          <svg viewBox="0 0 1080 450" className="absolute inset-0 h-full w-full">
            {[40,100,160,220,280,340,400].map(y => <line key={y} x1="54" y1={y} x2="1050" y2={y} stroke="#d9dde3" strokeWidth="1" />)}
            <polyline points={points.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="#6c4dff" strokeWidth="4" />
            <polyline points="54,268 302,192 550,112 798,76 1048,32" fill="none" stroke="#b9bdc4" strokeWidth="2" />
            <polyline points="54,316 302,244 550,184 798,160 1048,126" fill="none" stroke="#c3c6cb" strokeWidth="2" />
            <polyline points="54,340 302,268 550,160 798,76 1048,66" fill="none" stroke="#d4d7dc" strokeWidth="2" />
            {points.map(([x,y,value], index) => <g key={`${x}-${index}`}><circle cx={x} cy={y} r={index === points.length - 1 ? "8" : "5"} fill="#6c4dff" stroke="white" strokeWidth="2" /><text x={Number(x)-8} y={Number(y)-22} fill="#171719" fontSize="13" fontWeight="700">{Math.round(value)}</text></g>)}
          </svg>
          <div className="absolute bottom-[4px] left-[34px] right-[22px] flex justify-between text-[12px] text-[#53565e]">{versions.map((item, index) => <button type="button" key={`${item.id}-${index}`} onClick={() => item.id && void openSubmission(item.id).then(() => go("report"))}>V{index + 1} {item.design_stage}</button>)}</div>
          <div className="absolute right-[68px] top-[126px] h-[126px] w-[248px] rounded-[12px] bg-[#6c4dff] p-4 text-[12px] leading-6 text-white"><b className="text-[15px]">V4 深化方案 <span className="float-right">总分 82</span></b><p className="mt-2">主要提升：结构与构造 +8<br />仍需复核：消防疏散距离<br />系统建议：进入细部节点优化</p></div>
        </div>
      </Card>
    </div>
  );
}
