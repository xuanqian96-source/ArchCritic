// 本地账户接口：负责注册、登录、会话恢复和退出。
import { requestJson } from "./client";
import type { LocalUser } from "../types/api";

export function getCurrentUser(): Promise<LocalUser> {
  return requestJson("/api/auth/me", { timeoutMs: 15_000 });
}

export function checkAccountAvailability(account: string): Promise<{ available: boolean }> {
  return requestJson(`/api/auth/account-availability?account=${encodeURIComponent(account)}`, { timeoutMs: 10_000 });
}

export function registerAccount(payload: { username: string; password: string; display_name: string }): Promise<LocalUser> {
  return requestJson("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function loginAccount(payload: { username: string; password: string }): Promise<LocalUser> {
  return requestJson("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function logoutAccount(): Promise<{ ok: boolean }> {
  return requestJson("/api/auth/logout", { method: "POST" });
}

export function updateAccountProfile(displayName: string): Promise<LocalUser> {
  return requestJson("/api/auth/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
}

export function updateAccountPassword(currentPassword: string, newPassword: string): Promise<{ ok: boolean }> {
  return requestJson("/api/auth/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
