// 建筑知识助手：提供真实模型问答、内置检索工具和推荐结果联动。
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { getKnowledgeAssistantMessages, sendKnowledgeAssistantMessage, type KnowledgeAssistantResult, type KnowledgeAssistantTool, type KnowledgeLibraryItem } from "../api/knowledge";

interface DragState { pointerId: number; offsetX: number; offsetY: number; startX: number; startY: number; moved: boolean; }
interface AssistantMessage { role: "user" | "assistant"; content: string; result?: Partial<KnowledgeAssistantResult>; }
interface KnowledgeAssistantProps {
  view: "overview" | "detail";
  tab: "all" | "knowledge" | "case";
  category: string;
  currentItem: KnowledgeLibraryItem | null;
  resultSetId: string | null;
  onResult: (result: KnowledgeAssistantResult) => void;
  onOpenItem: (itemId: string) => void;
}

const CONVERSATION_KEY = "archcritic-knowledge-assistant-conversation";
const TOOL_DEFINITIONS: { id: KnowledgeAssistantTool; name: string; description: string; placeholder: string }[] = [
  { id: "case_recommendation", name: "案例推荐", description: "按类型、面积、场地和关注点找案例", placeholder: "描述建筑类型、面积、场地和关注问题…" },
  { id: "knowledge_query", name: "知识查询", description: "查概念、方法、规范与设计原则", placeholder: "输入想了解的概念、方法或规范问题…" },
  { id: "similar_cases", name: "相似案例", description: "根据当前案例寻找可比较项目", placeholder: "说明希望比较的案例特征或设计维度…" },
  { id: "case_compare", name: "案例对比", description: "对比 2—4 个案例的设计策略", placeholder: "输入要对比的案例名称、编号或维度…" },
  { id: "learning_path", name: "学习路径", description: "按目标生成有顺序的学习清单", placeholder: "描述设计任务、阶段和希望补强的问题…" },
  { id: "problem_breakdown", name: "设计问题拆解", description: "把宽泛需求拆成可解决的问题", placeholder: "描述当前设计任务或评图反馈…" },
  { id: "current_card_qa", name: "当前卡片问答", description: "围绕正在看的卡片继续追问", placeholder: "围绕当前卡片输入你的问题…" },
];

const INLINE_TOOL_ICON_PATHS: Record<KnowledgeAssistantTool, string> = {
  none: '<path d="M5 12h14M12 5v14"/>',
  case_recommendation: '<path d="M4 20V9l8-5 8 5v11M8 20v-6h8v6M9 10h.01M15 10h.01"/>',
  knowledge_query: '<path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22zM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z"/>',
  similar_cases: '<rect x="3" y="3" width="13" height="13" rx="2"/><path d="M8 20h11a2 2 0 0 0 2-2V8"/>',
  case_compare: '<rect x="3" y="4" width="7" height="16" rx="2"/><rect x="14" y="4" width="7" height="16" rx="2"/><path d="m8 9-2 2 2 2m8 2 2-2-2-2"/>',
  learning_path: '<circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18h3a3 3 0 0 0 3-3v-6a3 3 0 0 1 3-3h1"/>',
  problem_breakdown: '<path d="M6 3v18M6 7h5M11 7v5M11 12h6M11 12v6M11 18h6"/><circle cx="18" cy="12" r="1"/><circle cx="18" cy="18" r="1"/>',
  current_card_qa: '<path d="M21 12a8 8 0 0 1-8 8H7l-4 2 1.5-4A9 9 0 1 1 21 12z"/><path d="M9.7 9a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.2.9-1.2 1.9M12 16h.01"/>',
};

// 读取富文本输入区中的纯问题文字，工具标签不会进入模型问题。
function readEditorQuestion(editor: HTMLDivElement): string {
  const clone = editor.cloneNode(true) as HTMLDivElement;
  clone.querySelectorAll(".knowledge-assistant-inline-tool").forEach((node) => node.remove());
  return (clone.textContent ?? "").replace(/\u200b/g, "").replace(/\u00a0/g, " ");
}

// 生成并持久化浏览器侧会话编号。
function getConversationId(): string {
  const existing = window.localStorage.getItem(CONVERSATION_KEY);
  if (existing) return existing;
  const created = window.crypto.randomUUID();
  window.localStorage.setItem(CONVERSATION_KEY, created);
  return created;
}

// 切换本地账户后旧会话不再属于当前用户，此时建立新的隔离会话。
function resetConversationId(): string {
  const created = window.crypto.randomUUID();
  window.localStorage.setItem(CONVERSATION_KEY, created);
  return created;
}

// 渲染知识库页面右下角的可拖动 AI 助手。
export function KnowledgeAssistant({ view, tab, category, currentItem, resultSetId, onResult, onOpenItem }: KnowledgeAssistantProps) {
  const toggleRef = useRef<HTMLButtonElement>(null);
  const faceRef = useRef<HTMLSpanElement>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const editorSelectionRef = useRef<Range | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const ignoreClickRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [toolbarOpen, setToolbarOpen] = useState(false);
  const [tool, setTool] = useState<KnowledgeAssistantTool>("none");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [error, setError] = useState("");
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const conversationIdRef = useRef(getConversationId());

  // 保存输入区光标，点击工具菜单后仍能把标签插到原来的文字位置。
  const rememberEditorSelection = () => {
    const editor = editorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (editor.contains(range.commonAncestorContainer)) editorSelectionRef.current = range.cloneRange();
  };

  // 同步输入文字，并让发送按钮立即反映当前状态。
  const syncEditorQuestion = () => {
    if (editorRef.current) setQuestion(readEditorQuestion(editorRef.current));
    rememberEditorSelection();
  };

  // 删除当前行内工具标签，但保留用户已经输入的文字。
  const clearSelectedTool = () => {
    editorRef.current?.querySelectorAll(".knowledge-assistant-inline-tool").forEach((node) => node.remove());
    setTool("none");
    setError("");
    if (editorRef.current) setQuestion(readEditorQuestion(editorRef.current));
  };

  // 在当前光标位置插入带图标的工具标签。
  const insertToolToken = (nextTool: KnowledgeAssistantTool) => {
    const editor = editorRef.current;
    const definition = TOOL_DEFINITIONS.find((item) => item.id === nextTool);
    if (!editor || !definition || nextTool === "none") return;
    editor.querySelectorAll(".knowledge-assistant-inline-tool").forEach((node) => node.remove());
    const token = document.createElement("span");
    token.className = "knowledge-assistant-inline-tool";
    token.contentEditable = "false";
    token.dataset.tool = nextTool;
    token.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${INLINE_TOOL_ICON_PATHS[nextTool]}</svg><strong>${definition.name}</strong><span aria-hidden="true">×</span>`;
    token.addEventListener("click", clearSelectedTool);
    const trailingSpace = document.createTextNode("\u00a0");
    const savedRange = editorSelectionRef.current;
    if (savedRange && editor.contains(savedRange.commonAncestorContainer)) {
      savedRange.deleteContents();
      savedRange.insertNode(trailingSpace);
      savedRange.insertNode(token);
    } else {
      editor.append(token, trailingSpace);
    }
    const range = document.createRange();
    range.setStartAfter(trailingSpace);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    editorSelectionRef.current = range.cloneRange();
    editor.focus();
    setTool(nextTool);
    setQuestion(readEditorQuestion(editor));
  };

  // 发送后只清空问题文字，按照 PRD 保留本轮选择的工具。
  const clearEditorText = () => {
    const editor = editorRef.current;
    if (editor) {
      const token = editor.querySelector(".knowledge-assistant-inline-tool");
      editor.replaceChildren();
      if (token) editor.append(token, document.createTextNode("\u00a0"));
    }
    setQuestion("");
    editorSelectionRef.current = null;
  };

  useEffect(() => {
    void getKnowledgeAssistantMessages(conversationIdRef.current)
      .then((saved) => setMessages(saved.map((message) => ({ role: message.role, content: message.content, result: message.result }))))
      .catch((loadError) => {
        if (loadError instanceof Error && loadError.message.includes("会话不存在")) {
          conversationIdRef.current = resetConversationId();
          setMessages([]);
        }
      });
  }, []);

  useEffect(() => {
    const openAssistant = () => setOpen(true);
    window.addEventListener("open-knowledge-assistant", openAssistant);
    return () => window.removeEventListener("open-knowledge-assistant", openAssistant);
  }, []);

  useEffect(() => {
    const area = conversationRef.current;
    if (area) area.scrollTop = area.scrollHeight;
  }, [loadingText, messages]);

  useEffect(() => {
    // 鼠标靠近时只让白色眼睛跟随，黑色脸部始终保持固定。
    const moveEyes = (event: PointerEvent) => {
      const rect = toggleRef.current?.getBoundingClientRect();
      const face = faceRef.current;
      if (!rect || !face) return;
      const deltaX = event.clientX - (rect.left + rect.width / 2);
      const deltaY = event.clientY - (rect.top + rect.height / 2);
      const distance = Math.max(1, Math.hypot(deltaX, deltaY));
      const offset = Math.min(3.5, distance / 28);
      if (distance <= 240) {
        face.classList.add("is-tracking");
        face.style.setProperty("--eye-x", `${(deltaX / distance) * offset}px`);
        face.style.setProperty("--eye-y", `${(deltaY / distance) * offset}px`);
      } else {
        face.classList.remove("is-tracking");
        face.style.removeProperty("--eye-x");
        face.style.removeProperty("--eye-y");
      }
    };
    window.addEventListener("pointermove", moveEyes, { passive: true });
    return () => window.removeEventListener("pointermove", moveEyes);
  }, []);

  useEffect(() => {
    // 使用随机间隔而不是固定周期，让眨眼更自然。
    let blinkTimer = 0;
    let openTimer = 0;
    const scheduleBlink = () => {
      blinkTimer = window.setTimeout(() => {
        faceRef.current?.classList.add("is-blinking");
        openTimer = window.setTimeout(() => { faceRef.current?.classList.remove("is-blinking"); scheduleBlink(); }, 135);
      }, 2600 + Math.random() * 4200);
    };
    scheduleBlink();
    return () => { window.clearTimeout(blinkTimer); window.clearTimeout(openTimer); };
  }, []);

  // 记录拖动起点，点击与拖动共用同一个圆形入口。
  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const canvas = event.currentTarget.closest(".canvas-content")?.getBoundingClientRect();
    const scale = canvas ? canvas.width / 1536 : 1;
    dragRef.current = { pointerId: event.pointerId, offsetX: (event.clientX - rect.left) / scale, offsetY: (event.clientY - rect.top) / scale, startX: event.clientX, startY: event.clientY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  // 拖动时限制入口始终处于知识库画布范围内。
  const moveDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 4) drag.moved = true;
    if (!drag.moved) return;
    const canvas = event.currentTarget.closest(".canvas-content")?.getBoundingClientRect();
    const scale = canvas ? canvas.width / 1536 : 1;
    setPosition({ left: Math.min(Math.max((event.clientX - (canvas?.left ?? 0)) / scale - drag.offsetX, 12), 1462), top: Math.min(Math.max((event.clientY - (canvas?.top ?? 0)) / scale - drag.offsetY, 12), 746) });
  };

  // 结束拖动并阻止拖动后的同一次点击误开面板。
  const finishDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (drag.moved) { ignoreClickRef.current = true; window.setTimeout(() => { ignoreClickRef.current = false; }, 0); }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    dragRef.current = null;
  };

  // 调用真实知识助手并把结构化推荐交给知识库页面。
  const submitQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = question.trim();
    if (!content || loading) return;
    setError("");
    setLoading(true);
    setMessages((current) => [...current, { role: "user", content }]);
    clearEditorText();
    const requestController = new AbortController();
    requestControllerRef.current = requestController;
    setLoadingText("正在理解你的设计条件……");
    const retrievalTimer = window.setTimeout(() => setLoadingText("正在知识库中查找……"), 650);
    const answerTimer = window.setTimeout(() => setLoadingText("正在整理推荐理由……"), 1800);
    try {
      const result = await sendKnowledgeAssistantMessage({
        conversation_id: conversationIdRef.current,
        tool,
        message: content,
        context: { view, current_card_id: currentItem?.id ?? null, main_tab: tab, category, previous_result_set_id: resultSetId },
      }, requestController.signal);
      setMessages((current) => [...current, { role: "assistant", content: result.answer, result }]);
      onResult(result);
    } catch (submitError) {
      if (!requestController.signal.aborted) {
        setError(submitError instanceof Error ? submitError.message : "AI 助手暂时无法回答，请稍后重试。");
      }
    } finally {
      window.clearTimeout(retrievalTimer);
      window.clearTimeout(answerTimer);
      setLoading(false);
      setLoadingText("");
      if (requestControllerRef.current === requestController) requestControllerRef.current = null;
    }
  };

  const selectedTool = TOOL_DEFINITIONS.find((item) => item.id === tool);
  const availableTools = TOOL_DEFINITIONS.filter((item) => item.id !== "current_card_qa" || currentItem);

  return (
    <>
      {open && <button type="button" className="knowledge-assistant-overlay" aria-label="关闭建筑知识助手" onClick={() => { setOpen(false); setToolbarOpen(false); }} />}
      {!open && <button ref={toggleRef} type="button" className="knowledge-assistant-toggle" style={position ? { left: position.left, top: position.top, right: "auto", bottom: "auto" } : undefined} aria-label="打开 AI 助手" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onClick={() => { if (!ignoreClickRef.current) setOpen(true); }}>
        <span ref={faceRef} className="knowledge-assistant-face" aria-hidden="true"><span className="knowledge-assistant-eye left" /><span className="knowledge-assistant-eye right" /></span>
      </button>}

      <section className={`knowledge-assistant-panel ${open ? "open" : ""}`} aria-label="AI 助手">
        <header><div className="knowledge-assistant-title"><strong>您的建筑知识助手</strong><small>帮您查找案例，回答相关问题</small></div></header>
        <div className="knowledge-assistant-conversation knowledge-scroll" ref={conversationRef}>
          {!messages.length && <AssistantBubble content="描述你的设计任务，或从下方工具中选择一种学习方式。我只会推荐知识库中真实存在的卡片。" />}
          {messages.map((message, index) => message.role === "user" ? <div className="knowledge-message-row user" key={index}><p>{message.content}</p></div> : <AssistantBubble content={message.content} result={message.result} onOpenItem={onOpenItem} key={index} />)}
          {loading && <AssistantBubble content={loadingText} loading />}
        </div>
        {toolbarOpen && <div className="knowledge-assistant-tool-menu knowledge-scroll" aria-label="知识助手工具">
          {availableTools.map((item) => <button type="button" className={tool === item.id ? "active" : ""} onClick={() => { insertToolToken(item.id); setToolbarOpen(false); setError(""); }} key={item.id}><ToolIcon tool={item.id} /><span><strong>{item.name}</strong><small>{item.description}</small></span></button>)}
        </div>}
        <form className="knowledge-assistant-composer" onSubmit={submitQuestion}>
          {currentItem && tool === "current_card_qa" && <p className="knowledge-assistant-current-card">{currentItem.id} · {currentItem.title}</p>}
          <button type="button" className={`knowledge-assistant-plus ${toolbarOpen ? "active" : ""}`} aria-label="打开内置工具" onClick={() => setToolbarOpen((current) => !current)}>＋</button>
          <div
            ref={editorRef}
            className="knowledge-assistant-editor knowledge-scroll"
            contentEditable={!loading}
            suppressContentEditableWarning
            role="textbox"
            aria-label="向 AI 提问"
            aria-multiline="true"
            data-empty={question.trim() ? "false" : "true"}
            data-placeholder={selectedTool?.placeholder ?? "输入你想询问的建筑问题…"}
            onInput={syncEditorQuestion}
            onBlur={rememberEditorSelection}
            onKeyUp={rememberEditorSelection}
            onMouseUp={rememberEditorSelection}
            onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                event.currentTarget.closest("form")?.requestSubmit();
              }
            }}
          />
          <button type={loading ? "button" : "submit"} className="app-action-button" disabled={!loading && !question.trim()} onClick={loading ? () => requestControllerRef.current?.abort() : undefined}>{loading ? "取消" : "发送"}</button>
          {error && <p className="knowledge-assistant-error">{error}</p>}
        </form>
      </section>
    </>
  );
}

// 渲染助手消息及其中可点击的知识库引用。
function AssistantBubble({ content, result, loading = false, onOpenItem }: { content: string; result?: Partial<KnowledgeAssistantResult>; loading?: boolean; onOpenItem?: (itemId: string) => void }) {
  const recommendations = result?.recommendations ?? [];
  const titleById = new Map((result?.citations ?? []).map((item) => [item.id, item.title]));
  return <div className="knowledge-message-row"><img className="knowledge-message-avatar" src="/assets/v1/头像.png" alt="建筑知识助手" /><div className="knowledge-message-stack"><p className={loading ? "is-loading" : ""}>{content}</p>{recommendations.length > 0 && <div className="knowledge-assistant-references">{recommendations.slice(0, 8).map((item) => <button type="button" onClick={() => onOpenItem?.(item.id)} key={item.id}>{item.id}{titleById.get(item.id) ? ` · ${titleById.get(item.id)}` : ""}</button>)}</div>}</div></div>;
}

// 使用统一线宽的内置 SVG 图标，不引入额外图标依赖。
function ToolIcon({ tool }: { tool: KnowledgeAssistantTool }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (tool === "case_recommendation") return <svg viewBox="0 0 24 24" {...common}><path d="M4 20V9l8-5 8 5v11M8 20v-6h8v6M9 10h.01M15 10h.01" /></svg>;
  if (tool === "knowledge_query") return <svg viewBox="0 0 24 24" {...common}><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22zM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z" /></svg>;
  if (tool === "similar_cases") return <svg viewBox="0 0 24 24" {...common}><rect x="3" y="3" width="13" height="13" rx="2" /><path d="M8 20h11a2 2 0 0 0 2-2V8" /></svg>;
  if (tool === "case_compare") return <svg viewBox="0 0 24 24" {...common}><rect x="3" y="4" width="7" height="16" rx="2" /><rect x="14" y="4" width="7" height="16" rx="2" /><path d="m8 9-2 2 2 2m8 2 2-2-2-2" /></svg>;
  if (tool === "learning_path") return <svg viewBox="0 0 24 24" {...common}><circle cx="5" cy="18" r="2" /><circle cx="19" cy="6" r="2" /><path d="M7 18h3a3 3 0 0 0 3-3v-6a3 3 0 0 1 3-3h1" /></svg>;
  if (tool === "problem_breakdown") return <svg viewBox="0 0 24 24" {...common}><path d="M6 3v18M6 7h5M11 7v5M11 12h6M11 12v6M11 18h6" /><circle cx="18" cy="12" r="1" /><circle cx="18" cy="18" r="1" /></svg>;
  return <svg viewBox="0 0 24 24" {...common}><path d="M21 12a8 8 0 0 1-8 8H7l-4 2 1.5-4A9 9 0 1 1 21 12z" /><path d="M9.7 9a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.2.9-1.2 1.9M12 16h.01" /></svg>;
}
