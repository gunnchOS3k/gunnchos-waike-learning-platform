import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { BrowserLearning, parseLearningHash } from './BrowserLearning';
import { PUBLIC_TRACKS, loadPublicContent, publicAssignmentsForTrack, publicContentForTrack } from '../../lib/product/publicCurriculum';
beforeEach(async () => { localStorage.clear(); await loadPublicContent(PUBLIC_TRACKS[0]); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe('browser course learning', () => {
  it('only accepts known course and unit deep links', () => {
    expect(parseLearningHash('#/learn/DIGITAL_CONFIDENCE/10')).toEqual({track:'DIGITAL_CONFIDENCE',unit:10});
    for (const h of ['#/learn/UNKNOWN/1','#/learn/DIGITAL_CONFIDENCE/0','#/learn/DIGITAL_CONFIDENCE/11','#/learn/../1','#/learn/DIGITAL_CONFIDENCE/1?hub=evil']) expect(parseLearningHash(h)).toBeNull();
  });
  it('evaluates selected responses and preserves practice as ungraded evidence', async () => {
    const quiz=publicContentForTrack(PUBLIC_TRACKS[0])!.quizzes[0];
    const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({kind:'formative_practice',persisted:false,earned:0,possible:quiz.items!.length,feedback:quiz.items!.map(q=>({id:q.id,correct:false,explanation:'Review the lesson.'}))})});
    vi.stubGlobal('fetch',fetch);
    render(<BrowserLearning trackId="DIGITAL_CONFIDENCE" unit={1} onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByLabelText(/Save practice on this browser/));
    const groups=Array.from(document.querySelectorAll('fieldset'));
    groups.forEach(group=>fireEvent.click(group.querySelector('input')!));
    fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await waitFor(()=>expect(screen.getByText(/Practice result: 0/)).toBeInTheDocument());
    const request=JSON.parse(fetch.mock.calls[0][1].body);
    expect(Object.keys(request.responses)).toHaveLength(quiz.items!.length);
    expect(request.quiz_sha256).toBe(quiz.sha256);
    expect(fetch.mock.calls[0][1].credentials).toBe('omit');
    expect(screen.getByText(/Course completion: not established/)).toBeInTheDocument();
    expect(localStorage.length).toBe(1);
    fireEvent.click(screen.getByRole('button',{name:'Retry with a fresh response'}));
    expect(screen.getAllByRole('radio').every(r=>!(r as HTMLInputElement).checked)).toBe(true);
  });
  it('does not invent a score when evaluation fails',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('Connection lost')));
    render(<BrowserLearning trackId="DIGITAL_CONFIDENCE" unit={1} onNavigate={vi.fn()} />);
    Array.from(document.querySelectorAll('fieldset')).forEach(g=>fireEvent.click(g.querySelector('input')!));
    fireEvent.click(screen.getByRole('button',{name:'Check my answers'}));
    await waitFor(()=>expect(screen.getByText('Connection lost')).toBeInTheDocument());
    expect(screen.queryByText(/Practice result:/)).toBeNull(); expect(localStorage.length).toBe(0);
  });
  it('stores an opted-in private draft and restores it without creating a submission',()=>{
    const props={trackId:'DIGITAL_CONFIDENCE',unit:1,onNavigate:vi.fn()};
    const view=render(<BrowserLearning {...props}/>);
    fireEvent.click(screen.getByLabelText(/Save practice on this browser/));
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'Fictional ticket draft'}});
    fireEvent.click(screen.getByRole('button',{name:'Save draft on this device'}));view.unmount();
    render(<BrowserLearning {...props}/>);expect(screen.getByRole('textbox')).toHaveValue('Fictional ticket draft');
    expect(screen.getByText(/Draft only/)).toBeInTheDocument();
  });
  it('reads lesson progress back after device saving is turned on', async () => {
    const props={trackId:'DIGITAL_CONFIDENCE',unit:1,onNavigate:vi.fn()};
    const view=render(<BrowserLearning {...props}/>);
    fireEvent.click(screen.getByRole('button',{name:'Mark this lesson read'}));
    expect(screen.getByText(/Lesson reads: 1 \//)).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    fireEvent.click(screen.getByLabelText(/Save practice on this browser/));
    view.unmount();
    render(<BrowserLearning {...props}/>);
    await waitFor(() => expect(screen.getByText(/Lesson reads: 1 \//)).toBeInTheDocument());
    expect(screen.getByText(/1 lessons marked read/)).toBeInTheDocument();
    expect(screen.getByText(/Course completion: not established/)).toBeInTheDocument();
  });
  it('executes a unit-1 read for every canonical track without awarding completion', async () => {
    expect(PUBLIC_TRACKS.map(t => t.trackId)).toEqual([
      'DIGITAL_CONFIDENCE','IT_SUPPORT_HARDWARE','SOFTWARE_BUILDER','NETWORKING_INFRA','CYBER_SOC','DATA_DASHBOARDS','AI_ML_EDGE','EMBEDDED_PROTOTYPING','WIRELESS_6G','PM_AGILE_LSS','GAME_DEV_INTERACTIVE','SEVEN_GC_APPRENTICESHIP','CLOUD_DEVOPS','COMM_PD_ETHICS','ROBOTICS_CONTROL','GUNNCHOS_PRODUCT_LAB','HARDWARE_ENGINEERING','DATA_VIZ_BI',
    ]);
    for (const track of PUBLIC_TRACKS) {
      const content = await loadPublicContent(track);
      expect(content.lessons[0]?.markdown.length).toBeGreaterThan(0);
      const view = render(<BrowserLearning trackId={track.trackId} unit={1} onNavigate={vi.fn()} />);
      const reader = screen.getByTestId('browser-learning');
      expect(reader.querySelector('header h1')?.textContent).toBe(track.title);
      fireEvent.click(screen.getByRole('button', { name: 'Mark this lesson read' }));
      expect(screen.getByText(/Lesson reads: 1 \//)).toBeInTheDocument();
      expect(screen.getByText(/Course completion: not established/)).toBeInTheDocument();
      view.unmount();
      cleanup();
    }
  });
  it('lets a guest complete an ungraded journey on more than one track', async () => {
    expect(PUBLIC_TRACKS).toHaveLength(18);
    for (const track of PUBLIC_TRACKS) {
      const content = await loadPublicContent(track);
      expect(content.lessons[0]?.markdown.length).toBeGreaterThan(80);
      expect((content.labs[0]?.markdown || '').length).toBeGreaterThan(40);
      expect(content.quizzes.length).toBeGreaterThan(0);
      expect(content.assignments.length).toBeGreaterThan(0);
      for (const quiz of content.quizzes) {
        for (const item of quiz.items || []) {
          expect(item).not.toHaveProperty('answer_index');
          expect(item).not.toHaveProperty('answer');
          expect(JSON.stringify(item).toLowerCase()).not.toContain('answer_key');
        }
      }
      for (const card of publicAssignmentsForTrack(track)) {
        expect(card.submission_state).toBe('Requires a school Hub');
        expect(card.grade_state).toBe('none');
      }
    }
    for (const track of [PUBLIC_TRACKS[0], PUBLIC_TRACKS[8], PUBLIC_TRACKS[17]]) {
      const content = publicContentForTrack(track)!;
      const quiz = content.quizzes[0];
      const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>({kind:'formative_practice',persisted:false,earned:0,possible:quiz.items!.length,feedback:quiz.items!.map(q=>({id:q.id,correct:false,explanation:'Review the lesson.'}))})});
      vi.stubGlobal('fetch', fetch);
      const view = render(<BrowserLearning trackId={track.trackId} unit={1} onNavigate={vi.fn()} />);
      expect((screen.getByTestId('full-lesson-content').textContent || '').length).toBeGreaterThan(40);
      expect(screen.getByRole('heading', {name:'Practice lab'})).toBeInTheDocument();
      expect(screen.getByText(/This practice score is not an authenticated grade/)).toBeInTheDocument();
      expect(screen.getByText(/A guest draft is not submitted automatically/)).toBeInTheDocument();
      expect(screen.queryByText(/answer key/i)).toBeNull();
      expect(screen.queryByRole('button', {name:/exam/i})).toBeNull();
      Array.from(document.querySelectorAll('fieldset')).forEach(group => fireEvent.click(group.querySelector('input')!));
      fireEvent.click(screen.getByRole('button', {name:'Check my answers'}));
      await waitFor(() => expect(screen.getByText(/No server record was created/)).toBeInTheDocument());
      expect(screen.getByText(/Course completion: not established/)).toBeInTheDocument();
      expect(fetch.mock.calls[0][0]).toBe(`/api/v1/public-practice/${track.trackId}/1`);
      expect(fetch.mock.calls[0][1].credentials).toBe('omit');
      const body = JSON.parse(fetch.mock.calls[0][1].body);
      expect(body.quiz_sha256).toBe(quiz.sha256);
      expect(body).not.toHaveProperty('grade');
      view.unmount();
      cleanup();
      localStorage.clear();
    }
  });
  it('opens the signed-in week-1 lesson, practices without a grade, and requests source tutoring', async () => {
    const quiz = publicContentForTrack(PUBLIC_TRACKS[0])!.quizzes[0];
    const fetch = vi.fn(async (url: string) => {
      const target = String(url);
      if (target.endsWith('/lessons/1')) {
        return { ok: true, json: async () => ({ text: 'Server lesson week 1', progress_store: 'lesson_progress', grade_written: false }) };
      }
      if (target.endsWith('/lessons/1/practice')) {
        return { ok: true, json: async () => ({ kind: 'formative_practice', persisted: false, grade_written: false, earned: 0, possible: quiz.items!.length, feedback: quiz.items!.map(item => ({ id: item.id, correct: false, explanation: 'Review the lesson.' })) }) };
      }
      if (target.endsWith('/ai/learner/assist')) {
        return { ok: true, json: async () => ({ ok: true, suggestion_only: true, mutates_grades: false, text: 'Source: lesson\n\nServer lesson week 1' }) };
      }
      throw new Error(target);
    });
    vi.stubGlobal('fetch', fetch);
    render(<BrowserLearning trackId="DIGITAL_CONFIDENCE" unit={1} onNavigate={vi.fn()} auth={{ token: 'learner-token', baseUrl: 'https://hub.example', sectionId: 'sec_alpha_dc_w01', onReview: vi.fn() }} />);
    await waitFor(() => expect(screen.getByText('Progress is stored in lesson_progress. No grade was written.')).toBeInTheDocument());
    expect(fetch.mock.calls[0][0]).toBe('https://hub.example/api/v1/sections/sec_alpha_dc_w01/lessons/1');
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer learner-token');
    Array.from(document.querySelectorAll('fieldset')).forEach(group => fireEvent.click(group.querySelector('input')!));
    fireEvent.click(screen.getByRole('button', { name: 'Check my answers' }));
    await waitFor(() => expect(screen.getByText(/Practice result: 0 \/ \d+\. No grade was written\./)).toBeInTheDocument());
    const practice = fetch.mock.calls.find(call => String(call[0]).endsWith('/practice'));
    expect(practice?.[0]).toBe('https://hub.example/api/v1/sections/sec_alpha_dc_w01/lessons/1/practice');
    expect(practice?.[1].headers.Authorization).toBe('Bearer learner-token');
    expect(JSON.parse(practice?.[1].body)).not.toHaveProperty('grade');
    fireEvent.change(screen.getByLabelText('Ask about this lesson'), { target: { value: 'kiosk idle essay session' } });
    fireEvent.click(screen.getByRole('button', { name: 'Request source tutoring' }));
    await waitFor(() => expect(screen.getByText('Deterministic source text. modelCompletion is empty. This is not model inference.')).toBeInTheDocument());
    const tutoring = fetch.mock.calls.find(call => String(call[0]).endsWith('/assist'));
    const asked = JSON.parse(tutoring?.[1].body);
    expect(asked.section_id).toBe('sec_alpha_dc_w01');
    expect(asked.capability).toBe('explain');
    expect(asked).not.toHaveProperty('learner_id');
    expect(asked).not.toHaveProperty('grade');
  });
});
