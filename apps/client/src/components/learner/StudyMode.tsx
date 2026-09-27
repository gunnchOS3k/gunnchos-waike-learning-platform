import { useMemo, useState } from "react";
import { studyModesForContent, type StudyModeId } from "../../lib/product/studyMode";
import { SafeMarkdown } from "../content/SafeMarkdown";

type Props = {
  title: string;
  markdown: string;
  labLaunchable?: boolean;
  masteryLabel?: string | null;
  onAsk: () => void;
  onLab?: () => void;
};

export function StudyMode({ title, markdown, labLaunchable = false, masteryLabel, onAsk, onLab }: Props) {
  const ttsAvailable = typeof window !== "undefined" && "speechSynthesis" in window;
  const modes = useMemo(
    () =>
      studyModesForContent({
        hasReadableText: Boolean(markdown.trim()),
        ttsAvailable,
        authoredPractice: false,
        authoredFlashcards: false,
        labLaunchable,
        masteryEvidence: Boolean(masteryLabel),
      }),
    [markdown, ttsAvailable, labLaunchable, masteryLabel],
  );
  const [active, setActive] = useState<StudyModeId>("read");
  const [cards, setCards] = useState<Array<{ front: string; back: string; accepted: boolean }>>([]);
  const [explain, setExplain] = useState("");
  const [rate, setRate] = useState(1);
  const current = modes.find((m) => m.id === active);

  function speak() {
    if (!ttsAvailable || !markdown.trim()) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(markdown.replace(/[#*`>|[\]()]/g, " ").slice(0, 4000));
    u.rate = rate;
    window.speechSynthesis.speak(u);
  }

  return (
    <section className="panel" data-testid="study-mode">
      <h2>Study · {title}</h2>
      <div className="mode-bar" aria-label="Study modes">
        {modes.map((m) => (
          <button
            key={m.id}
            type="button"
            className={active === m.id ? "mode-active" : "ghost"}
            disabled={!m.available && m.id !== "practice" && m.id !== "flashcards" && m.id !== "self_check" && m.id !== "explain" && m.id !== "ask"}
            data-testid={`study-${m.id}`}
            onClick={() => setActive(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <p className="muted" data-testid="study-honesty">
        {current?.honesty}
      </p>
      {active === "read" ? <SafeMarkdown markdown={markdown} testId="study-read" /> : null}
      {active === "listen" ? (
        <div data-testid="study-listen">
          <p className="muted">System speech reads the lesson text. Pause, resume, or change speed.</p>
          <div className="toolbar">
            <button type="button" onClick={speak}>
              Listen
            </button>
            <button type="button" className="ghost" onClick={() => window.speechSynthesis?.pause()}>
              Pause
            </button>
            <button type="button" className="ghost" onClick={() => window.speechSynthesis?.resume()}>
              Resume
            </button>
            <label className="field-label" htmlFor="tts-rate">
              Speed {rate.toFixed(1)}x
            </label>
            <input
              id="tts-rate"
              type="number"
              min={0.5}
              max={2}
              step={0.1}
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
            />
          </div>
        </div>
      ) : null}
      {active === "practice" ? (
        <p className="muted">No authored practice questions are attached. Ask gunnchAI for a labeled practice draft.</p>
      ) : null}
      {active === "flashcards" ? (
        <div>
          <p className="muted">Add your own cards. AI drafts stay drafts until you accept them.</p>
          <button
            type="button"
            className="ghost"
            onClick={() => setCards((c) => [...c, { front: "Term", back: "Your definition", accepted: true }])}
          >
            Add card
          </button>
          <ul>
            {cards.map((c, i) => (
              <li key={i}>
                {c.front} → {c.back}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {active === "ask" ? (
        <button type="button" data-testid="study-ask" onClick={onAsk}>
          Ask gunnchAI about this lesson
        </button>
      ) : null}
      {active === "self_check" ? (
        <p className="muted">Self-check is not a quiz and does not change your grade.</p>
      ) : null}
      {active === "lab" ? (
        labLaunchable ? (
          <button type="button" onClick={onLab}>
            Open lab
          </button>
        ) : (
          <p className="muted">No lab is attached.</p>
        )
      ) : null}
      {active === "explain" ? (
        <div>
          <label className="field-label" htmlFor="explain-back">
            Explain this in your own words
          </label>
          <textarea id="explain-back" rows={5} value={explain} onChange={(e) => setExplain(e.target.value)} />
          <p className="muted">gunnchAI may coach. This is not a formal grade.</p>
        </div>
      ) : null}
      {active === "mastery" ? (
        <p data-testid="study-mastery">{masteryLabel || "No mastery evidence yet."}</p>
      ) : null}
    </section>
  );
}
