// 应用路由：串联设计稿中的全部页面，并复用统一工作区连接现有后端。
import { useCallback, useEffect, useMemo, useState } from "react";
import { Canvas } from "./components";
import { LandingPage } from "./pagesPublic";
import {
  AgentsPage,
  ConfirmPage,
  CreateModalPage,
  DashboardPage,
  ProcessingPage,
  ProjectInfoPage,
  UploadPage,
} from "./pagesFlow";
import { HistoryPage, ReportPage } from "./pagesResults";
import { AuthPage } from "./pagesAuth";
import { KnowledgePage } from "./pages/knowledgePage";
import { prefetchKnowledgeLibrary, prefetchKnowledgeQuiz } from "./api/knowledge";
import { useAuth } from "./state/auth";

export type Route =
  | "landing"
  | "auth"
  | "dashboard"
  | "create"
  | "info"
  | "upload"
  | "agents"
  | "confirm"
  | "processing"
  | "report"
  | "history"
  | "knowledge";

export interface PageProps {
  go: (route: Route) => void;
}

const VALID_ROUTES = new Set<Route>([
  "landing",
  "auth",
  "dashboard",
  "create",
  "info",
  "upload",
  "agents",
  "confirm",
  "processing",
  "report",
  "history",
  "knowledge",
]);

// 从地址栏读取页面，方便刷新后继续验收当前页面。
function readRoute(): Route {
  const route = window.location.hash.replace("#/", "") as Route;
  return VALID_ROUTES.has(route) ? route : "landing";
}

interface CanvasLayout {
  scale: number;
  left: number;
  top: number;
}

// 根据窗口大小整体缩放画布，内部尺寸始终保持设计稿原值。
function useCanvasLayout(): CanvasLayout {
  const [layout, setLayout] = useState<CanvasLayout>({ scale: 1, left: 0, top: 0 });
  useEffect(() => {
    const update = () => {
      const scale = Math.min(window.innerWidth / 1536, window.innerHeight / 820);
      setLayout({
        scale,
        left: Math.round(Math.max(0, (window.innerWidth - 1536 * scale) / 2)),
        top: 0,
      });
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return layout;
}

// 渲染当前页面并处理页面间跳转。
export default function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  const layout = useCanvasLayout();
  const { loading, user } = useAuth();

  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  const go = useCallback((next: Route) => {
    const protectedNext = next !== "landing" && next !== "auth";
    const resolved = protectedNext && !user ? "auth" : next;
    window.location.hash = `/${resolved}`;
    setRoute(resolved);
  }, [user]);

  useEffect(() => {
    if (loading) return;
    if (!user && route !== "landing" && route !== "auth") go("auth");
    if (user && route === "auth") go("dashboard");
  }, [go, loading, route, user]);

  useEffect(() => {
    if (!user) return;
    const libraryTimer = window.setTimeout(prefetchKnowledgeLibrary, 300);
    const quizTimer = window.setTimeout(prefetchKnowledgeQuiz, 1800);
    return () => {
      window.clearTimeout(libraryTimer);
      window.clearTimeout(quizTimer);
    };
  }, [user]);

  const page = useMemo(() => {
    const props = { go };
    return {
      landing: <LandingPage {...props} />,
      auth: <AuthPage {...props} />,
      dashboard: <DashboardPage {...props} />,
      create: <CreateModalPage {...props} />,
      info: <ProjectInfoPage {...props} />,
      upload: <UploadPage {...props} />,
      agents: <AgentsPage {...props} />,
      confirm: <ConfirmPage {...props} />,
      processing: <ProcessingPage {...props} />,
      report: <ReportPage {...props} />,
      history: <HistoryPage {...props} />,
      knowledge: <KnowledgePage {...props} />,
    }[route];
  }, [go, route]);

  if (loading && route !== "landing") return <div className="flex h-screen w-screen items-center justify-center bg-[#f4f6f8] text-[13px] font-bold text-[#53565e]">正在读取本地账户...</div>;
  if (!user && route !== "landing" && route !== "auth") return <AuthPage go={go} />;
  if (route === "landing") return page;

  return <Canvas {...layout}>{page}</Canvas>;
}
