// 流程步骤记录：保存每个草稿上次停留的新建评图步骤。
import type { Route } from "../App";

const FLOW_ROUTE_KEY = "archcritic:submission-flow-routes";
const flowRoutes: Route[] = ["info", "agents", "upload", "confirm"];

function readRouteMap(): Record<string, Route> {
  try {
    const raw = window.localStorage.getItem(FLOW_ROUTE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, route]) => flowRoutes.includes(route as Route)),
    ) as Record<string, Route>;
  } catch {
    return {};
  }
}

// 记录某个提交停留在哪个流程页面。
export function rememberSubmissionRoute(submissionId: number | undefined | null, route: Route) {
  if (!submissionId || !flowRoutes.includes(route)) return;
  const routeMap = readRouteMap();
  routeMap[String(submissionId)] = route;
  window.localStorage.setItem(FLOW_ROUTE_KEY, JSON.stringify(routeMap));
}

// 读取某个提交上次停留的流程页面。
export function readSubmissionRoute(submissionId: number | undefined | null, fallback: Route = "info"): Route {
  if (!submissionId) return fallback;
  return readRouteMap()[String(submissionId)] ?? fallback;
}
