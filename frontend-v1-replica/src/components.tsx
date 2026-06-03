// 共用组件：承载设计稿中反复出现的画布、侧栏、步骤条、按钮和图纸缩略图。
import { useEffect, useRef, useState, type PropsWithChildren, type ReactNode } from "react";
import type { PageProps, Route } from "./App";
import { useProfile, type UserProfile } from "./state/profile";
import { getCachedProjectGroups, getLatestVersion, loadProjectGroups, type ProjectGroup, type ProjectVersion } from "./state/projectGroups";
import { useWorkspace } from "./state/workspace";

// 固定设计画布，并按浏览器空间等比缩放。
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
    <button type={type} disabled={disabled} className={`h-10 whitespace-nowrap rounded-[12px] px-5 text-[14px] font-bold disabled:cursor-not-allowed disabled:opacity-60 ${styles[kind]} ${className}`} onClick={onClick}>
      {children}
    </button>
  );
}

// 渲染工作区左侧栏，保持 Figma 中的固定尺寸和项目文本。
export function Sidebar({ go, creating = false }: Pick<PageProps, "go"> & { creating?: boolean; projectName?: string }) {
  const { projects: savedProjects, project: activeProject, submission: activeSubmission, openProject, openSubmission, setNotice } = useWorkspace();
  const { profile } = useProfile();
  const sidebarRef = useRef<HTMLElement>(null);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [accountOpen, setAccountOpen] = useState(false);
  const [profileEditing, setProfileEditing] = useState(false);
  const [projectGroups, setProjectGroups] = useState<ProjectGroup[]>(() => getCachedProjectGroups(savedProjects));
  const [versionProjectKey, setVersionProjectKey] = useState<string | null>(null);
  const [manageProjectKey, setManageProjectKey] = useState<string | null>(null);
  const [manageVersionId, setManageVersionId] = useState<number | null>(null);
  const visibleProjects = projectGroups.slice(0, 12);
  const currentRoute = window.location.hash.replace("#/", "");

  useEffect(() => {
    let mounted = true;
    setProjectGroups(getCachedProjectGroups(savedProjects));
    void loadProjectGroups(savedProjects).then((groups) => mounted && setProjectGroups(groups));
    return () => { mounted = false; };
  }, [savedProjects]);

  // 收起全部项目弹出卡片。
  const closeProjectMenus = () => {
    setVersionProjectKey(null);
    setManageProjectKey(null);
    setManageVersionId(null);
  };

  useEffect(() => {
    if (!versionProjectKey && !manageProjectKey && !manageVersionId) return;
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("[data-sidebar-popup]") || target.closest("[data-sidebar-trigger]")) return;
      closeProjectMenus();
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [versionProjectKey, manageProjectKey, manageVersionId]);

  // 打开项目的最近版本，并进入对应页面。
  const openLatestProject = async (group: ProjectGroup) => {
    closeProjectMenus();
    const latest = getLatestVersion(group);
    if (!latest) {
      await openProject(group.latestProject.id);
      go("confirm");
      return;
    }
    await openSubmission(latest.submission.id);
    if (latest.submission.status === "evaluating") go("processing");
    else if (latest.history?.overall_score != null || latest.submission.status === "completed") go("report");
    else go("confirm");
  };

  // 打开指定历史版本报告。
  const openVersion = async (version: ProjectVersion) => {
    closeProjectMenus();
    await openSubmission(version.submission.id);
    if (version.submission.status === "evaluating") go("processing");
    else if (version.history?.overall_score != null || version.submission.status === "completed") go("report");
    else go("confirm");
  };

  // 数据改写入口暂时只提示，避免未经确认修改数据库。
  const showProtectedAction = (message: string) => {
    closeProjectMenus();
    setNotice(message);
    window.alert(message);
  };

  return (
    <>
    <aside ref={sidebarRef} className="font-chat sidebar-shadow panel absolute left-[23px] top-[11px] z-10 h-[796px] w-[248px] overflow-visible">
      <div className="absolute left-[21px] top-[21px] flex h-8 w-8 items-center justify-center rounded-full bg-[#171719] text-[17px] font-bold text-white">A</div>
      <b className="absolute left-[65px] top-[24px] text-[16px] leading-[22px]">ArchCritic</b>
      <button className="absolute left-[21px] top-[75px] h-10 w-[204px] rounded-[16px] bg-[#171719] text-[13px] font-bold text-white" onClick={() => go("create")}>
        {creating ? "新建评图中" : "+ 新建评图"}
      </button>
      <div className="sidebar-scroll absolute bottom-[76px] left-0 right-[7px] top-[125px] overflow-y-scroll pb-4">
        <NavItem text="首页" icon="home" active={currentRoute === "dashboard" || currentRoute === "create"} onClick={() => go("dashboard")} />
        <NavItem text="知识库" icon="library" />
        <div className="group ml-[21px] mt-3 flex h-[38px] w-[204px] items-center">
          <b className="ml-[14px] text-[13px] leading-[18px] text-[#171719]">我的项目</b>
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
          const rowSelected = currentRoute !== "dashboard" && group.projects.some((project) => project.id === activeProject?.id);
          return (
            <div className="relative ml-[21px] mt-2 w-[204px]" key={group.key}>
              <div className={`group relative h-12 w-[204px] rounded-[14px] hover:bg-[#eef0f4] ${rowSelected ? "bg-[#eef0f4]" : "bg-transparent"}`}>
                <button type="button" className="absolute inset-y-0 left-0 w-[142px] text-left" onClick={() => void openLatestProject(group)}>
                  <span className={`absolute left-[14px] top-[8px] max-w-[118px] truncate text-[12px] leading-4 ${rowSelected ? "font-bold" : ""}`}>{group.name}</span>
                  <span className="absolute left-[14px] top-[27px] text-[10px] leading-[13px] text-[#9a9ea7]">{formatSidebarDate(latest?.submission.created_at ?? group.latestProject.created_at)}</span>
                </button>
                <button
                  type="button"
                  data-sidebar-trigger
                  aria-label={`查看${group.name}版本`}
                  className={`absolute right-[26px] top-[14px] flex h-5 w-5 items-center justify-center rounded-full transition-opacity ${versionProjectKey === group.key ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                  onClick={() => { setManageProjectKey(null); setManageVersionId(null); setVersionProjectKey((current) => current === group.key ? null : group.key); }}
                >
                  <ChevronIcon direction={versionProjectKey === group.key ? "down" : "right"} className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  data-sidebar-trigger
                  aria-label={`管理${group.name}`}
                  className={`absolute right-0 top-[12px] flex h-6 w-6 items-center justify-center rounded-full transition-opacity hover:bg-white ${manageProjectKey === group.key ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                  onClick={() => { setVersionProjectKey(null); setManageVersionId(null); setManageProjectKey((current) => current === group.key ? null : group.key); }}
                >
                  <DotsIcon />
                </button>
              </div>
              {versionProjectKey === group.key && (
                <ProjectVersionMenu
                  versions={versions}
                  activeSubmissionId={activeSubmission?.id}
                  manageVersionId={manageVersionId}
                  onOpenVersion={(version) => void openVersion(version)}
                  onManageVersion={(submissionId) => setManageVersionId((current) => current === submissionId ? null : submissionId)}
                  onProtectedAction={showProtectedAction}
                />
              )}
              {manageProjectKey === group.key && <ProjectManageMenu onProtectedAction={showProtectedAction} />}
            </div>
          );
        })}
      </div>
      {accountOpen && <AccountMenu profile={profile} onEditProfile={() => { setAccountOpen(false); setProfileEditing(true); }} />}
      <button type="button" className="absolute bottom-[12px] left-[21px] h-[52px] w-[204px] rounded-[16px] border border-[#e8ebef] bg-white/75 text-left" onClick={() => setAccountOpen((current) => !current)}>
        <ProfileAvatar profile={profile} className="absolute left-[11px] top-[11px] h-7 w-7 text-[13px]" />
        <b className="absolute left-[51px] top-[9px] text-[12px] leading-4">{profile.displayName}</b>
        <span className="absolute left-[51px] top-[27px] text-[10px] leading-[13px] text-[#9a9ea7]">Plus</span>
      </button>
    </aside>
    {profileEditing && <ProfileModal profile={profile} onClose={() => setProfileEditing(false)} />}
    </>
  );
}

// 渲染侧栏导航项。
function NavItem({ text, icon, active, onClick }: { text: string; icon: "home" | "library"; active?: boolean; onClick?: () => void }) {
  return (
    <button
      className={`relative mb-2 ml-[21px] block h-[38px] w-[204px] rounded-[14px] text-left ${active ? "bg-[#e8ebef] font-bold text-[#171719]" : "text-[#53565e]"}`}
      onClick={onClick}
    >
      <span className={`absolute left-[12px] top-[10px] ${active ? "text-[#6c4dff]" : "text-[#9a9ea7]"}`}>
        {icon === "home" ? <HomeIcon /> : <LibraryIcon />}
      </span>
      <span className="absolute left-[34px] top-[9px] text-[13px] leading-[18px]">{text}</span>
    </button>
  );
}

// 把项目日期显示为侧栏中的简短形式。
function formatSidebarDate(date?: string | null) {
  return date?.slice(0, 10).replace(/-/g, "/") ?? "最近编辑";
}

// 渲染项目右侧三点菜单。
function ProjectManageMenu({ onProtectedAction }: { onProtectedAction: (message: string) => void }) {
  return (
    <section data-sidebar-popup className="figma-shadow relative z-30 ml-auto mt-1 w-[132px] rounded-[10px] border border-[#e8ebef] bg-white p-1">
      <SidebarMenuItem icon="pin" text="置顶项目" onClick={() => onProtectedAction("置顶项目将在项目排序功能接入后启用。")} />
      <SidebarMenuItem icon="edit" text="重命名" onClick={() => onProtectedAction("重命名涉及项目资料写入，请确认后再接入。")} />
      <SidebarMenuItem icon="trash" text="删除项目" danger onClick={() => onProtectedAction("删除项目涉及数据库删除，请确认后再接入。")} />
    </section>
  );
}

// 渲染项目版本列表，点击版本可进入对应报告。
function ProjectVersionMenu({ versions, activeSubmissionId, manageVersionId, onOpenVersion, onManageVersion, onProtectedAction }: { versions: ProjectVersion[]; activeSubmissionId?: number; manageVersionId: number | null; onOpenVersion: (version: ProjectVersion) => void; onManageVersion: (submissionId: number) => void; onProtectedAction: (message: string) => void }) {
  if (!versions.length) return <section data-sidebar-popup className="relative z-30 mt-1 px-[14px] py-2 text-[11px] text-[#9a9ea7]">暂无历史版本</section>;
  return (
    <section data-sidebar-popup className="relative z-30 mt-1 w-[204px]">
      {versions.map((version) => {
        return (
          <div className="group relative" key={version.submission.id}>
            <button type="button" className={`flex h-8 w-full items-center rounded-[8px] px-[14px] text-left text-[11px] hover:bg-[#eef0f4] ${version.submission.id === activeSubmissionId ? "font-bold" : ""}`} onClick={() => onOpenVersion(version)}>
              <span>V{version.versionNumber}</span>
              <span className="ml-3 text-[10px] font-medium text-[#9ca3af]">{version.history?.overall_score == null ? "草稿" : `${Math.round(version.history.overall_score)}分`}</span>
            </button>
            <button type="button" data-sidebar-trigger aria-label={`管理V${version.versionNumber}`} className="absolute right-0 top-1 flex h-6 w-6 items-center justify-center rounded-full opacity-0 hover:bg-white group-hover:opacity-100" onClick={() => onManageVersion(version.submission.id)}><DotsIcon /></button>
            {manageVersionId === version.submission.id && (
              <section data-sidebar-popup className="figma-shadow relative z-40 ml-auto mt-1 w-[132px] rounded-[10px] border border-[#e8ebef] bg-white p-1">
                <SidebarMenuItem icon="edit" text="重命名版本" onClick={() => onProtectedAction("重命名版本涉及提交资料写入，请确认后再接入。")} />
                <SidebarMenuItem icon="trash" text="删除版本" danger onClick={() => onProtectedAction("删除版本涉及数据库删除，请确认后再接入。")} />
              </section>
            )}
          </div>
        );
      })}
    </section>
  );
}

type SidebarMenuIcon = "pin" | "edit" | "trash";

// 渲染侧栏管理菜单中的一行。
function SidebarMenuItem({ icon, text, danger = false, onClick }: { icon: SidebarMenuIcon; text: string; danger?: boolean; onClick: () => void }) {
  return <button type="button" className={`flex h-8 w-full items-center rounded-[8px] px-2 text-left text-[12px] hover:bg-[#f7f8fa] ${danger ? "text-[#dc2626]" : "text-[#111318]"}`} onClick={onClick}><SidebarMenuIconView icon={icon} /><span className="ml-2">{text}</span></button>;
}

// 渲染项目菜单图标。
function SidebarMenuIconView({ icon }: { icon: SidebarMenuIcon }) {
  if (icon === "pin") return <span className="relative h-5 w-5"><span className="absolute left-1 top-1 h-[7px] w-[10px] rounded-[2px] bg-current" /><span className="absolute left-[8px] top-[10px] h-[10px] w-0.5 rounded-full bg-current" /></span>;
  if (icon === "edit") return <span className="h-[3px] w-4 rotate-[25deg] rounded-full bg-current" />;
  return <span className="relative h-5 w-5"><span className="absolute left-1 top-[7px] h-3 w-3 rounded-[2px] border-[1.5px] border-current" /><span className="absolute left-1 top-[3px] h-0.5 w-3 rounded-full bg-current" /></span>;
}

// 渲染项目操作入口中的三点按钮。
function DotsIcon() {
  return <span className="flex gap-[3px]">{[0, 1, 2].map((item) => <span className="h-[3px] w-[3px] rounded-full bg-[#6b7280]" key={item} />)}</span>;
}

// 渲染账号按钮打开的菜单。
function AccountMenu({ profile, onEditProfile }: { profile: UserProfile; onEditProfile: () => void }) {
  return (
    <section className="figma-shadow absolute bottom-[72px] left-[13px] z-30 w-[222px] rounded-[20px] border border-[#e8ebef] bg-white p-3">
      <div className="flex h-[54px] items-center border-b border-[#e8ebef] px-1 pb-3">
        <ProfileAvatar profile={profile} className="h-9 w-9 text-[13px]" />
        <div className="ml-3"><b className="block text-[14px]">{profile.displayName}</b><span className="text-[12px] text-[#9a9ea7]">Plus</span></div>
        <ChevronIcon direction="right" className="ml-auto" />
      </div>
      <div className="space-y-1 py-2">
        <AccountMenuItem icon="sparkle" text="升级套餐" />
        <AccountMenuItem icon="profile" text="个人资料" onClick={onEditProfile} />
        <AccountMenuItem icon="settings" text="设置" />
      </div>
      <div className="space-y-1 border-t border-[#e8ebef] pt-2">
        <AccountMenuItem icon="help" text="帮助" trailing />
        <AccountMenuItem icon="logout" text="退出登录" />
      </div>
    </section>
  );
}

// 渲染账号菜单内的一行操作。
function AccountMenuItem({ icon, text, trailing = false, onClick }: { icon: MenuIconName; text: string; trailing?: boolean; onClick?: () => void }) {
  return (
    <button type="button" className="flex h-9 w-full items-center rounded-[10px] px-2 text-left text-[13px] hover:bg-[#f4f6f8]" onClick={onClick}>
      <MenuIcon name={icon} />
      <span className="ml-3">{text}</span>
      {trailing && <ChevronIcon direction="right" className="ml-auto" />}
    </button>
  );
}

// 渲染统一用户头像，上传图片后会在全部入口同步显示。
function ProfileAvatar({ profile, className = "" }: { profile: UserProfile; className?: string }) {
  return profile.avatarDataUrl
    ? <img alt="用户头像" className={`rounded-full object-cover ${className}`} src={profile.avatarDataUrl} />
    : <span className={`flex items-center justify-center rounded-full bg-[#6c4dff] font-bold text-white ${className}`}>{profile.displayName.slice(0, 1) || "钱"}</span>;
}

// 渲染可修改用户名、头像和密码的用户资料卡片。
function ProfileModal({ profile, onClose }: { profile: UserProfile; onClose: () => void }) {
  const { updateProfile } = useProfile();
  const avatarInput = useRef<HTMLInputElement>(null);
  const [displayName, setDisplayName] = useState(profile.displayName);
  const [avatarDataUrl, setAvatarDataUrl] = useState(profile.avatarDataUrl);
  const [showPassword, setShowPassword] = useState(false);
  const [passwordEditing, setPasswordEditing] = useState(false);
  const [message, setMessage] = useState("");

  // 读取本地图片并暂存在资料卡片中，保存后同步到全部头像。
  const chooseAvatar = (file?: File) => {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => setAvatarDataUrl(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  };

  // 保存显示名称和头像资料。
  const saveProfile = () => {
    if (!displayName.trim()) {
      setMessage("显示名称不能为空。");
      return;
    }
    updateProfile({
      displayName: displayName.trim(),
      avatarDataUrl,
    });
    onClose();
  };

  if (passwordEditing) {
    return <PasswordModal profile={profile} onClose={() => setPasswordEditing(false)} />;
  }

  return (
    <div className="font-chat absolute inset-0 z-[60] bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="text-[22px] font-bold">个人资料</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <div className="absolute left-[252px] top-[68px]">
          <ProfileAvatar profile={{ ...profile, avatarDataUrl }} className="h-20 w-20 text-[24px]" />
          <button type="button" aria-label="更换用户头像" className="absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] bg-white text-[#53565e]" onClick={() => avatarInput.current?.click()}>
            <CameraIcon />
          </button>
          <input ref={avatarInput} className="hidden" type="file" accept="image/*" onChange={(event) => chooseAvatar(event.target.files?.[0])} />
        </div>
        <label className="absolute left-7 top-[176px] flex h-[58px] w-[528px] items-center rounded-[10px] border border-[#e8ebef] px-4">
          <span className="w-[88px] text-[14px] text-[#9a9ea7]">显示名称</span>
          <input className="min-w-0 flex-1 bg-transparent text-[14px] font-bold outline-none" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </label>
        <div className="absolute left-7 top-[246px] flex h-[58px] w-[528px] items-center rounded-[10px] border border-[#e8ebef] px-4">
          <span className="w-[88px] text-[14px] text-[#9a9ea7]">账号名</span>
          <b className="text-[14px]">{profile.accountName}</b>
        </div>
        <div className="absolute left-7 top-[316px] flex h-[58px] w-[528px] items-center rounded-[10px] border border-[#e8ebef] px-4">
          <span className="w-[88px] text-[14px] text-[#9a9ea7]">密码</span>
          <b className={`text-[14px] ${!showPassword && profile.password ? "tracking-[3px]" : ""} ${profile.password ? "" : "font-normal text-[#9a9ea7]"}`}>{profile.password ? showPassword ? profile.password : "••••••••" : "尚未设置"}</b>
          <button type="button" aria-label={showPassword ? "隐藏密码" : "显示密码"} className="ml-auto flex h-7 w-7 items-center justify-center text-[#9a9ea7]" onClick={() => setShowPassword((current) => !current)}>
            <EyeIcon hidden={showPassword} />
          </button>
          <button type="button" className="ml-3 text-[14px] font-bold text-[#6c4dff]" onClick={() => setPasswordEditing(true)}>修改密码</button>
        </div>
        {message && <span className="absolute bottom-[73px] left-7 text-[12px] text-[#ff5570]">{message}</span>}
        <div className="absolute bottom-7 right-7 flex gap-3">
          <Button kind="white" className="h-9 rounded-[10px]" onClick={onClose}>取消</Button>
          <Button className="h-9 rounded-[10px]" onClick={saveProfile}>保存</Button>
        </div>
      </section>
    </div>
  );
}

// 渲染独立密码修改卡片，保存或取消后返回个人资料。
function PasswordModal({ profile, onClose }: { profile: UserProfile; onClose: () => void }) {
  const { updateProfile } = useProfile();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");

  // 校验当前密码与新密码后保存。
  const savePassword = () => {
    if (profile.password && currentPassword !== profile.password) {
      setMessage("当前密码不正确。");
      return;
    }
    if (newPassword.length < 6) {
      setMessage("新密码至少需要 6 个字符。");
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage("两次输入的新密码不一致。");
      return;
    }
    updateProfile({ password: newPassword });
    onClose();
  };

  return (
    <div className="font-chat absolute inset-0 z-[70] bg-[#171719]/30">
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7">
        <h2 className="text-[22px] font-bold">修改密码</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <p className="absolute left-7 top-[74px] text-[13px] text-[#6b7385]">保存新密码后，将返回个人资料卡片。</p>
        <PasswordField top={132} label="当前密码" placeholder={profile.password ? "请输入当前密码" : "首次设置可留空"} value={currentPassword} onChange={setCurrentPassword} />
        <PasswordField top={202} label="新密码" placeholder="请输入新密码" value={newPassword} onChange={setNewPassword} />
        <PasswordField top={272} label="确认新密码" placeholder="请再次输入新密码" value={confirmPassword} onChange={setConfirmPassword} />
        {message && <span className="absolute bottom-[83px] left-7 text-[12px] text-[#ff5570]">{message}</span>}
        <div className="absolute bottom-7 right-7 flex gap-3">
          <Button kind="white" className="h-9 rounded-[10px]" onClick={onClose}>取消</Button>
          <Button className="h-9 rounded-[10px]" onClick={savePassword}>保存</Button>
        </div>
      </section>
    </div>
  );
}

// 渲染修改密码卡片内的一行密码输入框。
function PasswordField({ top, label, placeholder, value, onChange }: { top: number; label: string; placeholder: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="absolute left-7 flex h-[58px] w-[528px] items-center rounded-[10px] border border-[#e8ebef] px-4" style={{ top }}>
      <span className="w-[108px] text-[14px] text-[#9a9ea7]">{label}</span>
      <input type="password" className="min-w-0 flex-1 bg-transparent text-[14px] outline-none" placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

// 渲染头像上传按钮中的相机图标。
function CameraIcon() {
  return <svg viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M5 7h3l1.5-2h5L16 7h3a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V9a2 2 0 012-2z" /><circle cx="12" cy="13" r="3" /></svg>;
}

// 渲染密码显示或隐藏按钮的小眼睛图标。
function EyeIcon({ hidden }: { hidden: boolean }) {
  return <svg viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-current stroke-[1.8]"><path d="M2.5 12s3.4-5 9.5-5 9.5 5 9.5 5-3.4 5-9.5 5-9.5-5-9.5-5z" /><circle cx="12" cy="12" r="2.5" />{hidden && <path d="m4 4 16 16" />}</svg>;
}

type MenuIconName = "sparkle" | "profile" | "settings" | "help" | "logout";

// 渲染账号菜单的线性图标。
function MenuIcon({ name }: { name: MenuIconName }) {
  const paths = {
    sparkle: <path d="M12 2l2.2 6.2L20 10l-5.8 1.8L12 18l-2.2-6.2L4 10l5.8-1.8L12 2z" />,
    profile: <><circle cx="12" cy="8" r="3" /><path d="M5 19c1.2-3.4 3.5-5 7-5s5.8 1.6 7 5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4L17 7m-10 10-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6" /></>,
    help: <><circle cx="12" cy="12" r="8" /><path d="M9.8 9a2.3 2.3 0 014.4.8c0 1.8-2.2 2.1-2.2 3.7M12 17h.01" /></>,
    logout: <><path d="M10 5H5v14h5" /><path d="M14 8l4 4-4 4m4-4H9" /></>,
  };
  return <svg viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-[#171719] stroke-[1.8]">{paths[name]}</svg>;
}

// 渲染侧栏主页图标。
function HomeIcon() {
  return <svg viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current stroke-[1.6]"><path d="M3 9.2 10 3l7 6.2V17H6a3 3 0 01-3-3V9.2z" /><path d="M8 17v-5h4v5" /></svg>;
}

// 渲染侧栏知识库图标。
function LibraryIcon() {
  return <svg viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current stroke-[1.6]"><path d="M4 3.5h10.5A1.5 1.5 0 0116 5v12H5.5A1.5 1.5 0 014 15.5v-12z" /><path d="M4 15.5A1.5 1.5 0 015.5 14H16M7 7h6" /></svg>;
}

// 渲染展开或收起箭头。
function ChevronIcon({ direction, className = "" }: { direction: "down" | "right"; className?: string }) {
  const path = direction === "down" ? "m5 7 4 4 4-4" : "m7 5 4 4-4 4";
  return <svg viewBox="0 0 18 18" className={`h-4 w-4 fill-none stroke-[#6b7385] stroke-2 ${className}`}><path d={path} /></svg>;
}

// 渲染主内容标题。
export function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <>
      <h1 className="absolute left-[307px] top-[53px] text-[34px] font-bold leading-[44px]">{title}</h1>
      <p className="absolute left-[309px] top-[107px] text-[14px] leading-[22px] text-[#53565e]">{subtitle}</p>
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

// 渲染页面右上角流程按钮。
export function FlowActions({ go, previous, next, finalText = "下一步", onSave, beforeNext }: { go: (route: Route) => void; previous?: Route; next: Route; finalText?: string; onSave?: () => void; beforeNext?: () => Promise<unknown> | void }) {
  const nextPage = async () => {
    await beforeNext?.();
    go(next);
  };
  return (
    <div className="absolute right-[66px] top-[154px] flex gap-4">
      {previous && <Button kind="white" onClick={() => go(previous)} className="w-[112px] text-[#9a9ea7]">上一步</Button>}
      <Button kind="white" className="w-[122px]" onClick={onSave}>保存草稿</Button>
      <Button kind="purple" onClick={() => void nextPage()} className="w-[123px] rounded-[16px]">{finalText}</Button>
    </div>
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
