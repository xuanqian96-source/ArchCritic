// 登录状态：恢复本地会话，并向全部页面提供注册、登录和退出能力。
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { getCurrentUser, loginAccount, logoutAccount, registerAccount, updateAccountPassword, updateAccountProfile } from "../api/auth";
import type { LocalUser } from "../types/api";

interface AuthState {
  user: LocalUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  updateDisplayName: (displayName: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<LocalUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    void getCurrentUser()
      .then((current) => { if (mounted) setUser(current); })
      .catch(() => { if (mounted) setUser(null); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setUser(await loginAccount({ username, password }));
  }, []);

  const register = useCallback(async (username: string, password: string, displayName: string) => {
    setUser(await registerAccount({ username, password, display_name: displayName }));
  }, []);

  const logout = useCallback(async () => {
    await logoutAccount();
    setUser(null);
  }, []);

  const updateDisplayName = useCallback(async (displayName: string) => {
    setUser(await updateAccountProfile(displayName));
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await updateAccountPassword(currentPassword, newPassword);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout, updateDisplayName, changePassword }), [changePassword, loading, login, logout, register, updateDisplayName, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("登录状态尚未初始化。");
  return context;
}
