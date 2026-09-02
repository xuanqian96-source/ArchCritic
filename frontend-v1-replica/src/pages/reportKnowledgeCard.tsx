// 报告关联知识卡：在反馈弹窗中呈现完整正文、层级和原位图片。
import { useEffect, useState } from "react";
import { apiUrl } from "../api/client";
import { getCachedKnowledgeDetail, getKnowledgeDetail, type KnowledgeLibraryDetail } from "../api/knowledge";
import type { KnowledgeImage, KnowledgeReference } from "../types/api";

// 用知识库详情接口替换报告摘要快照，失败时保留快照作为兜底。
export function useReportKnowledgeDetail(reference: KnowledgeReference | null) {
  const [detail, setDetail] = useState<KnowledgeLibraryDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const itemId = reference?.library_item_id?.trim();
    if (!itemId) {
      setDetail(null);
      setLoading(false);
      setError("");
      return;
    }
    let active = true;
    const cached = getCachedKnowledgeDetail(itemId);
    setDetail(cached);
    setLoading(!cached);
    setError("");
    void getKnowledgeDetail(itemId)
      .then((value) => { if (active) setDetail(value); })
      .catch((loadError) => { if (active) setError(loadError instanceof Error ? loadError.message : "知识卡正文读取失败。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reference?.library_item_id]);
  return {
    detail,
    loading,
    error,
    title: detail?.title || reference?.title || "知识库卡片",
    excerpt: detail?.excerpt || reference?.excerpt || "",
    content: detail?.content || reference?.display_content || reference?.content || reference?.excerpt || "",
    images: (detail?.images ?? reference?.image_urls ?? []) as KnowledgeImage[],
  };
}

// 按知识库阅读页的层级展示报告快照中的完整正文与图片。
export function ReportKnowledgeContent({ content, images, onPreview }: { content: string; images: KnowledgeImage[]; onPreview: (image: KnowledgeImage) => void }) {
  const visibleContent = content || "当前知识卡片暂无详细内容。";
  const imageByName = new Map(images.map((image) => [image.name, image]));
  return <>{visibleContent.split("\n").map((rawLine, index) => {
    const line = rawLine.trim();
    if (!line || (index === 0 && line.startsWith("# "))) return null;
    const imageMatch = line.match(/^!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]$/) ?? line.match(/^!\[[^\]]*\]\(([^)]+)\)$/);
    if (imageMatch) {
      const name = imageMatch[1].split("/").pop() ?? imageMatch[1];
      const image = imageByName.get(name);
      return image ? <button type="button" className="my-5 block w-full overflow-hidden rounded-[14px] border border-[#e8ebef] bg-[#fafbfc] text-left" onClick={() => onPreview(image)} key={`${name}-${index}`}><img className="max-h-[340px] w-full object-contain" src={apiUrl(image.url)} alt={name} loading="lazy" decoding="async" /><span className="block px-4 py-2 text-[11px] text-[#8b9099]">点击查看原图 · {name}</span></button> : null;
    }
    const plain = line
      .replace(/^#{1,6}\s*/, "")
      .replace(/^>\s*/, "")
      .replace(/^[-*]\s+/, "")
      .replace(/\*\*/g, "")
      .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_match, target, label) => label || target)
      .trim();
    if (!plain) return null;
    if (line.startsWith("## ")) return <h3 className="mb-3 mt-7 text-[17px] font-bold leading-6 text-[#171719]" key={index}>{plain}</h3>;
    if (line.startsWith("### ")) return <h4 className="mb-2 mt-5 text-[15px] font-bold leading-6 text-[#171719]" key={index}>{plain}</h4>;
    if (line.startsWith(">")) return <blockquote className="my-4 rounded-r-[12px] border-l-4 border-[#8b73ff] bg-[#f7f5ff] px-4 py-3 text-[14px] leading-7 text-[#53565e]" key={index}>{plain}</blockquote>;
    if (/^[-*]\s+/.test(line)) return <div className="mb-2 grid grid-cols-[14px_1fr] text-[14px] leading-7 text-[#53565e]" key={index}><span className="text-[#6c4dff]">•</span><p>{plain}</p></div>;
    return <p className="mb-3 text-[14px] leading-7 text-[#53565e]" key={index}>{plain}</p>;
  })}</>;
}
