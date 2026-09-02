// 报告 AI 辅助助手：用与知识助手一致的悬浮入口、遮罩面板和对话输入完成报告追问。
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { PageProps } from "../App";
import { saveReportKnowledgeContext } from "../state/reportKnowledgeContext";
import type { ChatMessage, OverallReport } from "../types/api";
import { buildChatSuggestions, renderChatText } from "./reportShared";

const REPORT_CHAT_TOOLS: { id: NonNullable<ChatMessage["tool"]>; name: string; description: string; placeholder: string }[] = [
  { id: "drawing_review", name: "图纸复核", description: "重新核对图纸证据与原报告判断", placeholder: "描述你认为评判有误的位置…" },
  { id: "issue_explanation", name: "问题解释", description: "结合图纸、知识库与专业知识详细说明", placeholder: "输入想进一步了解的扣分点…" },
  { id: "knowledge_recommendation", name: "知识推荐", description: "按当前任务与薄弱点推荐学习卡片", placeholder: "描述希望补强的设计问题…" },
];

const REPORT_TOOL_ICON_PATHS: Record<string, string> = {
  drawing_review: '<path d="M3 5h18v14H3zM7 15l3-3 2 2 3-4 3 5"/><circle cx="8" cy="9" r="1"/>',
  issue_explanation: '<circle cx="12" cy="12" r="9"/><path d="M9.7 9a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.2.9-1.2 1.9M12 16h.01"/>',
  knowledge_recommendation: '<path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22zM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z"/>',
};

interface DragState { pointerId: number; offsetX: number; offsetY: number; startX: number; startY: number; moved: boolean; }

// 读取富文本输入中的纯问题，工具标签不会进入模型正文。
function readReportQuestion(editor: HTMLDivElement): string {
  const clone = editor.cloneNode(true) as HTMLDivElement;
  clone.querySelectorAll(".report-chat-inline-tool").forEach((node) => node.remove());
  return (clone.textContent ?? "").replace(/\u200b/g, "").replace(/\u00a0/g, " ");
}

// 清除 contentEditable 在空内容时自动留下的 div/br，避免输入框凭空多出一行。
function syncReportQuestion(editor: HTMLDivElement): string {
  const value = readReportQuestion(editor);
  if (!value.trim() && editor.childNodes.length) editor.replaceChildren();
  return value;
}

// 删除工具标签前后生成的不可见空格。
function removeGeneratedLeadingSpace(editor: HTMLDivElement): void {
  editor.normalize();
  const firstNode = editor.firstChild;
  if (firstNode?.nodeType !== Node.TEXT_NODE) return;
  firstNode.textContent = (firstNode.textContent ?? "").replace(/^[\s\u00a0]+/, "");
  if (!firstNode.textContent) firstNode.remove();
}

interface ReportAssistantProps {
  submissionId: number;
  messages: ChatMessage[];
  report: OverallReport | null;
  sendQuestion: (content: string, tool?: ChatMessage["tool"], signal?: AbortSignal, onDelta?: (text: string) => void) => Promise<void>;
  go: PageProps["go"];
}

// 渲染报告页右下角的统一 AI 辅助助手。
export function ReportAssistant({ submissionId, messages, report, sendQuestion, go }: ReportAssistantProps) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [paused, setPaused] = useState(false);
  const [sendingTool, setSendingTool] = useState<NonNullable<ChatMessage["tool"]>>("none");
  const [streamingText, setStreamingText] = useState("");
  const [toolOpen, setToolOpen] = useState(false);
  const [tool, setTool] = useState<NonNullable<ChatMessage["tool"]>>("none");
  const scrollRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const faceRef = useRef<HTMLSpanElement>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const ignoreClickRef = useRef(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const lastMessage = messages[messages.length - 1];
  const waiting = !paused && lastMessage?.role === "user";
  const canPause = sending || waiting;
  const waitingTool = sending ? sendingTool : lastMessage?.tool ?? "none";
  const waitingText = waitingTool === "drawing_review" ? "正在重新核对图纸与报告……" : waitingTool === "knowledge_recommendation" ? "正在结合报告整理知识建议……" : "正在结合图纸和知识整理回答……";
  const openingMessage: ChatMessage = { role: "assistant", content: "报告已生成。我可以继续解释扣分原因、复核图纸问题，或整理下一轮修改方向。" };
  const displayMessages = [openingMessage, ...messages];
  const latestPersistedMessageId = messages.reduce((latest, message) => Math.max(latest, message.id ?? 0), 0);
  const suggestions = useMemo(() => buildChatSuggestions(report), [report]);
  const selectedTool = REPORT_CHAT_TOOLS.find((item) => item.id === tool);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      const node = scrollRef.current;
      if (node) node.scrollTop = node.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [displayMessages.length, open, waiting]);

  useEffect(() => {
    if (!toolOpen) return;
    const closeTools = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest(".report-chat-tool-menu, .report-chat-plus")) return;
      setToolOpen(false);
    };
    document.addEventListener("pointerdown", closeTools);
    return () => document.removeEventListener("pointerdown", closeTools);
  }, [toolOpen]);

  useEffect(() => {
    let blinkTimer = 0;
    let openTimer = 0;
    const scheduleBlink = () => {
      blinkTimer = window.setTimeout(() => {
        faceRef.current?.classList.add("is-blinking");
        openTimer = window.setTimeout(() => { faceRef.current?.classList.remove("is-blinking"); scheduleBlink(); }, 135);
      }, 2600 + Math.random() * 4200);
    };
    scheduleBlink();
    return () => { window.clearTimeout(blinkTimer); window.clearTimeout(openTimer); requestControllerRef.current?.abort(); };
  }, []);

  useEffect(() => {
    const openAssistant = () => { setOpen(true); setPaused(false); };
    window.addEventListener("open-report-assistant", openAssistant);
    return () => window.removeEventListener("open-report-assistant", openAssistant);
  }, []);

  // 清除输入框中的工具和问题。
  const clearEditor = () => {
    editorRef.current?.replaceChildren();
    setQuestion("");
    setTool("none");
  };

  // 将工具以轻量紫色文字插入输入区，悬停时才显示卡片与移除按钮。
  const insertToolToken = (nextTool: NonNullable<ChatMessage["tool"]>) => {
    const editor = editorRef.current;
    const definition = REPORT_CHAT_TOOLS.find((item) => item.id === nextTool);
    if (!editor || !definition || nextTool === "none") return;
    if (!readReportQuestion(editor).trim()) editor.replaceChildren();
    editor.querySelectorAll(".report-chat-inline-tool").forEach((node) => node.remove());
    removeGeneratedLeadingSpace(editor);
    const token = document.createElement("span");
    token.className = "knowledge-assistant-inline-tool report-chat-inline-tool";
    token.contentEditable = "false";
    token.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${REPORT_TOOL_ICON_PATHS[nextTool] ?? ""}</svg><strong>${definition.name}</strong><span aria-hidden="true">×</span>`;
    token.addEventListener("click", () => {
      token.remove();
      removeGeneratedLeadingSpace(editor);
      setTool("none");
      setQuestion(readReportQuestion(editor));
    });
    editor.prepend(token, document.createTextNode("\u00a0"));
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    editor.focus();
    setTool(nextTool);
    setQuestion(readReportQuestion(editor));
  };

  // 把快捷问题写入输入区。
  const fillQuestion = (content: string) => {
    editorRef.current?.replaceChildren(document.createTextNode(content));
    editorRef.current?.focus();
    setQuestion(content);
    setTool("none");
  };

  // 发送报告问题；中止只停止当前页面等待，后端仍可保存已发出的问题与回答。
  const submit = async (content = question) => {
    if (!content.trim() || sending) return;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setPaused(false);
    setSending(true);
    setStreamingText("");
    setSendingTool(tool);
    const submittedTool = tool;
    clearEditor();
    setToolOpen(false);
    try {
      await sendQuestion(content, submittedTool, controller.signal, (delta) => setStreamingText((current) => current + delta));
    } finally {
      setSending(false);
      setSendingTool("none");
      setStreamingText("");
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  };

  // 将暂停按钮显示为中文，并停止当前页面的等待状态。
  const pause = () => {
    setPaused(true);
    requestControllerRef.current?.abort();
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.nativeEvent.isComposing || event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void submit();
  };

  // 记录入口拖动起点，轻点仍保持打开助手的原行为。
  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const canvas = event.currentTarget.closest(".canvas-content")?.getBoundingClientRect();
    const scale = canvas ? canvas.width / 1536 : 1;
    dragRef.current = { pointerId: event.pointerId, offsetX: (event.clientX - rect.left) / scale, offsetY: (event.clientY - rect.top) / scale, startX: event.clientX, startY: event.clientY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  // 拖动范围与知识助手一致，始终限制在产品画布内。
  const moveDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 4) drag.moved = true;
    if (!drag.moved) return;
    const canvas = event.currentTarget.closest(".canvas-content")?.getBoundingClientRect();
    const scale = canvas ? canvas.width / 1536 : 1;
    setPosition({ left: Math.min(Math.max((event.clientX - (canvas?.left ?? 0)) / scale - drag.offsetX, 12), 1462), top: Math.min(Math.max((event.clientY - (canvas?.top ?? 0)) / scale - drag.offsetY, 12), 746) });
  };

  // 拖动结束后忽略同一次点击，避免松手时误打开遮罩。
  const finishDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (drag.moved) { ignoreClickRef.current = true; window.setTimeout(() => { ignoreClickRef.current = false; }, 0); }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    dragRef.current = null;
  };

  return (
    <>
      {open && <button type="button" className="knowledge-assistant-overlay" aria-label="关闭 AI 辅助助手" onClick={() => { setOpen(false); setToolOpen(false); }} />}
      {!open && <button type="button" className="knowledge-assistant-toggle report-assistant-toggle" style={position ? { left: position.left, top: position.top, right: "auto", bottom: "auto" } : undefined} aria-label="打开 AI 辅助助手" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onClick={() => { if (!ignoreClickRef.current) { setOpen(true); setPaused(false); } }}><span ref={faceRef} className="knowledge-assistant-face" aria-hidden="true"><span className="knowledge-assistant-eye left" /><span className="knowledge-assistant-eye right" /></span></button>}
      <section className={`knowledge-assistant-panel report-assistant-panel ${open ? "open" : ""}`} aria-label="AI 辅助助手">
        <header><div className="knowledge-assistant-title"><strong>您的设计反馈助手</strong><small>结合报告、图纸与知识内容继续分析</small></div></header>
        <div className="knowledge-assistant-conversation knowledge-scroll" ref={scrollRef}>
          {displayMessages.map((message, index) => message.role === "user" ? <ReportUserBubble content={message.content} tool={message.tool} key={`${message.role}-${index}-${message.content}`} /> : <ReportAssistantBubble submissionId={submissionId} contextMessageId={latestPersistedMessageId} message={message} go={go} key={`${message.role}-${index}-${message.content}`} />)}
          {waiting && <ReportAssistantBubble submissionId={submissionId} message={{ role: "assistant", content: streamingText || waitingText }} loading={!streamingText} go={go} />}
          {!messages.length && <div className="knowledge-assistant-suggestions report-assistant-suggestions">{suggestions.map((item) => <button type="button" disabled={waiting} onClick={() => fillQuestion(item)} key={item}>{item}</button>)}</div>}
        </div>
        {toolOpen && <div className="knowledge-assistant-tool-menu report-chat-tool-menu" aria-label="报告助手工具">{REPORT_CHAT_TOOLS.map((item) => <button type="button" className={tool === item.id ? "active" : ""} onClick={() => { insertToolToken(item.id); setToolOpen(false); }} key={item.id}><ReportToolIcon tool={item.id} /><span><strong>{item.name}</strong><small>{item.description}</small></span></button>)}</div>}
        <form className="knowledge-assistant-composer" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <button type="button" className={`knowledge-assistant-plus report-chat-plus ${toolOpen ? "active" : ""}`} aria-label="打开报告助手工具" onClick={() => setToolOpen((current) => !current)}>＋</button>
          <div ref={editorRef} className="knowledge-assistant-editor knowledge-scroll" contentEditable suppressContentEditableWarning role="textbox" aria-label="继续向报告助手提问" aria-multiline="true" data-empty={question.trim() ? "false" : "true"} data-placeholder={selectedTool?.placeholder ?? "输入你想继续追问的问题…"} onInput={(event) => setQuestion(syncReportQuestion(event.currentTarget))} onKeyDown={handleInputKeyDown} />
          <button type={canPause ? "button" : "submit"} className="app-action-button" disabled={!canPause && !question.trim()} aria-label={canPause ? "暂停生成" : "发送"} onClick={canPause ? pause : undefined}>{canPause ? "暂停" : "发送"}</button>
        </form>
      </section>
    </>
  );
}

// 渲染助手消息、等待文案和知识引用。
function ReportAssistantBubble({ submissionId, contextMessageId, message, loading = false, go }: { submissionId: number; contextMessageId?: number; message: ChatMessage; loading?: boolean; go: PageProps["go"] }) {
  return <div className="knowledge-message-row"><img className="knowledge-message-avatar" src="/assets/v1/头像.png" alt="AI 辅助助手" /><div className="knowledge-message-stack"><p className={loading ? "is-loading" : ""}>{renderChatText(message.content)}</p>{message.citations && message.citations.length > 0 && <div className="knowledge-assistant-references">{message.citations.map((item) => <button type="button" title={`${item.id} · ${item.title}`} key={item.id} onClick={() => { saveReportKnowledgeContext(submissionId, message.citations ?? [], contextMessageId ?? message.id); go("knowledge"); }}>{item.id} · {item.title}</button>)}</div>}{message.report_updated && <small className="report-chat-updated">报告已根据本次图纸复核同步更新</small>}</div></div>;
}

// 渲染用户消息，发送后的工具只保留紫色图标和文字。
function ReportUserBubble({ content, tool }: { content: string; tool?: ChatMessage["tool"] }) {
  return <div className="knowledge-message-row user"><p>{tool && tool !== "none" && <span className="report-chat-tool-pill"><ReportToolIcon tool={tool} /><strong>{REPORT_CHAT_TOOLS.find((item) => item.id === tool)?.name}</strong></span>}<span>{content}</span></p></div>;
}

// 使用统一线宽渲染报告工具图标。
function ReportToolIcon({ tool }: { tool: NonNullable<ChatMessage["tool"]> }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (tool === "drawing_review") return <svg viewBox="0 0 24 24" {...common}><path d="M3 5h18v14H3zM7 15l3-3 2 2 3-4 3 5" /><circle cx="8" cy="9" r="1" /></svg>;
  if (tool === "knowledge_recommendation") return <svg viewBox="0 0 24 24" {...common}><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22zM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z" /></svg>;
  return <svg viewBox="0 0 24 24" {...common}><circle cx="12" cy="12" r="9" /><path d="M9.7 9a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.2.9-1.2 1.9M12 16h.01" /></svg>;
}
