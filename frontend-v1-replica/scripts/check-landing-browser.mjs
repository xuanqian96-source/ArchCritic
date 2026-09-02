/* 使用 Chrome 调试协议逐页点击官网翻页按钮，并检查主要内容是否居中且完整可见。 */
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const endpoint = process.argv[2] || process.env.ARCHCRITIC_CDP_ENDPOINT || "http://127.0.0.1:9222/json/list";
const outputDir = pathToFileURL(`${path.join(process.env.TEMP || ".", "archcritic-landing-browser-check")}${path.sep}`);
const pages = ["demo", "hero", "teaching-loop", "product", "knowledge-story", "workflow", "agents", "site-info"];
const requests = new Map();
let requestId = 0;

// 等待页面动画与浏览器绘制完成。
function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

// 发送一条 Chrome 调试协议指令。
function send(socket, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++requestId;
    requests.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

// 在主页面中读取同源首页 iframe 的布局状态。
async function evaluate(socket, expression) {
  const result = await send(socket, "Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text || "页面脚本执行失败";
    throw new Error(detail);
  }
  return result.result.value;
}

// 保存当前视口截图，方便复核自动测量结果。
async function capture(socket, name) {
  const result = await send(socket, "Page.captureScreenshot", { format: "png", fromSurface: true });
  await fs.writeFile(new URL(`${name}.png`, outputDir), Buffer.from(result.data, "base64"));
}

// 汇总当前章节中真正可见内容的边界，而不是使用整屏容器冒充居中。
const inspectExpression = `(() => {
  const frame = document.querySelector("iframe");
  const win = frame.contentWindow;
  const doc = frame.contentDocument;
  const ids = ${JSON.stringify(pages)};
  const currentId = ids.reduce((best, id) => {
    const distance = Math.abs(doc.getElementById(id).getBoundingClientRect().top);
    return distance < best.distance ? { id, distance } : best;
  }, { id: ids[0], distance: Infinity }).id;
  const selectors = {
    demo: ["#demo .cta-inner"],
    hero: ["#hero .hero-copy", "#hero .hero-scene"],
    "teaching-loop": ["#teaching-loop .loop-copy", "#teaching-loop .loop-orbit"],
    product: ["#product .product-showcase > div:first-child", "#product .product-feature-grid"],
    "knowledge-story": ["#knowledge-story .story-copy", "#knowledge-story .knowledge-metrics"],
    workflow: ["#workflow .workflow > div:first-child", "#workflow .flow-panel"],
    agents: ["#agents > .section-inner", "#agents .agent-gallery"],
    "site-info": ["#site-info .site-info-header", "#site-info .site-info-grid"]
  };
  const rects = selectors[currentId].map((selector) => {
    const rect = doc.querySelector(selector).getBoundingClientRect();
    return { selector, top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right, height: rect.height, centerY: rect.top + rect.height / 2 };
  });
  const top = Math.min(...rects.map((rect) => rect.top));
  const bottom = Math.max(...rects.map((rect) => rect.bottom));
  const prev = doc.querySelector(".page-prev-button");
  const next = doc.querySelector(".page-next-button");
  const prevStyle = getComputedStyle(prev);
  const nextStyle = getComputedStyle(next);
  const prevIcon = prev.querySelector(".page-next-icon");
  const nextIcon = next.querySelector(".page-next-icon");
  const prevIconRect = prevIcon.getBoundingClientRect();
  const nextIconRect = nextIcon.getBoundingClientRect();
  const lede = doc.querySelector("#agents .section-lede");
  const titleSelector = ({
    hero: "#hero-title",
    "teaching-loop": "#teaching-loop .section-title",
    product: "#product .section-title",
    "knowledge-story": "#knowledge-story .section-title",
    workflow: "#workflow .section-title",
    agents: "#agents .section-title",
    "site-info": "#site-info .site-info-title"
  })[currentId];
  const titleStyle = titleSelector ? getComputedStyle(doc.querySelector(titleSelector)) : null;
  const records = doc.querySelector("#demo .homepage-records");
  const recordsRect = records.getBoundingClientRect();
  const siteInfo = doc.querySelector("#site-info").textContent;
  const siteInfoPanels = doc.querySelectorAll("#site-info .site-info-panel");
  const blurTargets = Array.from(doc.querySelectorAll(
    "#teaching-loop [data-reveal], #product [data-reveal], #knowledge-story [data-reveal], #workflow [data-reveal], #agents [data-reveal]"
  ));
  const residualBlurs = blurTargets.flatMap((element) => {
    const filter = getComputedStyle(element).filter;
    return filter !== "none" && filter !== "blur(0px)"
      ? [{ id: element.closest("section")?.id || "", className: element.className, filter }]
      : [];
  });
  const workflowVisibleRects = currentId === "workflow"
    ? Array.from(doc.querySelectorAll("#workflow .section-kicker, #workflow .section-title, #workflow .section-lede"))
      .map((element) => element.getBoundingClientRect())
    : [];
  const workflowVisibleCenter = workflowVisibleRects.length
    ? (Math.min(...workflowVisibleRects.map((rect) => rect.top)) + Math.max(...workflowVisibleRects.map((rect) => rect.bottom))) / 2
    : null;
  return {
    id: currentId,
    viewportHeight: win.innerHeight,
    sectionTop: doc.getElementById(currentId).getBoundingClientRect().top,
    contentTop: top,
    contentBottom: bottom,
    contentCenterOffset: (top + bottom) / 2 - win.innerHeight / 2,
    complete: top >= -1 && bottom <= win.innerHeight + 1,
    rects,
    prev: { hidden: prev.hidden, bottom: win.innerHeight - prev.getBoundingClientRect().bottom, background: prevStyle.backgroundColor, border: prevStyle.borderStyle },
    next: { hidden: next.hidden, bottom: prev.ownerDocument.defaultView.innerHeight - next.getBoundingClientRect().bottom, background: nextStyle.backgroundColor, border: nextStyle.borderStyle },
    navigationUsesSameIcon: prevIcon.className === nextIcon.className,
    navigationIconCenterDifference: Math.abs((prevIconRect.top + prevIconRect.height / 2) - (nextIconRect.top + nextIconRect.height / 2)),
    prevIconTransform: getComputedStyle(prevIcon).transform,
    nextIconTransform: getComputedStyle(nextIcon).transform,
    hasResidualBlur: residualBlurs.length > 0,
    residualBlurs,
    titleSize: titleStyle?.fontSize || null,
    titleLineHeight: titleStyle?.lineHeight || null,
    recordsCentered: Math.abs((recordsRect.left + recordsRect.right) / 2 - win.innerWidth / 2) <= 1,
    recordsVisibleOnFirstPage: currentId !== "demo" || (recordsRect.top >= 0 && recordsRect.bottom <= win.innerHeight),
    recordTextComplete: records.textContent.includes("粤ICP备2026026176号") && records.textContent.includes("粤公网安备44010602016941号"),
    siteInfoComplete: siteInfo.includes("ArchSpark Lab｜筑火实验室")
      && siteInfo.includes("1611914241@qq.com")
      && siteInfo.includes("智能体")
      && siteInfo.includes("AI 使用说明")
      && siteInfo.includes("AI 生成内容可能存在错误")
      && siteInfo.includes("齐奕老师")
      && !siteInfo.includes("不替代教师评价与最终评分")
      && siteInfoPanels.length === 5,
    workflowColumnCenterDifference: currentId === "workflow" ? Math.abs(workflowVisibleCenter - rects[1].centerY) : null,
    workflowVisibleTextCenterOffset: currentId === "workflow" ? workflowVisibleCenter - win.innerHeight / 2 : null,
    agentLedeLines: currentId === "agents" ? Math.round(lede.getBoundingClientRect().height / parseFloat(getComputedStyle(lede).lineHeight)) : null,
    titleHasPeriod: Boolean(doc.querySelector("h1 .hero-line:last-child, h2 .title-line:last-child, .site-info-title")?.textContent.trim().endsWith("。"))
  };
})()`;

// 从第一页开始，完全通过页面上的下一页按钮完成逐屏检查。
async function run() {
  const targets = await fetch(endpoint).then((response) => response.json());
  const target = targets.find((item) => item.type === "page" && item.url.includes("127.0.0.1:4173"));
  if (!target) throw new Error("没有找到 ArchCritic 浏览器页面");

  await fs.mkdir(outputDir, { recursive: true });
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !requests.has(message.id)) return;
    const request = requests.get(message.id);
    requests.delete(message.id);
    if (message.error) request.reject(new Error(message.error.message));
    else request.resolve(message.result);
  });
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  await send(socket, "Page.enable");
  await send(socket, "Runtime.enable");
  await evaluate(socket, `(() => { const win = document.querySelector("iframe").contentWindow; win.scrollTo(0, 0); return true; })()`);
  await wait(250);

  const results = [];
  for (let index = 0; index < pages.length; index += 1) {
    const state = await evaluate(socket, inspectExpression);
    results.push(state);
    await capture(socket, `${String(index + 1).padStart(2, "0")}-${state.id}`);
    if (index < pages.length - 1) {
      await evaluate(socket, `document.querySelector("iframe").contentDocument.querySelector(".page-next-button").click()`);
      await wait(850);
    }
  }

  await evaluate(socket, `document.querySelector("iframe").contentDocument.querySelector(".page-prev-button").click()`);
  await wait(850);
  const upwardState = await evaluate(socket, inspectExpression);
  if (upwardState.id !== "agents") throw new Error(`向上翻页失败：实际到达 ${upwardState.id}`);
  const invalidPage = results.find((state) => !state.complete || Math.abs(state.contentCenterOffset) > 20 || state.hasResidualBlur);
  if (invalidPage) throw new Error(`页面布局或清晰度检查失败：${invalidPage.id}，中心偏差 ${invalidPage.contentCenterOffset}，残留滤镜 ${JSON.stringify(invalidPage.residualBlurs)}`);
  const workflowState = results.find((state) => state.id === "workflow");
  if (!workflowState || workflowState.workflowColumnCenterDifference > 2 || Math.abs(workflowState.workflowVisibleTextCenterOffset) > 2) {
    throw new Error("评图工作流可见文字没有与画面及右侧内容垂直居中");
  }
  const middleState = results.find((state) => state.id === "teaching-loop");
  if (!middleState?.navigationUsesSameIcon || Math.abs(middleState.prev.bottom - middleState.next.bottom) > 1 || middleState.navigationIconCenterDifference > 0.1) {
    throw new Error("上下翻页按钮未使用同款图标或没有并排放置");
  }
  const titleSizes = results.map((state) => state.titleSize).filter(Boolean);
  if (new Set(titleSizes).size !== 1) throw new Error(`首页白色大标题字号不一致：${titleSizes.join(", ")}`);
  const titleLineHeights = results.map((state) => state.titleLineHeight).filter(Boolean);
  if (new Set(titleLineHeights).size !== 1) throw new Error(`首页白色大标题行高不一致：${titleLineHeights.join(", ")}`);
  if (!results.every((state) => state.recordTextComplete) || !results[0].recordsCentered || !results[0].recordsVisibleOnFirstPage) {
    throw new Error("首屏备案信息缺失、未居中或超出画面");
  }
  if (!results.every((state) => state.siteInfoComplete)) throw new Error("末页作者、智能体入口或 AI 使用说明不完整");

  socket.close();
  if (process.argv.includes("--compact")) {
    console.log(JSON.stringify({
      pages: results.length,
      complete: results.filter((state) => state.complete).length,
      titleSizes: [...new Set(titleSizes)],
      titleLineHeights: [...new Set(titleLineHeights)],
      navigationIconCenterDifference: middleState.navigationIconCenterDifference,
      upwardCheck: upwardState.id
    }));
  } else {
    console.log(JSON.stringify({ pages: results, upwardCheck: upwardState.id }, null, 2));
  }
}

run().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
