// 报告知识推荐跳转状态：在知识页保留当前提交、整组推荐和报告助手来源。
import type { ChatMessage } from "../types/api";

const STORAGE_KEY = "archcritic-report-knowledge-context";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface ReportKnowledgeContext {
  submissionId: number;
  citations: NonNullable<ChatMessage["citations"]>;
  lastMessageId?: number;
  createdAt: number;
}

// 保存报告助手本轮全部推荐，而不是只保存用户点击的一张卡。
export function saveReportKnowledgeContext(submissionId: number, citations: NonNullable<ChatMessage["citations"]>, lastMessageId?: number): void {
  const value: ReportKnowledgeContext = { submissionId, citations, lastMessageId, createdAt: Date.now() };
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

// 读取仍属于当前提交的报告推荐上下文。
export function readReportKnowledgeContext(submissionId?: number): ReportKnowledgeContext | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as ReportKnowledgeContext;
    if (!Number.isInteger(value.submissionId) || !Array.isArray(value.citations) || !value.citations.length) return null;
    if (Date.now() - Number(value.createdAt || 0) > MAX_AGE_MS) return null;
    if (submissionId !== undefined && value.submissionId !== submissionId) return null;
    return value;
  } catch {
    return null;
  }
}

// 返回报告后清除来源状态，普通进入知识库时继续使用知识助手。
export function clearReportKnowledgeContext(): void {
  window.sessionStorage.removeItem(STORAGE_KEY);
}
