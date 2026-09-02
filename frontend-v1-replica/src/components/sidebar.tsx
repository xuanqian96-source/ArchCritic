// 工作区侧栏：组织用户项目、历史版本、草稿离开和账户入口。
import { useEffect, useRef, useState } from "react";
import type { PageProps, Route } from "../App";
import { deleteProject, updateProject } from "../api/projects";
import { deleteSubmission, updateSubmission } from "../api/submissions";
import { readSubmissionRoute, rememberSubmissionRoute } from "../state/flowRoutes";
import { useProfile } from "../state/profile";
import { useAuth } from "../state/auth";
import { consumeOnboardingTour, queueOnboardingTour } from "../state/onboarding";
import { getCachedProjectGroups, getLatestVersion, getProjectVersionLabel, isProjectGroupPinned, loadProjectGroups, readPinnedProjectIds, sortPinnedProjectGroups, type ProjectGroup, type ProjectVersion, writePinnedProjectIds } from "../state/projectGroups";
import { useWorkspace } from "../state/workspace";
import { AccountMenu, ChevronIcon, ProfileAvatar, ProfileModal } from "./accountComponents";
import { FeedbackModal, HelpMenu, InformationListModal, LogoutConfirmModal, OnboardingTour } from "./helpComponents";
import { ArchCriticLogo, ConfirmCard, DotsIcon, DraftExitCard, formatSidebarDate, NavItem, PinMarkIcon, ProjectManageMenu, ProjectVersionMenu, revealSidebarPopup, SidebarMenuIconView, type ConfirmAction } from "./sidebarParts";
import { guideItems } from "../data/helpContent";

export function Sidebar({ go, creating = false }: Pick<PageProps, "go"> & { creating?: boolean; projectName?: string }) {
  const { draftDirty, projects: savedProjects, project: activeProject, submission: activeSubmission, openProject, openSubmission, prefetchSubmission, refreshProjects, resetDraft, saveDraft, setNotice, syncProjectName, syncSubmissionTitle } = useWorkspace();
  const { profile } = useProfile();
  const { logout } = useAuth();
  const sidebarRef = useRef<HTMLElement>(null);
  const helpCloseTimer = useRef<number | null>(null);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [accountOpen, setAccountOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [profileEditing, setProfileEditing] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [faqOpen, setFaqOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [logoutMessage, setLogoutMessage] = useState("");
  const [projectGroups, setProjectGroups] = useState<ProjectGroup[]>(() => getCachedProjectGroups(savedProjects));
  const [versionProjectKey, setVersionProjectKey] = useState<string | null>(null);
  const [manageProjectKey, setManageProjectKey] = useState<string | null>(null);
  const [manageVersionId, setManageVersionId] = useState<number | null>(null);
  const [pinnedProjectIds, setPinnedProjectIds] = useState<number[]>(() => readPinnedProjectIds());
  const [editingProjectKey, setEditingProjectKey] = useState<string | null>(null);
  const [editingProjectName, setEditingProjectName] = useState("");
  const [editingVersionId, setEditingVersionId] = useState<number | null>(null);
  const [editingVersionName, setEditingVersionName] = useState("");
  const [batchEditProjectKey, setBatchEditProjectKey] = useState<string | null>(null);
  const [checkedVersionIds, setCheckedVersionIds] = useState<number[]>([]);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [exitPromptOpen, setExitPromptOpen] = useState(false);
  const visibleProjects = sortPinnedProjectGroups(projectGroups, pinnedProjectIds).slice(0, 12);
  const currentRoute = window.location.hash.replace("#/", "");

  useEffect(() => {
    let mounted = true;
    setProjectGroups(getCachedProjectGroups(savedProjects));
    void loadProjectGroups(savedProjects).then((groups) => mounted && setProjectGroups(groups));
    return () => { mounted = false; };
  }, [savedProjects]);

  useEffect(() => {
    visibleProjects.forEach((group) => {
      const latest = getLatestVersion(group);
      if (latest) prefetchSubmission(latest.submission.id, { project: latest.project, submission: latest.submission });
    });
  }, [prefetchSubmission, visibleProjects]);

  // 收起全部项目弹出卡片。
  const closeProjectMenus = () => {
    setManageProjectKey(null);
    setManageVersionId(null);
  };

  // 退出批量编辑版本状态。
  const closeBatchEdit = () => {
    setBatchEditProjectKey(null);
    setCheckedVersionIds([]);
  };

  useEffect(() => {
    if (!manageProjectKey && !manageVersionId) return;
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-sidebar-menu]") || target.closest("[data-sidebar-menu-trigger]")) return;
      setManageProjectKey(null);
      setManageVersionId(null);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [manageProjectKey, manageVersionId]);

  useEffect(() => {
    if (!batchEditProjectKey) return;
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-sidebar-version-row]") || target.closest("[data-sidebar-batch-action]")) return;
      closeBatchEdit();
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [batchEditProjectKey]);

  useEffect(() => {
    if (!consumeOnboardingTour()) return;
    setTourOpen(true);
  }, []);

  useEffect(() => () => {
    if (helpCloseTimer.current != null) window.clearTimeout(helpCloseTimer.current);
  }, []);

  useEffect(() => {
    if (!accountOpen) return;
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-account-menu]") || target.closest("[data-account-trigger]")) return;
      setAccountOpen(false);
      setHelpOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [accountOpen]);

  // 悬停帮助区域时展开二级菜单，短延迟让鼠标能平稳移入右侧卡片。
  const keepHelpOpen = () => {
    if (helpCloseTimer.current != null) window.clearTimeout(helpCloseTimer.current);
    helpCloseTimer.current = null;
    setHelpOpen(true);
  };

  // 鼠标离开帮助入口和二级菜单后自动收起。
  const scheduleHelpClose = () => {
    if (helpCloseTimer.current != null) window.clearTimeout(helpCloseTimer.current);
    helpCloseTimer.current = window.setTimeout(() => {
      setHelpOpen(false);
      helpCloseTimer.current = null;
    }, 90);
  };

  // 新手指引统一从首页开始，确保所有高亮区域可见。
  const startTour = () => {
    setAccountOpen(false);
    setHelpOpen(false);
    if (currentRoute === "dashboard") {
      setTourOpen(true);
      return;
    }
    queueOnboardingTour();
    go("dashboard");
  };

  // 完成后端退出并清理当前工作区。
  const confirmLogout = async () => {
    setLogoutBusy(true);
    setLogoutMessage("");
    try {
      await logout();
      resetDraft();
      go("auth");
    } catch (error) {
      setLogoutMessage(error instanceof Error ? error.message : "退出失败，请稍后重试。");
      setLogoutBusy(false);
    }
  };

  // 打开项目的最近版本，并进入对应页面。
  const openLatestProject = async (group: ProjectGroup) => {
    closeProjectMenus();
    const latest = getLatestVersion(group);
    if (!latest) {
      await openProject(group.latestProject.id, group.latestProject);
      go("info");
      return;
    }
    await openSubmission(latest.submission.id, { project: latest.project, submission: latest.submission });
    if (latest.submission.status === "evaluating") go("processing");
    else if (latest.history?.overall_score != null || latest.submission.status === "completed") go("report");
    else go(readSubmissionRoute(latest.submission.id, "info"));
  };

  // 打开指定历史版本报告。
  const openVersion = async (version: ProjectVersion) => {
    closeProjectMenus();
    await openSubmission(version.submission.id, { project: version.project, submission: version.submission });
    if (version.submission.status === "evaluating") go("processing");
    else if (version.history?.overall_score != null || version.submission.status === "completed") go("report");
    else go(readSubmissionRoute(version.submission.id, "info"));
  };

  // 显示操作结果，并关闭项目管理菜单。
  const showActionMessage = (message: string) => {
    closeProjectMenus();
    setNotice(message);
  };

  // 置顶或取消置顶同名项目组。
  const togglePinProject = (group: ProjectGroup) => {
    const groupIds = group.projects.map((project) => project.id);
    const pinned = isProjectGroupPinned(group, pinnedProjectIds);
    const nextIds = pinned
      ? pinnedProjectIds.filter((id) => !groupIds.includes(id))
      : [...groupIds, ...pinnedProjectIds.filter((id) => !groupIds.includes(id))];
    setPinnedProjectIds(nextIds);
    writePinnedProjectIds(nextIds);
    showActionMessage(pinned ? "已取消置顶。" : "项目已置顶。");
  };

  // 进入项目名称编辑状态。
  const startRenameProject = (group: ProjectGroup) => {
    closeProjectMenus();
    setEditingProjectKey(group.key);
    setEditingProjectName(group.name);
  };

  // 保存项目组新名称。
  const commitRenameProject = async (group: ProjectGroup) => {
    const name = editingProjectName.trim();
    setEditingProjectKey(null);
    if (!name || name === group.name) return;
    const groupIds = group.projects.map((project) => project.id);
    setProjectGroups((current) => current.map((item) => item.key === group.key ? { ...item, key: name, name } : item));
    await Promise.all(group.projects.map((project) => updateProject(project.id, { name })));
    syncProjectName(groupIds, name);
    await refreshProjects();
    showActionMessage("项目已重命名。");
  };

  // 删除项目组下全部同名项目。
  const deleteProjectGroup = async (group: ProjectGroup) => {
    closeProjectMenus();
    setConfirmAction({
      title: "删除项目",
      message: `确定删除“${group.name}”及其全部版本吗？此操作不可恢复。`,
      confirmText: "确认删除",
      onConfirm: async () => {
        const groupIds = group.projects.map((project) => project.id);
        setProjectGroups((current) => current.filter((item) => item.key !== group.key));
        await Promise.all(group.projects.map((project) => deleteProject(project.id)));
        const nextPinnedIds = pinnedProjectIds.filter((id) => !groupIds.includes(id));
        setPinnedProjectIds(nextPinnedIds);
        writePinnedProjectIds(nextPinnedIds);
        if (activeProject && groupIds.includes(activeProject.id)) {
          resetDraft();
          go("dashboard");
        }
        await refreshProjects();
        showActionMessage("项目已删除。");
      },
    });
  };

  // 进入版本名称编辑状态。
  const startRenameVersion = (version: ProjectVersion) => {
    closeProjectMenus();
    closeBatchEdit();
    setEditingVersionId(version.submission.id);
    setEditingVersionName(getProjectVersionLabel(version));
  };

  // 保存版本新名称。
  const commitRenameVersion = async (version: ProjectVersion) => {
    const name = editingVersionName.trim();
    setEditingVersionId(null);
    if (!name || name === getProjectVersionLabel(version)) return;
    setProjectGroups((current) => current.map((group) => ({
      ...group,
      versions: group.versions.map((item) => item.submission.id === version.submission.id
        ? { ...item, submission: { ...item.submission, title: name } }
        : item),
    })));
    await updateSubmission(version.submission.id, { title: name });
    syncSubmissionTitle(version.submission.id, name);
    await refreshProjects();
    showActionMessage("版本已重命名。");
  };

  // 删除单个版本。
  const deleteVersion = async (version: ProjectVersion) => {
    closeProjectMenus();
    closeBatchEdit();
    setConfirmAction({
      title: "删除版本",
      message: `确定删除“${getProjectVersionLabel(version)}”吗？此操作不可恢复。`,
      confirmText: "确认删除",
      onConfirm: async () => {
        setProjectGroups((current) => current.map((group) => ({
          ...group,
          versions: group.versions.filter((item) => item.submission.id !== version.submission.id),
        })));
        await deleteSubmission(version.submission.id);
        if (activeSubmission?.id === version.submission.id) {
          resetDraft();
          go("dashboard");
        }
        await refreshProjects();
        showActionMessage("版本已删除。");
      },
    });
  };

  // 进入版本批量编辑状态。
  const startBatchEditVersions = (group: ProjectGroup) => {
    closeProjectMenus();
    setEditingVersionId(null);
    setVersionProjectKey(group.key);
    setBatchEditProjectKey(group.key);
    setCheckedVersionIds([]);
  };

  // 勾选或取消勾选一个版本。
  const toggleCheckedVersion = (submissionId: number) => {
    setCheckedVersionIds((current) => current.includes(submissionId)
      ? current.filter((id) => id !== submissionId)
      : [...current, submissionId]);
  };

  // 批量删除已勾选的版本。
  const deleteCheckedVersions = async (group: ProjectGroup) => {
    const ids = checkedVersionIds;
    if (!ids.length) return;
    setConfirmAction({
      title: "删除版本",
      message: `确定删除选中的 ${ids.length} 个版本吗？此操作不可恢复。`,
      confirmText: "确认删除",
      onConfirm: async () => {
        setProjectGroups((current) => current.map((item) => item.key === group.key
          ? { ...item, versions: item.versions.filter((version) => !ids.includes(version.submission.id)) }
          : item));
        await Promise.all(ids.map((id) => deleteSubmission(id)));
        if (activeSubmission && ids.includes(activeSubmission.id)) {
          resetDraft();
          go("dashboard");
        }
        closeBatchEdit();
        await refreshProjects();
        showActionMessage("已删除选中的版本。");
      },
    });
  };

  // 新建流程中返回首页：未保存时先提示用户选择保存或放弃。
  const leaveCreateFlow = () => {
    if (!creating) {
      go("create");
      return;
    }
    if (!draftDirty) {
      go("dashboard");
      return;
    }
    setExitPromptOpen(true);
  };

  const saveAndExit = async () => {
    const savedSubmission = await saveDraft();
    const currentRoute = window.location.hash.replace("#/", "") as Route;
    rememberSubmissionRoute(savedSubmission.id, currentRoute);
    setExitPromptOpen(false);
    go("dashboard");
  };

  const discardAndExit = () => {
    resetDraft();
    setExitPromptOpen(false);
    go("dashboard");
  };

  return (
    <>
    <aside ref={sidebarRef} className="font-chat sidebar-shadow panel absolute left-[23px] top-[11px] z-10 h-[796px] w-[248px] overflow-visible">
      <ArchCriticLogo go={go} />
      <button className="sidebar-primary-text absolute left-[21px] top-[75px] h-10 w-[204px] rounded-[16px] bg-[#171719] font-bold text-white" onClick={leaveCreateFlow}>
        {creating ? "返回首页" : "+ 新建评图"}
      </button>
      <div className="sidebar-scroll absolute bottom-[76px] left-0 right-[7px] top-[125px] overflow-y-auto pb-4">
        <NavItem text="首页" icon="home" active={currentRoute === "dashboard"} onClick={() => go("dashboard")} />
        <NavItem text="知识库" icon="library" active={currentRoute === "knowledge"} onClick={() => go("knowledge")} />
        <div className="group mb-2 ml-[21px] flex h-[38px] w-[204px] items-center">
          <b className="sidebar-primary-text ml-[14px] font-bold text-[#171719]">我的项目</b>
          <button
            type="button"
            aria-label={projectsExpanded ? "收起项目列表" : "展开项目列表"}
            className="ml-1 flex h-6 w-6 items-center justify-center opacity-0 transition-opacity group-hover:opacity-100"
            onClick={() => setProjectsExpanded((current) => !current)}
          >
            <ChevronIcon direction={projectsExpanded ? "down" : "right"} />
          </button>
        </div>
        {projectsExpanded && visibleProjects.map((group) => {
          const latest = getLatestVersion(group);
          const versions = [...group.versions].reverse();
          const hasVersionDropdown = versions.length > 1;
          const rowSelected = !["dashboard", "create", "knowledge"].includes(currentRoute) && group.projects.some((project) => project.id === activeProject?.id);
          const pinned = isProjectGroupPinned(group, pinnedProjectIds);
          const editingThisProject = editingProjectKey === group.key;
          const batchEditingThisProject = batchEditProjectKey === group.key;
          const checkedCount = batchEditingThisProject ? checkedVersionIds.length : 0;
          return (
            <div className="relative ml-[21px] mt-2 w-[204px]" data-sidebar-item key={group.key}>
              <div className={`group relative h-12 w-[204px] rounded-[14px] ${batchEditingThisProject ? "bg-transparent" : rowSelected ? "bg-[#eef0f4]" : "bg-transparent hover:bg-[#eef0f4]"}`}>
                {editingThisProject ? (
                  <div className="absolute inset-y-0 left-0 w-[142px] text-left">
                    <input
                      autoFocus
                      className={`sidebar-project-name-text absolute left-[14px] top-[8px] h-4 w-[118px] truncate bg-transparent p-0 outline-none ${rowSelected ? "font-bold" : "font-normal"}`}
                      value={editingProjectName}
                      onClick={(event) => event.stopPropagation()}
                      onFocus={(event) => {
                        const input = event.currentTarget;
                        requestAnimationFrame(() => input.setSelectionRange(input.value.length, input.value.length));
                      }}
                      onChange={(event) => setEditingProjectName(event.target.value)}
                      onBlur={() => void commitRenameProject(group)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void commitRenameProject(group);
                        if (event.key === "Escape") setEditingProjectKey(null);
                      }}
                    />
                    <span className="absolute left-[14px] top-[27px] text-[10px] leading-[13px] text-[#9a9ea7]">{formatSidebarDate(group.lastActivityAt)}</span>
                  </div>
                ) : (
                  <button type="button" className="absolute inset-y-0 left-0 w-[142px] text-left" onClick={() => batchEditingThisProject ? closeBatchEdit() : void openLatestProject(group)}>
                    <span className={`sidebar-project-name-text absolute left-[14px] top-[8px] max-w-[118px] truncate ${rowSelected ? "font-bold" : ""}`}>{group.name}</span>
                    <span className="absolute left-[14px] top-[27px] text-[10px] leading-[13px] text-[#9a9ea7]">{formatSidebarDate(group.lastActivityAt)}</span>
                  </button>
                )}
                {pinned && <PinMarkIcon className="absolute left-[1px] top-[10px]" />}
                {batchEditingThisProject ? (
                  checkedCount > 0 && (
                    <button
                      type="button"
                      data-sidebar-batch-action
                      className="sidebar-menu-text absolute right-0 top-[12px] flex h-6 items-center rounded-[8px] px-2 font-bold text-[#171719] hover:bg-[#eef0f4]"
                      onClick={() => void deleteCheckedVersions(group)}
                    >
                      <SidebarMenuIconView icon="trash" />
                      <span className="ml-[5px]">删除版本</span>
                    </button>
                  )
                ) : hasVersionDropdown ? (
                  <button
                    type="button"
                    data-sidebar-trigger
                    aria-label={`查看${group.name}版本`}
                    className={`absolute right-[26px] top-[14px] flex h-5 w-5 items-center justify-center rounded-full transition-opacity ${versionProjectKey === group.key ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                    onClick={(event) => {
                      const row = event.currentTarget.closest("[data-sidebar-item]") as HTMLElement | null;
                      const willOpen = versionProjectKey !== group.key;
                      closeBatchEdit();
                      setManageProjectKey(null);
                      setManageVersionId(null);
                      setVersionProjectKey(willOpen ? group.key : null);
                      if (willOpen) revealSidebarPopup(row);
                    }}
                  >
                    <ChevronIcon direction={versionProjectKey === group.key ? "down" : "right"} className="h-3 w-3" />
                  </button>
                ) : null}
                <button
                  type="button"
                  data-sidebar-menu-trigger
                  aria-label={`管理${group.name}`}
                  className={`absolute right-0 top-[12px] h-6 w-6 items-center justify-center rounded-full transition-opacity hover:bg-white ${batchEditingThisProject ? "hidden" : "flex"} ${manageProjectKey === group.key ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                  onClick={(event) => {
                    const row = event.currentTarget.closest("[data-sidebar-item]") as HTMLElement | null;
                    const willOpen = manageProjectKey !== group.key;
                    closeBatchEdit();
                    setVersionProjectKey(null);
                    setManageVersionId(null);
                    setManageProjectKey(willOpen ? group.key : null);
                    if (willOpen) revealSidebarPopup(row);
                  }}
                >
                  <DotsIcon />
                </button>
              </div>
              {hasVersionDropdown && versionProjectKey === group.key && (
                <ProjectVersionMenu
                  versions={versions}
                  activeSubmissionId={activeSubmission?.id}
                  manageVersionId={manageVersionId}
                  onOpenVersion={(version) => void openVersion(version)}
                  onManageVersion={(submissionId) => setManageVersionId((current) => current === submissionId ? null : submissionId)}
                  editingVersionId={editingVersionId}
                  editingVersionName={editingVersionName}
                  onEditingVersionName={setEditingVersionName}
                  onRenameVersion={startRenameVersion}
                  onCommitRenameVersion={(version) => void commitRenameVersion(version)}
                  onCancelRenameVersion={() => setEditingVersionId(null)}
                  onDeleteVersion={(version) => void deleteVersion(version)}
                  batchEditing={batchEditingThisProject}
                  checkedVersionIds={checkedVersionIds}
                  onToggleCheckedVersion={toggleCheckedVersion}
                  onStartBatchEdit={() => startBatchEditVersions(group)}
                />
              )}
              {manageProjectKey === group.key && (
                <ProjectManageMenu
                  pinned={pinned}
                  onTogglePin={() => togglePinProject(group)}
                  onRename={() => startRenameProject(group)}
                  onDelete={() => void deleteProjectGroup(group)}
                />
              )}
            </div>
          );
        })}
      </div>
      {accountOpen && <AccountMenu
        helpActive={helpOpen}
        onEditProfile={() => { setAccountOpen(false); setHelpOpen(false); setProfileEditing(true); }}
        onHelpEnter={keepHelpOpen}
        onHelpLeave={scheduleHelpClose}
        onLogout={() => { setAccountOpen(false); setHelpOpen(false); setLogoutMessage(""); setLogoutConfirmOpen(true); }}
      />}
      {accountOpen && helpOpen && <HelpMenu
        onMouseEnter={keepHelpOpen}
        onMouseLeave={scheduleHelpClose}
        onTour={startTour}
        onFaq={() => { setAccountOpen(false); setHelpOpen(false); setFaqOpen(true); }}
        onFeedback={() => { setAccountOpen(false); setHelpOpen(false); setFeedbackOpen(true); }}
      />}
      <button type="button" data-account-trigger className="absolute bottom-[12px] left-[21px] h-[52px] w-[204px] rounded-[16px] border border-[#e8ebef] bg-white/75 text-left" onClick={() => { setAccountOpen((current) => !current); setHelpOpen(false); }}>
        <ProfileAvatar profile={profile} className="absolute left-[11px] top-[11px] h-7 w-7 text-[13px]" />
        <b className="sidebar-primary-text absolute left-[51px] top-[7px] font-bold">{profile.displayName}</b>
        <span className="absolute left-[51px] top-[27px] text-[10px] leading-[13px] text-[#9a9ea7]">内测用户</span>
      </button>
    </aside>
    {profileEditing && <ProfileModal profile={profile} onClose={() => setProfileEditing(false)} />}
    {faqOpen && <InformationListModal title="操作指引与常见问题" items={guideItems} onClose={() => setFaqOpen(false)} />}
    {feedbackOpen && <FeedbackModal onClose={() => setFeedbackOpen(false)} onDone={() => { setFeedbackOpen(false); go("dashboard"); }} />}
    {logoutConfirmOpen && <LogoutConfirmModal busy={logoutBusy} message={logoutMessage} onCancel={() => !logoutBusy && setLogoutConfirmOpen(false)} onConfirm={() => void confirmLogout()} />}
    {tourOpen && <OnboardingTour onClose={() => setTourOpen(false)} />}
    {confirmAction && <ConfirmCard action={confirmAction} onClose={() => setConfirmAction(null)} />}
    {exitPromptOpen && <DraftExitCard onClose={() => setExitPromptOpen(false)} onSave={saveAndExit} onDiscard={discardAndExit} />}
    </>
  );
}

// 渲染左上角品牌字标。
