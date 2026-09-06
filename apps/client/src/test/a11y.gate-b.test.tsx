import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  InstructorAiPanel,
  LearnerAiPanel,
  type AiClient,
  type AiAssistResult,
  type EffectiveAiPolicy,
} from "../components/ai/AiPanels";

afterEach(() => {
  cleanup();
});

const learnerPolicy: EffectiveAiPolicy = {
  policy: "AI_HINTS_ONLY",
  scope: "section",
  section_id: "sec_alpha_dc_w01",
  allowed_learner_capabilities: ["hint", "explain"],
  allowed_instructor_capabilities: ["feedback_suggest"],
};

const okResult: AiAssistResult = {
  ok: true,
  text: "Try breaking the problem into smaller steps.",
  grounded: true,
  citations: [{ source: "lesson.md", snippet: "practice safely" }],
  refused: false,
  refusal_code: null,
  disclosure: "Suggestion only — not an answer key.",
  suggestion_only: true,
  mutates_grades: false,
};

function mockAi(overrides: Partial<AiClient> = {}): AiClient {
  return {
    getPolicy: vi.fn(async () => learnerPolicy),
    learnerAssist: vi.fn(async () => okResult),
    instructorAssist: vi.fn(async () => okResult),
    applyGrade: vi.fn(async () => {
      throw new Error("403:AI_GRADE_MUTATION_FORBIDDEN");
    }),
    ...overrides,
  };
}

describe("Gate B AI panel accessibility smoke (not certification)", () => {
  it("learner panel exposes labelled region, labels, and live status roles", async () => {
    const ai = mockAi();
    render(<LearnerAiPanel ai={ai} sectionId="sec_alpha_dc_w01" />);

    const region = screen.getByTestId("learner-ai-panel");
    expect(region).toHaveAttribute("aria-labelledby", "learner-ai-heading");
    expect(screen.getByRole("heading", { name: /gunnchai tutor/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("learner-ai-policy")).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/help type/i)).toBeInTheDocument();
    const query = screen.getByLabelText(/your question/i);
    expect(query).toHaveAttribute("aria-describedby", "learner-ai-hint");
    expect(screen.getByTestId("learner-ai-ask")).toBeDisabled();
  });

  it("learner disabled policy uses status role", async () => {
    const disabledPolicy: EffectiveAiPolicy = {
      ...learnerPolicy,
      policy: "AI_DISABLED",
      allowed_learner_capabilities: [],
    };
    const ai = mockAi({
      getPolicy: vi.fn(async () => disabledPolicy),
    });
    render(<LearnerAiPanel ai={ai} sectionId="sec_alpha_dc_w01" />);
    await waitFor(() => {
      expect(screen.getByTestId("learner-ai-disabled")).toHaveAttribute("role", "status");
    });
  });

  it("instructor panel keeps apply-grade control reachable and status roles", async () => {
    const ai = mockAi();
    render(<InstructorAiPanel ai={ai} sectionId="sec_alpha_dc_w01" />);

    const region = screen.getByTestId("instructor-ai-panel");
    expect(region).toHaveAttribute("aria-labelledby", "instructor-ai-heading");
    expect(screen.getByRole("heading", { name: /instructor suggestions/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/suggestion type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/context \/ request/i)).toBeInTheDocument();
    expect(screen.getByTestId("instructor-ai-apply-blocked")).toBeInTheDocument();
  });
});
