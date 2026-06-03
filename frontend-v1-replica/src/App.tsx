// 应用路由：串联设计稿中的全部页面，并复用统一工作区连接现有后端。
import { useEffect, useMemo, useState } from "react";
import { Canvas } from "./components";
import { LandingPage, LoginPage } from "./pagesPublic";
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

export type Route =
  | "landing"
  | "login"
  | "dashboard"
  | "create"
  | "info"
  | "upload"
  | "agents"
  | "confirm"
  | "processing"
  | "report"
  | "history";

export interface PageProps {
  go: (route: Route) => void;
}

const VALID_ROUTES = new Set<Route>([
  "landing",
  "login",
  "dashboard",
  "create",
  "info",
  "upload",
  "agents",
  "confirm",
  "processing",
  "report",
  "history",
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

  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  const go = (next: Route) => {
    window.location.hash = `/${next}`;
    setRoute(next);
  };

  const page = useMemo(() => {
    const props = { go };
    return {
      landing: <LandingPage {...props} />,
      login: <LoginPage {...props} />,
      dashboard: <DashboardPage {...props} />,
      create: <CreateModalPage {...props} />,
      info: <ProjectInfoPage {...props} />,
      upload: <UploadPage {...props} />,
      agents: <AgentsPage {...props} />,
      confirm: <ConfirmPage {...props} />,
      processing: <ProcessingPage {...props} />,
      report: <ReportPage {...props} />,
      history: <HistoryPage {...props} />,
    }[route];
  }, [route]);

  return <Canvas {...layout}>{page}</Canvas>;
}
