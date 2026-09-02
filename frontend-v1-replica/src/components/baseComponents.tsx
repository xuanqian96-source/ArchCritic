// 基础界面组件：画布、按钮、步骤条、字段与通用卡片。
import { useEffect, useState, type PointerEvent as ReactPointerEvent, type PropsWithChildren, type ReactNode, type WheelEvent } from "react";
import { createPortal } from "react-dom";
import type { PageProps, Route } from "../App";
import { useWorkspace } from "../state/workspace";

export function Canvas({ scale, left, top, children }: PropsWithChildren<{ scale: number; left: number; top: number }>) {
  return (
    <div className="canvas-frame absolute" style={{ left, top, transform: `scale(${scale})` }}>
      <div className="canvas-content">{children}</div>
    </div>
  );
}

// 渲染通用按钮，文字和状态由页面传入。
export function Button({
  children,
  onClick,
  kind = "dark",
  className = "",
  disabled = false,
  type = "button",
}: PropsWithChildren<{ onClick?: () => void; kind?: "dark" | "purple" | "white" | "ghost"; className?: string; disabled?: boolean; type?: "button" | "submit" }>) {
  const styles = {
    dark: "bg-[#171719] text-white",
    purple: "bg-[#6c4dff] text-white",
    white: "border border-[#e8ebef] bg-white text-[#171719]",
    ghost: "border border-[#9a9ea7] bg-transparent text-[#9a9ea7]",
  };
  return (
    <button type={type} disabled={disabled} className={`app-action-button h-10 whitespace-nowrap rounded-[12px] px-5 disabled:cursor-not-allowed disabled:opacity-60 ${styles[kind]} ${className}`} onClick={onClick}>
      {children}
    </button>
  );
}

// 把提示卡挂到页面最外层，确保遮罩不受画布宽度、缩放或父容器定位影响。
export function AppPromptOverlay({ children, onClose }: PropsWithChildren<{ onClose: () => void }>) {
  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-[#171719]/30 p-5" role="dialog" aria-modal="true" onClick={onClose}>
      {children}
    </div>,
    document.body,
  );
}

// 渲染可缩放、可拖动的大图查看层，供知识库、项目信息和上传图纸复用。
export function ZoomableImageStage({ src, alt, onClose, className = "", imageClassName = "max-h-[92vh] max-w-[92vw]" }: { src: string; alt: string; onClose: () => void; className?: string; imageClassName?: string }) {
  const [imageZoom, setImageZoom] = useState(1);
  const [imagePan, setImagePan] = useState({ x: 0, y: 0 });
  const [imageDrag, setImageDrag] = useState<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);

  useEffect(() => {
    setImageZoom(1);
    setImagePan({ x: 0, y: 0 });
    setImageDrag(null);
  }, [src]);

  // 鼠标滚轮只在默认大小和 4 倍之间缩放，缩回默认大小时自动居中。
  const handleImageWheel = (event: WheelEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setImageZoom((current) => {
      const next = Math.max(1, Math.min(4, Number((current + (event.deltaY < 0 ? 0.08 : -0.08)).toFixed(2))));
      if (next === 1) setImagePan({ x: 0, y: 0 });
      return next;
    });
  };

  // 放大后允许按住左键拖动画面，默认大小不移动。
  const startImageDrag = (event: ReactPointerEvent<HTMLImageElement>) => {
    event.stopPropagation();
    if (imageZoom <= 1) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setImageDrag({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: imagePan.x,
      originY: imagePan.y,
    });
  };

  const moveImageDrag = (event: ReactPointerEvent<HTMLImageElement>) => {
    event.stopPropagation();
    if (!imageDrag || imageDrag.pointerId !== event.pointerId) return;
    setImagePan({
      x: imageDrag.originX + event.clientX - imageDrag.startX,
      y: imageDrag.originY + event.clientY - imageDrag.startY,
    });
  };

  const stopImageDrag = (event: ReactPointerEvent<HTMLImageElement>) => {
    event.stopPropagation();
    if (imageDrag?.pointerId === event.pointerId) setImageDrag(null);
  };

  return (
    <section className={`absolute inset-0 overflow-hidden p-8 ${className}`} onClick={(event) => { event.stopPropagation(); onClose(); }} onWheel={handleImageWheel}>
      <div className="flex h-full w-full items-center justify-center overflow-hidden">
        <img
          className={`${imageClassName} select-none rounded-[14px] bg-white object-contain shadow-2xl ${imageZoom > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-default"}`}
          draggable={false}
          style={{ transform: `translate(${imagePan.x}px, ${imagePan.y}px) scale(${imageZoom})`, transformOrigin: "center center" }}
          src={src}
          alt={alt}
          onClick={(event) => event.stopPropagation()}
          onPointerDown={startImageDrag}
          onPointerMove={moveImageDrag}
          onPointerUp={stopImageDrag}
          onPointerCancel={stopImageDrag}
        />
      </div>
    </section>
  );
}

// 渲染工作区左侧栏，保持 Figma 中的固定尺寸和项目文本。
export function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <>
      <h1 className="absolute left-[307px] top-[53px] text-[34px] font-bold leading-[44px]">{title}</h1>
      <p className="absolute left-[307px] top-[107px] text-[14px] leading-[22px] text-[#53565e]">{subtitle}</p>
    </>
  );
}

// 渲染四步新建评图步骤条。
export function Steps({ current, order = "default" }: { current: 1 | 2 | 3 | 4; order?: "default" | "confirm" }) {
  const steps = order === "confirm" ? ["项目信息", "上传图纸", "选择阶段", "确认提交"] : ["项目信息", "选择阶段", "上传图纸", "确认提交"];
  return (
    <div className="absolute left-[328px] top-[164px] flex items-center">
      {steps.map((text, index) => {
        const active = index + 1 <= current;
        return (
          <div className="flex items-center" key={text}>
            <span className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold ${active ? "bg-[#6c4dff] text-white" : "bg-[#e8ebef] text-[#9a9ea7]"}`}>{index + 1}</span>
            <span className={`ml-2 w-[52px] text-[12px] ${active ? "text-[#171719]" : "text-[#9a9ea7]"}`}>{text}</span>
            {index < 3 && <span className={`mr-2 h-[2px] w-9 ${index + 1 < current ? "bg-[#6c4dff]" : "bg-[#cbd2dc]"}`} />}
          </div>
        );
      })}
    </div>
  );
}

// 显示流程校验或接口失败原因，避免使用浏览器系统弹窗。
export function FlowErrorCard({ title = "操作未完成", message, onClose }: { title?: string; message: string; onClose: () => void }) {
  return (
    <AppPromptOverlay onClose={onClose}>
      <section className="app-prompt-card figma-shadow" onClick={(event) => event.stopPropagation()}>
        <h2 className="app-prompt-title">{title}</h2>
        <p className="app-prompt-copy">{message}</p>
        <div className="app-prompt-actions">
          <button type="button" className="app-action-button h-9 rounded-[10px] bg-[#171719] px-5 text-white" onClick={onClose}>知道了</button>
        </div>
      </section>
    </AppPromptOverlay>
  );
}

// 渲染页面右上角流程按钮。
export function FlowActions({ go, previous, next, finalText = "下一步", onSave, beforeNext }: { go: (route: Route) => void; previous?: Route; next: Route; finalText?: string; onSave?: () => Promise<unknown> | void; beforeNext?: () => Promise<unknown> | void }) {
  const { draftDirty, setNotice } = useWorkspace();
  const [activeAction, setActiveAction] = useState<"save" | "next" | null>(null);
  const [error, setError] = useState("");
  const submitting = activeAction === "save";

  // 单独保存草稿时停留在当前页面，并等待后端保存完成。
  const saveOnly = async () => {
    if (!onSave) return;
    setActiveAction("save");
    setError("");
    try {
      await onSave();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "草稿保存失败，请稍后重试。");
    } finally {
      setActiveAction(null);
    }
  };

  const saveAfterRouteChange = () => {
    if (!onSave || !draftDirty) return;
    void Promise.resolve(onSave()).catch(() => {
      setNotice("后台保存失败，请稍后手动保存草稿。");
    });
  };

  const nextPage = async () => {
    setError("");
    setActiveAction("next");
    try {
      await beforeNext?.();
      go(next);
      saveAfterRouteChange();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "请先补充完整当前页面信息。");
    } finally {
      setActiveAction(null);
    }
  };
  return (
    <>
      <div className="absolute right-[23px] top-[154px] flex gap-4">
        {previous && <Button kind="white" disabled={submitting} onClick={() => go(previous)} className="report-top-action-button w-[112px] text-[#9a9ea7]">上一步</Button>}
        <Button kind="white" disabled={submitting || !onSave} className="report-top-action-button w-[122px]" onClick={() => void saveOnly()}>{activeAction === "save" ? "保存中" : "保存草稿"}</Button>
        <Button kind="purple" disabled={Boolean(activeAction)} onClick={() => void nextPage()} className="report-top-action-button w-[123px] rounded-[16px]">{activeAction === "next" ? "处理中" : finalText}</Button>
      </div>
      {error && <FlowErrorCard message={error} onClose={() => setError("")} />}
    </>
  );
}

// 渲染图纸卡片中的简化缩略图。
export function PlanThumb({ muted = false, className = "" }: { muted?: boolean; className?: string }) {
  return (
    <div className={`relative rounded-[12px] bg-[#e6e7e9] ${muted ? "opacity-65 grayscale" : ""} ${className}`}>
      <span className="absolute left-[28px] top-[24px] h-[26px] w-[54px] rounded-[4px] border border-[#3b82f6] bg-[#e6f0ff]" />
      <span className="absolute left-[105px] top-[22px] h-[21px] w-[54px] rounded-[4px] border border-[#22c55e] bg-[#e6f8ed]" />
      <span className="absolute left-[78px] top-[59px] h-[21px] w-[35px] rounded-[4px] border border-[#6c4dff] bg-[#ffe8ec]" />
      <span className="absolute bottom-[16px] left-[24px] h-px w-[143px] rotate-[6deg] bg-[#6c4dff]" />
    </div>
  );
}

// 渲染通用字段。
export function Field({ label, value, wide = false, onChange }: { label: string; value: string; wide?: boolean; onChange?: (value: string) => void }) {
  return (
    <label className={`block ${wide ? "w-full" : "w-[48%]"}`}>
      <b className="mb-2 block text-[12px] leading-4 text-[#9a9ea7]">{label}</b>
      <input value={value} onChange={(event) => onChange?.(event.target.value)} className="h-10 w-full rounded-[12px] border border-[#e8ebef] bg-white px-[13px] py-[9px] text-[13px] leading-[18px] text-[#171719] outline-none" />
    </label>
  );
}

// 渲染小标签。
export function Badge({ children, tone = "purple" }: PropsWithChildren<{ tone?: "purple" | "green" | "blue" | "dark" | "coral" }>) {
  const colors = {
    purple: "bg-[#efe9ff] text-[#6c4dff]",
    green: "bg-[#e6f8ed] text-[#22c55e]",
    blue: "bg-[#e6f0ff] text-[#3b82f6]",
    dark: "bg-[#171719] text-white",
    coral: "bg-[#ffe8ec] text-[#6c4dff]",
  };
  return <span className={`inline-flex h-7 items-center rounded-full px-4 text-[12px] font-bold ${colors[tone]}`}>{children}</span>;
}

// 渲染白色卡片。
export function Card({ children, className = "", id }: PropsWithChildren<{ className?: string; id?: string }>) {
  return <section id={id} className={`white-panel figma-shadow ${className}`}>{children}</section>;
}

// 渲染 Figma 中固定展示的细滚动轴。
export function FigmaScrollbar({ className = "", thumbClassName = "" }: { className?: string; thumbClassName?: string }) {
  return (
    <div className={`pointer-events-none absolute w-2 ${className}`}>
      <span className="absolute left-0.5 top-0 h-full w-1 rounded-full bg-[#e8ebef]" />
      <span className={`absolute left-px top-0 w-1.5 rounded-full bg-[#cbd2dc] ${thumbClassName}`} />
    </div>
  );
}

// 渲染小图标占位，保持 Figma 中的圆形视觉。
export function IconCircle({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return <span className={`inline-flex items-center justify-center rounded-full ${className}`}>{children as ReactNode}</span>;
}
