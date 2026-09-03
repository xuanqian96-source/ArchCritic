// 知识测试：每次按难度抽取五题，支持自由浏览、即时判定、错题集和中途退出总结。
import { useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "../api/client";
import {
  getKnowledgeQuiz,
  getCachedKnowledgeQuiz,
  submitKnowledgeQuizAnswer,
  type KnowledgeQuizAnswerResult,
  type KnowledgeQuizPayload,
  type KnowledgeQuizQuestion,
} from "../api/knowledge";
import { AppPromptOverlay } from "../components/baseComponents";

const EMPTY_QUIZ: KnowledgeQuizPayload = { questions: [], difficulties: [] };
const SESSION_KEY = "archcritic-knowledge-quiz-session-v3";
const WRONG_BOOK_KEY = "archcritic-knowledge-quiz-wrong-book-v1";
const QUESTIONS_PER_QUIZ = 5;
const DIFFICULTY_DETAILS: Record<string, { order: string; kicker: string; description: string }> = {
  beginner: { order: "01", kicker: "建立基础判断", description: "从场地、功能与空间的核心概念开始，适合首次测试。" },
  advanced: { order: "02", kicker: "连接设计条件", description: "综合多项设计条件进行判断，检验知识迁移能力。" },
  master: { order: "03", kicker: "处理复杂议题", description: "关注运营、社会性与综合策略，适合深入复盘。" },
};

type QuizAnswer = string | string[];
type StoredQuizSession = {
  difficulty: string;
  questionIds: string[];
  index: number;
  answers: Record<string, QuizAnswer>;
  results: Record<string, KnowledgeQuizAnswerResult>;
};
type WrongBookItem = {
  question: KnowledgeQuizQuestion;
  correctAnswers: string[];
  answerPoints: string[];
  explanation: string;
  savedAt: number;
};

// 读取当前浏览器中尚未结束的知识测试进度。
function readStoredSession(): StoredQuizSession | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(SESSION_KEY) ?? "null") as Partial<StoredQuizSession> | null;
    if (!value?.difficulty || !Array.isArray(value.questionIds) || !value.questionIds.length || typeof value.index !== "number") return null;
    return { difficulty: value.difficulty, questionIds: value.questionIds, index: value.index, answers: value.answers ?? {}, results: value.results ?? {} };
  } catch {
    return null;
  }
}

// 读取历史错题，异常数据直接忽略。
function readWrongBook(): WrongBookItem[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(WRONG_BOOK_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item): item is WrongBookItem => Boolean(item?.question?.id && Array.isArray(item.correctAnswers))) : [];
  } catch {
    return [];
  }
}

// 渲染知识测试的难度选择、五题测试、错题集和结果页。
export function KnowledgeQuiz({ onOpenCard, exitRequest, onExit }: { onOpenCard: (cardId: string) => void; exitRequest: number; onExit: () => void }) {
  const stored = useMemo(readStoredSession, []);
  const initialPayload = useMemo(() => getCachedKnowledgeQuiz(), []);
  const [payload, setPayload] = useState(initialPayload ?? EMPTY_QUIZ);
  const [difficulty, setDifficulty] = useState(stored?.difficulty ?? "");
  const [questionIds, setQuestionIds] = useState(stored?.questionIds ?? []);
  const [index, setIndex] = useState(stored?.index ?? 0);
  const [answers, setAnswers] = useState<Record<string, QuizAnswer>>(stored?.answers ?? {});
  const [results, setResults] = useState<Record<string, KnowledgeQuizAnswerResult>>(stored?.results ?? {});
  const [completed, setCompleted] = useState(false);
  const [endedEarly, setEndedEarly] = useState(false);
  const [pendingDifficulty, setPendingDifficulty] = useState("");
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);
  const [wrongBook, setWrongBook] = useState<WrongBookItem[]>(readWrongBook);
  const [wrongBookOpen, setWrongBookOpen] = useState(false);
  const [loading, setLoading] = useState(!initialPayload);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const handledExitRequest = useRef(0);

  useEffect(() => {
    let active = true;
    void getKnowledgeQuiz()
      .then((value) => active && setPayload(value))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : "知识测试读取失败。"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const questionById = useMemo(() => new Map(payload.questions.map((item) => [item.id, item])), [payload.questions]);
  const questions = useMemo(() => questionIds.map((id) => questionById.get(id)).filter((item): item is KnowledgeQuizQuestion => Boolean(item)), [questionById, questionIds]);
  const question = questions[index] ?? null;
  const allAnswered = questions.length > 0 && questions.every((item) => Boolean(results[item.id]));

  useEffect(() => {
    if (!difficulty || !questionIds.length || completed) return;
    window.localStorage.setItem(SESSION_KEY, JSON.stringify({ difficulty, questionIds, index, answers, results }));
  }, [answers, completed, difficulty, index, questionIds, results]);

  useEffect(() => {
    if (exitRequest <= 0 || handledExitRequest.current === exitRequest) return;
    handledExitRequest.current = exitRequest;
    if (!difficulty || !questionIds.length || completed) onExit();
    else setExitConfirmOpen(true);
  }, [completed, difficulty, exitRequest, onExit, questionIds.length]);

  // 确认后从所选难度随机抽取五题并清空上一轮状态。
  const startQuiz = () => {
    const candidates = payload.questions.filter((item) => item.difficulty === pendingDifficulty);
    const selected = sampleQuestions(candidates, QUESTIONS_PER_QUIZ);
    setDifficulty(pendingDifficulty);
    setQuestionIds(selected.map((item) => item.id));
    setIndex(0);
    setAnswers({});
    setResults({});
    setCompleted(false);
    setEndedEarly(false);
    setPendingDifficulty("");
    setWrongBookOpen(false);
    setError("");
  };

  // 返回难度选择页，并清除当前场次。
  const resetQuiz = () => {
    window.localStorage.removeItem(SESSION_KEY);
    setDifficulty("");
    setQuestionIds([]);
    setIndex(0);
    setAnswers({});
    setResults({});
    setCompleted(false);
    setEndedEarly(false);
    setError("");
  };

  // 更新当前题答案，已经提交的题目保持锁定。
  const updateAnswer = (value: QuizAnswer) => {
    if (!question || results[question.id]) return;
    setAnswers((current) => ({ ...current, [question.id]: value }));
  };

  // 提交当前题，错误题目同步写入本地错题集。
  const submitAnswer = async () => {
    if (!question || results[question.id]) return;
    const answer = answers[question.id] ?? (question.question_type === "multiple_choice" ? [] : "");
    if (!hasAnswer(answer)) return;
    setSubmitting(true);
    setError("");
    try {
      const result = await submitKnowledgeQuizAnswer(question.id, answer);
      setResults((current) => ({ ...current, [question.id]: result }));
      if (!result.is_correct) {
        setWrongBook((current) => {
          const nextItem = { question, correctAnswers: result.correct_answers, answerPoints: result.answer_points, explanation: result.explanation, savedAt: Date.now() };
          const next = [nextItem, ...current.filter((item) => item.question.id !== question.id)];
          window.localStorage.setItem(WRONG_BOOK_KEY, JSON.stringify(next));
          return next;
        });
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "答案提交失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  };

  // 所有题目均已提交时进入总结，否则按顺序查看下一题。
  const nextQuestion = () => {
    if (!question || !results[question.id]) return;
    if (allAnswered) {
      window.localStorage.removeItem(SESSION_KEY);
      setCompleted(true);
      return;
    }
    const nextUnanswered = questions.findIndex((item, questionIndex) => questionIndex > index && !results[item.id]);
    const firstUnanswered = questions.findIndex((item) => !results[item.id]);
    setIndex(nextUnanswered >= 0 ? nextUnanswered : firstUnanswered);
  };

  // 中途确认退出后结束本场，只显示本场总结，不保存未完成场次。
  const finishEarly = () => {
    window.localStorage.removeItem(SESSION_KEY);
    setExitConfirmOpen(false);
    setEndedEarly(true);
    setCompleted(true);
  };

  if (loading) return <p className="knowledge-quiz-empty">正在整理知识测试题目……</p>;
  if (!difficulty) return <>
    {wrongBookOpen
      ? <WrongBook items={wrongBook} onBack={() => setWrongBookOpen(false)} onOpenCard={onOpenCard} />
      : <DifficultySelection payload={payload} error={error} wrongCount={wrongBook.length} onChoose={setPendingDifficulty} onWrongBook={() => setWrongBookOpen(true)} />}
    {pendingDifficulty && <StartConfirm difficulty={payload.difficulties.find((item) => item.value === pendingDifficulty)?.label ?? pendingDifficulty} onCancel={() => setPendingDifficulty("")} onConfirm={startQuiz} />}
  </>;
  if (completed) return <QuizSummary questions={questions} results={results} difficulty={difficulty} payload={payload} endedEarly={endedEarly} onReview={() => setCompleted(false)} onReset={resetQuiz} onExit={onExit} />;
  if (!question) return <div className="knowledge-quiz-empty"><p>本场题目无法读取，请重新选择难度。</p><button type="button" onClick={resetQuiz}>重新选择难度</button></div>;

  const answer = answers[question.id] ?? (question.question_type === "multiple_choice" ? [] : "");
  const result = results[question.id];
  return <>
    <div className="knowledge-quiz-layout">
      <QuizSidebar questions={questions} results={results} currentIndex={index} difficultyLabel={question.difficulty_label} onNavigate={setIndex} onReset={resetQuiz} />
      <section className="knowledge-quiz-card">
        <div className="knowledge-quiz-meta"><span>{index + 1} / {questions.length}</span><span>{question.question_type_label} · {question.category} · {question.difficulty_label}</span></div>
        <h2>{question.prompt}</h2>
        <span className="knowledge-quiz-source">{question.card_id} · {question.card_title}</span>
        {question.image_url && <figure className="knowledge-quiz-image"><img src={apiUrl(question.image_url)} alt={question.image_alt} /><figcaption>{question.image_alt}</figcaption></figure>}
        <QuestionInput question={question} answer={answer} locked={Boolean(result)} onChange={updateAnswer} />
        {result && <AnswerFeedback result={result} isShortAnswer={question.question_type === "short_answer"} />}
        {error && <p className="knowledge-quiz-error" role="alert">{error}</p>}
        <div className="knowledge-quiz-actions">
          <button type="button" disabled={index === 0} onClick={() => setIndex((current) => Math.max(0, current - 1))}>上一题</button>
          {!result ? <button type="button" className="primary" disabled={!hasAnswer(answer) || submitting} onClick={() => void submitAnswer()}>{submitting ? "提交中" : "提交答案"}</button> : <button type="button" className="primary" onClick={nextQuestion}>{allAnswered ? "查看结果" : "下一题"}</button>}
        </div>
      </section>
    </div>
    {exitConfirmOpen && <ExitConfirm onCancel={() => setExitConfirmOpen(false)} onConfirm={finishEarly} />}
  </>;
}

// 渲染开始测试前的三档难度和错题集入口。
function DifficultySelection({ payload, error, wrongCount, onChoose, onWrongBook }: { payload: KnowledgeQuizPayload; error: string; wrongCount: number; onChoose: (difficulty: string) => void; onWrongBook: () => void }) {
  return <section className="knowledge-quiz-start">
    <header className="knowledge-quiz-start-header">
      <div>
        <span className="knowledge-quiz-start-eyebrow"><i /> KNOWLEDGE CHECK</span>
        <h2>选择你的挑战难度</h2>
        <p>五道题，一次专注练习。提交后即时查看答案与知识依据。</p>
      </div>
      <div className="knowledge-quiz-start-rule"><strong>本次规则</strong><span>随机 5 题</span><span>即时反馈</span><span>自由切题</span></div>
    </header>
    {error ? <p className="knowledge-quiz-error" role="alert">{error}</p> : <div className="knowledge-quiz-difficulties">{payload.difficulties.map((item) => {
      const detail = DIFFICULTY_DETAILS[item.value] ?? { order: "", kicker: "知识练习", description: "完成本次知识测试。" };
      return <button type="button" className={`knowledge-quiz-difficulty knowledge-quiz-difficulty-${item.value}`} key={item.value} onClick={() => onChoose(item.value)}>
        <span className="knowledge-quiz-difficulty-top"><i>{detail.order}</i><b>本次 5 题</b></span>
        <DifficultyIcon difficulty={item.value} />
        <small>{detail.kicker}</small><strong>{item.label}</strong><p>{detail.description}</p>
        <span className="knowledge-quiz-difficulty-footer"><em>题库 {item.count} 题</em><b>开始测试 <i>→</i></b></span>
      </button>;
    })}</div>}
    <button type="button" className="knowledge-quiz-wrong-entry" onClick={onWrongBook}>
      <span className="knowledge-quiz-wrong-icon"><i /><i /><i /></span>
      <span className="knowledge-quiz-wrong-copy"><strong>错题集</strong><small>{wrongCount ? `已有 ${wrongCount} 道题等待复习` : "答错的题目会自动收录在这里"}</small></span>
      <b>{wrongCount}</b><i className="knowledge-quiz-wrong-arrow">→</i>
    </button>
  </section>;
}

// 用统一线性图标区分三档难度，不引入额外图片资源。
function DifficultyIcon({ difficulty }: { difficulty: string }) {
  if (difficulty === "beginner") return <svg className="knowledge-quiz-difficulty-icon" viewBox="0 0 48 48" aria-hidden="true"><path d="M11 35V22l13-10 13 10v13" /><path d="M17 35V24h14v11M8 36h32" /></svg>;
  if (difficulty === "advanced") return <svg className="knowledge-quiz-difficulty-icon" viewBox="0 0 48 48" aria-hidden="true"><path d="M9 36 20 10l7 17 4-8 8 17H9Z" /><path d="m16 20 4 3 4-4 3 3" /></svg>;
  return <svg className="knowledge-quiz-difficulty-icon" viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="15" /><path d="m24 14 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z" /></svg>;
}

// 开始前二次确认所选难度。
function StartConfirm({ difficulty, onCancel, onConfirm }: { difficulty: string; onCancel: () => void; onConfirm: () => void }) {
  return <QuizPrompt title={`确认开始${difficulty}测试？`} copy="系统将从该难度题库随机抽取 5 道题。开始后每题提交即判定答案。" cancelText="重新选择" confirmText="开始测试" onCancel={onCancel} onConfirm={onConfirm} />;
}

// 中途返回时确认结束本场测试。
function ExitConfirm({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  return <QuizPrompt title="确认退出本次测试？" copy="退出后本次测试会立即结束，并按当前答题情况生成得分总结；未作答题目按 0 分计算。" cancelText="继续答题" confirmText="结束并查看得分" onCancel={onCancel} onConfirm={onConfirm} />;
}

// 使用页面最外层遮罩显示测试确认卡片。
function QuizPrompt({ title, copy, cancelText, confirmText, onCancel, onConfirm }: { title: string; copy: string; cancelText: string; confirmText: string; onCancel: () => void; onConfirm: () => void }) {
  return <AppPromptOverlay onClose={onCancel}><section className="app-prompt-card figma-shadow" onClick={(event) => event.stopPropagation()}><h2 className="app-prompt-title">{title}</h2><p className="app-prompt-copy">{copy}</p><div className="app-prompt-actions"><button type="button" className="app-action-button h-9 rounded-[10px] border border-[#e8ebef] bg-white px-5" onClick={onCancel}>{cancelText}</button><button type="button" className="app-action-button h-9 rounded-[10px] bg-[#171719] px-5 text-white" onClick={onConfirm}>{confirmText}</button></div></section></AppPromptOverlay>;
}

// 答题卡允许随时浏览五道题，并分别标记正确与错误。
function QuizSidebar({ questions, results, currentIndex, difficultyLabel, onNavigate, onReset }: { questions: KnowledgeQuizQuestion[]; results: Record<string, KnowledgeQuizAnswerResult>; currentIndex: number; difficultyLabel: string; onNavigate: (index: number) => void; onReset: () => void }) {
  const answered = questions.filter((question) => results[question.id]).length;
  return <aside className="knowledge-quiz-sidebar">
    <div><small>当前难度</small><strong>{difficultyLabel}</strong><p>已完成 {answered} / {questions.length} 题</p></div>
    <div className="knowledge-quiz-progress"><span style={{ width: `${questions.length ? answered / questions.length * 100 : 0}%` }} /></div>
    <div className="knowledge-quiz-navigator">{questions.map((item, questionIndex) => {
      const result = results[item.id];
      return <button type="button" className={`${questionIndex === currentIndex ? "current" : ""} ${result?.is_correct ? "correct" : result ? "wrong" : ""}`} onClick={() => onNavigate(questionIndex)} key={item.id} aria-label={`第 ${questionIndex + 1} 题`}>{questionIndex + 1}</button>;
    })}</div>
    <button type="button" className="knowledge-quiz-reset" onClick={onReset}>重新选择难度</button>
  </aside>;
}

// 根据题型渲染文本框、单选、复选或判断选项。
function QuestionInput({ question, answer, locked, onChange }: { question: KnowledgeQuizQuestion; answer: QuizAnswer; locked: boolean; onChange: (answer: QuizAnswer) => void }) {
  if (question.question_type === "short_answer") return <textarea value={typeof answer === "string" ? answer : ""} disabled={locked} onChange={(event) => onChange(event.target.value)} placeholder="写下你的判断、依据与设计应对……" />;
  const selected = new Set(Array.isArray(answer) ? answer : answer ? [answer] : []);
  const multiple = question.question_type === "multiple_choice";
  return <div className="knowledge-quiz-options" role={multiple ? "group" : "radiogroup"}>{question.options.map((option) => <button type="button" role={multiple ? "checkbox" : "radio"} aria-checked={selected.has(option.id)} disabled={locked} className={selected.has(option.id) ? "selected" : ""} onClick={() => onChange(multiple ? toggleOption(selected, option.id) : option.id)} key={option.id}><span>{option.id}</span>{option.label}</button>)}</div>;
}

// 渲染本题即时判定、正确答案和来源说明。
function AnswerFeedback({ result, isShortAnswer }: { result: KnowledgeQuizAnswerResult; isShortAnswer: boolean }) {
  return <div className={`knowledge-quiz-feedback ${result.is_correct ? "correct" : "review"}`}>
    <div><strong>{isShortAnswer ? result.status_label : result.is_correct ? "回答正确" : "答案有误"}</strong><span>本题得分 {Math.round(result.score * 100)}%</span></div>
    <section><strong>参考答案</strong>{result.correct_answers.map((answer) => <p key={answer}>• {answer}</p>)}</section>
    {isShortAnswer && result.matched_points.length > 0 && <section><strong>已经覆盖</strong>{result.matched_points.map((point) => <p key={point}>• {point}</p>)}</section>}
    {isShortAnswer && result.missed_points.length > 0 && <section><strong>还可补充</strong>{result.missed_points.map((point) => <p key={point}>• {point}</p>)}</section>}
    <small>{result.explanation}</small>
  </div>;
}

// 渲染完成或中途结束后的总成绩。
function QuizSummary({ questions, results, difficulty, payload, endedEarly, onReview, onReset, onExit }: { questions: KnowledgeQuizQuestion[]; results: Record<string, KnowledgeQuizAnswerResult>; difficulty: string; payload: KnowledgeQuizPayload; endedEarly: boolean; onReview: () => void; onReset: () => void; onExit: () => void }) {
  const score = questions.length ? Math.round(questions.reduce((sum, item) => sum + (results[item.id]?.score ?? 0), 0) / questions.length * 100) : 0;
  const difficultyLabel = payload.difficulties.find((item) => item.value === difficulty)?.label ?? difficulty;
  const correct = questions.filter((item) => results[item.id]?.is_correct).length;
  const answered = questions.filter((item) => results[item.id]).length;
  return <section className="knowledge-quiz-summary">
    <span>{difficultyLabel}测试{endedEarly ? "已结束" : "完成"}</span><strong>{score}</strong><small>综合得分</small>
    <h2>本次共 5 题，已作答 {answered} 题，其中 {correct} 题回答正确。</h2>
    <p>{endedEarly ? "未作答题目按 0 分计算，本场中断进度不会保留。" : "错题已自动加入错题集，可以返回初始界面集中复习。"}</p>
    <div>{endedEarly ? <button type="button" className="primary" onClick={onExit}>返回知识库</button> : <><button type="button" onClick={onReview}>返回逐题复盘</button><button type="button" className="primary" onClick={onReset}>重新选择难度</button></>}</div>
  </section>;
}

// 渲染本地保存的错题和对应答案。
function WrongBook({ items, onBack, onOpenCard }: { items: WrongBookItem[]; onBack: () => void; onOpenCard: (cardId: string) => void }) {
  return <section className="knowledge-quiz-wrong-book">
    <header><div><span>错题集</span><h2>复习之前答错的题目</h2></div><button type="button" onClick={onBack}>返回难度选择</button></header>
    {!items.length ? <p className="knowledge-quiz-wrong-empty">目前还没有错题。完成测试后，答错的题目会自动收录在这里。</p> : <div className="knowledge-quiz-wrong-list">{items.map((item) => <article key={item.question.id}><small>{item.question.question_type_label} · {item.question.difficulty_label}</small><h3>{item.question.prompt}</h3><strong>正确答案</strong>{item.correctAnswers.map((answer) => <p key={answer}>• {answer}</p>)}<button type="button" onClick={() => onOpenCard(item.question.card_id)}>查看来源：{item.question.card_title}</button></article>)}</div>}
  </section>;
}

// 使用 Fisher-Yates 洗牌后截取本场题目。
function sampleQuestions(items: KnowledgeQuizQuestion[], count: number): KnowledgeQuizQuestion[] {
  const shuffled = [...items];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[randomIndex]] = [shuffled[randomIndex], shuffled[index]];
  }
  return shuffled.slice(0, Math.min(count, shuffled.length));
}

// 判断文字或选项答案是否已经填写。
function hasAnswer(answer: QuizAnswer): boolean {
  return Array.isArray(answer) ? answer.length > 0 : answer.trim().length > 0;
}

// 切换多选题的一个选项并保持稳定顺序。
function toggleOption(selected: Set<string>, optionId: string): string[] {
  const next = new Set(selected);
  if (next.has(optionId)) next.delete(optionId);
  else next.add(optionId);
  return [...next].sort();
}
