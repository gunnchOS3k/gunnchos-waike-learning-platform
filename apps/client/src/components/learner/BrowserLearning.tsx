import {DigitalConfidencePractical} from "./DigitalConfidencePractical";
import { useEffect, useRef, useState } from 'react';
import { bearerHubAllowed } from '../../lib/hub/resolveHub';
import { PUBLIC_TRACKS, usePublicContent, type PublicTrack, type PublicTrackContent } from '../../lib/product/publicCurriculum';
import { SafeMarkdown } from '../content/SafeMarkdown';
import './browserLearning.css';

type Result = { kind: string; persisted: false; earned: number; possible: number; feedback: { id: string; correct: boolean; explanation: string }[] };
type RecordState = { viewed: number[]; quizzes: Record<string, { earned: number; possible: number }>; drafts: Record<string, string> };
const empty = (): RecordState => ({ viewed: [], quizzes: {}, drafts: {} });
const SOURCE_TUTORING_NOTE = 'Deterministic source text. modelCompletion is empty. This is not model inference. Inference is still blocked.';
type SignedAuth = { token: string; baseUrl: string; sectionId: string; onReview: () => void };
function sessionScope(token: string, sectionId: string): string {
  let hash = 2166136261;
  for (const ch of `${sectionId}:${token}`) hash = Math.imul(hash ^ ch.charCodeAt(0), 16777619);
  return (hash >>> 0).toString(16);
}
function configuredLearnHost(): string {
  return String(import.meta.env.VITE_HUB_URL || '');
}
async function hubFetch(input: string, init: RequestInit, controller: AbortController): Promise<Response> {
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof TypeError && String(error.message).includes('AbortSignal')) return fetch(input, init);
    throw error;
  }
}
export function tutoringNote(data: { text?: unknown; modelCompletion?: unknown; detail?: { modelCompletion?: unknown } }): string {
  const completion = data.modelCompletion ?? data.detail?.modelCompletion;
  const realCompletion = typeof completion === 'string' && completion.trim().length > 0;
  const saysSource = typeof data.text === 'string' && /deterministic source text/i.test(data.text);
  if (realCompletion && !saysSource) return '';
  return SOURCE_TUTORING_NOTE;
}
export function campusReturnHref(search: string): string | null {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const keys = [...params.keys()];
  if (keys.length !== 1 || keys[0] !== "return") return null;
  return params.get("return") === "https://gunnchos.com" ? "https://gunnchos.com" : null;
}
export function parseLearningHash(hash: string): { track: string; unit: number } | null {
  const match = /^#\/learn\/([A-Z_0-9]+)\/(\d+)$/.exec(hash);
  if (!match || !PUBLIC_TRACKS.some(t => t.trackId === match[1])) return null;
  const unit = Number(match[2]);
  return unit >= 1 && unit <= 10 ? { track: match[1], unit } : null;
}
export function BrowserLearning({ trackId, unit, onNavigate, auth }: { trackId: string; unit: number; onNavigate: (track: string, unit: number) => void; auth?: SignedAuth }) {
  const track = PUBLIC_TRACKS.find(t => t.trackId === trackId) || PUBLIC_TRACKS[0];
  const {content, error, retry} = usePublicContent(track);
  if (!content) return <section className="browser-learning" aria-busy={!error}><h1>{track.title}</h1><p role={error ? "alert" : "status"}>{error || "Downloading this course…"}</p>{error && <button onClick={retry}>Retry course download</button>}</section>;
  return <LoadedBrowserLearning key={track.trackId} {...{trackId, unit, onNavigate, auth, track, content}} />;
}
function LoadedBrowserLearning({trackId, unit, onNavigate, auth, track, content}: {trackId: string; unit: number; onNavigate: (track: string, unit: number) => void; auth?: SignedAuth; track: PublicTrack; content: PublicTrackContent}) {
  const lesson = content.lessons[unit - 1];
  const quiz = content.quizzes[unit - 1];
  const assignment = content.assignments[unit - 1];
  const lab = content.labs.find(l => l.id === lesson.labId);
  const signedIn = Boolean(auth?.token && auth.sectionId && !auth.sectionId.startsWith('catalog:'));
  const storageKey = signedIn && auth
    ? `waike.practice.v1:${sessionScope(auth.token, auth.sectionId)}:${track.trackId}:${content.contentRootSha256}`
    : `waike.practice.v1:${track.trackId}:${content.contentRootSha256}`;
  function clearCourseRecords() {
    const keys = Array.from({length: localStorage.length}, (_, i) => localStorage.key(i)).filter((k): k is string => Boolean((k?.startsWith('waike.practice.v1:') && k.includes(`:${track.trackId}:`)) || (trackId==='DIGITAL_CONFIDENCE' && k?.startsWith('waike.dc.work.v1:'))));
    keys.forEach(k => localStorage.removeItem(k));
  }
  const [record, setRecord] = useState<RecordState>(empty);
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState('');
  const [responses, setResponses] = useState<Record<string, number>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  const [serverLesson, setServerLesson] = useState<{ text: string; progress_store: string; grade_written: boolean } | null>(null);
  const [resumedLesson, setResumedLesson] = useState<string | null>(null);
  const [tutorQuestion, setTutorQuestion] = useState('');
  const [tutorText, setTutorText] = useState('');
  const [tutorNote, setTutorNote] = useState('');
  const viewKey = `${signedIn && auth ? `${auth.token}\n${auth.sectionId}` : 'guest'}\n${track.trackId}\n${unit}`;
  const [viewEpoch, setViewEpoch] = useState(viewKey);
  const requestEpoch = useRef(0);
  const inflight = useRef<AbortController | null>(null);
  if (viewEpoch !== viewKey) {
    inflight.current?.abort();
    inflight.current = null;
    requestEpoch.current += 1;
    setViewEpoch(viewKey);
    setRecord(empty());
    setConsent(false);
    setMessage('');
    setResponses({});
    setResult(null);
    setBusy(false);
    setDraft('');
    setServerLesson(null);
    setResumedLesson(null);
    setTutorQuestion('');
    setTutorText('');
    setTutorNote('');
  }
  function hubAllowsToken(): boolean {
    return Boolean(signedIn && auth && bearerHubAllowed(auth.baseUrl, configuredLearnHost()));
  }
  const token = auth?.token ?? '';
  const baseUrl = auth?.baseUrl ?? '';
  const sectionId = auth?.sectionId ?? '';
  useEffect(() => {
    if (!signedIn || !token || !sectionId) return;
    if (!bearerHubAllowed(baseUrl, configuredLearnHost())) {
      setMessage('This Hub address is not an allowed origin. No token was sent.');
      return;
    }
    const epoch = requestEpoch.current;
    const controller = new AbortController();
    inflight.current = controller;
    const lessonId = `w${String(unit).padStart(2, '0')}`;
    void (async () => {
      try {
        const prior = await hubFetch(
          `${baseUrl}/api/v1/sync/pull?section_id=${encodeURIComponent(sectionId)}&since_revision=0`,
          { headers: { Authorization: `Bearer ${token}` } },
          controller,
        );
        if (epoch !== requestEpoch.current) return;
        if (prior.ok) {
          const body = await prior.json() as { lesson_progress?: Array<{ lesson_id?: string; percent_complete?: number }> };
          const stored = Array.isArray(body.lesson_progress) ? body.lesson_progress.find((row) => row.lesson_id === lessonId) : undefined;
          if (stored && epoch === requestEpoch.current) setResumedLesson(lessonId);
          if (stored?.percent_complete === 100 && epoch === requestEpoch.current) setMessage(`Lesson ${lessonId} is complete. No grade was written.`);
        }
        const response = await hubFetch(`${baseUrl}/api/v1/sections/${encodeURIComponent(sectionId)}/lessons/${unit}`, {
          headers: { Authorization: `Bearer ${token}` },
        }, controller);
        if (epoch !== requestEpoch.current) return;
        if (!response.ok) {
          setMessage('The signed-in lesson could not be opened. No grade was written.');
          return;
        }
        const data = await response.json();
        if (epoch === requestEpoch.current && typeof data.text === 'string') setServerLesson(data);
      } catch (error: unknown) {
        if (epoch !== requestEpoch.current || (error instanceof DOMException && error.name === 'AbortError')) return;
        setMessage('The signed-in lesson could not be opened. No grade was written.');
      }
    })();
    return () => { controller.abort(); };
  }, [signedIn, token, baseUrl, sectionId, unit]);
  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed.viewed) && parsed.viewed.every((n: unknown) => Number.isInteger(n) && Number(n) >= 1 && Number(n) <= 10) && parsed.quizzes && typeof parsed.quizzes === 'object' && parsed.drafts && typeof parsed.drafts === 'object' && Object.values(parsed.drafts).every(d => typeof d === 'string' && d.length <= 20000)) {
          setRecord(parsed); setConsent(true); setDraft(parsed.drafts[String(unit)] || '');
        }
      }
    } catch { setMessage('Saved practice could not be read. You can continue without saving.'); }
  }, [storageKey, unit]);
  function save(next: RecordState) {
    setRecord(next);
    if (!consent) { setMessage('Kept for this lesson view. Turn on device saving before navigating to retain it.'); return; }
    try { localStorage.setItem(storageKey, JSON.stringify(next)); setMessage('Saved on this browser.'); }
    catch { setMessage('Browser storage is unavailable. Download your evidence before leaving.'); }
  }
  async function evaluate(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setResult(null); setMessage('');
    const epoch = requestEpoch.current;
    const trusted = hubAllowsToken();
    if (signedIn && !trusted) {
      setMessage('This Hub address is not an allowed origin. No token was sent.');
      setBusy(false);
      return;
    }
    const controller = new AbortController();
    inflight.current = controller;
    try {
      const practiceUrl = trusted && auth
        ? `${auth.baseUrl}/api/v1/sections/${encodeURIComponent(auth.sectionId)}/lessons/${unit}/practice`
        : `/api/v1/public-practice/${track.trackId}/${unit}`;
      const response = await hubFetch(practiceUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(trusted && auth ? { Authorization: `Bearer ${auth.token}` } : {}) },
        credentials: 'omit',
        body: JSON.stringify({ responses, quiz_sha256: quiz.sha256 }),
      }, controller);
      if (epoch !== requestEpoch.current) return;
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' ? error.detail : 'Practice evaluation is unavailable. Your answers have not been graded.');
      }
      const next: Result & { grade_written?: boolean } = await response.json();
      if (epoch !== requestEpoch.current) return;
      if (signedIn && next.grade_written) throw new Error('Practice must not write a grade.');
      setResult(next);
      save({ ...record, quizzes: { ...record.quizzes, [unit]: { earned: next.earned, possible: next.possible } } });
    } catch (error) {
      if (epoch !== requestEpoch.current || (error instanceof DOMException && error.name === 'AbortError')) return;
      setMessage(error instanceof Error ? error.message : 'Evaluation unavailable; no score recorded.');
    }
    finally { if (epoch === requestEpoch.current) setBusy(false); }
  }
  async function requestTutoring(event: React.FormEvent) {
    event.preventDefault();
    if (!signedIn || !auth) return;
    if (!hubAllowsToken()) {
      setMessage('This Hub address is not an allowed origin. No token was sent.');
      return;
    }
    const epoch = requestEpoch.current;
    const controller = new AbortController();
    inflight.current = controller;
    setBusy(true); setTutorText(''); setTutorNote(''); setMessage('');
    try {
      const response = await hubFetch(`${auth.baseUrl}/api/v1/ai/learner/assist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
        credentials: 'omit',
        body: JSON.stringify({ section_id: auth.sectionId, capability: 'explain', query: tutorQuestion, processing_mode: 'local-only' }),
      }, controller);
      const data = await response.json();
      if (epoch !== requestEpoch.current) return;
      if (!response.ok || data.suggestion_only !== true || data.mutates_grades) throw new Error('Tutoring stayed unavailable. No grade was written.');
      const note = tutoringNote(data);
      setTutorText(typeof data.text === 'string' ? data.text : '');
      setTutorNote(note);
    } catch (error) {
      if (epoch !== requestEpoch.current || (error instanceof DOMException && error.name === 'AbortError')) return;
      setMessage(error instanceof Error ? error.message : 'Tutoring unavailable. No grade was written.');
    }
    finally { if (epoch === requestEpoch.current) setBusy(false); }
  }
  async function markLessonComplete() {
    if (!signedIn || !auth) return;
    if (!hubAllowsToken()) {
      setMessage('This Hub address is not an allowed origin. No token was sent.');
      return;
    }
    const lessonId = `w${String(unit).padStart(2, '0')}`;
    try {
      const response = await hubFetch(`${auth.baseUrl}/api/v1/sections/${encodeURIComponent(auth.sectionId)}/lessons/${unit}/complete`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${auth.token}` },
        credentials: 'omit',
      }, new AbortController());
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.grade_written || data.percent_complete !== 100) {
        setMessage('Lesson completion was not stored. No grade was written.');
        return;
      }
      setMessage(`Lesson ${lessonId} is complete. No grade was written.`);
    } catch {
      setMessage('Lesson completion was not stored. No grade was written.');
    }
  }
  function download() {
    const blob = new Blob([JSON.stringify({ schema: 'waike.guest.practice.v1', trackId: track.trackId, sourceCommit: content.sourceCommit, contentHash: content.contentRootSha256, ...record, currentDraft: draft, status: 'ungraded guest evidence; no credential or completion credit' }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = `${track.trackId}-practice.json`; link.click(); URL.revokeObjectURL(url);
  }
  return <section className="browser-learning" aria-label="Course learning reader" data-testid="browser-learning">
    <header><p className="eyebrow">WAIKE / Open learning</p><h1>{track.title}</h1>
      {!auth && <><label htmlFor="reader-course">Choose course</label><select id="reader-course" value={track.trackId} onChange={e => onNavigate(e.target.value, 1)}>{PUBLIC_TRACKS.map(t => <option key={t.trackId} value={t.trackId}>{t.title}</option>)}</select></>}
      <label htmlFor="reader-unit">Choose unit</label><select id="reader-unit" value={unit} onChange={e => onNavigate(track.trackId, Number(e.target.value))}>{content.lessons.map((l,i) => <option key={l.id} value={i+1}>{i+1}. {l.title}</option>)}</select>
      {campusReturnHref(window.location.search) && <a data-testid="campus-return" href={campusReturnHref(window.location.search) || undefined}>Return to gunnchos.com</a>}
      <p>Prerequisites: {content.prerequisites?.required?.join('; ') || 'Review the course syllabus before starting.'}</p>
    </header>
    <nav aria-label="Unit sections">{[["lesson","Lesson"],["practice-lab","Lab"],["practice-quiz","Quiz"],["practice-assignment","Assignment"],["practice-progress","My evidence"]].map(([id,label]) => <a key={id} href={`#${id}`} onClick={e => { e.preventDefault(); document.getElementById(id)?.scrollIntoView(); }}>{label}</a>)}</nav>
    {content.delivery && <p>{content.delivery.definition.introduction}</p>}
    {content.delivery && <><DigitalConfidencePractical key={`dc:${unit}`} delivery={content.delivery} unit={unit}/>{unit===10&&<DigitalConfidencePractical delivery={content.delivery} unit={11} auth={auth}/>}</>}
    <article id="lesson" tabIndex={-1}>{content.delivery && <p>Shared General IT reading and authorized technical extension. Begin with the guided activity above; terminal commands require the separately stated environment and permission.</p>}{resumedLesson && <p data-testid="resumed-progress">Resumed stored lesson progress for {resumedLesson}. This read did not write a grade.</p>}{serverLesson && <p>Progress is stored in {serverLesson.progress_store}. No grade was written.</p>}<SafeMarkdown markdown={(serverLesson?.text || lesson.markdown).replace(/^(#{1,5}) /gm, "$1# ")} testId="full-lesson-content" />
      <button onClick={() => { save({ ...record, viewed: Array.from(new Set([...record.viewed, unit])) }); void markLessonComplete(); }}>Mark this lesson read</button>
      <p>Reading records engagement. It does not demonstrate mastery.</p>
    </article>
    <section id="practice-lab"><h2>Practice lab</h2>{content.delivery && <p>The guided Digital Confidence practical above is the beginner pathway. This shared General IT laboratory is an optional technical extension.</p>}{lab ? <SafeMarkdown markdown={lab.markdown.replace(/^(#{1,5}) /gm, "$1# ")} /> : <p>The linked lab could not be loaded. No lab completion is recorded.</p>}
      {lesson.labId === 'lab_storage' && <StoragePractice />}
      <p>Command-line activities require the canonical curriculum checkout and the stated tools. Submit your own artifact; running a reference fixture does not establish your competence. Browser calculations are formative practice.</p>
    </section>
    <section id="practice-quiz"><h2>Unit {unit} practice quiz</h2>{content.delivery && <p>Shared General IT extension quiz. The beginner practical provides criterion feedback above; these additional questions also cover the technical reading.</p>}<p>Answer every question, then check your reasoning. This practice score is not an authenticated grade. Questions are sent to the evaluator; no account or draft is sent.</p>
      <form onSubmit={evaluate}>{quiz.items?.map((item, i) => <fieldset key={item.id}><legend>{i+1}. {item.stem}</legend>
        {item.choices.map((choice,index) => <label className="quiz-choice" key={index}><input required type="radio" name={item.id} checked={responses[item.id] === index} onChange={() => { setResponses({ ...responses, [item.id]: index }); setResult(null); }} />{choice}</label>)}
        {result && <p className={result.feedback[i]?.correct ? 'practice-correct' : 'practice-review'}>{result.feedback[i]?.correct ? 'Correct. ' : 'Review. '}{result.feedback[i]?.explanation}</p>}
      </fieldset>)}<button disabled={busy}>{busy ? 'Checking…' : 'Check my answers'}</button><button type="button" onClick={() => { setResponses({}); setResult(null); }}>Retry with a fresh response</button></form>
      {result && <p role="status">Practice result: {result.earned} / {result.possible}. {signedIn ? 'No grade was written.' : 'No server record was created.'}</p>}
      {signedIn && <form onSubmit={requestTutoring}><label>Ask about this lesson<input value={tutorQuestion} onChange={e => setTutorQuestion(e.target.value)} /></label><button disabled={busy || tutorQuestion.trim().length === 0}>Request tutoring</button></form>}
      {tutorNote && <p role="status">{tutorNote}</p>}
      {tutorText && <SafeMarkdown markdown={tutorText} testId="source-tutoring" />}
    </section>
    <section id="practice-assignment"><h2>Independent assignment</h2>{content.delivery && <p>Shared General IT extension assignment. The Digital Confidence independent evidence portfolio appears after the Week 10 practical and uses its own rubric.</p>}<SafeMarkdown markdown={assignment.markdown.replace(/^(#{1,5}) /gm, "$1# ")} />
      <label>My private draft (avoid personal information, passwords and real learner records)<textarea rows={8} maxLength={20000} value={draft} onChange={e => setDraft(e.target.value)} /></label>
      <button onClick={() => save({ ...record, drafts: { ...record.drafts, [unit]: draft } })}>Save draft on this device</button>
      <p>Draft only. To submit for assessment, sign in to an authorized school Hub and open this course’s Assignments workspace. Submission, instructor feedback and official grades use that Hub’s existing records. A guest draft is not submitted automatically.</p>
      <details><summary>Assessment rubric</summary><pre>{content.references?.find(r => r.path.endsWith('rubrics.json'))?.markdown || 'Instructor review required.'}</pre></details>
    </section>
    <section id="practice-progress"><h2>My evidence</h2>
      <p>Lesson reads: {record.viewed.length} / {content.lessons.length}. Quizzes practiced: {Object.keys(record.quizzes).length}. Drafts saved: {Object.keys(record.drafts).length}. Labs and assignments still require verified evidence and review. Course completion: not established.</p>
      <dl><dt>Viewed</dt><dd>{record.viewed.length} lessons marked read</dd><dt>Practiced</dt><dd>{Object.keys(record.quizzes).length} quizzes with a checked response</dd><dt>Submitted</dt><dd>No guest work submitted to a school Hub</dd><dt>Evaluated</dt><dd>Formative quiz feedback only; practical and instructor evaluation pending</dd><dt>Completed</dt><dd>Not established</dd><dt>Competency demonstrated</dt><dd>Not established; requires verified practical evidence and authorized review</dd></dl>
      <label><input type="checkbox" checked={consent} onChange={e => {
        const enabled = e.target.checked;
        setConsent(enabled);
        if (!enabled) {
          try { localStorage.removeItem(storageKey); } catch { /* unavailable storage */ }
          return;
        }
        try {
          localStorage.setItem(storageKey, JSON.stringify(record));
          setMessage('Saved on this browser.');
        } catch { setMessage('Browser storage is unavailable. Download your evidence before leaving.'); }
      }} />Save practice on this browser. Other people using this browser may be able to see it.</label>
      <button onClick={download}>Download my practice evidence</button><button onClick={() => { try { clearCourseRecords(); } catch { setMessage('The browser could not clear saved records. Use its site-data settings to remove them.'); return; } setRecord(empty()); setDraft(''); setConsent(false); setMessage('This course’s saved practice was cleared.'); }}>Clear this course’s device record</button>
      <p>Records are tied to this content version. They are not synced across devices. Updated content starts a separate practice record.</p>
      <details><summary>Glossary and course syllabus</summary>{content.references?.filter(r => !r.path.endsWith('.json')).map(r => <SafeMarkdown key={r.path} markdown={r.markdown} />)}</details>
      <details><summary>Source version</summary><p>Canonical owner: waike-research-ops. Source commit: {content.sourceCommit}. Content hash: {content.contentRootSha256}. Educational acceptance pending.</p></details>
    </section>
    {Boolean(content.resources?.length) && <section><h2>Download the local worked example</h2><p>Save the files together, read the README, and run them only in your own practice environment. No code is executed by this reader.</p>{content.resources?.map(file => <div key={file.path}><button onClick={() => { const url=URL.createObjectURL(new Blob([file.markdown], {type:'text/plain'})); const link=document.createElement('a'); link.href=url; link.download=file.path.split('/').pop()!; link.click(); URL.revokeObjectURL(url); }}>Download {file.path.split('/').pop()}</button>{file.path.endsWith('README.md') && <SafeMarkdown markdown={file.markdown.replace(/^(#{1,5}) /gm, "$1# ")} />}</div>)}</section>}
    <p role="status">{message}</p>
    <nav aria-label="Unit navigation"><button disabled={unit === 1} onClick={() => onNavigate(track.trackId, unit-1)}>Previous unit</button><span>Unit {unit} of {content.lessons.length}</span><button disabled={unit === content.lessons.length} onClick={() => onNavigate(track.trackId, unit+1)}>Next unit</button></nav>
  </section>;
}
function StoragePractice() {
  const [used, setUsed] = useState('180'); const [reserve, setReserve] = useState('12'); const [answer, setAnswer] = useState(''); const [feedback, setFeedback] = useState('');
  return <aside><h3>Run the capacity calculation</h3><p>Fixture: a 256 GiB volume. All values use the same unit. Usable free capacity = size − used − reserved. Divide by size for the free ratio; multiply by 100 for a percentage. This course’s 15% policy is a fixture assumption.</p>
    <label>Used GiB<input type="number" min="0" max="256" value={used} onChange={e => { setUsed(e.target.value); setFeedback(''); }} /></label>
    <label>Reserved GiB<input type="number" min="0" max="256" value={reserve} onChange={e => { setReserve(e.target.value); setFeedback(''); }} /></label>
    <label>Your free percentage<input type="number" step="any" value={answer} onChange={e => { setAnswer(e.target.value); setFeedback(''); }} /></label>
    <button onClick={() => { const u=Number(used), r=Number(reserve), a=Number(answer); if (!used || !reserve || !answer || ![u,r,a].every(Number.isFinite) || u<0 || r<0 || u+r>256 || a<0 || a>100) { setFeedback('Enter valid nonnegative capacities totaling no more than 256 GiB and a percentage from 0 to 100.'); return; } const percent=(256-u-r)/256*100; setFeedback(Math.abs(a-percent)<0.01 ? `Calculation verified: ${percent.toFixed(3)}%. ${percent>=15 ? 'Meets' : 'Below'} this fixture’s 15% policy. Change the inputs and predict the result again.` : 'The calculation differs. Subtract both used and reserved capacity before dividing by 256. Try again.'); }}>Verify my calculation</button><p role="status">{feedback}</p>
  </aside>;
}
