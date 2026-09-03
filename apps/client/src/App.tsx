import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { AssessmentWorkspace } from "./components/assessment/AssessmentWorkspace";
import { InstructorQueue } from "./components/assessment/InstructorQueue";
import { CourseCard } from "./components/CourseCard";
import { LessonReader } from "./components/LessonReader";
import { TrustBanner } from "./components/TrustBanner";
import { createHttpHubClient, type HubActor, type HubClient } from "./lib/hub/client";
import { createMockHubClient } from "./lib/hub/mockHub";
import { browseInstallPack, isTauri } from "./lib/tauriBridge";
import type { LessonContent, LessonInfo, ModuleView, TrustStatus } from "./lib/types";
import {
  mockModule,
  mockTrust,
  simulateInstallFailure,
  simulateVerifiedInstall,
} from "./lib/mockRuntime";

type Mode = "lessons" | "assignments" | "instruct";

function formatPackError(err: unknown): string {
  const raw = typeof err === "string" ? err : err && typeof err === "object" ? JSON.stringify(err) : String(err);
  const upper = raw.toUpperCase();
  if (upper.includes("WRONG_ROLE")) {
    return "WRONG_ROLE — Import a signed learner pack. Instructor packs are rejected here.";
  }
  if (
    upper.includes("TAMPERED") ||
    upper.includes("BAD_SIGNATURE") ||
    upper.includes("UNSIGNED") ||
    upper.includes("MISSING_SIGNATURE")
  ) {
    return "TAMPERED_CONTENT / signature failure — Package is corrupted or altered and was not trusted.";
  }
  if (
    upper.includes("INCOMPATIBLE") ||
    upper.includes("SCHEMA_DOWNGRADE") ||
    upper.includes("PLATFORM_TOO_OLD")
  ) {
    return "INCOMPATIBLE_SCHEMA — This package is incompatible with this client.";
  }
  return raw;
}

function resolveHub(actor: HubActor): HubClient {
  const base = (import.meta.env.VITE_HUB_URL as string | undefined) || "";
  if (base) return createHttpHubClient(base.replace(/\/$/, ""), actor);
  return createMockHubClient(actor);
}

export default function App() {
  const [trust, setTrust] = useState<TrustStatus>(mockTrust);
  const [module, setModule] = useState<ModuleView | null>(isTauri() ? null : mockModule);
  const [lesson, setLesson] = useState<LessonContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumeOffset, setResumeOffset] = useState(0);
  const [resumeHint, setResumeHint] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("lessons");
  const [actor, setActor] = useState<HubActor>({ actorId: "learner-a", role: "learner" });

  const hub = useMemo(() => resolveHub(actor), [actor]);

  useEffect(() => {
    if (!isTauri()) return;
    (async () => {
      try {
        const packs = await invoke<TrustStatus[]>("list_installed_packs");
        if (packs.length === 0) return;
        const t = packs[0];
        setTrust(t);
        const lessons = await invoke<LessonInfo[]>("list_lessons", { packId: t.pack_id });
        setModule({
          pack_id: t.pack_id,
          module_id: t.module_id,
          title: t.title,
          lessons,
          trust: t,
        });
        const resume = await invoke<{
          lesson_id: string;
          scroll_offset: number;
        } | null>("get_resume_position", { packId: t.pack_id });
        if (resume) {
          setResumeHint(`Resume ${resume.lesson_id} @ ${Math.round(resume.scroll_offset)}px`);
        }
      } catch (e) {
        setError(formatPackError(e));
      }
    })();
  }, []);

  async function onInstall() {
    setError(null);
    try {
      if (!isTauri()) {
        const failure = (window as unknown as { __WAIKE_MOCK_FAIL__?: string }).__WAIKE_MOCK_FAIL__;
        if (failure) {
          throw simulateInstallFailure(failure);
        }
        const verified = simulateVerifiedInstall();
        setTrust(verified.trust);
        setModule(verified.module);
        setResumeHint(verified.resumeHint);
        if (verified.resumeLesson) {
          setLesson(verified.resumeLesson);
          setResumeOffset(verified.resumeLesson.resume_scroll_offset);
        }
        return;
      }
      const path = await browseInstallPack();
      if (!path) return;
      const t = await invoke<TrustStatus>("install_learner_pack", { path });
      setTrust(t);
      if (!t.trusted) {
        setError(t.verification_status);
        return;
      }
      const lessons = await invoke<LessonInfo[]>("list_lessons", { packId: t.pack_id });
      setModule({
        pack_id: t.pack_id,
        module_id: t.module_id,
        title: t.title,
        lessons,
        trust: t,
      });
    } catch (e) {
      setError(formatPackError(e));
    }
  }

  async function onOpenLesson(info: LessonInfo) {
    setError(null);
    try {
      if (!isTauri() || !module) {
        const resume =
          (window as unknown as { __WAIKE_RESUME_OFFSET__?: number }).__WAIKE_RESUME_OFFSET__ ?? 0;
        setLesson({
          lesson_id: info.lesson_id,
          title: info.title,
          path: info.path,
          markdown: `# ${info.title}\n\nReal lesson content from the pack (preview).`,
          resume_scroll_offset: resume,
        });
        setResumeOffset(resume);
        if (resume > 0) {
          setResumeHint(`Resume ${info.lesson_id} @ ${Math.round(resume)}px`);
        }
        return;
      }
      const content = await invoke<LessonContent>("open_lesson", {
        packId: module.pack_id,
        lessonId: info.lesson_id,
      });
      setLesson(content);
      setResumeOffset(content.resume_scroll_offset || 0);
      if (content.resume_scroll_offset > 0) {
        setResumeHint(
          `Resume ${content.lesson_id} @ ${Math.round(content.resume_scroll_offset)}px`,
        );
      }
    } catch (e) {
      setError(formatPackError(e));
    }
  }

  const onSavePosition = useCallback(
    async (offset: number) => {
      if (!lesson || !module) return;
      if (!isTauri()) {
        (window as unknown as { __WAIKE_RESUME_OFFSET__?: number }).__WAIKE_RESUME_OFFSET__ = offset;
        setResumeHint(`Resume ${lesson.lesson_id} @ ${Math.round(offset)}px`);
        return;
      }
      await invoke("save_lesson_position", {
        packId: module.pack_id,
        lessonId: lesson.lesson_id,
        path: lesson.path,
        scrollOffset: offset,
      });
    },
    [lesson, module],
  );

  function switchActor(next: HubActor) {
    setActor(next);
    if (next.role === "instructor" && mode === "assignments") setMode("instruct");
    if (next.role === "learner" && mode === "instruct") setMode("assignments");
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header>
        <h1 className="brand">WAIKE Learning OS</h1>
        <p className="tagline">
          Local-first learning client. Packages are verified before trust. Assessment lifecycle is
          live for DIGITAL_CONFIDENCE.
        </p>
        <div className="toolbar">
          <button type="button" onClick={() => void onInstall()}>
            Install learner pack
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              setLesson(null);
              setError(null);
              setMode("lessons");
            }}
          >
            Back to module
          </button>
        </div>
        <div className="mode-bar" role="navigation" aria-label="Primary">
          <button
            type="button"
            className={mode === "lessons" ? "mode-active" : "ghost"}
            onClick={() => setMode("lessons")}
          >
            Lessons
          </button>
          <button
            type="button"
            className={mode === "assignments" ? "mode-active" : "ghost"}
            data-testid="mode-assignments"
            onClick={() => {
              switchActor({ actorId: "learner-a", role: "learner" });
              setMode("assignments");
            }}
          >
            Assignments
          </button>
          <button
            type="button"
            className={mode === "instruct" ? "mode-active" : "ghost"}
            data-testid="mode-instruct"
            onClick={() => {
              switchActor({ actorId: "instructor-1", role: "instructor" });
              setMode("instruct");
            }}
          >
            Instruct
          </button>
          <span className="muted actor-chip" data-testid="actor-chip">
            {actor.role}:{actor.actorId}
          </span>
        </div>
      </header>

      <TrustBanner trust={trust} />
      {resumeHint ? (
        <p className="muted" data-testid="resume-hint">
          {resumeHint}
        </p>
      ) : null}
      {error ? (
        <div className="error-box" role="alert" data-testid="error-box">
          {error}
        </div>
      ) : null}

      <div className="layout" id="main">
        {mode === "lessons" ? (
          <>
            {module ? (
              <CourseCard module={module} onOpenLesson={(l) => void onOpenLesson(l)} />
            ) : (
              <section className="course-card">
                <h2>No course installed</h2>
                <p className="muted">Install a signed DIGITAL_CONFIDENCE learner pack to begin.</p>
              </section>
            )}
            {lesson ? (
              <LessonReader
                lesson={lesson}
                resumeOffset={resumeOffset}
                onSavePosition={(o) => void onSavePosition(o)}
              />
            ) : (
              <section className="lesson-reader">
                <h2>Lesson reader</h2>
                <p className="muted">Select a lesson after the pack verifies.</p>
              </section>
            )}
          </>
        ) : null}
        {mode === "assignments" ? <AssessmentWorkspace hub={hub} /> : null}
        {mode === "instruct" ? <InstructorQueue hub={hub} /> : null}
      </div>
    </div>
  );
}
