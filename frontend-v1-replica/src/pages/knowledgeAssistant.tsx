// 建筑知识助手：提供真实模型问答、内置检索工具和推荐结果联动。
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { getKnowledgeAssistantConversations, getKnowledgeAssistantMessages, streamKnowledgeAssistantMessage, type KnowledgeAssistantResult, type KnowledgeAssistantTool, type KnowledgeConversationSummary, type KnowledgeLibraryItem } from "../api/knowledge";

interface DragState { pointerId: number; offsetX: number; offsetY: number; startX: number; startY: number; moved: boolean; }
interface AssistantMessage { role: "user" | "assistant"; content: string; tool?: KnowledgeAssistantTool; result?: Partial<KnowledgeAssistantResult>; }
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
const CONVERSATION_SCROLL_KEY = "archcritic-knowledge-assistant-scroll";
const TOOL_DEFINITIONS: { id: KnowledgeAssistantTool; name: string; description: string; placeholder: string }[] = [
  { id: "case_recommendation", name: "案例推荐", description: "按类型、面积、场地和关注点找案例", placeholder: "描述建筑类型、面积、场地和关注问题…" },
  { id: "knowledge_query", name: "知识查询", description: "查概念、方法、规范与设计原则", placeholder: "输入想了解的概念、方法或规范问题…" },
  { id: "learning_path", name: "学习清单", description: "按目标生成知识卡与案例学习顺序", placeholder: "描述设计任务、阶段和希望补强的问题…" },
  { id: "current_card_qa", name: "当前卡片问答", description: "围绕正在看的卡片继续追问", placeholder: "围绕当前卡片输入你的问题…" },
];

const INLINE_TOOL_ICON_PATHS: Record<KnowledgeAssistantTool, string> = {
  none: '<path d="M5 12h14M12 5v14"/>',
  case_recommendation: '<path d="M4 20V9l8-5 8 5v11M8 20v-6h8v6M9 10h.01M15 10h.01"/>',
  knowledge_query: '<path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22zM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z"/>',
  learning_path: '<circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18h3a3 3 0 0 0 3-3v-6a3 3 0 0 1 3-3h1"/>',
  current_card_qa: '<path d="M21 12a8 8 0 0 1-8 8H7l-4 2 1.5-4A9 9 0 1 1 21 12z"/><path d="M9.7 9a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.2.9-1.2 1.9M12 16h.01"/>',
};

// 根据工具显示与当前操作一致的模型等待说明。
function waitingTextForTool(tool: KnowledgeAssistantTool): string {
  return {
    none: "正在理解你的问题并检索知识库……",
    case_recommendation: "正在根据你的需求检索相关案例……",
    knowledge_query: "正在查询相关知识内容……",
    learning_path: "正在整理适合你的学习清单……",
    current_card_qa: "正在阅读当前卡片并组织回答……",
  }[tool];
}

// 读取富文本输入区中的纯问题文字，工具标签不会进入模型问题。
function readEditorQuestion(editor: HTMLDivElement): string {
  const clone = editor.cloneNode(true) as HTMLDivElement;
  clone.querySelectorAll(".knowledge-assistant-inline-tool").forEach((node) => node.remove());
  return (clone.textContent ?? "").replace(/\u200b/g, "").replace(/\u00a0/g, " ");
}

// 删除工具标签遗留在输入区最前方的不可见空格。
function removeGeneratedLeadingSpace(editor: HTMLDivElement): void {
  editor.normalize();
  const firstNode = editor.firstChild;
  if (firstNode?.nodeType !== Node.TEXT_NODE) return;
  firstNode.textContent = (firstNode.textContent ?? "").replace(/^[\s\u00a0]+/, "");
  if (!firstNode.textContent) firstNode.remove();
}

// 历史消息也按当前上线口径展示，不暴露卡片编号和内部流程状态。
function cleanAssistantDisplayText(content: string): string {
  return content
    .replace(/[（(]\s*(?:KC-[A-Z]+-\d+|PBC-\d+)\s*[）)]/gi, "")
    .replace(/\b(?:KC-[A-Z]+-\d+|PBC-\d+)\b/gi, "")
    .replace(/(?:专业内容|上述内容|内容)?(?:均|仍|尚)?(?:待专业复核|待复核|待审核)[。；;]?/g, "")
    .replace(/\s+([，。；：、])/g, "$1")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
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
  const historyRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const editorSelectionRef = useRef<Range | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const restoreScrollRef = useRef(true);
  const forceLatestRef = useRef(false);
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
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<KnowledgeConversationSummary[]>([]);
  const [historyDraft, setHistoryDraft] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const conversationIdRef = useRef(getConversationId());

  // 新建空会话，不影响已保存在后端的历史记录。
  const createConversation = () => {
    conversationIdRef.current = resetConversationId();
    setMessages([]);
    setTool("none");
    setHistoryOpen(false);
    setToolbarOpen(false);
    setError("");
    if (editorRef.current) editorRef.current.replaceChildren();
    setQuestion("");
    forceLatestRef.current = true;
  };

  // 打开历史面板时读取当前账户的真实会话。
  const loadHistory = (query = "") => {
    setError("");
    void getKnowledgeAssistantConversations(query)
      .then(setHistory)
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "历史会话读取失败。"));
  };

  const toggleHistory = () => {
    const nextOpen = !historyOpen;
    setHistoryOpen(nextOpen);
    setToolbarOpen(false);
    if (nextOpen) loadHistory(historyQuery);
  };

  const selectConversation = (conversationId: string) => {
    conversationIdRef.current = conversationId;
    window.localStorage.setItem(CONVERSATION_KEY, conversationId);
    setError("");
    forceLatestRef.current = true;
    void getKnowledgeAssistantMessages(conversationId)
      .then((saved) => {
        setMessages(saved.map((message) => ({ role: message.role, content: message.content, tool: message.tool, result: message.result })));
        setHistoryOpen(false);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "会话读取失败。"));
  };

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
    if (editorRef.current) removeGeneratedLeadingSpace(editorRef.current);
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
    removeGeneratedLeadingSpace(editor);
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

  // 发送后清空问题和工具标签，工具会随用户消息进入对话记录。
  const clearEditorText = () => {
    const editor = editorRef.current;
    if (editor) editor.replaceChildren();
    setQuestion("");
    setTool("none");
    editorSelectionRef.current = null;
  };

  useEffect(() => {
    void getKnowledgeAssistantMessages(conversationIdRef.current)
      .then((saved) => {
        restoreScrollRef.current = true;
        setMessages(saved.map((message) => ({ role: message.role, content: message.content, tool: message.tool, result: message.result })));
      })
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
    if (!historyOpen) return;
    const closeHistory = (event: PointerEvent) => {
      if (!historyRef.current?.contains(event.target as Node)) setHistoryOpen(false);
    };
    document.addEventListener("pointerdown", closeHistory);
    return () => document.removeEventListener("pointerdown", closeHistory);
  }, [historyOpen]);

  useEffect(() => {
    if (!toolbarOpen) return;
    const closeToolbar = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest(".knowledge-assistant-tool-menu, .knowledge-assistant-plus")) return;
      setToolbarOpen(false);
    };
    document.addEventListener("pointerdown", closeToolbar);
    return () => document.removeEventListener("pointerdown", closeToolbar);
  }, [toolbarOpen]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      const area = conversationRef.current;
      if (!area) return;
      const scrollKey = `${CONVERSATION_SCROLL_KEY}:${conversationIdRef.current}`;
      if (forceLatestRef.current || loading) {
        area.scrollTop = area.scrollHeight;
      } else if (restoreScrollRef.current) {
        const savedValue = window.localStorage.getItem(scrollKey);
        const savedTop = savedValue === null ? Number.NaN : Number(savedValue);
        area.scrollTop = Number.isFinite(savedTop) ? Math.min(savedTop, area.scrollHeight) : area.scrollHeight;
      } else {
        area.scrollTop = area.scrollHeight;
      }
      forceLatestRef.current = false;
      restoreScrollRef.current = false;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [loading, loadingText, messages, open]);

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
    const submittedTool = tool;
    const waitingText = waitingTextForTool(submittedTool);
    setError("");
    setLoading(true);
    setMessages((current) => [...current, { role: "user", content, tool: submittedTool }]);
    clearEditorText();
    const requestController = new AbortController();
    requestControllerRef.current = requestController;
    setLoadingText(waitingText);
    setMessages((current) => [...current, { role: "assistant", content: waitingText }]);
    try {
      let streamedAnswer = "";
      const result = await streamKnowledgeAssistantMessage({
        conversation_id: conversationIdRef.current,
        tool: submittedTool,
        message: content,
        context: { view, current_card_id: currentItem?.id ?? null, main_tab: tab, category, previous_result_set_id: resultSetId },
      }, (delta) => {
        streamedAnswer += delta;
        setLoadingText("");
        setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, content: cleanAssistantDisplayText(streamedAnswer) } : item));
      }, requestController.signal);
      setMessages((current) => current.map((item, index) => index === current.length - 1 ? { role: "assistant", content: result.answer, result } : item));
      onResult(result);
    } catch (submitError) {
      if (!requestController.signal.aborted) {
        const message = submitError instanceof Error ? submitError.message : "AI 助手暂时无法回答，请稍后重试。";
        setMessages((current) => current.map((item, index) => index === current.length - 1 ? { role: "assistant", content: message } : item));
      } else {
        setMessages((current) => current[current.length - 1]?.role === "assistant" ? current.slice(0, -1) : current);
      }
    } finally {
      setLoading(false);
      setLoadingText("");
      if (requestControllerRef.current === requestController) requestControllerRef.current = null;
    }
  };

  const selectedTool = TOOL_DEFINITIONS.find((item) => item.id === tool);
  const availableTools = TOOL_DEFINITIONS.filter((item) => item.id !== "current_card_qa" || currentItem);

  return (
    <>
      {open && <button type="button" className="knowledge-assistant-overlay" aria-label="关闭建筑知识助手" onClick={() => { restoreScrollRef.current = true; setOpen(false); setToolbarOpen(false); setHistoryOpen(false); }} />}
      {!open && <button ref={toggleRef} type="button" className="knowledge-assistant-toggle" style={position ? { left: position.left, top: position.top, right: "auto", bottom: "auto" } : undefined} aria-label="打开 AI 助手" onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onClick={() => { if (!ignoreClickRef.current) { restoreScrollRef.current = true; setOpen(true); } }}>
        <span ref={faceRef} className="knowledge-assistant-face" aria-hidden="true"><span className="knowledge-assistant-eye left" /><span className="knowledge-assistant-eye right" /></span>
      </button>}

      <section className={`knowledge-assistant-panel ${open ? "open" : ""}`} aria-label="AI 助手">
        <header><div className="knowledge-assistant-title"><strong>您的建筑知识助手</strong><small>帮您查找案例，回答相关问题</small></div><div className="knowledge-assistant-header-actions"><button type="button" aria-label="新建会话" title="新建会话" onClick={createConversation}>＋</button><div className="knowledge-assistant-history-anchor" ref={historyRef}><button type="button" aria-label="历史会话" title="历史会话" aria-expanded={historyOpen} aria-controls="knowledge-assistant-history" onClick={toggleHistory}><HistoryIcon /></button>{historyOpen && <div className="knowledge-assistant-history" id="knowledge-assistant-history"><div className="knowledge-assistant-history-search"><input value={historyDraft} placeholder="搜索历史会话" onChange={(event) => setHistoryDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { setHistoryQuery(historyDraft.trim()); loadHistory(historyDraft.trim()); } }} /><button type="button" aria-label={historyQuery ? "返回全部历史" : "搜索"} onClick={() => { if (historyQuery) { setHistoryDraft(""); setHistoryQuery(""); loadHistory(""); } else { setHistoryQuery(historyDraft.trim()); loadHistory(historyDraft.trim()); } }}>{historyQuery ? "×" : "⌕"}</button></div><div className="knowledge-assistant-history-list knowledge-scroll">{history.map((item) => <button type="button" onClick={() => selectConversation(item.id)} key={item.id}><strong>{item.title}</strong><small>{item.message_count} 条消息 · {item.updated_at ? new Date(item.updated_at).toLocaleDateString("zh-CN") : "刚刚"}</small></button>)}{!history.length && <p>暂无匹配的历史会话</p>}</div></div>}</div></div></header>
        <div className="knowledge-assistant-conversation knowledge-scroll" ref={conversationRef} onScroll={(event) => window.localStorage.setItem(`${CONVERSATION_SCROLL_KEY}:${conversationIdRef.current}`, String(event.currentTarget.scrollTop))}>
          {!messages.length && <AssistantBubble content="描述你的设计任务，或从下方工具中选择一种学习方式。我只会推荐知识库中真实存在的卡片。" />}
          {messages.map((message, index) => message.role === "user" ? <UserBubble content={message.content} tool={message.tool} key={index} /> : <AssistantBubble content={message.content} result={message.result} onOpenItem={onOpenItem} onRestoreResult={onResult} key={index} />)}
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
          <button type={loading ? "button" : "submit"} className="app-action-button" disabled={!loading && !question.trim()} aria-label={loading ? "暂停生成" : "发送"} onClick={loading ? () => requestControllerRef.current?.abort() : undefined}>{loading ? "暂停" : "发送"}</button>
          {error && <p className="knowledge-assistant-error">{error}</p>}
        </form>
      </section>
    </>
  );
}

// 渲染助手消息及其中可点击的知识库引用。
function AssistantBubble({ content, result, loading = false, onOpenItem, onRestoreResult }: { content: string; result?: Partial<KnowledgeAssistantResult>; loading?: boolean; onOpenItem?: (itemId: string) => void; onRestoreResult?: (result: KnowledgeAssistantResult) => void }) {
  const recommendations = result?.recommendations ?? [];
  const citations = result?.citations ?? [];
  const visibleCitations = result?.intent === "current_card_qa" ? [] : citations.length ? citations : recommendations.map((item) => ({ id: item.id, title: "" }));
  const restoreRecommendations = recommendations.length > 0 && result?.ui_action !== "none";
  return <div className="knowledge-message-row"><img className="knowledge-message-avatar" src="/assets/v1/头像.png" alt="建筑知识助手" /><div className="knowledge-message-stack"><p className={loading ? "is-loading" : ""}>{loading ? content : cleanAssistantDisplayText(content)}</p>{visibleCitations.length > 0 && <div className="knowledge-assistant-references">{visibleCitations.map((item) => <button type="button" title={`${item.id}${item.title ? ` · ${item.title}` : ""}`} onClick={() => restoreRecommendations ? onRestoreResult?.(result as KnowledgeAssistantResult) : onOpenItem?.(item.id)} key={item.id}>{item.id}{item.title ? ` · ${item.title}` : ""}</button>)}</div>}</div></div>;
}

// 用户消息同时展示本轮使用的工具和需求文本。
function UserBubble({ content, tool }: { content: string; tool?: KnowledgeAssistantTool }) {
  const definition = TOOL_DEFINITIONS.find((item) => item.id === tool);
  return <div className="knowledge-message-row user"><p>{definition && tool && tool !== "none" && <span className="knowledge-message-tool"><ToolIcon tool={tool} /><strong>{definition.name}</strong></span>}<span>{content}</span></p></div>;
}

// 使用统一线宽的内置 SVG 图标，不引入额外图标依赖。
function ToolIcon({ tool }: { tool: KnowledgeAssistantTool }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (tool === "case_recommendation") return <svg viewBox="0 0 24 24" {...common}><path d="M4 20V9l8-5 8 5v11M8 20v-6h8v6M9 10h.01M15 10h.01" /></svg>;
  if (tool === "knowledge_query") return <svg viewBox="0 0 24 24" {...common}><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H11v17H7.5A3.5 3.5 0 0 0 4 22zM20 5.5A3.5 3.5 0 0 0 16.5 2H13v17h3.5A3.5 3.5 0 0 1 20 22z" /></svg>;
  if (tool === "learning_path") return <svg viewBox="0 0 24 24" {...common}><circle cx="5" cy="18" r="2" /><circle cx="19" cy="6" r="2" /><path d="M7 18h3a3 3 0 0 0 3-3v-6a3 3 0 0 1 3-3h1" /></svg>;
  return <svg viewBox="0 0 24 24" {...common}><path d="M21 12a8 8 0 0 1-8 8H7l-4 2 1.5-4A9 9 0 1 1 21 12z" /><path d="M9.7 9a2.4 2.4 0 1 1 3.5 2.1c-.8.4-1.2.9-1.2 1.9M12 16h.01" /></svg>;
}

// 历史会话入口图标。
function HistoryIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></svg>;
}
