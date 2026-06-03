// 公共页面：复刻 Figma 中的官网首页和登录页。
import type { PageProps } from "./App";
import { Badge, Button, PlanThumb } from "./components";

// 渲染官网首页。
export function LandingPage({ go }: PageProps) {
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <header className="absolute left-16 right-16 top-[46px] flex h-[34px] items-center">
        <div className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-[#171719] text-[15px] font-bold text-white">A</div>
        <b className="ml-3 text-[20px]">ArchCritic</b>
        <nav className="ml-[330px] flex gap-[54px] text-[14px] font-medium text-[#53565e]">
          <span>项目介绍</span><span>定价</span><span>常见问题</span>
        </nav>
        <Button kind="dark" className="ml-auto w-[156px] rounded-[16px]" onClick={() => go("login")}>GET ArchCritic</Button>
      </header>
      <main>
        <h1 className="absolute left-[100px] top-[210px] w-[600px] text-[56px] font-black leading-[66px] text-[#171719]">
          Your full-time<br />architecture critic
        </h1>
        <p className="absolute left-[104px] top-[373px] w-[568px] text-[16px] leading-8 text-[#53565e]">
          面向建筑设计课的 AI 评图辅助系统。上传图纸与说明，系统按阶段匹配评价框架，组织多 Agent 生成可执行修改清单。
        </p>
        <Button kind="purple" className="absolute left-[104px] top-[474px] h-10 w-[132px] rounded-[16px]" onClick={() => go("login")}>开始使用</Button>
        <Button kind="white" className="absolute left-[252px] top-[474px] h-10 w-[132px] rounded-[16px]">了解更多</Button>
      </main>
      <section className="figma-shadow absolute left-[760px] top-[150px] h-[620px] w-[650px] overflow-hidden rounded-[26px] border border-[#e8ebef] bg-white">
        <div className="absolute left-[21px] top-[21px] h-[576px] w-[142px] rounded-[18px] border border-[#e8ebef] bg-[#fafbfc]">
          <span className="absolute left-[15px] top-[15px] h-6 w-6 rounded-full bg-[#171719]" /><b className="absolute left-[48px] top-[17px] text-[12px]">ArchCritic</b>
          <span className="absolute left-[13px] top-[65px] h-8 w-[114px] rounded-[12px] bg-[#e8ebef] px-4 py-[8px] text-[10px] font-bold">●　新建评图</span>
          {["历史设计", "知识库", "设置"].map((item, index) => <span className="absolute left-[18px] text-[11px] text-[#6b7385]" style={{ top: 142 + index * 44 }} key={item}>●　{item}</span>)}
        </div>
        <h2 className="absolute left-[194px] top-[34px] text-[26px] font-bold">评图工作台</h2>
        <p className="absolute left-[196px] top-[76px] text-[12px] text-[#53565e]">上海美术馆概念方案 · 方案阶段</p>
        <div className="absolute left-[194px] top-[121px] h-[142px] w-[170px] rounded-[18px] border border-[#e8ebef] bg-white px-6 py-5">
          <b className="text-[40px] leading-[58px]">84</b><p className="text-[11px] text-[#53565e]">综合评分</p><span className="mt-2 inline-flex rounded-full bg-[#efe9ff] px-4 py-1 text-[10px] text-[#6c4dff]">方案阶段</span>
        </div>
        <div className="absolute left-[384px] top-[121px] h-[142px] w-[222px] rounded-[18px] bg-[#171719] px-5 py-5 text-white">
          <b className="block pt-2 text-[24px]">5 个 Agent</b><p className="mt-3 text-[11px] leading-5 text-[#e8ebef]">场地 · 功能 · 形式 · 结构 · 图面</p><span className="mt-1 inline-flex rounded-full bg-white px-4 py-1 text-[10px] text-[#171719]">协同分析</span>
        </div>
        <PlanThumb className="absolute left-[194px] top-[294px] h-[160px] w-[260px]" />
        <div className="absolute left-[478px] top-[294px] h-[160px] w-[128px] rounded-[14px] border border-[#e8ebef] bg-white p-4 text-[11px] text-[#53565e]">
          <Badge tone="coral">必须修改</Badge><b className="mt-4 block text-[14px] text-[#171719]">主入口与人流方向冲突</b><p className="mt-2">建议重组入口广场与展厅到达关系。</p>
        </div>
      </section>
    </div>
  );
}

// 渲染登录页。
export function LoginPage({ go }: PageProps) {
  return (
    <div className="relative h-full w-full bg-[#f4f6f8]">
      <div className="absolute left-[70px] top-[54px] h-7 w-7 rounded-full bg-[#171719]" />
      <b className="absolute left-[109px] top-[55px] text-[18px]">ArchCritic</b>
      <section className="absolute left-[260px] top-[184px] h-[560px] w-[580px] overflow-hidden rounded-[28px] bg-[#efe9ff]">
        <h1 className="absolute left-[62px] top-[72px] text-[36px] font-black leading-[48px] text-[#171719]">AI 赋能建筑评图<br />让设计更专业，让评审更高效</h1>
        <p className="absolute left-[64px] top-[184px] text-[14px] text-[#53565e]">多 Agent 会诊 · 阶段化评价 · 专项知识库 · 历史追踪</p>
        <div className="absolute bottom-[96px] left-[106px] h-[188px] w-[358px] overflow-hidden rounded-[14px] bg-white">
          <img className="h-full w-full" src="/assets/v1/login-preview.svg" />
        </div>
      </section>
      <section className="figma-shadow absolute left-[920px] top-[210px] h-[480px] w-[360px] rounded-[24px] border border-[#e8ebef] bg-white px-8 py-9">
        <h2 className="text-[28px] font-bold leading-10">欢迎登录</h2>
        <p className="mt-2 text-[13px] text-[#9a9ea7]">ArchCritic 评图辅助系统</p>
        <label className="mt-9 block text-[12px] font-bold text-[#53565e]">账号 / 邮箱
          <div className="mt-2 h-11 rounded-[12px] border border-[#e8ebef] px-[13px] py-[11px] text-[13px] font-normal text-[#171719]">archcritic@studio.edu</div>
        </label>
        <label className="mt-5 block text-[12px] font-bold text-[#53565e]">密码
          <div className="mt-2 h-11 rounded-[12px] border border-[#e8ebef] px-[13px] py-[10px] text-[16px] font-normal tracking-[3px] text-[#171719]">••••••••</div>
        </label>
        <Button kind="purple" className="mt-7 h-11 w-full rounded-[14px]" onClick={() => go("dashboard")}>登录</Button>
        <Button kind="white" className="mt-3 h-11 w-full rounded-[14px]">使用学校账号登录</Button>
      </section>
    </div>
  );
}
