// 知识库浏览页：复刻成员案例学习原型的右侧布局，并接入真实知识卡、案例卡和关联跳转。
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { PageProps } from "../App";
import { apiUrl } from "../api/client";
import { getCachedKnowledgeDetail, getCachedKnowledgeLibrary, getKnowledgeDetail, getKnowledgeLibrary, prefetchKnowledgeDetail, type KnowledgeAssistantResult, type KnowledgeImage, type KnowledgeKind, type KnowledgeLibraryDetail, type KnowledgeLibraryItem, type KnowledgeLibraryPayload } from "../api/knowledge";
import { Button, Sidebar, ZoomableImageStage } from "../components";
import { clearReportKnowledgeContext, readReportKnowledgeContext, saveReportKnowledgeContext, type ReportKnowledgeContext } from "../state/reportKnowledgeContext";
import { useWorkspace } from "../state/workspace";
import { KnowledgeAssistant } from "./knowledgeAssistant";
import { KnowledgeQuiz } from "./knowledgeQuiz";
import { ReportAssistant } from "./reportAssistant";

type LibraryTab = "all" | KnowledgeKind;
type LibraryView = "overview" | "detail";
type LibraryCounts = { all: number; knowledge: number; case: number };
type OverviewPosition = { scrollTop: number; itemId: string; itemOffset: number };
type AssistantBrowseSnapshot = { tab: LibraryTab; category: string; query: string; position: OverviewPosition };

const EMPTY_LIBRARY: KnowledgeLibraryPayload = {
  items: [],
  totals: { all: 0, knowledge: 0, case: 0 },
  levels: [],
  knowledge_categories: [],
  difficulties: [],
  building_types: [],
};
const SEARCH_HISTORY_KEY = "archcritic-knowledge-search-history";

// 渲染知识库主页面，并在总览与深度阅读之间切换。
export function KnowledgePage({ go }: PageProps) {
  const { chatMessages, report, sendQuestion, submission } = useWorkspace();
  const initialLibrary = getCachedKnowledgeLibrary();
  const [reportContext, setReportContext] = useState<ReportKnowledgeContext | null>(() => readReportKnowledgeContext());
  const [library, setLibrary] = useState<KnowledgeLibraryPayload>(initialLibrary ?? EMPTY_LIBRARY);
  const [view, setView] = useState<LibraryView>("overview");
  const [quizOpen, setQuizOpen] = useState(false);
  const [quizConfirmOpen, setQuizConfirmOpen] = useState(false);
  const [tab, setTab] = useState<LibraryTab>("all");
  const [category, setCategory] = useState("全部");
  const [overviewQuery, setOverviewQuery] = useState("");
  const [catalogQuery, setCatalogQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<KnowledgeLibraryDetail | null>(null);
  const [loading, setLoading] = useState(!initialLibrary);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<KnowledgeImage | null>(null);
  const [assistantResult, setAssistantResult] = useState<KnowledgeAssistantResult | null>(() => reportContext ? buildReportRecommendationResult(reportContext) : null);
  const [assistantQuery, setAssistantQuery] = useState("");
  const overviewPositionRef = useRef<OverviewPosition>({ scrollTop: 0, itemId: "", itemOffset: 0 });
  const assistantSnapshotRef = useRef<AssistantBrowseSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    void getKnowledgeLibrary(true)
      .then((payload) => active && setLibrary(payload))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : "知识库读取失败。"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!reportContext || !submission) return;
    if (reportContext.submissionId !== submission.id) {
      clearReportKnowledgeContext();
      setReportContext(null);
      setAssistantResult(null);
    }
  }, [reportContext, submission]);

  useEffect(() => {
    if (!reportContext) return;
    const latest = [...chatMessages].reverse().find((message) => message.role === "assistant" && message.tool === "knowledge_recommendation" && message.citations?.length);
    if (!latest?.citations?.length) return;
    if (!latest.id || latest.id <= (reportContext.lastMessageId ?? 0)) return;
    const citationsKey = latest.citations.map((item) => item.id).join("|");
    const currentKey = reportContext.citations.map((item) => item.id).join("|");
    if (citationsKey === currentKey) return;
    const next = { ...reportContext, citations: latest.citations, lastMessageId: latest.id, createdAt: Date.now() };
    saveReportKnowledgeContext(next.submissionId, next.citations, next.lastMessageId);
    setReportContext(next);
    setAssistantResult(buildReportRecommendationResult(next));
    setTab("all");
    setCategory("全部");
    setCatalogQuery("");
    setView("overview");
  }, [chatMessages, reportContext]);

  useEffect(() => {
    const pendingItemId = window.localStorage.getItem("archcritic-open-knowledge-item");
    if (!pendingItemId) return;
    window.localStorage.removeItem("archcritic-open-knowledge-item");
    setSelectedId(pendingItemId);
    setView("detail");
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    const cachedDetail = getCachedKnowledgeDetail(selectedId);
    if (cachedDetail) setDetail(cachedDetail);
    setDetailLoading(!cachedDetail);
    void getKnowledgeDetail(selectedId)
      .then((item) => active && setDetail(item))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : "卡片正文读取失败。"))
      .finally(() => active && setDetailLoading(false));
    return () => { active = false; };
  }, [selectedId]);

  const itemById = useMemo(() => new Map(library.items.map((item) => [item.id, item])), [library.items]);
  const assistantBaseItems = useMemo(() => assistantResult ? assistantResult.recommendations.map((item) => itemById.get(item.id)).filter((item): item is KnowledgeLibraryItem => Boolean(item)) : library.items, [assistantResult, itemById, library.items]);
  const activeOverviewQuery = assistantResult ? assistantQuery : overviewQuery;
  const overviewSearchItems = useMemo(() => filterItems(assistantBaseItems, "all", "全部", activeOverviewQuery.trim().toLowerCase()), [activeOverviewQuery, assistantBaseItems]);
  const catalogSearchItems = useMemo(() => filterItems(assistantBaseItems, "all", "全部", catalogQuery.trim().toLowerCase()), [assistantBaseItems, catalogQuery]);
  const categories = useMemo(() => {
    const allCategories = tab === "knowledge" ? library.levels : tab === "case" ? library.building_types : [...library.levels, ...library.building_types];
    if (tab === "all") return allCategories;
    const resultCategoryNames = new Set(
      overviewSearchItems
        .filter((item) => item.kind === tab)
        .map((item) => item.category),
    );
    if (!assistantResult && !activeOverviewQuery.trim()) return allCategories;
    return allCategories.filter((item) => resultCategoryNames.has(item));
  }, [activeOverviewQuery, assistantResult, library.building_types, library.levels, overviewSearchItems, tab]);
  const displayedCategory = category !== "全部" && !categories.includes(category) ? "全部" : category;
  const overviewItems = useMemo(() => filterItems(overviewSearchItems, tab, displayedCategory, ""), [displayedCategory, overviewSearchItems, tab]);
  const catalogItems = useMemo(() => sortLibraryItems(filterItems(catalogSearchItems, tab, "全部", ""), tab === "all"), [catalogSearchItems, tab]);
  const overviewCounts = useMemo(() => countKinds(overviewSearchItems), [overviewSearchItems]);
  const catalogCounts = useMemo(() => countKinds(catalogSearchItems), [catalogSearchItems]);
  const visibleDetail = detail?.id === selectedId ? detail : null;

  // 打开真实卡片详情，保持成员原型中的总览到阅读页切换逻辑。
  const openItem = (itemId: string, nextCatalogQuery?: string) => {
    if (nextCatalogQuery !== undefined) setCatalogQuery(nextCatalogQuery);
    setSelectedId(itemId);
    setView("detail");
  };

  // 关联跳转可能跨越知识卡与案例卡，需要同步目录筛选条件。
  const openRelated = (itemId: string) => {
    const target = library.items.find((item) => item.id === itemId);
    if (target) {
      setTab(target.kind);
      setCategory("全部");
      setCatalogQuery("");
    }
    openItem(itemId);
  };

  const selectTab = (nextTab: LibraryTab) => {
    setTab(nextTab);
    setCategory("全部");
  };

  // 详情中清空搜索时同步清除总览关键词，但保留当前标签和分类。
  const clearDetailSearch = () => {
    setCatalogQuery("");
    if (assistantResult) setAssistantQuery("");
    else setOverviewQuery("");
  };

  // 首次进入 AI 推荐时保存原总览，后续调整条件不覆盖这份快照。
  const applyAssistantResult = (result: KnowledgeAssistantResult) => {
    if (result.ui_action !== "show_assistant_results" && result.ui_action !== "update_assistant_results") return;
    if (!assistantSnapshotRef.current) {
      assistantSnapshotRef.current = { tab, category, query: overviewQuery, position: { ...overviewPositionRef.current } };
    }
    setAssistantResult(result);
    setAssistantQuery("");
    setCatalogQuery("");
    setTab("all");
    setCategory("全部");
    setView("overview");
    overviewPositionRef.current = { scrollTop: 0, itemId: result.recommendations[0]?.id ?? "", itemOffset: 0 };
  };

  // 退出 AI 推荐后精确恢复进入前的标签、分类、搜索和滚动位置。
  const exitAssistantResults = () => {
    if (reportContext) {
      clearReportKnowledgeContext();
      go("report");
      return;
    }
    const snapshot = assistantSnapshotRef.current;
    if (snapshot) {
      setTab(snapshot.tab);
      setCategory(snapshot.category);
      setOverviewQuery(snapshot.query);
      overviewPositionRef.current = snapshot.position;
    }
    setAssistantResult(null);
    setAssistantQuery("");
    setCatalogQuery("");
    setView("overview");
    assistantSnapshotRef.current = null;
  };

  return (
    <div className="font-chat relative h-full w-full bg-[#f4f6f8]">
      <Sidebar go={go} />
      <main className="knowledge-workspace" aria-live="polite">
        {quizOpen ? <section className="knowledge-view knowledge-view-active"><KnowledgeHeader eyebrow="按分类和难度检验你的知识掌握程度" action={<Button kind="white" className="report-top-action-button" onClick={() => setQuizOpen(false)}>返回知识库</Button>} /><KnowledgeQuiz onOpenCard={(itemId) => { setQuizOpen(false); openItem(itemId); }} /></section> : view === "overview" ? (
          <OverviewView library={library} searchItems={overviewSearchItems} counts={overviewCounts} items={overviewItems} loading={loading} error={error} tab={tab} category={displayedCategory} categories={categories} query={activeOverviewQuery} assistantResult={assistantResult} assistantReturnLabel={reportContext ? "返回报告界面" : "返回原总览"} restorePosition={overviewPositionRef.current} onPositionChange={(position) => { overviewPositionRef.current = position; }} onQuery={assistantResult ? setAssistantQuery : setOverviewQuery} onExitAssistant={exitAssistantResults} onAdjustAssistant={() => window.dispatchEvent(new Event(reportContext ? "open-report-assistant" : "open-knowledge-assistant"))} onQuiz={() => setQuizConfirmOpen(true)} onTab={selectTab} onCategory={setCategory} onOpen={(itemId, position) => { overviewPositionRef.current = position; openItem(itemId, activeOverviewQuery); }} />
        ) : (
          <DetailView counts={catalogCounts} searchItems={catalogSearchItems} items={catalogItems} detail={visibleDetail} selectedId={selectedId} loading={detailLoading} tab={tab} query={catalogQuery} itemById={itemById} hideEmptyTypes={Boolean(assistantResult)} backLabel={assistantResult ? "返回推荐总览" : "返回知识库总览"} onQuery={setCatalogQuery} onClearQuery={clearDetailSearch} onTab={selectTab} onOpen={openItem} onRelated={openRelated} onPreview={setPreview} onBack={() => { setCatalogQuery(""); setView("overview"); }} />
        )}
      </main>
      {reportContext && submission ? <ReportAssistant submissionId={submission.id} messages={chatMessages} report={report} sendQuestion={sendQuestion} go={go} /> : <KnowledgeAssistant view={view} tab={tab} category={displayedCategory} currentItem={view === "detail" ? itemById.get(selectedId) ?? null : null} resultSetId={assistantResult?.result_set_id ?? null} onResult={applyAssistantResult} onOpenItem={(itemId) => { if (itemById.has(itemId)) openItem(itemId, activeOverviewQuery); }} />}
      {quizConfirmOpen && <QuizConfirmOverlay onCancel={() => setQuizConfirmOpen(false)} onConfirm={() => { setQuizConfirmOpen(false); setQuizOpen(true); }} />}
      {preview && <ZoomableImageStage className="z-[100] bg-[#171719]/75" src={apiUrl(preview.url)} alt={preview.name} onClose={() => setPreview(null)} />}
    </div>
  );
}

// 渲染成员原型中的案例瀑布流总览。
function OverviewView({ library, searchItems, counts, items, loading, error, tab, category, categories, query, assistantResult, assistantReturnLabel, restorePosition, onPositionChange, onQuery, onExitAssistant, onAdjustAssistant, onQuiz, onTab, onCategory, onOpen }: {
  library: KnowledgeLibraryPayload;
  searchItems: KnowledgeLibraryItem[];
  counts: LibraryCounts;
  items: KnowledgeLibraryItem[];
  loading: boolean;
  error: string;
  tab: LibraryTab;
  category: string;
  categories: string[];
  query: string;
  assistantResult: KnowledgeAssistantResult | null;
  assistantReturnLabel: string;
  restorePosition: OverviewPosition;
  onPositionChange: (position: OverviewPosition) => void;
  onQuery: (value: string) => void;
  onExitAssistant: () => void;
  onAdjustAssistant: () => void;
  onQuiz: () => void;
  onTab: (tab: LibraryTab) => void;
  onCategory: (category: string) => void;
  onOpen: (id: string, position: OverviewPosition) => void;
}) {
  const overviewScrollRef = useRef<HTMLDivElement>(null);

  // 返回总览时优先按原卡片锚点恢复，列表变化时也能回到对应内容附近。
  useLayoutEffect(() => {
    const scrollArea = overviewScrollRef.current;
    if (!scrollArea) return;
    const anchoredCard = restorePosition.itemId
      ? scrollArea.querySelector<HTMLElement>(`[data-knowledge-id="${restorePosition.itemId}"]`)
      : null;
    const desiredScrollTop = anchoredCard
      ? scrollArea.scrollTop + anchoredCard.getBoundingClientRect().top - scrollArea.getBoundingClientRect().top - restorePosition.itemOffset
      : restorePosition.scrollTop;
    const maxScrollTop = Math.max(0, scrollArea.scrollHeight - scrollArea.clientHeight);
    scrollArea.scrollTop = Math.min(maxScrollTop, Math.max(0, desiredScrollTop));
  }, [restorePosition]);

  return (
    <section className="knowledge-view knowledge-view-overview knowledge-view-active">
      <KnowledgeHeader eyebrow={assistantResult ? "根据你的设计条件整理" : "知识与案例学习"} />
      {assistantResult && <AssistantResultBanner result={assistantResult} returnLabel={assistantReturnLabel} onAdjust={onAdjustAssistant} onExit={onExitAssistant} />}
      <div className="knowledge-overview-tools">
        <KnowledgeFilters counts={counts} items={searchItems} tab={tab} category={category} categories={categories} withCount hideEmpty={Boolean(assistantResult)} onQuiz={assistantResult ? undefined : onQuiz} onTab={onTab} onCategory={onCategory} />
        <SearchInput value={query} placeholder="搜索标题、编号或关键词" onChange={onQuery} onClear={() => onQuery("")} />
      </div>
      <div className="knowledge-masonry-wrap knowledge-scroll" ref={overviewScrollRef} onScroll={(event) => onPositionChange({ scrollTop: event.currentTarget.scrollTop, itemId: "", itemOffset: 0 })}>
        {loading && <EmptyState text="正在读取本地知识库…" />}
        {!loading && error && !library.items.length && <EmptyState text={error} />}
        {!loading && !error && !items.length && <EmptyState text="没有找到相关知识卡或案例。" />}
        {!loading && items.length > 0 && <OverviewMasonry items={items} tab={tab} recommendations={assistantResult?.recommendations ?? []} onOpen={onOpen} />}
      </div>
    </section>
  );
}

// 显示本轮 AI 提取条件，并提供调整和恢复原总览入口。
function AssistantResultBanner({ result, returnLabel, onAdjust, onExit }: { result: KnowledgeAssistantResult; returnLabel: string; onAdjust: () => void; onExit: () => void }) {
  const conditions = result.extracted_conditions;
  const caseCount = result.recommendations.filter((item) => item.kind === "case").length;
  const knowledgeCount = result.recommendations.length - caseCount;
  const labels = [
    ...((conditions.building_types as string[] | undefined) ?? []),
    conditions.area_target_sqm ? `约 ${Math.round(Number(conditions.area_target_sqm))}㎡` : "",
    ...((conditions.site_contexts as string[] | undefined) ?? []),
    ...((conditions.dimensions as string[] | undefined) ?? []),
  ].filter(Boolean);
  return <div className="knowledge-assistant-result-banner"><div><span>AI 为你推荐</span><strong>{labels.join(" · ") || "根据本轮对话整理的学习内容"}</strong><small>共 {result.recommendations.length} 张卡片 · 案例 {caseCount} · 知识卡 {knowledgeCount}，推荐理由仅基于当前知识库。</small></div><div><button type="button" onClick={onAdjust}>调整条件</button><button type="button" className="primary" onClick={onExit}>{returnLabel}</button></div></div>;
}

// 把报告助手的真实引用转换为知识库现有的推荐结果总览结构。
function buildReportRecommendationResult(context: ReportKnowledgeContext): KnowledgeAssistantResult {
  const recommendations = context.citations.map((item) => ({
    id: item.id,
    kind: item.id.startsWith("PBC-") ? "case" as const : "knowledge" as const,
    reason: "结合当前报告问题推荐",
    matched_fields: ["当前报告"],
    limitations: [],
    score: 0,
    review_status: "",
    human_review_confirmed: false,
  }));
  return {
    answer: "根据当前报告整理相关案例与知识卡。",
    intent: "knowledge_query",
    clarification_required: false,
    extracted_conditions: {},
    recommendations,
    citations: context.citations,
    result_set_id: null,
    ui_action: "show_assistant_results",
  };
}

// “全部”严格先展示完案例，再在下方展示知识卡。
function OverviewMasonry({ items, tab, recommendations, onOpen }: { items: KnowledgeLibraryItem[]; tab: LibraryTab; recommendations: KnowledgeAssistantResult["recommendations"]; onOpen: (id: string, position: OverviewPosition) => void }) {
  const recommendationById = new Map(recommendations.map((item) => [item.id, item]));
  if (recommendations.length > 0) {
    return <OverviewGrid items={items} className="knowledge-grid-full knowledge-ai-result-grid" recommendationById={recommendationById} onOpen={onOpen} />;
  }
  if (tab === "all") {
    const cases = sortLibraryItems(items.filter((item) => item.kind === "case"), false);
    const knowledge = sortLibraryItems(items.filter((item) => item.kind === "knowledge"), false);
    return <div className="knowledge-overview-stacked">
      {cases.length > 0 && <OverviewGrid items={cases} className="knowledge-grid-full knowledge-overview-case-section" recommendationById={recommendationById} onOpen={onOpen} />}
      {knowledge.length > 0 && <OverviewGrid items={knowledge} className="knowledge-grid-full knowledge-overview-knowledge-section" recommendationById={recommendationById} onOpen={onOpen} />}
    </div>;
  }
  return <OverviewGrid items={sortLibraryItems(items, false)} className="knowledge-grid-full" recommendationById={recommendationById} onOpen={onOpen} />;
}

// 使用普通网格按从左到右的顺序排卡，避免瀑布流出现跨栏和中间空洞。
function OverviewGrid({ items, className, recommendationById, onOpen }: { items: KnowledgeLibraryItem[]; className: string; recommendationById: Map<string, KnowledgeAssistantResult["recommendations"][number]>; onOpen: (id: string, position: OverviewPosition) => void }) {
  return <div className={`knowledge-card-grid ${className}`}>{items.map((item, index) => <OverviewCard item={item} index={index} recommendation={recommendationById.get(item.id)} onClick={(position) => onOpen(item.id, position)} key={item.id} />)}</div>;
}

// 渲染成员原型中的左侧目录和右侧深度阅读。
function DetailView({ counts, searchItems, items, detail, selectedId, loading, tab, query, itemById, hideEmptyTypes, backLabel, onQuery, onClearQuery, onTab, onOpen, onRelated, onPreview, onBack }: {
  counts: LibraryCounts;
  searchItems: KnowledgeLibraryItem[];
  items: KnowledgeLibraryItem[];
  detail: KnowledgeLibraryDetail | null;
  selectedId: string;
  loading: boolean;
  tab: LibraryTab;
  query: string;
  itemById: Map<string, KnowledgeLibraryItem>;
  hideEmptyTypes: boolean;
  backLabel: string;
  onQuery: (value: string) => void;
  onClearQuery: () => void;
  onTab: (tab: LibraryTab) => void;
  onOpen: (id: string) => void;
  onRelated: (id: string) => void;
  onPreview: (image: KnowledgeImage) => void;
  onBack: () => void;
}) {
  const catalogListRef = useRef<HTMLDivElement>(null);

  // 进入详情或切换卡片后，把当前选中项定位到左侧目录可视区域中央。
  useLayoutEffect(() => {
    const catalogList = catalogListRef.current;
    const selectedCard = catalogList?.querySelector<HTMLElement>(".knowledge-catalog-item.selected");
    if (!catalogList || !selectedCard) return;
    const listRect = catalogList.getBoundingClientRect();
    const cardRect = selectedCard.getBoundingClientRect();
    const centeredTop = catalogList.scrollTop + cardRect.top - listRect.top - (catalogList.clientHeight - cardRect.height) / 2;
    const maxScrollTop = Math.max(0, catalogList.scrollHeight - catalogList.clientHeight);
    catalogList.scrollTop = Math.min(maxScrollTop, Math.max(0, centeredTop));
  }, [items, selectedId]);

  return (
    <section className="knowledge-view knowledge-view-detail knowledge-view-active">
      <KnowledgeHeader eyebrow="知识与案例学习 / 深度阅读" action={<Button kind="white" className="knowledge-back report-top-action-button" onClick={onBack}>{backLabel}</Button>} />
      <div className="knowledge-detail-layout">
        <aside className="knowledge-catalog">
          <SearchInput value={query} placeholder="搜索标题、编号或关键词" onChange={onQuery} onClear={onClearQuery} />
          <KnowledgeFilters counts={counts} items={searchItems} tab={tab} category="全部" categories={[]} compact withCount hideEmpty={hideEmptyTypes} showCategories={false} onTab={onTab} onCategory={() => undefined} />
          <div className="knowledge-catalog-list knowledge-scroll" ref={catalogListRef}>
            {!items.length && <EmptyState text="没有找到相关卡片。" />}
            {items.map((item, index) => <CatalogCard item={item} index={index} active={selectedId === item.id} onClick={() => onOpen(item.id)} key={item.id} />)}
          </div>
        </aside>
        <article className="knowledge-reader knowledge-scroll">
          {loading && !detail ? <EmptyState text="正在读取卡片正文…" /> : detail ? <KnowledgeDetail detail={detail} itemById={itemById} onRelated={onRelated} onPreview={onPreview} /> : <EmptyState text="请选择一张卡片查看内容。" />}
        </article>
      </div>
    </section>
  );
}

// 渲染知识库页面标题和右侧信息。
function KnowledgeHeader({ eyebrow, action }: { eyebrow: string; action?: ReactNode }) {
  return <header className="knowledge-view-header"><div><h1>知识库</h1><p>{eyebrow}</p></div>{action}</header>;
}

// 渲染类型和分类筛选，保留当前系统两级筛选能力。
function KnowledgeFilters({ counts, items, tab, category, categories, withCount = false, compact = false, hideEmpty = false, showCategories = true, onQuiz, onTab, onCategory }: {
  counts: LibraryCounts;
  items: KnowledgeLibraryItem[];
  tab: LibraryTab;
  category: string;
  categories: string[];
  withCount?: boolean;
  compact?: boolean;
  hideEmpty?: boolean;
  showCategories?: boolean;
  onQuiz?: () => void;
  onTab: (tab: LibraryTab) => void;
  onCategory: (category: string) => void;
}) {
  const categoryScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (categoryScrollRef.current) categoryScrollRef.current.scrollLeft = 0;
  }, [categories, tab]);

  return (
    <div className={`knowledge-filter-bar ${compact ? "knowledge-filter-compact" : ""}`}>
      <div className="knowledge-primary-filters">
        <FilterButton active={tab === "all"} label="全部" count={withCount ? counts.all : undefined} onClick={() => onTab("all")} />
        {(!hideEmpty || counts.case > 0) && <FilterButton active={tab === "case"} label="建筑案例" count={withCount ? counts.case : undefined} onClick={() => onTab("case")} />}
        {(!hideEmpty || counts.knowledge > 0) && <FilterButton active={tab === "knowledge"} label="知识卡" count={withCount ? counts.knowledge : undefined} onClick={() => onTab("knowledge")} />}
        {onQuiz && <FilterButton active={false} label="知识测试" onClick={onQuiz} />}
      </div>
      {showCategories && tab !== "all" && categories.length > 0 && <><span className="knowledge-filter-divider" /><div className="knowledge-category-scroll" ref={categoryScrollRef}><div className="knowledge-category-filters"><FilterButton active={category === "全部"} label="全部分类" onClick={() => onCategory("全部")} />{categories.map((item) => <FilterButton active={category === item} label={item} count={withCount ? filteredCount(items, tab, item) : undefined} onClick={() => onCategory(item)} key={item} />)}</div></div></>}
    </div>
  );
}

// 进入知识测试前先说明测试方式，避免误触后直接切换页面。
function QuizConfirmOverlay({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  return <div className="knowledge-quiz-confirm-overlay" onClick={onCancel}><section role="dialog" aria-modal="true" aria-labelledby="knowledge-quiz-confirm-title" onClick={(event) => event.stopPropagation()}><span>知识测试</span><h2 id="knowledge-quiz-confirm-title">确定进入知识测试吗？</h2><p>你可以选择知识分类和难度，通过知识卡中的自测题检验学习情况。测试过程中可以随时返回知识库。</p><div><button type="button" onClick={onCancel}>暂不进入</button><button type="button" className="primary" onClick={onConfirm}>开始测试</button></div></section></div>;
}

// 渲染单个横向筛选按钮。
function FilterButton({ active, label, count, onClick }: { active: boolean; label: string; count?: number; onClick: () => void }) {
  return <button type="button" className={`knowledge-filter ${active ? "active" : ""}`} onClick={onClick}>{label}{count !== undefined && <span>{count}</span>}</button>;
}

// 从浏览器读取最近三条有效搜索记录。
function readSearchHistory(): string[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(SEARCH_HISTORY_KEY) ?? "[]");
    const history = Array.isArray(value) ? value.filter((item): item is string => typeof item === "string").slice(0, 3) : [];
    window.localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(history));
    return history;
  } catch {
    return [];
  }
}

// 保存搜索记录并自动去重，只保留最近三条。
function saveSearchHistory(query: string): string[] {
  const next = [query, ...readSearchHistory().filter((item) => item !== query)].slice(0, 3);
  try {
    window.localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next));
  } catch {
    return next;
  }
  return next;
}

// 输入内容只作草稿，按回车或点击历史记录后才真正搜索。
function SearchInput({ value, placeholder, onChange, onClear }: { value: string; placeholder: string; onChange: (value: string) => void; onClear?: () => void }) {
  const [draft, setDraft] = useState(value);
  const [history, setHistory] = useState<string[]>(readSearchHistory);
  const [historyOpen, setHistoryOpen] = useState(false);
  useEffect(() => setDraft(value), [value]);
  const clearSearch = () => {
    setDraft("");
    if (onClear) onClear();
    else onChange("");
    setHistoryOpen(false);
  };
  const submitSearch = (rawValue: string) => {
    const query = rawValue.trim();
    if (!query) {
      clearSearch();
      return;
    }
    setDraft(query);
    onChange(query);
    setHistory(saveSearchHistory(query));
    setHistoryOpen(false);
  };
  return (
    <div className="knowledge-search-wrap">
      <button type="button" className="knowledge-search-submit" aria-label="搜索" onMouseDown={(event) => event.preventDefault()} onClick={() => submitSearch(draft)}><span /></button>
      <input
        className="knowledge-search"
        aria-label={placeholder}
        placeholder={placeholder}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onFocus={() => { setHistory(readSearchHistory()); setHistoryOpen(true); }}
        onClick={() => { setHistory(readSearchHistory()); setHistoryOpen(true); }}
        onBlur={(event) => { if (!event.currentTarget.parentElement?.contains(event.relatedTarget)) setHistoryOpen(false); }}
        onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); submitSearch(draft); } }}
      />
      {value && <button type="button" className="knowledge-search-clear" aria-label="清空搜索" onMouseDown={(event) => event.preventDefault()} onClick={clearSearch}>×</button>}
      {historyOpen && history.length > 0 && <div className="knowledge-search-history" aria-label="最近搜索">{history.map((item) => <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => submitSearch(item)} key={item}><span>↗</span>{item}</button>)}</div>}
    </div>
  );
}

// 渲染总览瀑布流卡片。
function OverviewCard({ item, index, recommendation, onClick }: { item: KnowledgeLibraryItem; index: number; recommendation?: KnowledgeAssistantResult["recommendations"][number]; onClick: (position: OverviewPosition) => void }) {
  const textOnly = item.kind === "knowledge" && !item.thumbnail;
  return (
    <button type="button" data-knowledge-id={item.id} className={`knowledge-overview-card ${textOnly ? "knowledge-card-text-only" : ""} ${knowledgeLevelClass(item)}`} onPointerEnter={() => prefetchKnowledgeDetail(item.id)} onFocus={() => prefetchKnowledgeDetail(item.id)} onClick={(event) => {
      const scrollArea = event.currentTarget.closest<HTMLElement>(".knowledge-masonry-wrap");
      const itemOffset = scrollArea ? event.currentTarget.getBoundingClientRect().top - scrollArea.getBoundingClientRect().top : 0;
      onClick({ scrollTop: scrollArea?.scrollTop ?? 0, itemId: item.id, itemOffset });
    }}>
      <KnowledgeVisual item={item} index={index} mode="overview" />
      <span className="knowledge-card-content"><span className="knowledge-card-meta">{item.kind_label} / {item.level_label || item.category}</span><strong>{item.title}</strong><span className="knowledge-card-id">{item.id}</span><span className="knowledge-card-excerpt">{item.excerpt}</span>{recommendation && <span className="knowledge-ai-reason"><b>推荐理由</b>{recommendation.reason}<small>部分内容可能存在遗漏或偏差，请留意核对</small></span>}</span>
    </button>
  );
}

// 渲染详情目录中的紧凑卡片。
function CatalogCard({ item, index, active, onClick }: { item: KnowledgeLibraryItem; index: number; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`knowledge-catalog-item ${active ? "selected" : ""} ${item.kind === "knowledge" && !item.thumbnail ? "knowledge-catalog-text-only" : ""} ${knowledgeLevelClass(item)}`} onPointerEnter={() => prefetchKnowledgeDetail(item.id)} onFocus={() => prefetchKnowledgeDetail(item.id)} onClick={onClick}>
      <KnowledgeVisual item={item} index={index} mode="catalog" />
      <span><small>{item.id} · {item.level_label || item.category}</small><strong>{item.title}</strong><span>{item.excerpt}</span></span>
    </button>
  );
}

// 用三档紫色区分入门、进阶和研习知识卡。
function knowledgeLevelClass(item: KnowledgeLibraryItem): string {
  if (item.kind !== "knowledge") return "";
  if (item.level === "beginner") return "knowledge-level-beginner";
  if (item.level === "master") return "knowledge-level-master";
  return "knowledge-level-advanced";
}

// 知识卡使用纯文字版式，案例优先使用真实缩略图并保留缺图兜底。
function KnowledgeVisual({ item, index, mode }: { item: KnowledgeLibraryItem; index: number; mode: "overview" | "catalog" }) {
  if (item.thumbnail) return <img className={`knowledge-visual knowledge-visual-${mode}`} src={apiUrl(item.thumbnail)} alt="" loading="lazy" decoding="async" />;
  if (item.kind === "knowledge") return null;
  return <span className={`knowledge-visual knowledge-visual-${mode} knowledge-visual-tone-${index % 6}`}><i /><b>C</b></span>;
}

// 渲染卡片详情及可跳转关联。
function KnowledgeDetail({ detail, itemById, onRelated, onPreview }: { detail: KnowledgeLibraryDetail; itemById: Map<string, KnowledgeLibraryItem>; onRelated: (id: string) => void; onPreview: (image: KnowledgeImage) => void }) {
  return (
    <div className="knowledge-reader-inner">
      <p className="knowledge-breadcrumb">{detail.kind_label} / {detail.level_label || detail.category} · {detail.id}</p>
      <h2>{detail.title}</h2>
      <p className="knowledge-lead">{detail.excerpt}</p>
      <div className="knowledge-article"><MarkdownBody content={detail.content} images={detail.images} itemById={itemById} onRelated={onRelated} onPreview={onPreview} /></div>
    </div>
  );
}

// 用轻量方式显示知识库既有 Markdown，保留图片在原文中的对应位置。
function MarkdownBody({ content, images, itemById, onRelated, onPreview }: { content: string; images: KnowledgeImage[]; itemById: Map<string, KnowledgeLibraryItem>; onRelated: (id: string) => void; onPreview: (image: KnowledgeImage) => void }) {
  const imageByName = useMemo(() => new Map(images.map((image) => [image.name, image])), [images]);
  let relationSection = false;
  return <>{content.split("\n").map((rawLine, index) => {
    const line = rawLine.trim();
    if (!line || (index === 0 && line.startsWith("# "))) return null;
    const imageMatch = line.match(/^!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]$/) ?? line.match(/^!\[[^\]]*\]\(([^)]+)\)$/);
    if (imageMatch) {
      const name = imageMatch[1].split("/").pop() ?? imageMatch[1];
      const image = imageByName.get(name);
      return image ? <button type="button" className="knowledge-article-image" onClick={() => onPreview(image)} key={`${name}-${index}`}><img src={apiUrl(image.url)} alt={name} loading="lazy" decoding="async" /><span>点击查看原图 · {name}</span></button> : null;
    }
    if (line.startsWith("## ")) {
      const heading = plainInline(line.slice(3));
      relationSection = ["关联知识卡", "关联案例", "相近案例"].includes(heading);
      return <h3 key={index}>{heading}</h3>;
    }
    if (line.startsWith("### ")) return <h4 key={index}>{plainInline(line.slice(4))}</h4>;
    if (line.startsWith(">")) return <blockquote key={index}>{plainInline(line.replace(/^>\s*/, ""))}</blockquote>;
    const relationMatch = relationSection ? line.match(/^[-*]\s+\[\[([^\]|]+)(?:\|([^\]]+))?\]\]$/) : null;
    if (relationMatch) {
      const target = relationMatch[1];
      const itemId = (relationMatch[2] ?? target).match(/(?:KC-[A-Z]+-\d+|PBC-\d+)/i)?.[0]?.toUpperCase() ?? "";
      const targetItem = itemById.get(itemId);
      const title = targetItem?.title ?? target.replace(/^(?:KC-[A-Z]+-\d+|PBC-\d+)_?/i, "");
      return <div className="knowledge-relation-row" key={index}><span>•</span><button type="button" disabled={!targetItem} onClick={() => targetItem && onRelated(itemId)}>{itemId}{title ? ` · ${title}` : ""}</button></div>;
    }
    if (/^[-*]\s+/.test(line)) return <div className="knowledge-list-row" key={index}><span>•</span><p>{plainInline(line.replace(/^[-*]\s+/, ""))}</p></div>;
    if (/^（.+）$/.test(line)) return <p className="knowledge-image-caption" key={index}>{plainInline(line)}</p>;
    if ((line.match(/→/g) ?? []).length >= 2) return <p className="knowledge-flow-line" key={index}>{plainInline(line)}</p>;
    if (/^\d+[.、]\s*/.test(line)) return <p key={index}>{plainInline(line)}</p>;
    if (line.startsWith("|")) return <p className="knowledge-table-line" key={index}>{line}</p>;
    return <p key={index}>{plainInline(line)}</p>;
  })}</>;
}

// 过滤知识库列表，供总览与详情目录共同使用。
function filterItems(items: KnowledgeLibraryItem[], tab: LibraryTab, category: string, query: string): KnowledgeLibraryItem[] {
  return items.filter((item) => {
    if (tab !== "all" && item.kind !== tab) return false;
    if (category !== "全部" && item.category !== category && item.level_label !== category) return false;
    if (!query) return true;
    return `${item.id} ${item.title} ${item.excerpt} ${item.category} ${item.level_label}`.toLowerCase().includes(query);
  });
}

// 计算某个筛选项下的卡片数量。
function filteredCount(items: KnowledgeLibraryItem[], tab: LibraryTab, category: string): number {
  return items.filter((item) => (tab === "all" || item.kind === tab) && (item.category === category || item.level_label === category)).length;
}

// 根据当前搜索结果实时计算全部、案例和知识卡数量。
function countKinds(items: KnowledgeLibraryItem[]): LibraryCounts {
  const caseCount = items.filter((item) => item.kind === "case").length;
  return { all: items.length, case: caseCount, knowledge: items.length - caseCount };
}

// 案例优先展示；知识卡严格按入门、进阶、研习、规范应用排列。
function sortLibraryItems(items: KnowledgeLibraryItem[], casesFirst: boolean): KnowledgeLibraryItem[] {
  const levelOrder: Record<string, number> = { 入门: 0, 进阶: 1, 研习: 2, 规范应用: 3 };
  return [...items].sort((left, right) => {
    if (casesFirst && left.kind !== right.kind) return left.kind === "case" ? -1 : 1;
    if (left.kind === "knowledge" && right.kind === "knowledge") {
      const levelDifference = (levelOrder[left.level_label] ?? 4) - (levelOrder[right.level_label] ?? 4);
      if (levelDifference) return levelDifference;
    }
    return left.id.localeCompare(right.id, undefined, { numeric: true });
  });
}

// 清理行内 Markdown 和 Obsidian 链接，避免把编辑符号展示给学生。
function plainInline(value: string): string {
  return value.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2").replace(/\[\[([^\]]+)\]\]/g, "$1").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/\\\./g, ".").replace(/[`*_]/g, "");
}

// 渲染加载、错误或空列表状态。
function EmptyState({ text }: { text: string }) {
  return <div className="knowledge-empty">{text}</div>;
}
