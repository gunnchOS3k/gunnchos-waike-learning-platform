import type { LessonContent, ModuleView, TrustStatus } from "./types";

export const mockTrust: TrustStatus = {
  pack_id: "DIGITAL_CONFIDENCE.learner.v1",
  module_id: "DIGITAL_CONFIDENCE",
  title: "Digital Confidence to Computer Operator",
  verification_status: "unverified",
  content_root_sha256: "",
  source_commit: "",
  trusted: false,
  reason: "VERIFY_BEFORE_TRUST",
};

export const mockModule: ModuleView = {
  pack_id: mockTrust.pack_id,
  module_id: "DIGITAL_CONFIDENCE",
  title: "Digital Confidence to Computer Operator",
  lessons: [
    {
      lesson_id: "DIGITAL_CONFIDENCE.W01",
      title: "Digital Confidence — Week 1",
      path: "lessons/by_course/digital_confidence/week_01/lesson_plan.md",
      week: 1,
      order: 1,
    },
  ],
  trust: mockTrust,
};

export function simulateVerifiedInstall(): {
  trust: TrustStatus;
  module: ModuleView;
  resumeHint: string | null;
  resumeLesson: LessonContent | null;
} {
  const trust: TrustStatus = {
    ...mockTrust,
    trusted: true,
    verification_status: "verified",
    content_root_sha256: "abc123",
    source_commit: "8eb2827dc58ffa391842da1bfb1ee665c25a31a7",
    reason: null,
  };
  const module: ModuleView = { ...mockModule, trust, title: trust.title };
  return { trust, module, resumeHint: null, resumeLesson: null };
}

export function simulateInstallFailure(code: string): { code: string; message: string } {
  return { code, message: code };
}
