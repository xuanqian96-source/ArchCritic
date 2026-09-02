// 问题反馈接口：把登录用户提交的建议保存到后端。
import { requestJson } from "./client";

export interface FeedbackReceipt {
  id: number;
  status: string;
  created_at?: string | null;
}

// 提交一条问题反馈。
export function submitFeedback(content: string): Promise<FeedbackReceipt> {
  return requestJson("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    timeoutMs: 15_000,
  });
}
