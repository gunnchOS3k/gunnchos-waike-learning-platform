import type { ModuleStatus } from "./types";

export const MODULE_STATUS_LABEL: Record<ModuleStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  submitted: "Submitted",
  needs_review: "Needs review",
  complete: "Complete",
  locked: "Locked by real prerequisite",
};

export function resolveModuleStatus(args: {
  started: boolean;
  submitted: boolean;
  needsReview: boolean;
  complete: boolean;
  lockedByPrerequisite: boolean;
}): ModuleStatus {
  if (args.lockedByPrerequisite && !args.complete && !args.started) return "locked";
  if (args.complete) return "complete";
  if (args.needsReview) return "needs_review";
  if (args.submitted) return "submitted";
  if (args.started) return "in_progress";
  return "not_started";
}
