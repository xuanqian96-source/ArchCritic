// 账户界面组件：资料编辑、密码修改、账户菜单和通用错误提示。
import { useRef, useState } from "react";
import { Button } from "./baseComponents";
import { useProfile, type UserProfile } from "../state/profile";

// 渲染账号按钮打开的菜单。
export function AccountMenu({ onEditProfile, onLogout }: { onEditProfile: () => void; onLogout: () => void }) {
  return (
    <section data-account-menu className="figma-shadow absolute bottom-[72px] left-[21px] z-30 w-[204px] rounded-[20px] border border-[#e8ebef] bg-white p-3">
      <div className="space-y-1 pb-2">
        <AccountMenuItem icon="sparkle" text="升级套餐" />
        <AccountMenuItem icon="profile" text="个人资料" onClick={onEditProfile} />
        <AccountMenuItem icon="settings" text="设置" />
      </div>
      <div className="space-y-1 border-t border-[#e8ebef] pt-2">
        <AccountMenuItem icon="help" text="帮助" trailing />
        <AccountMenuItem icon="logout" text="退出登录" onClick={onLogout} />
      </div>
    </section>
  );
}

// 渲染账号菜单内的一行操作。
export function AccountMenuItem({ icon, text, trailing = false, onClick }: { icon: MenuIconName; text: string; trailing?: boolean; onClick?: () => void }) {
  return (
    <button type="button" className="flex h-9 w-full items-center rounded-[10px] px-2 text-left text-[13px] hover:bg-[#f4f6f8]" onClick={onClick}>
      <MenuIcon name={icon} />
      <span className="ml-3">{text}</span>
      {trailing && <ChevronIcon direction="right" className="ml-auto" />}
    </button>
  );
}

// 渲染统一用户头像，上传图片后会在全部入口同步显示。
export function ProfileAvatar({ profile, className = "" }: { profile: UserProfile; className?: string }) {
  return profile.avatarDataUrl
    ? <img alt="用户头像" className={`rounded-full object-cover ${className}`} src={profile.avatarDataUrl} />
    : <span className={`flex items-center justify-center rounded-full bg-[#6c4dff] font-bold text-white ${className}`}>{profile.displayName.slice(0, 1) || "钱"}</span>;
}

// 渲染可修改用户名、头像和密码的用户资料卡片。
export function ProfileModal({ profile, onClose }: { profile: UserProfile; onClose: () => void }) {
  const { updateProfile } = useProfile();
  const avatarInput = useRef<HTMLInputElement>(null);
  const [displayName, setDisplayName] = useState(profile.displayName);
  const [avatarDataUrl, setAvatarDataUrl] = useState(profile.avatarDataUrl);
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
  const saveProfile = async () => {
    if (!displayName.trim()) {
      setMessage("显示名称不能为空。");
      return;
    }
    await updateProfile({
      displayName: displayName.trim(),
      avatarDataUrl,
    });
    onClose();
  };

  if (passwordEditing) {
    return <PasswordModal onClose={() => setPasswordEditing(false)} />;
  }

  return (
    <div className="font-chat absolute inset-0 z-[60] bg-[#171719]/30" onClick={onClose}>
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7" onClick={(event) => event.stopPropagation()}>
        <h2 className="text-[22px] font-bold">个人资料</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <div className="absolute left-[252px] top-[68px]">
          <button type="button" aria-label="更换用户头像" className="block h-20 w-20 rounded-full" onClick={() => avatarInput.current?.click()}>
            <ProfileAvatar profile={{ ...profile, avatarDataUrl }} className="h-20 w-20 text-[24px]" />
          </button>
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
          <b className="text-[14px] tracking-[3px]">••••••••</b>
          <button type="button" className="ml-3 text-[14px] font-bold text-[#6c4dff]" onClick={() => setPasswordEditing(true)}>修改密码</button>
        </div>
        {message && <span className="absolute bottom-[73px] left-7 text-[12px] text-[#ff5570]">{message}</span>}
        <div className="absolute bottom-7 right-7 flex gap-3">
          <Button kind="white" className="h-9 rounded-[10px]" onClick={onClose}>取消</Button>
          <Button className="h-9 rounded-[10px]" onClick={() => void saveProfile()}>保存</Button>
        </div>
      </section>
    </div>
  );
}

// 渲染独立密码修改卡片，保存或取消后返回个人资料。
export function PasswordModal({ onClose }: { onClose: () => void }) {
  const { changePassword } = useProfile();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");

  // 校验当前密码与新密码后保存。
  const savePassword = async () => {
    if (newPassword.length < 8) {
      setMessage("新密码至少需要 8 个字符。");
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage("两次输入的新密码不一致。");
      return;
    }
    try {
      await changePassword(currentPassword, newPassword);
      onClose();
    } catch (passwordError) {
      setMessage(passwordError instanceof Error ? passwordError.message : "密码修改失败。");
    }
  };

  return (
    <div className="font-chat absolute inset-0 z-[70] bg-[#171719]/30">
      <section className="figma-shadow absolute left-[476px] top-[156px] h-[508px] w-[584px] rounded-[22px] border border-[#e8ebef] bg-white p-7">
        <h2 className="text-[22px] font-bold">修改密码</h2>
        <button type="button" className="absolute right-6 top-6 flex h-7 w-7 items-center justify-center rounded-full border border-[#e8ebef] text-[18px] text-[#9a9ea7]" onClick={onClose}>×</button>
        <p className="absolute left-7 top-[74px] text-[13px] text-[#6b7385]">保存新密码后，将返回个人资料卡片。</p>
        <PasswordField top={132} label="当前密码" placeholder="请输入当前密码" value={currentPassword} onChange={setCurrentPassword} />
        <PasswordField top={202} label="新密码" placeholder="请输入新密码" value={newPassword} onChange={setNewPassword} />
        <PasswordField top={272} label="确认新密码" placeholder="请再次输入新密码" value={confirmPassword} onChange={setConfirmPassword} />
        {message && <span className="absolute bottom-[83px] left-7 text-[12px] text-[#ff5570]">{message}</span>}
        <div className="absolute bottom-7 right-7 flex gap-3">
          <Button kind="white" className="h-9 rounded-[10px]" onClick={onClose}>取消</Button>
          <Button className="h-9 rounded-[10px]" onClick={() => void savePassword()}>保存</Button>
        </div>
      </section>
    </div>
  );
}

// 渲染修改密码卡片内的一行密码输入框。
export function PasswordField({ top, label, placeholder, value, onChange }: { top: number; label: string; placeholder: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="absolute left-7 flex h-[58px] w-[528px] items-center rounded-[10px] border border-[#e8ebef] px-4" style={{ top }}>
      <span className="w-[108px] text-[14px] text-[#9a9ea7]">{label}</span>
      <input type="password" className="min-w-0 flex-1 bg-transparent text-[14px] outline-none" placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

// 渲染头像上传按钮中的相机图标。
export function CameraIcon() {
  return <svg viewBox="0 0 24 24" className="h-4 w-4 fill-none stroke-current stroke-[1.8]"><path d="M5 7h3l1.5-2h5L16 7h3a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V9a2 2 0 012-2z" /><circle cx="12" cy="13" r="3" /></svg>;
}

export type MenuIconName = "sparkle" | "profile" | "settings" | "help" | "logout";

// 渲染账号菜单的线性图标。
export function MenuIcon({ name }: { name: MenuIconName }) {
  const paths = {
    sparkle: <path d="M12 2l2.2 6.2L20 10l-5.8 1.8L12 18l-2.2-6.2L4 10l5.8-1.8L12 2z" />,
    profile: <><circle cx="12" cy="8" r="3" /><path d="M5 19c1.2-3.4 3.5-5 7-5s5.8 1.6 7 5" /></>,
    settings: <><path d="M9.67 4.14a2.34 2.34 0 014.66 0 2.34 2.34 0 003.32 1.91 2.34 2.34 0 012.33 4.03 2.34 2.34 0 000 3.84 2.34 2.34 0 01-2.33 4.03 2.34 2.34 0 00-3.32 1.91 2.34 2.34 0 01-4.66 0 2.34 2.34 0 00-3.32-1.91 2.34 2.34 0 01-2.33-4.03 2.34 2.34 0 000-3.84 2.34 2.34 0 012.33-4.03 2.34 2.34 0 003.32-1.91Z" /><circle cx="12" cy="12" r="3" /></>,
    help: <><circle cx="12" cy="12" r="8" /><path d="M9.8 9a2.3 2.3 0 014.4.8c0 1.8-2.2 2.1-2.2 3.7M12 17h.01" /></>,
    logout: <><path d="M10 5H5v14h5" /><path d="M14 8l4 4-4 4m4-4H9" /></>,
  };
  return <svg viewBox="0 0 24 24" className="h-5 w-5 fill-none stroke-[#171719] stroke-[1.8]">{paths[name]}</svg>;
}

// 渲染侧栏主页图标。
export function HomeIcon() {
  return <svg viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current stroke-[1.6]"><path d="M3 9.2 10 3l7 6.2V17H6a3 3 0 01-3-3V9.2z" /><path d="M8 17v-5h4v5" /></svg>;
}

// 渲染侧栏知识库图标。
export function LibraryIcon() {
  return <svg viewBox="0 0 20 20" className="h-4 w-4 fill-none stroke-current stroke-[1.6]"><path d="M4 3.5h10.5A1.5 1.5 0 0116 5v12H5.5A1.5 1.5 0 014 15.5v-12z" /><path d="M4 15.5A1.5 1.5 0 015.5 14H16M7 7h6" /></svg>;
}

// 渲染展开或收起箭头。
export function ChevronIcon({ direction, className = "" }: { direction: "down" | "right"; className?: string }) {
  const path = direction === "down" ? "m5 7 4 4 4-4" : "m7 5 4 4-4 4";
  return <svg viewBox="0 0 18 18" className={`h-4 w-4 fill-none stroke-[#6b7385] stroke-2 ${className}`}><path d={path} /></svg>;
}

// 渲染主内容标题。
