export type StudyModeId =
  | "read"
  | "listen"
  | "practice"
  | "flashcards"
  | "ask"
  | "self_check"
  | "lab"
  | "explain"
  | "mastery";

export interface StudyModeAvailability {
  id: StudyModeId;
  label: string;
  available: boolean;
  honesty: string;
}

export function studyModesForContent(flags: {
  hasReadableText: boolean;
  ttsAvailable: boolean;
  authoredPractice: boolean;
  authoredFlashcards: boolean;
  labLaunchable: boolean;
  masteryEvidence: boolean;
}): StudyModeAvailability[] {
  return [
    {
      id: "read",
      label: "Read",
      available: flags.hasReadableText,
      honesty: "Safe rendered course text.",
    },
    {
      id: "listen",
      label: "Listen",
      available: flags.hasReadableText && flags.ttsAvailable,
      honesty: "Reading aid using system speech. Not studio narration.",
    },
    {
      id: "practice",
      label: "Practice",
      available: true,
      honesty: flags.authoredPractice
        ? "Authored low-stakes practice."
        : "No authored practice. gunnchAI can propose labeled drafts only.",
    },
    {
      id: "flashcards",
      label: "Flashcards",
      available: true,
      honesty: flags.authoredFlashcards
        ? "Authored cards plus learner-created cards."
        : "Learner-created cards. AI drafts stay unlabeled until you accept them.",
    },
    {
      id: "ask",
      label: "Ask gunnchAI",
      available: true,
      honesty: "Contextual help. Never answer keys.",
    },
    {
      id: "self_check",
      label: "Self-check",
      available: true,
      honesty: "Not graded. Separate from formal assessments.",
    },
    {
      id: "lab",
      label: "Lab",
      available: flags.labLaunchable,
      honesty: flags.labLaunchable ? "Opens the existing WAIKE lab flow." : "No lab is attached to this lesson.",
    },
    {
      id: "explain",
      label: "Explain It Back",
      available: true,
      honesty: "Coaching only. Not authoritative grading.",
    },
    {
      id: "mastery",
      label: "Mastery",
      available: flags.masteryEvidence,
      honesty: flags.masteryEvidence ? "Shows recorded evidence and next remediation." : "No mastery evidence yet.",
    },
  ];
}
