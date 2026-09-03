// 知识库接口：只负责读取学习目录和卡片详情，页面可在后续前端改版时直接替换。
import { apiUrl, requestJson } from "./client";

export type KnowledgeKind = "knowledge" | "case";

export interface KnowledgeLibraryItem {
  id: string;
  title: string;
  kind: KnowledgeKind;
  kind_label: string;
  category: string;
  level: string;
  level_label: string;
  excerpt: string;
  related_ids: string[];
  thumbnail: string;
  image_count: number;
}

export interface KnowledgeImage {
  name: string;
  url: string;
}

export interface KnowledgeLibraryDetail extends KnowledgeLibraryItem {
  content: string;
  images: KnowledgeImage[];
}

export interface KnowledgeLibraryPayload {
  items: KnowledgeLibraryItem[];
  totals: { all: number; knowledge: number; case: number };
  levels: string[];
  knowledge_categories: string[];
  difficulties: string[];
  building_types: string[];
}

export type KnowledgeAssistantTool = "none" | "case_recommendation" | "knowledge_query" | "learning_path" | "current_card_qa";

export type KnowledgeQuizQuestionType = "single_choice" | "multiple_choice" | "true_false" | "image_choice" | "short_answer";

export interface KnowledgeQuizOption {
  id: string;
  label: string;
}

export interface KnowledgeQuizQuestion {
  id: string;
  card_id: string;
  card_title: string;
  category: string;
  difficulty: string;
  difficulty_label: string;
  prompt: string;
  question_type: KnowledgeQuizQuestionType;
  question_type_label: string;
  options: KnowledgeQuizOption[];
  image_url: string;
  image_alt: string;
}

export interface KnowledgeQuizPayload {
  questions: KnowledgeQuizQuestion[];
  difficulties: { value: string; label: string; count: number }[];
}

export interface KnowledgeQuizAnswerResult {
  question_id: string;
  is_correct: boolean;
  score: number;
  status_label: string;
  correct_answers: string[];
  answer_points: string[];
  matched_points: string[];
  missed_points: string[];
  explanation: string;
}

export interface KnowledgeConversationSummary {
  id: string;
  title: string;
  selected_tool: string;
  message_count: number;
  updated_at: string | null;
}

export interface KnowledgeRecommendation {
  id: string;
  kind: KnowledgeKind;
  reason: string;
  matched_fields: string[];
  limitations: string[];
  score: number;
  review_status: string;
  human_review_confirmed: boolean;
}

export interface KnowledgeAssistantResult {
  answer: string;
  intent: KnowledgeAssistantTool;
  clarification_required: boolean;
  extracted_conditions: Record<string, unknown>;
  recommendations: KnowledgeRecommendation[];
  citations: { id: string; title: string }[];
  result_set_id: string | null;
  ui_action: "none" | "show_assistant_results" | "update_assistant_results" | "focus_current_card";
}

export interface KnowledgeAssistantMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  tool: KnowledgeAssistantTool;
  result: Partial<KnowledgeAssistantResult>;
  created_at: string | null;
}

export interface KnowledgeAssistantRequest {
  conversation_id: string;
  tool: KnowledgeAssistantTool;
  message: string;
  context: {
    view: "overview" | "detail";
    current_card_id: string | null;
    main_tab: "all" | KnowledgeKind;
    category: string;
    previous_result_set_id: string | null;
  };
}

const CACHE_MAX_AGE_MS = 10 * 60 * 1000;
const QUIZ_CACHE_MAX_AGE_MS = 30 * 60 * 1000;
const QUIZ_SESSION_CACHE_KEY = "archcritic-knowledge-quiz-payload-v1";
let libraryCache: { value: KnowledgeLibraryPayload; cachedAt: number } | null = null;
let libraryRequest: Promise<KnowledgeLibraryPayload> | null = null;
let quizCache = readQuizSessionCache();
let quizRequest: Promise<KnowledgeQuizPayload> | null = null;
const detailCache = new Map<string, { value: KnowledgeLibraryDetail; cachedAt: number }>();
const detailRequests = new Map<string, Promise<KnowledgeLibraryDetail>>();

// 读取内存中的知识库目录，让页面返回时可以立即恢复内容。
export function getCachedKnowledgeLibrary(): KnowledgeLibraryPayload | null {
  return libraryCache?.value ?? null;
}

// 读取知识库目录，并合并同一时间发生的重复请求。
export function getKnowledgeLibrary(forceRefresh = false): Promise<KnowledgeLibraryPayload> {
  if (!forceRefresh && libraryCache && Date.now() - libraryCache.cachedAt < CACHE_MAX_AGE_MS) {
    return Promise.resolve(libraryCache.value);
  }
  if (libraryRequest) return libraryRequest;
  libraryRequest = requestJson<KnowledgeLibraryPayload>("/api/knowledge")
    .then((value) => {
      libraryCache = { value, cachedAt: Date.now() };
      return value;
    })
    .finally(() => { libraryRequest = null; });
  return libraryRequest;
}

// 在用户进入知识库之前预取目录，失败时交给页面正常重试和提示。
export function prefetchKnowledgeLibrary(): void {
  void getKnowledgeLibrary().catch(() => undefined);
}

// 读取内存中的卡片详情，供返回和重复打开时立即显示。
export function getCachedKnowledgeDetail(itemId: string): KnowledgeLibraryDetail | null {
  return detailCache.get(itemId)?.value ?? null;
}

// 按编号读取一张完整卡片，并缓存已经打开过的正文。
export function getKnowledgeDetail(itemId: string): Promise<KnowledgeLibraryDetail> {
  const cached = detailCache.get(itemId);
  if (cached && Date.now() - cached.cachedAt < CACHE_MAX_AGE_MS) return Promise.resolve(cached.value);
  const pending = detailRequests.get(itemId);
  if (pending) return pending;
  const request = requestJson<KnowledgeLibraryDetail>(`/api/knowledge/${encodeURIComponent(itemId)}`)
    .then((value) => {
      detailCache.set(itemId, { value, cachedAt: Date.now() });
      return value;
    })
    .finally(() => { detailRequests.delete(itemId); });
  detailRequests.set(itemId, request);
  return request;
}

// 用户接近卡片时提前读取正文，点击后通常可以直接显示。
export function prefetchKnowledgeDetail(itemId: string): void {
  void getKnowledgeDetail(itemId).catch(() => undefined);
}

// 发送知识助手问题，真实模型不可用时保留后端的明确错误。
export function sendKnowledgeAssistantMessage(payload: KnowledgeAssistantRequest, signal?: AbortSignal): Promise<KnowledgeAssistantResult> {
  return requestJson<KnowledgeAssistantResult>("/api/knowledge/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
    timeoutMs: 70_000,
  });
}

// 读取服务端事件流，在生成过程中持续交付正文，结束后返回完整推荐结果。
export async function streamKnowledgeAssistantMessage(payload: KnowledgeAssistantRequest, onDelta: (text: string) => void, signal?: AbortSignal): Promise<KnowledgeAssistantResult> {
  const response = await fetch(apiUrl("/api/knowledge/assistant/chat/stream"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(error.detail ?? "AI 助手暂时无法回答，请稍后重试。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: KnowledgeAssistantResult | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = block.match(/^event:\s*(.+)$/m)?.[1];
      const rawData = block.match(/^data:\s*(.+)$/m)?.[1];
      if (!event || !rawData) continue;
      const data = JSON.parse(rawData) as unknown;
      if (event === "delta" && typeof data === "string") onDelta(data);
      if (event === "error") throw new Error(typeof data === "string" ? data : "AI 助手调用失败。");
      if (event === "final") finalResult = data as KnowledgeAssistantResult;
    }
    if (done) break;
  }
  if (!finalResult) throw new Error("AI 返回内容不完整，请重试。");
  return finalResult;
}

// 恢复当前账户已经保存的知识助手会话。
export function getKnowledgeAssistantMessages(conversationId: string): Promise<KnowledgeAssistantMessage[]> {
  return requestJson<KnowledgeAssistantMessage[]>(`/api/knowledge/assistant/conversations/${encodeURIComponent(conversationId)}/messages`, { timeoutMs: 10_000 });
}

// 获取历史会话；搜索只作用于已有会话标题。
export function getKnowledgeAssistantConversations(query = ""): Promise<KnowledgeConversationSummary[]> {
  const suffix = query.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
  return requestJson<KnowledgeConversationSummary[]>(`/api/knowledge/assistant/conversations${suffix}`, { timeoutMs: 10_000 });
}

// 从当前会话恢复不含答案的题库缓存，刷新页面后也无需重复等待。
function readQuizSessionCache(): { value: KnowledgeQuizPayload; cachedAt: number } | null {
  try {
    const cached = JSON.parse(window.sessionStorage.getItem(QUIZ_SESSION_CACHE_KEY) ?? "null") as { value?: KnowledgeQuizPayload; cachedAt?: number } | null;
    if (!cached?.value?.questions || typeof cached.cachedAt !== "number" || Date.now() - cached.cachedAt >= QUIZ_CACHE_MAX_AGE_MS) return null;
    return { value: cached.value, cachedAt: cached.cachedAt };
  } catch {
    return null;
  }
}

// 读取已经准备好的题库，让知识测试组件可以首屏直接显示。
export function getCachedKnowledgeQuiz(): KnowledgeQuizPayload | null {
  return quizCache?.value ?? null;
}

// 读取不提前暴露答案的多题型知识测试题库，并合并重复请求。
export function getKnowledgeQuiz(forceRefresh = false): Promise<KnowledgeQuizPayload> {
  if (!forceRefresh && quizCache && Date.now() - quizCache.cachedAt < QUIZ_CACHE_MAX_AGE_MS) return Promise.resolve(quizCache.value);
  if (quizRequest) return quizRequest;
  quizRequest = requestJson<KnowledgeQuizPayload>("/api/knowledge/quiz", { timeoutMs: 20_000 })
    .then((value) => {
      quizCache = { value, cachedAt: Date.now() };
      try {
        window.sessionStorage.setItem(QUIZ_SESSION_CACHE_KEY, JSON.stringify(quizCache));
      } catch {
        // 浏览器禁用会话存储时仍保留内存缓存，不影响本次使用。
      }
      return value;
    })
    .finally(() => { quizRequest = null; });
  return quizRequest;
}

// 登录后在后台准备题库，使用户稍后进入测试时无需等待。
export function prefetchKnowledgeQuiz(): void {
  void getKnowledgeQuiz().catch(() => undefined);
}

// 提交一道题，答案和解析只在作答完成后返回。
export function submitKnowledgeQuizAnswer(questionId: string, answer: string | string[]): Promise<KnowledgeQuizAnswerResult> {
  return requestJson<KnowledgeQuizAnswerResult>("/api/knowledge/quiz/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, answer }),
    timeoutMs: 20_000,
  });
}
