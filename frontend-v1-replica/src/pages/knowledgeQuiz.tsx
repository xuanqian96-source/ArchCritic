// 知识测试：使用知识卡原有开放式自测题，支持分类、难度和自我复盘。
import { useEffect, useMemo, useState } from "react";
import { getKnowledgeQuiz, type KnowledgeQuizPayload } from "../api/knowledge";

const EMPTY_QUIZ: KnowledgeQuizPayload = { questions: [], categories: [], difficulties: [] };

export function KnowledgeQuiz({ onOpenCard }: { onOpenCard: (cardId: string) => void }) {
  const [payload, setPayload] = useState(EMPTY_QUIZ);
  const [category, setCategory] = useState("全部");
  const [difficulty, setDifficulty] = useState("全部");
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [mastered, setMastered] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    void getKnowledgeQuiz().then(setPayload).catch((loadError) => setError(loadError instanceof Error ? loadError.message : "知识测试读取失败。"));
  }, []);

  const questions = useMemo(() => payload.questions.filter((item) =>
    (category === "全部" || item.category === category)
    && (difficulty === "全部" || item.difficulty_label === difficulty),
  ), [category, difficulty, payload.questions]);
  const question = questions[index] ?? null;
  const resetQuestion = (nextIndex: number) => { setIndex(nextIndex); setAnswer(""); setRevealed(false); };

  return <div className="knowledge-quiz-layout">
    <aside className="knowledge-quiz-sidebar"><strong>选择测试范围</strong>
      <label>知识分类<select value={category} onChange={(event) => { setCategory(event.target.value); resetQuestion(0); }}><option>全部</option>{payload.categories.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>难度<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value); resetQuestion(0); }}><option>全部</option>{payload.difficulties.map((item) => <option key={item}>{item}</option>)}</select></label>
      <p>当前共 {questions.length} 题</p><small>题目来自知识卡已有的观察、自测与设计检查内容，不额外编造标准答案。</small>
    </aside>
    <section className="knowledge-quiz-card">
      {error ? <p className="knowledge-quiz-empty">{error}</p> : !question ? <p className="knowledge-quiz-empty">当前范围暂无可用题目。</p> : <>
        <div className="knowledge-quiz-meta"><span>{index + 1} / {questions.length}</span><span>{question.category} · {question.difficulty_label}</span></div>
        <h2>{question.prompt}</h2><button type="button" className="knowledge-quiz-source" onClick={() => onOpenCard(question.card_id)}>{question.card_id} · {question.card_title}</button>
        <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="先写下你的判断、依据与设计应对……" />
        {revealed && <div className="knowledge-quiz-reference"><strong>复盘要点</strong>{question.reference_points.map((item) => <p key={item}>• {item}</p>)}</div>}
        <div className="knowledge-quiz-actions"><button type="button" onClick={() => setRevealed(true)} disabled={!answer.trim()}>查看参考要点</button>{revealed && <><button type="button" className={mastered[question.id] === false ? "active" : ""} onClick={() => setMastered((current) => ({ ...current, [question.id]: false }))}>需要复习</button><button type="button" className={mastered[question.id] ? "active" : ""} onClick={() => setMastered((current) => ({ ...current, [question.id]: true }))}>已经掌握</button></>}<button type="button" className="primary" disabled={index >= questions.length - 1} onClick={() => resetQuestion(index + 1)}>下一题</button></div>
      </>}
    </section>
  </div>;
}
