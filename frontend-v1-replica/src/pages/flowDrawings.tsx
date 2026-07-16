// 图纸与 Agent 流程：选择阶段、管理 Agent 和上传编辑图纸。
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { createPortal } from "react-dom";
import type { PageProps } from "../App";
import { apiUrl } from "../api/client";
import { Button, Card, FlowActions, FlowErrorCard, ZoomableImageStage } from "../components";
import { useWorkspace } from "../state/workspace";
import type { DrawingFile } from "../types/api";
import { EditIcon, TaskbookDeleteCard, TrashIcon, UploadIcon } from "./flowSetup";
import { agentCards, drawingTypeOptions, floorPlanOptions, FlowShell, getStageAgentTypes, type AgentCardSpec, type DrawingPreviewTarget, type PendingUpload, type ReplacingUpload, saveDraftAtRoute, saveDraftAtRouteInBackground, useRememberFlowRoute, validateAgentStep, validateUploadStep } from "./flowShared";

export function AgentsPage({ go }: PageProps) {
  useRememberFlowRoute("agents");
  const { draft, draftDirty, setDraftField, saveDraft, setNotice, toggleAgent } = useWorkspace();
  const [error, setError] = useState("");
  const selectStage = (stage: string) => {
    setDraftField("designStage", stage);
    setDraftField("enabledAgents", getStageAgentTypes(stage));
  };
  const nextPage = () => {
    setError("");
    try {
      validateAgentStep(draft);
      go("upload");
      if (draftDirty) saveDraftAtRouteInBackground(saveDraft, "agents", setNotice);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "请先补充完整当前页面信息。");
    }
  };
  const supportedAgentTypes = getStageAgentTypes(draft.designStage);
  return (
    <FlowShell go={go} title="选择设计阶段" subtitle="系统会根据项目阶段自动调整评价重点与 Agent 协作方式。" current={2}>
      <div className="absolute right-[23px] top-[156px] flex gap-5"><Button kind="white" className="report-top-action-button w-[109px]" onClick={() => go("info")}>上一步</Button><Button kind="purple" className="report-top-action-button w-[110px] rounded-[16px]" onClick={nextPage}>下一步</Button></div>
      <Card className="absolute left-[307px] top-[224px] h-[579px] w-[521px] p-7">
        <h2 className="text-[22px] font-bold">选择项目阶段</h2>
        <div className="mt-7 space-y-9">
          <StageCard title="概念阶段" desc="概念立意、空间构想、场地阅读" active={draft.designStage === "概念阶段"} onClick={() => selectStage("概念阶段")} />
          <StageCard title="方案阶段" desc="场地回应、功能流线、形式构图、结构可行性" active={draft.designStage === "方案阶段"} onClick={() => selectStage("方案阶段")} />
          <StageCard title="图纸阶段" desc="图面表达、排版质量、方案完整度" active={draft.designStage === "图纸阶段"} onClick={() => selectStage("图纸阶段")} />
        </div>
      </Card>
      <Card className="absolute left-[858px] top-[224px] h-[579px] w-[655px] p-7">
        <h2 className="text-[22px] font-bold">启用的 Agent</h2>
        <div className="report-light-scroll mt-6 grid max-h-[470px] grid-cols-2 gap-6 overflow-y-auto pr-3">
          {agentCards.map((agent) => <AgentTile key={agent.type} agent={agent} active={draft.enabledAgents.includes(agent.type)} supported={supportedAgentTypes.includes(agent.type)} onToggle={() => toggleAgent(agent.type)} />)}
        </div>
      </Card>
      {error && <FlowErrorCard message={error} onClose={() => setError("")} />}
    </FlowShell>
  );
}

// 渲染阶段选项。
function StageCard({ title, desc, active, onClick }: { title: string; desc: string; active?: boolean; onClick?: () => void }) {
  return <button type="button" onClick={onClick} className={`flow-surface-motion relative block h-[130px] w-full rounded-[18px] border p-5 text-left ${active ? "border-[#6c4dff] bg-[#efe9ff]" : "border-[#e8ebef] bg-white"}`}><b className="text-[18px]">{title}</b><p className="mt-2 text-[13px] text-[#53565e]">{desc}</p>{active && <span className="absolute right-6 top-[30px] rounded-full px-4 py-2 text-[12px] font-bold text-[#6c4dff]">当前选择</span>}</button>;
}

// 渲染 Agent 选项。
function AgentTile({ agent, active, supported, onToggle }: { agent: AgentCardSpec; active: boolean; supported: boolean; onToggle: () => void }) {
  return <button type="button" disabled={!supported} onClick={onToggle} className={`flow-surface-motion relative h-[220px] overflow-hidden rounded-[18px] border p-4 text-left disabled:cursor-not-allowed ${active ? "border-[#6c4dff] bg-[#efe9ff]" : supported ? "border-[#e8ebef] bg-white hover:border-[#cfc7ff]" : "border-[#eef0f3] bg-[#fafbfc] opacity-45"}`}><b className={`text-[12px] ${active ? "text-[#6c4dff]" : "text-[#9a9ea7]"}`}>{active ? "已启用" : supported ? "可启用" : "当前阶段不使用"}</b><h3 className="mt-5 text-[18px] font-bold">{agent.display}</h3><p className="mt-2 w-[118px] text-[12px] leading-[18px] text-[#53565e]">{agent.cardDesc}</p><img className="absolute bottom-0 right-1 h-[132px] w-[132px] object-contain" src={agent.image} alt="" loading="eager" decoding="async" /></button>;
}

// 渲染上传图纸页。
export function UploadPage({ go }: PageProps) {
  useRememberFlowRoute("upload");
  const inputRef = useRef<HTMLInputElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const { drawings, selectedDrawingId, selectDrawing, uploadFiles, replaceSelectedDrawing, saveDraft, updateSelectedDrawing, deleteDrawingIds } = useWorkspace();
  const [batchEditing, setBatchEditing] = useState(false);
  const [checkedDrawingIds, setCheckedDrawingIds] = useState<number[]>([]);
  const [deleteBatchOpen, setDeleteBatchOpen] = useState(false);
  const [previewTarget, setPreviewTarget] = useState<DrawingPreviewTarget | null>(null);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [replacingUpload, setReplacingUpload] = useState<ReplacingUpload | null>(null);
  const [drawingDescription, setDrawingDescription] = useState("");
  const [error, setError] = useState("");
  const selected = drawings.find((item) => item.id === selectedDrawingId) ?? drawings[0];
  const selectedReplacing = Boolean(replacingUpload && selected?.id === replacingUpload.drawingId);
  const pendingDetail = !selected && pendingUploads[0] ? pendingUploads[0] : null;
  const detailName = (selectedReplacing ? replacingUpload?.name : selected?.original_name ?? pendingDetail?.name) ?? "";
  const detailPending = selectedReplacing || Boolean(pendingDetail);
  const selectedIndex = selected ? drawings.findIndex((item) => item.id === selected.id) : 0;
  const previewSrc = selected ? apiUrl(selected.file_url) : "";
  useEffect(() => {
    setDrawingDescription(selected?.description ?? "");
  }, [selected?.id, selected?.description]);
  const toggleBatchEditing = () => {
    setBatchEditing((current) => !current);
    if (batchEditing) setCheckedDrawingIds([]);
  };
  const toggleDrawingChecked = (fileId: number) => {
    setCheckedDrawingIds((current) => current.includes(fileId) ? current.filter((id) => id !== fileId) : [...current, fileId]);
  };
  const handleUploadChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    if (files.length) {
      const pending = files.map((file, index) => ({ id: `${file.name}-${file.lastModified}-${index}`, name: file.name }));
      setPendingUploads((current) => [...current, ...pending]);
      void uploadFiles(files).catch((caught) => setError(caught instanceof Error ? caught.message : "图纸上传失败。")).finally(() => {
        setPendingUploads((current) => current.filter((item) => !pending.some((pendingItem) => pendingItem.id === item.id)));
      });
    }
    event.currentTarget.value = "";
  };
  const handleReplaceChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (file) {
      const replacingId = selected?.id ?? null;
      setReplacingUpload({ drawingId: replacingId, name: file.name });
      void replaceSelectedDrawing(file).catch((caught) => setError(caught instanceof Error ? caught.message : "图纸替换失败。")).finally(() => setReplacingUpload(null));
    }
    event.currentTarget.value = "";
  };
  const saveDrawingDescription = async () => {
    if (!selected || drawingDescription === (selected.description ?? "")) return;
    await updateSelectedDrawing({ description: drawingDescription });
  };
  const saveUploadDraft = async () => {
    await saveDrawingDescription();
    await saveDraftAtRoute(saveDraft, "upload");
  };
  const validateAndContinue = async () => {
    validateUploadStep(drawings);
    await saveDrawingDescription();
  };
  const openDrawingPreview = () => {
    if (!selected || !previewSrc) return;
    setPreviewTarget({ src: previewSrc, alt: selected.original_name, pdf: isPdfDrawing(selected) });
  };
  return (
    <FlowShell go={go} title="上传设计图纸" subtitle="上传您的设计图纸，AI 将基于多维度为您提供专业评审建议。" current={3}>
      <FlowActions go={go} previous="agents" next="confirm" onSave={saveUploadDraft} beforeNext={validateAndContinue} />
      <Card className="absolute left-[307px] top-[202px] h-[601px] w-[793px] overflow-hidden">
        <div id="upload-scroll-area" className="report-light-scroll absolute inset-0 overflow-y-auto p-[19px]">
          <div className="flex items-center"><Button className="report-top-action-button w-[126px]" onClick={() => inputRef.current?.click()}><span className="text-white"><UploadIcon /></span>上传文件</Button>
          <input ref={inputRef} className="hidden" type="file" accept="image/*,.pdf,application/pdf" multiple onChange={handleUploadChange} />
          <input ref={replaceInputRef} className="hidden" type="file" accept="image/*,.pdf,application/pdf" onChange={handleReplaceChange} />
          <Button kind="white" className="report-top-action-button ml-[29px] w-[126px]" onClick={toggleBatchEditing}><span className="text-[#171719]"><EditIcon /></span>{batchEditing ? "完成编辑" : "批量编辑"}</Button>
          {batchEditing && <Button className="report-top-action-button ml-[29px] w-[126px]" disabled={!checkedDrawingIds.length} onClick={() => checkedDrawingIds.length && setDeleteBatchOpen(true)}><span className="text-white"><TrashIcon /></span>删除</Button>}
          <span className="ml-auto text-[12px] text-[#9a9ea7]">已上传 {drawings.length} 张图纸{pendingUploads.length ? `，${pendingUploads.length} 张正在上传` : ""}</span></div>
          {drawings.length || pendingUploads.length ? (
            <div className="mt-4 grid grid-cols-3 gap-[14px]">
              {drawings.map((item, index) => <DrawingCard key={item.id} name={replacingUpload?.drawingId === item.id ? replacingUpload.name : item.original_name} index={index} drawing={item} selected={!batchEditing && item.id === (selected?.id ?? drawings[0]?.id)} editing={batchEditing} checked={checkedDrawingIds.includes(item.id)} uploading={replacingUpload?.drawingId === item.id} onCheck={() => toggleDrawingChecked(item.id)} onClick={() => batchEditing ? toggleDrawingChecked(item.id) : selectDrawing(item.id)} />)}
              {pendingUploads.map((item, index) => <DrawingCard key={item.id} name={item.name} index={drawings.length + index} uploading />)}
            </div>
          ) : (
            <div className="flex h-[492px] items-center justify-center text-center text-[13px] leading-5 text-[#9a9ea7]">
              还没有上传图纸，点击上方“上传文件”添加设计图纸。
            </div>
          )}
        </div>
      </Card>
      <Card className="absolute left-[1124px] top-[202px] h-[601px] w-[389px] overflow-hidden p-0">
        {detailPending || selected ? (
          <div className="report-light-scroll absolute inset-y-[19px] left-0 right-2 overflow-y-auto overflow-x-hidden pl-[27px] pr-5">
            {detailPending ? (
            <>
              <UploadPendingPreview className="h-[210px]" />
              <h2 className="mt-4 break-all text-[20px] font-bold leading-[28px]">{displayDrawingName(detailName)}</h2>
              <p className="mt-1 text-[12px] text-[#9a9ea7]">上传时间 <span className="float-right">正在上传</span></p>
            </>
            ) : selected ? (
            <>
              <div
                role="button"
                tabIndex={0}
                className="group relative block w-full cursor-zoom-in overflow-hidden bg-white text-left"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  openDrawingPreview();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openDrawingPreview();
                  }
                }}
              >
                {isPdfDrawing(selected) ? <PdfPreview src={previewSrc} className="h-[210px]" /> : <img className="block w-full rounded-[6px] object-contain" src={previewSrc} />}
                <span className="absolute inset-0 hidden items-center justify-center bg-black/18 group-hover:flex"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/92 text-[#171719] shadow-[0_8px_24px_rgba(0,0,0,0.18)]"><EyeViewIcon /></span></span>
              </div>
              <h2 className="mt-4 break-all text-[20px] font-bold leading-[28px]">{displayDrawingName(detailName)}</h2>
              <p className="mt-1 text-[12px] text-[#9a9ea7]">上传时间 <span className="float-right">{formatDrawingTime(selected.created_at)}</span></p>
              <b className="mt-4 block text-[12px] text-[#9a9ea7]">图纸类型</b>
              <DrawingTypeSelect value={selected.drawing_type ?? "site"} onChange={(value) => void updateSelectedDrawing({ drawing_type: value })} />
              <b className="mt-3 block text-[12px] text-[#9a9ea7]">图纸说明</b>
              <label className="relative mt-2 block h-[112px] rounded-[12px] border border-[#e8ebef] bg-white px-3 py-[11px] text-[14px] leading-5 text-[#171719]">
                <textarea value={drawingDescription} maxLength={200} placeholder="添加图纸说明信息" onChange={(event) => setDrawingDescription(event.target.value)} onBlur={() => void saveDrawingDescription()} className="drawing-description-input h-[82px] w-full resize-none border-0 bg-transparent p-0 text-[14px] font-normal leading-5 text-[#171719] outline-none placeholder:text-[#9a9ea7]" />
                <span className="absolute bottom-2 right-3 text-[11px] leading-4 text-[#9a9ea7]">{drawingDescription.length}/200</span>
              </label>
              <div className="mt-4 flex justify-start gap-4 pb-3"><Button kind="white" className="report-top-action-button h-10 w-[118px] px-2" onClick={() => replaceInputRef.current?.click()}>重新选择</Button><Button kind="white" className="report-top-action-button h-10 w-[92px] px-2" onClick={() => drawings[selectedIndex - 1] && selectDrawing(drawings[selectedIndex - 1].id)}>上一张</Button><Button kind="white" className="report-top-action-button h-10 w-[92px] px-2" onClick={() => drawings[selectedIndex + 1] && selectDrawing(drawings[selectedIndex + 1].id)}>下一张</Button></div>
            </>
            ) : null}
          </div>
        ) : (
          <div className="absolute left-0 right-0 top-[75px] flex h-[492px] items-center justify-center px-8 text-center text-[13px] leading-5 text-[#9a9ea7]">
            上传后这里可以查看图纸详情。
          </div>
        )}
      </Card>
      {previewTarget && <DrawingPreviewOverlay src={previewTarget.src} alt={previewTarget.alt} pdf={previewTarget.pdf} onClose={() => setPreviewTarget(null)} />}
      {deleteBatchOpen && <TaskbookDeleteCard fileName={`选中的 ${checkedDrawingIds.length} 张图纸`} onClose={() => setDeleteBatchOpen(false)} onConfirm={async () => {
        await deleteDrawingIds(checkedDrawingIds);
        setCheckedDrawingIds([]);
        setBatchEditing(false);
        setDeleteBatchOpen(false);
      }} />}
      {error && <FlowErrorCard message={error} onClose={() => setError("")} />}
    </FlowShell>
  );
}

// 渲染上传图纸卡片。
function DrawingCard({ name, index, drawing, selected = index === 0, editing = false, checked = false, uploading = false, onClick }: { name: string; index: number; drawing?: DrawingFile; selected?: boolean; editing?: boolean; checked?: boolean; uploading?: boolean; onCheck?: () => void; onClick?: () => void }) {
  const label = drawing ? drawingTypeLabel(drawing.drawing_type) : "待上传";
  const mutedForBatch = editing && !checked;
  return (
    <article onClick={onClick} className={`relative h-[220px] cursor-pointer rounded-[12px] border p-[13px] transition-all ${selected ? "border-[#6c4dff] bg-[#f4f0ff] shadow-[0_10px_22px_rgba(108,77,255,0.12)]" : "border-[#e8ebef] bg-white hover:border-[#cfd5de]"} ${mutedForBatch ? "opacity-45 grayscale" : "opacity-100 grayscale-0"}`}>
      {editing && <span className={`absolute left-[9px] top-[9px] z-10 flex h-3 w-3 items-center justify-center rounded-[3px] border text-[9px] ${checked ? "border-[#171719] bg-[#171719] text-white" : "border-[#171719] bg-white"}`}>{checked ? "✓" : ""}</span>}
      {uploading ? <UploadPendingPreview className="mt-[14px] h-[116px]" compact /> : drawing ? (isPdfDrawing(drawing) ? <PdfPreview src={apiUrl(drawing.file_url)} className="mt-[14px] h-[116px]" compact /> : <img className="mt-[14px] h-[116px] w-full rounded-[12px] object-cover" src={apiUrl(drawing.file_url)} />) : <UploadPendingPreview className="mt-[14px] h-[116px]" compact />}
      <div className="mt-2 flex min-w-0 items-center justify-between gap-2"><b className="min-w-0 flex-1 truncate text-[14px]" title={name}>{displayDrawingName(name)}</b><span className="max-w-[92px] shrink-0 truncate rounded-full bg-[#171719] px-3 py-1 text-[10px] font-bold text-white" title={label}>{label}</span></div>
      <p className={`mt-2 border-t border-[#e8ebef] pt-2 text-[12px] ${uploading ? "text-[#6c4dff]" : drawing ? "text-[#22c55e]" : "text-[#9a9ea7]"}`}>{uploading ? <>正在上传中<LoadingDots /></> : drawing ? "上传成功" : "等待上传"}</p>
    </article>
  );
}

// 渲染 PDF 图纸内容预览。
function PdfPreview({ src, className = "", compact = false }: { src?: string; className?: string; compact?: boolean }) {
  if (!src) return <div className={`flex w-full items-center justify-center rounded-[12px] border border-[#e8ebef] bg-[#f7f8fa] ${className}`}><div className="text-center"><span className={`mx-auto flex items-center justify-center rounded-[10px] bg-[#171719] font-bold text-white ${compact ? "h-9 w-9 text-[11px]" : "h-12 w-12 text-[13px]"}`}>PDF</span><span className={`mt-2 block text-[#9a9ea7] ${compact ? "text-[10px]" : "text-[12px]"}`}>图纸文件</span></div></div>;
  return <div className={`flex w-full items-center justify-center rounded-[12px] border border-[#e8ebef] bg-[#f7f8fa] ${className}`}><div className="px-4 text-center"><span className={`mx-auto flex items-center justify-center rounded-[10px] bg-[#171719] font-bold text-white ${compact ? "h-9 w-9 text-[11px]" : "h-12 w-12 text-[13px]"}`}>PDF</span><span className={`mt-2 block text-[#9a9ea7] ${compact ? "text-[10px]" : "text-[12px]"}`}>{compact ? "重新上传生成预览" : "请重新上传 PDF 生成图片预览"}</span></div></div>;
}

// 渲染上传中省略号动效。
function LoadingDots() {
  return <span className="inline-flex w-5 align-baseline"><span className="upload-loading-dots">...</span></span>;
}

// 渲染图纸上传或替换时的等待占位。
function UploadPendingPreview({ className = "", compact = false }: { className?: string; compact?: boolean }) {
  return (
    <div className={`flex w-full items-center justify-center rounded-[12px] border border-[#e8ebef] bg-white ${className}`}>
      <span className={`font-bold text-[#9a9ea7] ${compact ? "text-[11px]" : "text-[13px]"}`}>图片正在赶来的路上</span>
    </div>
  );
}

// 渲染图纸类型选择栏。
function DrawingTypeSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [showFloorOptions, setShowFloorOptions] = useState(false);
  const options = showFloorOptions ? floorPlanOptions : drawingTypeOptions;
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
      setShowFloorOptions(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const handleOptionClick = (optionValue: string) => {
    if (optionValue === "floor-plan") {
      setShowFloorOptions(true);
      return;
    }
    onChange(optionValue);
    setOpen(false);
    setShowFloorOptions(false);
  };
  return (
    <div ref={menuRef} className="relative mt-2">
      <button type="button" className={`confirm-model-button h-10 w-full rounded-[12px] border bg-white px-3 text-left ${open ? "border-[#6c4dff]" : "border-[#e8ebef]"}`} onClick={() => setOpen((current) => !current)}>
        <span className="min-w-0 flex-1 truncate">{drawingTypeLabel(value)}</span>
        <span className="ml-2 text-[10px] text-[#171719]">▼</span>
      </button>
      {open && (
        <div className="flow-popover absolute left-0 right-0 top-[44px] z-20 rounded-[14px] border border-[#e8ebef] bg-white p-1 shadow-[0_14px_34px_rgba(17,19,24,0.14)]">
          {showFloorOptions && <button type="button" className="confirm-model-option mb-1 h-8 w-full rounded-[10px] px-3 text-left text-[#9a9ea7] hover:bg-[#f7f8fa]" onClick={() => setShowFloorOptions(false)}>返回图纸类型</button>}
          {options.map((option) => (
            <button key={option.value} type="button" className={`confirm-model-option h-9 w-full rounded-[10px] px-3 text-left ${option.value === value ? "bg-[#f1f2f4] text-[#171719]" : "text-[#171719] hover:bg-[#f7f8fa]"}`} onClick={() => handleOptionClick(option.value)}>
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// 渲染图纸大图预览遮罩。
function DrawingPreviewOverlay({ src, alt, pdf = false, onClose }: { src: string; alt: string; pdf?: boolean; onClose: () => void }) {
  if (typeof document === "undefined") return null;
  const overlay = !pdf ? (
    <div className="fixed inset-0 z-[1000] overflow-hidden bg-black/55">
      <ZoomableImageStage src={src} alt={alt} onClose={onClose} />
    </div>
  ) : (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/55 p-8" onClick={onClose}>
      <div className="max-h-[88vh] max-w-[88vw] overflow-hidden rounded-[12px] bg-white p-3 shadow-[0_24px_80px_rgba(0,0,0,0.3)]" onClick={(event) => event.stopPropagation()}>
        <PdfPreview src={src} className="h-[360px] w-[520px]" />
      </div>
    </div>
  );
  return createPortal(overlay, document.body);
}

// 渲染图片查看图标。
function EyeViewIcon() {
  return <svg viewBox="0 0 24 24" className="h-6 w-6 fill-none stroke-current stroke-[1.8]" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" /><circle cx="12" cy="12" r="3" /></svg>;
}

// 把楼层数字转换为中文楼层。
function floorText(floor: number): string {
  return ["零", "一", "二", "三", "四", "五", "六", "七"][floor] ?? String(floor);
}

// 去掉图纸文件名后缀，只保留用户可读名称。
function displayDrawingName(name: string): string {
  return name.replace(/\.[^.\\/]+$/, "");
}

// 格式化后端返回的真实上传时间。
function formatDrawingTime(value?: string | null): string {
  if (!value) return "未记录";
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "未记录";
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

// 判断当前图纸是否是 PDF。
function isPdfDrawing(drawing: DrawingFile): boolean {
  return drawing.mime_type === "application/pdf";
}

// 把后端图纸类型转换为页面展示文字。
function drawingTypeLabel(type: string): string {
  const floorMatch = /^plan-(\d+)$/.exec(type);
  if (floorMatch) return `${floorText(Number(floorMatch[1]))}层平面图`;
  return { site: "总平面图", plan: "首层平面图", section: "剖面图", elevation: "立面图", analysis: "分析图", render: "效果图" }[type] ?? "待识别";
}

// 渲染提交确认页。
