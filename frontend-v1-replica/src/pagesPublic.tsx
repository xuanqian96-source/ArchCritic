// 公共页面：嵌入官网首页，功能页面的真实登录由 pagesAuth.tsx 负责。
import type { PageProps } from "./App";

// 渲染官网首页。
export function LandingPage(_props: PageProps) {
  return (
    <iframe
      className="block h-screen w-screen border-0 bg-[#101010]"
      src="/homepage-cn/archcritic-homepage-cn-figma-dark.html"
      title="ArchCritic 首页"
    />
  );
}
