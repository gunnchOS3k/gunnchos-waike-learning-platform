import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { BrowserLearning, parseLearningHash } from './BrowserLearning';
import { PUBLIC_TRACKS, publicContentForTrack } from '../../lib/product/publicCurriculum';
beforeEach(() => { localStorage.clear(); });
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
});
