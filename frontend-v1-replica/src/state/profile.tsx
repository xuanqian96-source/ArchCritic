// 用户资料状态：账户名和显示名称来自后端，头像按账户保存在当前浏览器。
import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { useAuth } from "./auth";

export interface UserProfile {
  displayName: string;
  accountName: string;
  avatarDataUrl: string;
}

interface ProfileState {
  profile: UserProfile;
  updateProfile: (values: Partial<Pick<UserProfile, "displayName" | "avatarDataUrl">>) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
}

const ProfileContext = createContext<ProfileState | null>(null);

function avatarStorageKey(username: string) {
  return `archcritic:user-avatar:${username}`;
}

export function ProfileProvider({ children }: PropsWithChildren) {
  const { changePassword, updateDisplayName, user } = useAuth();
  const accountName = user?.username ?? "";
  const [avatarByUser, setAvatarByUser] = useState<Record<string, string>>({});
  const storedAvatar = accountName
    ? avatarByUser[accountName] ?? window.localStorage.getItem(avatarStorageKey(accountName)) ?? ""
    : "";
  const profile = {
    displayName: user?.display_name ?? "未登录",
    accountName,
    avatarDataUrl: storedAvatar,
  };

  const updateProfile = async (values: Partial<Pick<UserProfile, "displayName" | "avatarDataUrl">>) => {
    if (values.displayName && values.displayName !== profile.displayName) {
      await updateDisplayName(values.displayName);
    }
    if (values.avatarDataUrl !== undefined && accountName) {
      window.localStorage.setItem(avatarStorageKey(accountName), values.avatarDataUrl);
      setAvatarByUser((current) => ({ ...current, [accountName]: values.avatarDataUrl ?? "" }));
    }
  };

  const value = useMemo(() => ({ profile, updateProfile, changePassword }), [changePassword, profile.accountName, profile.avatarDataUrl, profile.displayName]);
  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile(): ProfileState {
  const context = useContext(ProfileContext);
  if (!context) throw new Error("用户资料状态尚未初始化。");
  return context;
}
