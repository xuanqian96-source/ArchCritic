// 帮助中心组件：二级菜单、新手遮罩指引、常见问题、反馈提交和退出确认。
import { useEffect, useState } from "react";
import { submitFeedback } from "../api/feedback";
import type { HelpArticle as InformationItem } from "../data/helpContent";
import { AppPromptOverlay, Button } from "./baseComponents";

const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL?.trim() || "1611914241@qq.com";

// 渲染账户菜单右侧的帮助入口。
export function HelpMenu({ onTour, onFaq, onFeedback, onMouseEnter, onMouseLeave }: { onTour: () => void; onFaq: () => void; onFeedback: () => void; onMouseEnter: () => void; onMouseLeave: () => void }) {
  return (
    <section data-account-menu className="figma-shadow absolute bottom-[80px] left-[221px] z-30 w-[156px] rounded-[18px] border border-[#e8ebef] bg-white p-2" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      <HelpMenuItem icon="tour" text="新手指引" onClick={onTour} />
      <HelpMenuItem icon="faq" text="常见问题" onClick={onFaq} />
      <HelpMenuItem icon="feedback" text="问题反馈" onClick={onFeedback} />
    </section>
  );
}

// 渲染帮助二级菜单的一行。
function HelpMenuItem({ icon, text, onClick }: { icon: HelpIconName; text: string; onClick: () => void }) {
  return <button type="button" className="flex h-9 w-full items-center rounded-[10px] px-2 text-left text-[13px] hover:bg-[#f4f6f8]" onClick={onClick}><HelpMenuIcon name={icon} /><span className="ml-2">{text}</span></button>;
}

type HelpIconName = "tour" | "faq" | "feedback";

// 渲染帮助菜单的线性图标。
function HelpMenuIcon({ name }: { name: HelpIconName }) {
  const paths = {
    tour: <><path d="M4 6.5 9 4l6 2.5L20 4v13.5L15 20l-6-2.5L4 20V6.5Z" /><path d="M9 4v13.5M15 6.5V20" /></>,
    faq: <><circle cx="12" cy="12" r="8" /><path d="M9.7 9a2.4 2.4 0 014.6.9c0 1.8-2.3 2.1-2.3 3.7M12 17h.01" /></>,
    feedback: <><path d="M4 5.5h16v11H9l-5 3v-14Z" /><path d="M8 9h8M8 13h5" /></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" className="h-[18px] w-[18px] shrink-0 fill-none stroke-[#171719] stroke-[1.7]">{paths[name]}</svg>;
}

interface TourStep {
  title: string;
  detail: string;
  rect: { left: number; top: number; width: number; height: number };
  card: { left: number; top: number };
}

const TOUR_STEPS: TourStep[] = [
  { title: "工作区导航", detail: "你可以在左侧导航栏进入知识库、浏览历史项目、回溯不同版本，并随时返回查看相关报告。", rect: { left: 23, top: 11, width: 248, height: 796 }, card: { left: 300, top: 292 } },
  { title: "发起一次新评图", detail: "点击这里新建评图，也可以继承已有项目资料，继续提交修改后的方案。", rect: { left: 44, top: 86, width: 204, height: 40 }, card: { left: 284, top: 16 } },
  { title: "查看项目状态", detail: "首页会汇总最近项目的评图状态、更新时间和得分，点击卡片即可继续工作或查看报告。", rect: { left: 307, top: 183, width: 803, height: 624 }, card: { left: 1130, top: 376 } },
  { title: "公告与常见问题", detail: "右侧展示系统更新、操作指引和常见问题。点击条目可以查看完整说明。", rect: { left: 1146, top: 181, width: 367, height: 626 }, card: { left: 770, top: 376 } },
  { title: "账户与帮助", detail: "这里可以修改个人资料、重新查看本指引、反馈问题，或安全退出当前账户。", rect: { left: 44, top: 743, width: 204, height: 52 }, card: { left: 284, top: 580 } },
];

// 用遮罩逐步高亮首页关键区域。
export function OnboardingTour({ onClose }: { onClose: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const step = TOUR_STEPS[stepIndex];

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="absolute inset-0 z-[100]" role="dialog" aria-modal="true" aria-label="新手指引">
      <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
        <defs>
          <mask id="onboarding-cutout">
            <rect width="100%" height="100%" fill="white" />
            <rect x={step.rect.left - 6} y={step.rect.top - 6} width={step.rect.width + 12} height={step.rect.height + 12} rx="20" fill="black" />
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(23,23,25,.62)" mask="url(#onboarding-cutout)" />
      </svg>
      <div className="pointer-events-none absolute rounded-[20px] border-2 border-[#8b73ff] shadow-[0_0_0_4px_rgba(108,77,255,.18)]" style={step.rect} />
      <section className="figma-shadow absolute w-[360px] rounded-[20px] border border-[#e8ebef] bg-white p-6" style={step.card}>
        <div className="mb-3 flex items-center justify-between">
          <span className="text-[12px] font-bold text-[#6c4dff]">{stepIndex + 1} / {TOUR_STEPS.length}</span>
          <button type="button" className="onboarding-skip-button text-[#6b7280] hover:text-[#171719]" onClick={onClose}>跳过指引</button>
        </div>
        <h2 className="text-[20px] font-bold">{step.title}</h2>
        <p className="mt-3 text-[13px] leading-6 text-[#53565e]">{step.detail}</p>
        <div className="mt-5 flex justify-end gap-3">
          {stepIndex > 0 && <Button kind="white" className="h-9 rounded-[10px]" onClick={() => setStepIndex((current) => current - 1)}>上一步</Button>}
          <Button className="h-9 rounded-[10px]" onClick={() => stepIndex === TOUR_STEPS.length - 1 ? onClose() : setStepIndex((current) => current + 1)}>{stepIndex === TOUR_STEPS.length - 1 ? "完成" : "下一步"}</Button>
        </div>
      </section>
    </div>
  );
}

// 渲染公告或帮助文章详情，首页和账户帮助共用。
export function InformationDetailModal({ item, onClose }: { item: InformationItem; onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-[70] bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="pr-9 text-[22px] font-bold leading-8">{item.title}</h2>
        <button type="button" aria-label="关闭详情" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <p className="mt-5 text-[14px] leading-7 text-[#53565e]">{item.detail}</p>
      </section>
    </div>
  );
}

// 渲染全部公告或帮助文章，保持与首页“查看更多”一致。
export function InformationListModal({ title, items, onClose }: { title: string; items: InformationItem[]; onClose: () => void }) {
  const [detail, setDetail] = useState<InformationItem | null>(null);
  if (detail) return <InformationDetailModal item={detail} onClose={() => setDetail(null)} />;
  return (
    <div className="absolute inset-0 z-[70] bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="ml-2 text-[22px] font-bold">{title}</h2>
        <button type="button" aria-label="关闭列表" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <div className="information-list-scroll absolute bottom-7 left-7 right-7 top-[86px] overflow-y-auto pr-2">
          {items.map((item) => (
            <button type="button" className="flex h-[52px] w-full items-center rounded-[10px] border-b border-[#eef0f3] px-2 text-left hover:bg-[#f4f6f8]" onClick={() => setDetail(item)} key={item.title}>
              <span className="information-row-text max-w-[420px] truncate">{item.title}</span>
              <span className="detail-link-text ml-auto">查看详情</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

// 渲染作者联系方式和问题反馈表单。
export function FeedbackModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [content, setContent] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const submit = async () => {
    const trimmed = content.trim();
    if (trimmed.length < 5) {
      setMessage("请至少输入 5 个字，方便我们了解问题。");
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      await submitFeedback(trimmed);
      setSubmitted(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "反馈提交失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <AppPromptOverlay onClose={onDone}>
        <section className="app-prompt-card figma-shadow" onClick={(event) => event.stopPropagation()}>
          <h2 className="app-prompt-title">感谢你的反馈</h2>
          <p className="app-prompt-copy">你的意见已经成功提交。每一条反馈都会帮助我们持续完善 ArchCritic，让它更好地服务于公共建筑设计学习与教学。</p>
          <div className="app-prompt-actions">
            <Button className="h-9 rounded-[10px]" onClick={onDone}>我知道了</Button>
          </div>
        </section>
      </AppPromptOverlay>
    );
  }

  return (
    <div className="absolute inset-0 z-[70] bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[130px] h-[560px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="text-[22px] font-bold">问题反馈</h2>
        <div className="mt-5 space-y-1 text-[13px] leading-6">
          <p className="font-bold">作者团队：ArchSpark Lab｜筑火实验室</p>
          <p className="font-bold">联系邮箱：<a className="font-bold text-[#6c4dff]" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a></p>
        </div>
        <label className="mt-6 block text-[13px] font-bold" htmlFor="feedback-content">请描述你遇到的问题或建议</label>
        <textarea id="feedback-content" className="mt-3 h-[230px] w-full resize-none rounded-[14px] border border-[#e8ebef] p-4 text-[13px] leading-6 outline-none placeholder:text-[12px] placeholder:leading-5 focus:border-[#8b73ff]" maxLength={2000} placeholder="例如：在哪个页面、进行了什么操作、出现了什么问题……" value={content} onChange={(event) => setContent(event.target.value)} />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[12px] text-[#ff5570]">{message}</span>
          <span className="text-[11px] text-[#9a9ea7]">{content.length}/2000</span>
        </div>
        <div className="absolute bottom-7 right-7 flex gap-3">
          <Button kind="white" className="h-9 rounded-[10px]" onClick={onClose}>取消</Button>
          <Button className="h-9 rounded-[10px]" disabled={submitting} onClick={() => void submit()}>{submitting ? "提交中…" : "提交反馈"}</Button>
        </div>
      </section>
    </div>
  );
}

// 退出前再次确认，避免误触后中断当前工作。
export function LogoutConfirmModal({ busy, message, onCancel, onConfirm }: { busy: boolean; message: string; onCancel: () => void; onConfirm: () => void }) {
  return (
    <AppPromptOverlay onClose={onCancel}>
      <section className="app-prompt-card figma-shadow" onClick={(event) => event.stopPropagation()}>
        <h2 className="app-prompt-title">退出登录</h2>
        <p className="app-prompt-copy">确定退出当前账户吗？尚未保存的编辑内容可能会丢失。</p>
        {message && <p className="mt-2 text-[12px] text-[#ff5570]">{message}</p>}
        <div className="app-prompt-actions">
          <Button kind="white" className="h-9 rounded-[10px]" disabled={busy} onClick={onCancel}>取消</Button>
          <Button className="h-9 rounded-[10px]" disabled={busy} onClick={onConfirm}>{busy ? "正在退出…" : "确认退出"}</Button>
        </div>
      </section>
    </AppPromptOverlay>
  );
}
