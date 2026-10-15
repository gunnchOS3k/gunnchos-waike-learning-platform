import { useEffect, useState } from 'react';
import { PUBLIC_TRACKS, publicContentForTrack } from '../../lib/product/publicCurriculum';
import { SafeMarkdown } from '../content/SafeMarkdown';
import './browserLearning.css';

type Result = { kind: string; persisted: false; earned: number; possible: number; feedback: { id: string; correct: boolean; explanation: string }[] };
type RecordState = { viewed: number[]; quizzes: Record<string, { earned: number; possible: number }>; drafts: Record<string, string> };
const empty = (): RecordState => ({ viewed: [], quizzes: {}, drafts: {} });
export function parseLearningHash(hash: string): { track: string; unit: number } | null {
  const match = /^#\/learn\/([A-Z_0-9]+)\/(\d+)$/.exec(hash);
  if (!match || !PUBLIC_TRACKS.some(t => t.trackId === match[1])) return null;
  const unit = Number(match[2]);
  return unit >= 1 && unit <= 10 ? { track: match[1], unit } : null;
}
export function BrowserLearning({ trackId, unit, onNavigate }: { trackId: string; unit: number; onNavigate: (track: string, unit: number) => void }) {
  const track = PUBLIC_TRACKS.find(t => t.trackId === trackId) || PUBLIC_TRACKS[0];
  const content = publicContentForTrack(track)!;
  const lesson = content.lessons[unit - 1];
  const quiz = content.quizzes[unit - 1];
  const assignment = content.assignments[unit - 1];
  const lab = content.labs.find(l => l.id === lesson.labId);
  const storageKey = `waike.practice.v1:${track.trackId}:${content.contentRootSha256}`;
  const [record, setRecord] = useState<RecordState>(empty);
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState('');
  const [responses, setResponses] = useState<Record<string, number>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState('');
  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed.viewed) && parsed.quizzes && parsed.drafts) {
          setRecord(parsed); setConsent(true); setDraft(parsed.drafts[String(unit)] || '');
        }
      }
    } catch { setMessage('Saved practice could not be read. You can continue without saving.'); }
  }, [storageKey, unit]);
  function save(next: RecordState) {
    setRecord(next);
    if (!consent) { setMessage('Kept for this visit. Turn on device saving to keep it after closing.'); return; }
    try { localStorage.setItem(storageKey, JSON.stringify(next)); setMessage('Saved on this browser.'); }
    catch { setMessage('Browser storage is unavailable. Download your evidence before leaving.'); }
  }
  async function evaluate(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setResult(null); setMessage('');
    try {
      // Same-origin reverse proxy. No user-controlled server URL and no credentials.
      const response = await fetch(`/api/v1/public-practice/${track.trackId}/${unit}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'omit',
        body: JSON.stringify({ responses, quiz_sha256: quiz.sha256 }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' ? error.detail : 'Practice evaluation is unavailable. Your answers have not been graded.');
      }
      const next: Result = await response.json(); setResult(next);
      save({ ...record, quizzes: { ...record.quizzes, [unit]: { earned: next.earned, possible: next.possible } } });
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Evaluation unavailable; no score recorded.'); }
    finally { setBusy(false); }
  }
  function download() {
    const blob = new Blob([JSON.stringify({ schema: 'waike.guest.practice.v1', trackId: track.trackId, sourceCommit: content.sourceCommit, contentHash: content.contentRootSha256, ...record, currentDraft: draft, status: 'ungraded guest evidence; no credential or completion credit' }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a');
    link.href = url; link.download = `${track.trackId}-practice.json`; link.click(); URL.revokeObjectURL(url);
  }
  return <section className="browser-learning" aria-label="Course learning reader" data-testid="browser-learning">
    <header><p className="eyebrow">WAIKE / Open learning</p><h1>{track.title}</h1>
      <label htmlFor="reader-course">Choose course</label><select id="reader-course" value={track.trackId} onChange={e => onNavigate(e.target.value, 1)}>{PUBLIC_TRACKS.map(t => <option key={t.trackId} value={t.trackId}>{t.title}</option>)}</select>
      <label htmlFor="reader-unit">Choose unit</label><select id="reader-unit" value={unit} onChange={e => onNavigate(track.trackId, Number(e.target.value))}>{content.lessons.map((l,i) => <option key={l.id} value={i+1}>{i+1}. {l.title}</option>)}</select>
      <p>Prerequisites: {content.prerequisites?.required?.join('; ') || 'Review the course syllabus before starting.'}</p>
    </header>
    <nav aria-label="Unit sections">{[["lesson","Lesson"],["practice-lab","Lab"],["practice-quiz","Quiz"],["practice-assignment","Assignment"],["practice-progress","My evidence"]].map(([id,label]) => <a key={id} href={`#${id}`} onClick={e => { e.preventDefault(); document.getElementById(id)?.scrollIntoView(); }}>{label}</a>)}</nav>
    <article id="lesson" tabIndex={-1}><SafeMarkdown markdown={lesson.markdown.replace(/^(#{1,5}) /gm, "$1# ")} testId="full-lesson-content" />
      <button onClick={() => save({ ...record, viewed: Array.from(new Set([...record.viewed, unit])) })}>Mark this lesson read</button>
      <p>Reading records engagement. It does not demonstrate mastery.</p>
    </article>
    <section id="practice-lab"><h2>Practice lab</h2>{lab ? <SafeMarkdown markdown={lab.markdown.replace(/^(#{1,5}) /gm, "$1# ")} /> : <p>The linked lab could not be loaded. No lab completion is recorded.</p>}
      {lesson.labId === 'lab_storage' && <StoragePractice />}
      <p>Command-line activities require the canonical curriculum checkout and the stated tools. Submit your own artifact; running a reference fixture does not establish your competence. Browser calculations are formative practice.</p>
    </section>
    <section id="practice-quiz"><h2>Unit {unit} practice quiz</h2><p>Answer every question, then check your reasoning. This practice score is not an authenticated grade. Questions are sent to the evaluator; no account or draft is sent.</p>
      <form onSubmit={evaluate}>{quiz.items?.map((item, i) => <fieldset key={item.id}><legend>{i+1}. {item.stem}</legend>
        {item.choices.map((choice,index) => <label className="quiz-choice" key={index}><input required type="radio" name={item.id} checked={responses[item.id] === index} onChange={() => { setResponses({ ...responses, [item.id]: index }); setResult(null); }} />{choice}</label>)}
        {result && <p className={result.feedback[i]?.correct ? 'practice-correct' : 'practice-review'}>{result.feedback[i]?.correct ? 'Correct. ' : 'Review. '}{result.feedback[i]?.explanation}</p>}
      </fieldset>)}<button disabled={busy}>{busy ? 'Checking…' : 'Check my answers'}</button><button type="button" onClick={() => { setResponses({}); setResult(null); }}>Retry with a fresh response</button></form>
      {result && <p role="status">Practice result: {result.earned} / {result.possible}. No server record was created.</p>}
    </section>
    <section id="practice-assignment"><h2>Independent assignment</h2><SafeMarkdown markdown={assignment.markdown.replace(/^(#{1,5}) /gm, "$1# ")} />
      <label>My private draft (avoid personal information, passwords and real learner records)<textarea rows={8} maxLength={20000} value={draft} onChange={e => setDraft(e.target.value)} /></label>
      <button onClick={() => save({ ...record, drafts: { ...record.drafts, [unit]: draft } })}>Save draft on this device</button>
      <p>Draft only. To submit for assessment, sign in to an authorized school Hub and open this course’s Assignments workspace. Submission, instructor feedback and official grades use that Hub’s existing records. A guest draft is not submitted automatically.</p>
      <details><summary>Assessment rubric</summary><pre>{content.references?.find(r => r.path.endsWith('rubrics.json'))?.markdown || 'Instructor review required.'}</pre></details>
    </section>
    <section id="practice-progress"><h2>My evidence</h2>
      <p>Lesson reads: {record.viewed.length} / {content.lessons.length}. Quizzes practiced: {Object.keys(record.quizzes).length}. Drafts saved: {Object.keys(record.drafts).length}. Labs and assignments still require verified evidence and review. Course completion: not established.</p>
      <dl><dt>Viewed</dt><dd>{record.viewed.length} lessons marked read</dd><dt>Practiced</dt><dd>{Object.keys(record.quizzes).length} quizzes with a checked response</dd><dt>Submitted</dt><dd>No guest work submitted to a school Hub</dd><dt>Evaluated</dt><dd>Formative quiz feedback only; practical and instructor evaluation pending</dd><dt>Completed</dt><dd>Not established</dd><dt>Competency demonstrated</dt><dd>Not established; requires verified practical evidence and authorized review</dd></dl>
      <label><input type="checkbox" checked={consent} onChange={e => { setConsent(e.target.checked); if (!e.target.checked) { try { localStorage.removeItem(storageKey); } catch { /* unavailable storage */ } } }} />Save practice on this browser. Other people using this browser may be able to see it.</label>
      <button onClick={download}>Download my practice evidence</button><button onClick={() => { try { localStorage.removeItem(storageKey); } catch { /* unavailable storage */ } setRecord(empty()); setDraft(''); setConsent(false); setMessage('This course’s saved practice was cleared.'); }}>Clear this course’s device record</button>
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
    <label>Used GiB<input type="number" min="0" max="256" value={used} onChange={e => setUsed(e.target.value)} /></label>
    <label>Reserved GiB<input type="number" min="0" max="256" value={reserve} onChange={e => setReserve(e.target.value)} /></label>
    <label>Your free percentage<input type="number" step="any" value={answer} onChange={e => setAnswer(e.target.value)} /></label>
    <button onClick={() => { const u=Number(used), r=Number(reserve), a=Number(answer); if (!used || !reserve || !answer || ![u,r,a].every(Number.isFinite) || u<0 || r<0 || u+r>256 || a<0 || a>100) { setFeedback('Enter valid nonnegative capacities totaling no more than 256 GiB and a percentage from 0 to 100.'); return; } const percent=(256-u-r)/256*100; setFeedback(Math.abs(a-percent)<0.01 ? `Calculation verified: ${percent.toFixed(3)}%. ${percent>=15 ? 'Meets' : 'Below'} this fixture’s 15% policy. Change the inputs and predict the result again.` : 'The calculation differs. Subtract both used and reserved capacity before dividing by 256. Try again.'); }}>Verify my calculation</button><p role="status">{feedback}</p>
  </aside>;
}
