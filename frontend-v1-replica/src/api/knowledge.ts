// 知识库接口：只负责读取学习目录和卡片详情，页面可在后续前端改版时直接替换。
import { requestJson } from "./client";

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
  building_types: string[];
}

export type KnowledgeAssistantTool = "none" | "case_recommendation" | "knowledge_query" | "similar_cases" | "case_compare" | "learning_path" | "problem_breakdown" | "current_card_qa";

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
let libraryCache: { value: KnowledgeLibraryPayload; cachedAt: number } | null = null;
let libraryRequest: Promise<KnowledgeLibraryPayload> | null = null;
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

// 恢复当前账户已经保存的知识助手会话。
export function getKnowledgeAssistantMessages(conversationId: string): Promise<KnowledgeAssistantMessage[]> {
  return requestJson<KnowledgeAssistantMessage[]>(`/api/knowledge/assistant/conversations/${encodeURIComponent(conversationId)}/messages`, { timeoutMs: 10_000 });
}
