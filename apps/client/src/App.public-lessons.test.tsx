import {cleanup,render,screen,waitFor,within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import App from './App';
import {PUBLIC_TRACKS,loadPublicContent,publicContentForTrack} from './lib/product/publicCurriculum';
import {resetMockHubStore} from './lib/hub/mockHub';

beforeEach(async ()=>{resetMockHubStore();localStorage.clear();sessionStorage.clear();vi.stubEnv('VITE_PIXEL_PILOT','true');vi.stubEnv('VITE_HUB_URL','');await loadPublicContent(PUBLIC_TRACKS[0]);await loadPublicContent(PUBLIC_TRACKS[3]);});
afterEach(()=>{cleanup();resetMockHubStore();localStorage.clear();sessionStorage.clear();vi.unstubAllEnvs();});

describe('public Lessons navigation',()=>{
 it('opens the existing beginner reader from Home without requiring a selected course',async()=>{
  const user=userEvent.setup();render(<App/>);
  await user.click(screen.getByTestId('mode-home'));
  await user.click(screen.getByRole('button',{name:/^Lessons$/}));
  await waitFor(()=>expect(screen.getByTestId('browser-learning')).toHaveTextContent(publicContentForTrack(PUBLIC_TRACKS[0])!.lessons[0].title));
  expect(screen.getByTestId('browser-learning')).toHaveTextContent(PUBLIC_TRACKS[0].title);
  expect(screen.queryByTestId('learner-home')).not.toBeInTheDocument();
  expect(screen.queryByText('No course installed')).not.toBeInTheDocument();
 });
 it('returns to the selected course and unit rather than Home or another course',async()=>{
  const user=userEvent.setup();render(<App/>);
  await user.click(screen.getByTestId('mode-courses'));
  await user.click(screen.getAllByRole('button',{name:'Open course'})[3]);
  await user.click(within(screen.getByTestId('module-sequence')).getAllByRole('button',{name:/^Lesson:/})[1]);
  const title=publicContentForTrack(PUBLIC_TRACKS[3])!.lessons[1].title;
  expect(screen.getByTestId('browser-learning')).toHaveTextContent(title);
  await user.click(screen.getByTestId('mode-home'));
  await user.click(screen.getByRole('button',{name:/^Lessons$/}));
  await waitFor(()=>expect(screen.getByTestId('browser-learning')).toHaveTextContent(title));
  expect(screen.getByTestId('browser-learning')).toHaveTextContent(PUBLIC_TRACKS[3].title);
  expect(screen.queryByTestId('learner-home')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:/^Back to courses$/}));
  expect(document.querySelectorAll('[data-testid^="course-card-"]')).toHaveLength(18);
 });
 it('keeps the installed-pack lesson reader for native mode',async()=>{
  vi.stubEnv('VITE_PIXEL_PILOT','false');
  const user=userEvent.setup();render(<App/>);
  await user.click(screen.getByRole('button',{name:/Install learner pack/i}));
  await user.click(screen.getByRole('button',{name:/Week 1/i}));
  await user.click(screen.getByTestId('mode-home'));
  await user.click(screen.getByRole('button',{name:/^Lessons$/}));
  expect(screen.getByTestId('lesson-body')).toHaveTextContent(/Real lesson content/i);
  expect(screen.queryByTestId('study-mode')).not.toBeInTheDocument();
 });
});
