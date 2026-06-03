// 用户资料状态：在前端本地保存显示名称、头像和演示账号信息，供首页与侧栏同步使用。
import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";

const PROFILE_STORAGE_KEY = "archcritic:user-profile";

export interface UserProfile {
  displayName: string;
  accountName: string;
  password: string;
  avatarDataUrl: string;
}

interface ProfileState {
  profile: UserProfile;
  updateProfile: (values: Partial<UserProfile>) => void;
}

const DEFAULT_PROFILE: UserProfile = {
  displayName: "钱先生",
  accountName: "qianshanhe",
  password: "",
  avatarDataUrl: "",
};

const ProfileContext = createContext<ProfileState | null>(null);

// 从浏览器本地记录恢复用户资料。
function readStoredProfile(): UserProfile {
  try {
    const saved = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    return saved ? { ...DEFAULT_PROFILE, ...JSON.parse(saved) } : DEFAULT_PROFILE;
  } catch {
    return DEFAULT_PROFILE;
  }
}

// 为页面提供可持久保存的用户资料。
export function ProfileProvider({ children }: PropsWithChildren) {
  const [profile, setProfile] = useState<UserProfile>(readStoredProfile);

  // 更新用户资料，并在刷新页面后保留。
  const updateProfile = (values: Partial<UserProfile>) => {
    setProfile((current) => {
      const next = { ...current, ...values };
      window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const value = useMemo(() => ({ profile, updateProfile }), [profile]);
  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

// 读取当前用户资料。
export function useProfile(): ProfileState {
  const context = useContext(ProfileContext);
  if (!context) throw new Error("用户资料状态尚未初始化。");
  return context;
}
