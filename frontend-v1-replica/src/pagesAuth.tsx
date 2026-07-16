// 本地账户页：以简洁双栏布局承载登录和首次注册。
import { useState, type FormEvent } from "react";
import type { PageProps } from "./App";
import { useAuth } from "./state/auth";

type AuthMode = "login" | "register";

export function AuthPage({ go }: PageProps) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (mode === "register" && password !== confirmPassword) {
      setError("两次输入的密码不一致。");
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "register") await register(username, password, displayName);
      else await login(username, password);
      go("dashboard");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "账户操作失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (next: AuthMode) => {
    setMode(next);
    setError("");
    setPassword("");
    setConfirmPassword("");
  };

  return (
    <main className="relative h-full w-full overflow-hidden bg-[#f4f6f8] text-[#171719]">
      <button type="button" className="absolute left-[58px] top-[46px] flex items-center gap-3" onClick={() => go("landing")}>
        <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-[#171719] text-[15px] font-black text-white">A</span>
        <span className="text-[18px] font-bold">ArchCritic</span>
      </button>

      <section className="absolute left-[128px] top-[174px] w-[560px]">
        <p className="text-[12px] font-bold uppercase tracking-[0.24em] text-[#6c4dff]">Architecture review workspace</p>
        <h1 className="mt-7 text-[48px] font-black leading-[1.16]">让每一次方案修改<br />都有清楚的依据</h1>
        <p className="mt-7 w-[490px] text-[15px] leading-7 text-[#53565e]">登录后，项目、任务书、图纸、评图报告和历史版本都会保存在当前电脑，并只显示在你的账户中。</p>
        <div className="mt-12 grid w-[500px] grid-cols-3 border-y border-[#dfe2e7] py-6">
          {[['多 Agent', '按阶段协同'], ['任务书', '真实参与评分'], ['本地保存', '数据归属清楚']].map(([title, detail]) => (
            <div className="border-r border-[#dfe2e7] px-5 first:pl-0 last:border-0" key={title}>
              <b className="block text-[15px]">{title}</b><span className="mt-2 block text-[12px] text-[#9a9ea7]">{detail}</span>
            </div>
          ))}
        </div>
      </section>

      <form className="absolute right-[150px] top-[112px] w-[430px] border-l border-[#dfe2e7] py-12 pl-[72px]" onSubmit={(event) => void submit(event)}>
        <h2 className="text-[30px] font-bold">{mode === "login" ? "欢迎回来" : "创建本地账户"}</h2>
        <p className="mt-2 text-[13px] text-[#9a9ea7]">{mode === "login" ? "继续查看你的项目与历史评图" : "首次注册后即可开始保存个人项目"}</p>

        <div className="mt-9 flex h-10 border-b border-[#dfe2e7] text-[13px] font-bold">
          <button type="button" className={`w-1/2 border-b-2 ${mode === "login" ? "border-[#171719] text-[#171719]" : "border-transparent text-[#9a9ea7]"}`} onClick={() => switchMode("login")}>登录</button>
          <button type="button" className={`w-1/2 border-b-2 ${mode === "register" ? "border-[#171719] text-[#171719]" : "border-transparent text-[#9a9ea7]"}`} onClick={() => switchMode("register")}>首次注册</button>
        </div>

        <div className="mt-7 space-y-5">
          {mode === "register" && <AuthField label="显示名称" value={displayName} onChange={setDisplayName} placeholder="例如：钱同学" autoComplete="name" />}
          <AuthField label="用户名" value={username} onChange={setUsername} placeholder="至少 3 位字母或数字" autoComplete="username" />
          <AuthField label="密码" value={password} onChange={setPassword} placeholder={mode === "register" ? "至少 8 位" : "输入密码"} type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} />
          {mode === "register" && <AuthField label="确认密码" value={confirmPassword} onChange={setConfirmPassword} placeholder="再次输入密码" type="password" autoComplete="new-password" />}
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

function AuthField({ label, value, onChange, placeholder, type = "text", autoComplete }: { label: string; value: string; onChange: (value: string) => void; placeholder: string; type?: string; autoComplete: string }) {
  return <label className="block text-[12px] font-bold"><span>{label}</span><input required className="mt-2 h-11 w-full rounded-[12px] border border-[#dfe2e7] bg-white px-4 text-[13px] font-normal outline-none transition focus:border-[#6c4dff]" type={type} value={value} autoComplete={autoComplete} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}
