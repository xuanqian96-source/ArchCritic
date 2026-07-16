// 侧栏子组件：项目菜单、版本菜单和退出确认等轻量视图。
import { useState } from "react";
import type { PageProps, Route } from "../App";
import { getProjectVersionLabel, type ProjectVersion } from "../state/projectGroups";
import { ChevronIcon, HomeIcon, LibraryIcon } from "./accountComponents";

export interface ConfirmAction {
  title: string;
  message: string;
  confirmText: string;
  onConfirm: () => Promise<void>;
}

// 弹出侧栏菜单后把它滚动到可视区域内。
export function revealSidebarPopup(row: HTMLElement | null) {
  if (!row) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const popup = row.querySelector("[data-sidebar-popup]") as HTMLElement | null;
      (popup ?? row).scrollIntoView({ block: "nearest" });
    });
  });
}

export function ArchCriticLogo({ go }: Pick<PageProps, "go">) {
  return (
    <button type="button" className="absolute left-[21px] top-[22px] flex h-[30px] w-[150px] items-center bg-white" aria-label="返回 ArchCritic 首页" onClick={() => go("landing")}>
      <img
        alt="ArchCritic"
        className="h-[30px] w-[150px] object-cover object-center"
        src="/assets/v1/archcritic-logo.png"
      />
    </button>
  );
}

// 渲染侧栏导航项。
export function NavItem({ text, icon, active, onClick }: { text: string; icon: "home" | "library"; active?: boolean; onClick?: () => void }) {
  return (
    <button
      className={`relative mb-2 ml-[21px] block h-[38px] w-[204px] rounded-[14px] text-left ${active ? "bg-[#e8ebef] font-bold text-[#171719]" : "text-[#53565e]"}`}
      onClick={onClick}
    >
      <span className={`absolute left-[12px] top-[10px] ${active ? "text-[#6c4dff]" : "text-[#9a9ea7]"}`}>
        {icon === "home" ? <HomeIcon /> : <LibraryIcon />}
      </span>
      <span className={`sidebar-primary-text absolute left-[34px] top-[8px] ${active ? "font-bold" : "font-medium"}`}>{text}</span>
    </button>
  );
}

// 把项目日期显示为侧栏中的简短形式。
export function formatSidebarDate(date?: string | null) {
  return date?.slice(0, 10).replace(/-/g, "/") ?? "最近编辑";
}

// 渲染项目右侧三点菜单。
export function ProjectManageMenu({ pinned, onTogglePin, onRename, onDelete }: { pinned: boolean; onTogglePin: () => void; onRename: () => void; onDelete: () => void }) {
  return (
    <section data-sidebar-popup data-sidebar-menu className="figma-shadow relative z-30 ml-auto mt-1 w-[116px] rounded-[10px] border border-[#e8ebef] bg-white p-1">
      <SidebarMenuItem icon="pin" text={pinned ? "取消置顶" : "置顶项目"} onClick={onTogglePin} />
      <SidebarMenuItem icon="edit" text="重命名" onClick={onRename} />
      <SidebarMenuItem icon="trash" text="删除项目" danger onClick={onDelete} />
    </section>
  );
}

// 渲染项目版本列表，点击版本可进入对应报告。
export function ProjectVersionMenu({
  versions,
  activeSubmissionId,
  manageVersionId,
  editingVersionId,
  editingVersionName,
  onEditingVersionName,
  onOpenVersion,
  onManageVersion,
  onRenameVersion,
  onCommitRenameVersion,
  onCancelRenameVersion,
  onDeleteVersion,
  batchEditing,
  checkedVersionIds,
  onToggleCheckedVersion,
  onStartBatchEdit,
}: {
  versions: ProjectVersion[];
  activeSubmissionId?: number;
  manageVersionId: number | null;
  editingVersionId: number | null;
  editingVersionName: string;
  onEditingVersionName: (name: string) => void;
  onOpenVersion: (version: ProjectVersion) => void;
  onManageVersion: (submissionId: number) => void;
  onRenameVersion: (version: ProjectVersion) => void;
  onCommitRenameVersion: (version: ProjectVersion) => void;
  onCancelRenameVersion: () => void;
  onDeleteVersion: (version: ProjectVersion) => void;
  batchEditing: boolean;
  checkedVersionIds: number[];
  onToggleCheckedVersion: (submissionId: number) => void;
  onStartBatchEdit: () => void;
}) {
  if (!versions.length) return <section data-sidebar-popup className="relative z-30 mt-1 px-[14px] py-2 text-[11px] text-[#9a9ea7]">暂无历史版本</section>;
  return (
    <section data-sidebar-popup data-sidebar-version-list className="relative z-30 mt-1 w-[204px]">
      {versions.map((version) => {
        const editingThisVersion = editingVersionId === version.submission.id;
        const checked = checkedVersionIds.includes(version.submission.id);
        const mutedForBatch = batchEditing && !checked;
        return (
          <div className="group relative" data-sidebar-version-row key={version.submission.id}>
            {editingThisVersion ? (
              <div className="grid h-8 w-full grid-cols-[minmax(0,1fr)_42px] items-center gap-2 rounded-[8px] px-[14px] pr-8 text-left">
                <input
                  autoFocus
                  className="sidebar-version-name-text min-w-0 truncate bg-transparent p-0 outline-none"
                  value={editingVersionName}
                  onFocus={(event) => {
                    const input = event.currentTarget;
                    requestAnimationFrame(() => input.setSelectionRange(input.value.length, input.value.length));
                  }}
                  onChange={(event) => onEditingVersionName(event.target.value)}
                  onBlur={() => onCommitRenameVersion(version)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") onCommitRenameVersion(version);
                    if (event.key === "Escape") onCancelRenameVersion();
                  }}
                />
                <span className="text-right text-[11px] font-semibold leading-4 text-[#9ca3af]">{version.history?.overall_score == null ? "草稿" : `${Math.round(version.history.overall_score)}分`}</span>
              </div>
            ) : (
              <button type="button" className={`grid h-8 w-full items-center gap-2 rounded-[8px] px-[14px] text-left transition-opacity ${version.submission.id === activeSubmissionId ? "bg-[#eef0f4]" : "hover:bg-[#eef0f4]"} ${batchEditing ? "grid-cols-[minmax(0,1fr)_42px_18px] pr-2" : "grid-cols-[minmax(0,1fr)_42px] pr-8"} ${mutedForBatch ? "opacity-45" : "opacity-100"}`} onClick={() => batchEditing ? onToggleCheckedVersion(version.submission.id) : onOpenVersion(version)}>
                <span className={`sidebar-version-name-text truncate ${version.submission.id === activeSubmissionId ? "sidebar-selected-version-text" : ""}`}>{getProjectVersionLabel(version)}</span>
                <span className={`text-right text-[11px] leading-4 text-[#9ca3af] ${version.submission.id === activeSubmissionId ? "font-bold" : "font-semibold"}`}>{version.history?.overall_score == null ? "草稿" : `${Math.round(version.history.overall_score)}分`}</span>
                {batchEditing && <VersionCheckBox checked={checked} />}
              </button>
            )}
            {!batchEditing && <button
              type="button"
              data-sidebar-menu-trigger
              aria-label={`管理${getProjectVersionLabel(version)}`}
              className="absolute right-0 top-1 flex h-6 w-6 items-center justify-center rounded-full opacity-0 hover:bg-white group-hover:opacity-100"
              onClick={(event) => {
                const row = event.currentTarget.closest("[data-sidebar-version-row]") as HTMLElement | null;
                onManageVersion(version.submission.id);
                revealSidebarPopup(row);
              }}
            >
              <DotsIcon />
            </button>}
            {manageVersionId === version.submission.id && (
              <section data-sidebar-popup data-sidebar-menu className="figma-shadow relative z-40 ml-auto mt-1 w-[96px] rounded-[10px] border border-[#e8ebef] bg-white p-1">
                <SidebarMenuItem icon="edit" text="重命名" onClick={() => onRenameVersion(version)} />
                <SidebarMenuItem icon="batchEdit" text="批量编辑" onClick={onStartBatchEdit} />
                <SidebarMenuItem icon="trash" text="删除版本" danger onClick={() => onDeleteVersion(version)} />
              </section>
            )}
          </div>
        );
      })}
    </section>
  );
}

// 渲染批量编辑时的勾选框。
export function VersionCheckBox({ checked }: { checked: boolean }) {
  return (
    <span className={`flex h-[14px] w-[14px] items-center justify-center rounded-[3px] border ${checked ? "border-[#171719] bg-[#171719]" : "border-[#9a9ea7] bg-white"}`}>
      {checked && <span className="h-[5px] w-[8px] -rotate-45 border-b-2 border-l-2 border-white" />}
    </span>
  );
}

export type SidebarMenuIcon = "pin" | "edit" | "batchEdit" | "trash";

// 渲染侧栏管理菜单中的一行。
export function SidebarMenuItem({ icon, text, danger = false, onClick }: { icon: SidebarMenuIcon; text: string; danger?: boolean; onClick: () => void }) {
  return <button type="button" className={`sidebar-menu-text flex h-7 w-full items-center rounded-[8px] px-2 text-left hover:bg-[#f7f8fa] ${danger ? "text-[#dc2626]" : "text-[#111318]"}`} onClick={onClick}><SidebarMenuIconView icon={icon} /><span className="ml-[7px] min-w-0 flex-1 whitespace-nowrap">{text}</span></button>;
}

// 渲染项目菜单图标。
export function SidebarMenuIconView({ icon }: { icon: SidebarMenuIcon }) {
  if (icon === "pin") return <span className="relative inline-flex h-4 w-4 flex-none items-center justify-center"><span className="absolute left-[3px] top-[3px] h-[6px] w-[9px] rounded-[2px] bg-current" /><span className="absolute left-[7px] top-[8px] h-[8px] w-0.5 rounded-full bg-current" /></span>;
  if (icon === "edit") return <span className="inline-flex h-4 w-4 flex-none items-center justify-center"><span className="h-[3px] w-[14px] rotate-[25deg] rounded-full bg-current" /></span>;
  if (icon === "batchEdit") return <span className="inline-flex h-4 w-4 flex-none items-center justify-center"><svg viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current stroke-[2]"><path d="M5 14.5 6 11l7.4-7.4a1.4 1.4 0 0 1 2 0l1 1a1.4 1.4 0 0 1 0 2L9 14l-3.6 1z" /><path d="m12.3 4.7 3 3" /></svg></span>;
  return <span className="relative inline-flex h-4 w-4 flex-none items-center justify-center"><span className="absolute left-[3px] top-[6px] h-[10px] w-[10px] rounded-[2px] border-[1.5px] border-current" /><span className="absolute left-[3px] top-[2px] h-0.5 w-[10px] rounded-full bg-current" /></span>;
}

// 渲染项目操作入口中的三点按钮。
export function DotsIcon() {
  return <span className="flex gap-[3px]">{[0, 1, 2].map((item) => <span className="h-[3px] w-[3px] rounded-full bg-[#6b7280]" key={item} />)}</span>;
}

// 渲染项目已置顶标记。
export function PinMarkIcon({ className = "" }: { className?: string }) {
  return (
    <span className={`text-[#6b7280] ${className}`}>
      <svg viewBox="0 0 18 18" className="h-3 w-3 fill-current">
        <path d="M5 2h8v2l-2 1.8V9l2 2v1H9.8V16H8.2v-4H4v-1l2-2V5.8L4 4V2h1z" />
      </svg>
    </span>
  );
}

// 渲染项目或版本删除确认卡片，不使用浏览器系统弹窗。
export function ConfirmCard({ action, onClose }: { action: ConfirmAction; onClose: () => void }) {
  const [submitting, setSubmitting] = useState(false);

  // 确认后执行真实删除，并关闭卡片。
  const confirm = async () => {
    setSubmitting(true);
    try {
      await action.onConfirm();
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="absolute inset-0 z-[70] bg-white/70 backdrop-blur-[2px]" onClick={onClose} />
      <section className="figma-shadow font-chat absolute left-[472px] top-[270px] z-[80] h-[226px] w-[592px] rounded-[20px] border border-[#d9dde3] bg-white p-7">
        <h2 className="text-[24px] font-medium leading-8">{action.title}</h2>
        <p className="mt-6 text-[16px] leading-6 text-[#171719]">{action.message}</p>
        <p className="mt-4 text-[14px] leading-5 text-[#9a9ea7]">删除后，该项目或版本的历史记录将无法恢复。</p>
        <div className="absolute bottom-6 right-7 flex gap-4">
          <button type="button" className="h-11 w-[92px] rounded-[22px] border border-[#d9dde3] bg-white text-[15px] font-medium text-[#171719]" onClick={onClose}>取消</button>
          <button type="button" disabled={submitting} className="h-11 w-[126px] rounded-[22px] bg-[#171719] text-[15px] font-medium text-white disabled:opacity-60" onClick={() => void confirm()}>{submitting ? "删除中" : action.confirmText}</button>
        </div>
      </section>
    </>
  );
}

// 渲染新建流程未保存时的返回首页提示。
export function DraftExitCard({ onClose, onSave, onDiscard }: { onClose: () => void; onSave: () => Promise<void> | void; onDiscard: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // 保存失败时把原因显示出来，避免页面静默停住。
  const save = async () => {
    setSubmitting(true);
    setError("");
    try {
      await onSave();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "草稿保存失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="absolute inset-0 z-[70] bg-[#171719]/30" onClick={onClose} />
      <section className="figma-shadow font-chat absolute left-[472px] top-[270px] z-[80] h-[238px] w-[592px] rounded-[20px] border border-[#d9dde3] bg-white p-7">
        <h2 className="text-[24px] font-bold leading-8">草稿尚未保存</h2>
        <p className="mt-6 text-[16px] leading-6 text-[#171719]">当前新建评图还没有保存草稿。返回首页前，可以先保存当前填写内容。</p>
        {error && <p className="mt-4 text-[13px] font-bold leading-5 text-[#ef4444]">{error}</p>}
        <div className="absolute bottom-6 right-7 flex gap-4">
          <button type="button" disabled={submitting} className="app-action-button h-10 w-[82px] rounded-[12px] border border-[#d9dde3] bg-white text-[#171719] disabled:opacity-60" onClick={onClose}>取消</button>
          <button type="button" disabled={submitting} className="app-action-button h-10 w-[112px] rounded-[12px] border border-[#d9dde3] bg-white text-[#171719] disabled:opacity-60" onClick={onDiscard}>不保存</button>
          <button type="button" disabled={submitting} className="app-action-button h-10 w-[124px] rounded-[12px] bg-[#6c4dff] text-white disabled:opacity-60" onClick={() => void save()}>{submitting ? "保存中" : "保存并退出"}</button>
        </div>
      </section>
    </>
  );
}

// 渲染流程操作失败提示卡片。
