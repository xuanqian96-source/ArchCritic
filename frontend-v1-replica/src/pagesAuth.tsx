// 本地账户页：以简洁双栏布局承载登录和首次注册。
import { useRef, useState, type FormEvent } from "react";
import type { PageProps } from "./App";
import { checkAccountAvailability } from "./api/auth";
import { useAuth } from "./state/auth";

type AuthMode = "login" | "register";
type AuthDraft = { username: string; password: string; confirmPassword: string };
type AuthTouched = { account: boolean; password: boolean; confirmPassword: boolean };
type AccountAvailability = { account: string; status: "idle" | "checking" | "available" | "unavailable" };

const emptyDraft = (): AuthDraft => ({ username: "", password: "", confirmPassword: "" });
const emptyTouched = (): AuthTouched => ({ account: false, password: false, confirmPassword: false });

export function AuthPage({ go }: PageProps) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [loginDraft, setLoginDraft] = useState<AuthDraft>(emptyDraft);
  const [registerDraft, setRegisterDraft] = useState<AuthDraft>(emptyDraft);
  const [loginTouched, setLoginTouched] = useState<AuthTouched>(emptyTouched);
  const [registerTouched, setRegisterTouched] = useState<AuthTouched>(emptyTouched);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [availability, setAvailability] = useState<AccountAvailability>({ account: "", status: "idle" });
  const availabilityRequest = useRef(0);
  const draft = mode === "login" ? loginDraft : registerDraft;
  const touched = mode === "login" ? loginTouched : registerTouched;
  const normalizedAccount = draft.username.trim();
  const localAccountError = touched.account ? validateAccount(draft.username) : "";
  const duplicateAccountError = mode === "register" && touched.account && availability.account === normalizedAccount && availability.status === "unavailable"
    ? "该账号已被注册，请更换账号"
    : "";
  const accountError = localAccountError || duplicateAccountError;
  const passwordError = touched.password ? validatePassword(draft.password) : "";
  const confirmPasswordError = mode === "register" && touched.confirmPassword ? validateConfirmPassword(draft.password, draft.confirmPassword) : "";

  // 分别修改登录或注册草稿，切换页签时互不覆盖。
  const setDraftField = (field: keyof AuthDraft, value: string) => {
    const update = (current: AuthDraft) => ({ ...current, [field]: value });
    if (mode === "login") setLoginDraft(update);
    else setRegisterDraft(update);
    if (!value) {
      const touchedField = field === "username" ? "account" : field;
      touchFields({ [touchedField]: false });
    }
    if (mode === "register" && field === "username") {
      availabilityRequest.current += 1;
      setAvailability({ account: value.trim(), status: "idle" });
    }
  };

  // 分别记录两个页签中已经离开的输入栏。
  const touchFields = (fields: Partial<AuthTouched>) => {
    const update = (current: AuthTouched) => ({ ...current, ...fields });
    if (mode === "login") setLoginTouched(update);
    else setRegisterTouched(update);
  };

  // 查询后端，确认格式正确的注册账号是否可用。
  const verifyAccountAvailability = async (account: string) => {
    const normalized = account.trim();
    if (validateAccount(normalized)) return false;
    if (availability.account === normalized && availability.status === "available") return true;
    if (availability.account === normalized && availability.status === "unavailable") return false;
    const requestId = ++availabilityRequest.current;
    setAvailability({ account: normalized, status: "checking" });
    try {
      const result = await checkAccountAvailability(normalized);
      if (requestId === availabilityRequest.current) {
        setAvailability({ account: normalized, status: result.available ? "available" : "unavailable" });
      }
      return result.available;
    } catch {
      if (requestId === availabilityRequest.current) setAvailability({ account: normalized, status: "idle" });
      return true;
    }
  };

  const checkRegisterAccount = (forceRequired = false) => {
    if (!forceRequired && !draft.username.trim()) return;
    touchFields({ account: true });
    if (mode === "register" && !validateAccount(draft.username)) void verifyAccountAvailability(draft.username);
  };

  // 只有填写过内容时才在离开输入栏后提示，清空并点击空白处保持默认状态。
  const touchOnBlurIfFilled = (field: "password" | "confirmPassword", value: string) => {
    if (value) touchFields({ [field]: true });
  };

  // 点击表单外的空白区域时，撤销所有空输入栏遗留的必填提示。
  const clearEmptyValidation = () => {
    const clearEmptyFields = (current: AuthTouched): AuthTouched => ({
      account: draft.username.trim() ? current.account : false,
      password: draft.password ? current.password : false,
      confirmPassword: draft.confirmPassword ? current.confirmPassword : false,
    });
    if (mode === "login") setLoginTouched(clearEmptyFields);
    else setRegisterTouched(clearEmptyFields);
    if (!draft.username.trim()) {
      availabilityRequest.current += 1;
      setAvailability({ account: "", status: "idle" });
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    touchFields({ account: true, password: true, confirmPassword: mode === "register" });
    if (validateAccount(draft.username) || validatePassword(draft.password) || (mode === "register" && validateConfirmPassword(draft.password, draft.confirmPassword))) return;
    if (mode === "register" && !(await verifyAccountAvailability(draft.username))) return;
    setSubmitting(true);
    try {
      if (mode === "register") await register(draft.username, draft.password);
      else await login(draft.username, draft.password);
      go("dashboard");
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "账户操作失败，请稍后重试。";
      if (mode === "register" && message.includes("账号已被使用")) {
        setAvailability({ account: draft.username.trim(), status: "unavailable" });
        setRegisterTouched((current) => ({ ...current, account: true }));
      } else {
        setError(message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (next: AuthMode) => {
    setMode(next);
    setError("");
    setLoginTouched(emptyTouched());
    setRegisterTouched(emptyTouched());
  };

  return (
    <main
      className="relative h-full w-full overflow-hidden bg-[#f4f6f8] text-[#171719]"
      onPointerDown={(event) => {
        if (!(event.target as HTMLElement).closest("input, button")) clearEmptyValidation();
      }}
    >
      <button type="button" className="absolute left-[128px] top-[46px] flex items-center gap-3" onClick={() => go("landing")}>
        <img className="h-auto w-[160px]" src="/homepage-cn/LOGO-black.png" alt="ArchCritic" />
      </button>

      <section className="absolute left-[128px] top-1/2 w-[560px] -translate-y-1/2">
        <p className="text-[12px] font-bold uppercase tracking-[0.24em] text-[#6c4dff]">Public architecture design learning platform</p>
        <h1 className="mt-7 text-[44px] font-black leading-[1.16]"><span className="block whitespace-nowrap">陪伴你的公共建筑设计学习</span><span className="block">从理论到实践</span></h1>
        <p className="mt-7 w-[490px] text-[15px] leading-7 text-[#53565e]">从知识学习、案例理解到方案评图与版本复盘，在同一工作台中获得贯穿设计过程的辅助与反馈。</p>
        <div className="mt-12 grid w-[500px] grid-cols-3 border-y border-[#dfe2e7] py-6">
          {[['知识与案例', '建立设计认知'], ['AI 辅助评图', '发现方案问题'], ['版本与复盘', '看见修改过程']].map(([title, detail]) => (
            <div className="border-r border-[#dfe2e7] px-5 first:pl-0 last:border-0" key={title}>
              <b className="block text-[15px]">{title}</b><span className="mt-2 block text-[12px] text-[#9a9ea7]">{detail}</span>
            </div>
          ))}
        </div>
      </section>

      <form className="absolute right-[150px] top-[112px] w-[430px] border-l border-[#dfe2e7] py-12 pl-[72px]" onSubmit={(event) => void submit(event)}>
        <h2 className="text-[30px] font-bold">{mode === "login" ? "欢迎回来" : "创建本地账户"}</h2>
        <p className="mt-2 text-[13px] text-[#9a9ea7]">{mode === "login" ? "继续你的公共建筑设计学习与方案迭代" : "首次注册后即可开始公共建筑设计学习"}</p>

        <div className="mt-9 flex h-10 border-b border-[#dfe2e7] text-[13px] font-bold">
          <button type="button" className={`w-1/2 border-b-2 ${mode === "login" ? "border-[#171719] text-[#171719]" : "border-transparent text-[#9a9ea7]"}`} onClick={() => switchMode("login")}>登录</button>
          <button type="button" className={`w-1/2 border-b-2 ${mode === "register" ? "border-[#171719] text-[#171719]" : "border-transparent text-[#9a9ea7]"}`} onClick={() => switchMode("register")}>首次注册</button>
        </div>

        <div className="mt-7 space-y-3">
          <AuthField label="账号" value={draft.username} error={accountError} onChange={(value) => setDraftField("username", value)} onBlur={() => checkRegisterAccount()} placeholder="3–12 位英文字母或数字" autoComplete="username" />
          <AuthField label="密码" value={draft.password} error={passwordError} onChange={(value) => setDraftField("password", value)} onFocus={() => checkRegisterAccount(true)} onBlur={() => touchOnBlurIfFilled("password", draft.password)} placeholder={mode === "register" ? "至少 8 位" : "输入密码"} type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} />
          {mode === "register" && <AuthField label="确认密码" value={draft.confirmPassword} error={confirmPasswordError} onChange={(value) => setDraftField("confirmPassword", value)} onFocus={() => touchFields({ account: true, password: true })} onBlur={() => touchOnBlurIfFilled("confirmPassword", draft.confirmPassword)} placeholder="再次输入密码" type="password" autoComplete="new-password" />}
        </div>

        {error && <p className="mt-5 rounded-[10px] bg-[#fff1f1] px-4 py-3 text-[12px] font-bold leading-5 text-[#b44747]">{error}</p>}
        <button type="submit" disabled={submitting} className="mt-7 h-11 w-full rounded-[12px] bg-[#171719] text-[14px] font-bold text-white transition hover:bg-[#2d2d31] disabled:opacity-60">
          {submitting ? "请稍候..." : mode === "login" ? "登录并进入工作台" : "注册并进入工作台"}
        </button>
        <p className="mt-5 text-[11px] leading-5 text-[#9a9ea7]">账户和密码仅保存在当前电脑的本地数据库中，密码不会以明文保存。</p>
      </form>
    </main>
  );
}

function AuthField({ label, value, error, onChange, onBlur, onFocus, placeholder, type = "text", autoComplete }: { label: string; value: string; error: string; onChange: (value: string) => void; onBlur: () => void; onFocus?: () => void; placeholder: string; type?: string; autoComplete: string }) {
  return (
    <label className="block text-[12px] font-bold">
      <span>{label}</span>
      <input aria-invalid={Boolean(error)} className={`mt-2 h-11 w-full rounded-[12px] border bg-white px-4 text-[13px] font-normal outline-none transition ${error ? "border-[#ff5570] ring-1 ring-[#ff5570]/20" : "border-[#dfe2e7] focus:border-[#6c4dff]"}`} type={type} value={value} autoComplete={autoComplete} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} onBlur={onBlur} onFocus={onFocus} />
      <span className={`mt-1 block min-h-[16px] text-[10px] font-medium leading-4 ${error ? "text-[#d33f58]" : "text-transparent"}`}>{error || "输入正确"}</span>
    </label>
  );
}

// 校验账号仅由 3–12 位英文字母或数字组成。
function validateAccount(value: string) {
  if (!value.trim()) return "请输入账号";
  if (!/^[A-Za-z0-9]{3,12}$/.test(value.trim())) return "账号需为 3–12 位英文字母或数字，不能包含中文或符号";
  return "";
}

// 校验密码至少为 8 位。
function validatePassword(value: string) {
  if (!value) return "请输入密码";
  if (value.length < 8) return "密码至少需要 8 位";
  return "";
}

// 校验确认密码已填写且与密码一致。
function validateConfirmPassword(password: string, confirmation: string) {
  if (!confirmation) return "请再次输入密码";
  if (password !== confirmation) return "两次输入的密码不一致";
  return "";
}
