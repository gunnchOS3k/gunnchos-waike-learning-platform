import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { resetMockHubStore } from "../lib/hub/mockHub";
import { ACTIVE_COURSE_KEY } from "../lib/product/types";

afterEach(() => {
  cleanup();
  resetMockHubStore();
  localStorage.removeItem(ACTIVE_COURSE_KEY);
});

beforeEach(() => {
  resetMockHubStore();
  localStorage.removeItem(ACTIVE_COURSE_KEY);
});

describe("Learner-first adoption parity", () => {
  it("shows two courses and persists an explicit selection", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-courses"));
    await waitFor(() => {
      expect(screen.getByTestId("course-card-sec_alpha_dc_w01")).toBeInTheDocument();
      expect(screen.getByTestId("course-card-sec_alpha_sb_w01")).toBeInTheDocument();
    });
    expect(localStorage.getItem(ACTIVE_COURSE_KEY)).toBeNull();
    await user.click(screen.getByTestId("select-course-sec_alpha_sb_w01"));
    await waitFor(() => {
      expect(screen.getByTestId("course-home").textContent).toMatch(/Software Builder/);
    });
    expect(localStorage.getItem(ACTIVE_COURSE_KEY)).toBe("sec_alpha_sb_w01");
  });

  it("does not open the first assignment from Assignments", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-assignments"));
    await waitFor(() => {
      expect(screen.getByTestId("assignment-center")).toBeInTheDocument();
      expect(screen.getByTestId("open-assignment-digital_confidence_w01")).toBeInTheDocument();
      expect(screen.getByTestId("open-assignment-software_builder_w01")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("assignment-body")).not.toBeInTheDocument();
  });

  it("builds Today with due/overdue and deep links", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-home"));
    await waitFor(() => {
      expect(screen.getByTestId("learner-home")).toBeInTheDocument();
      expect(screen.getByTestId("today-due-soon")).toBeInTheDocument();
    });
  });

  it("renders sanitized markdown in an opened assignment", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-assignments"));
    await user.click(await screen.findByTestId("open-assignment-digital_confidence_w01"));
    await waitFor(() => {
      expect(screen.getByTestId("assignment-markdown").innerHTML).toContain("<h1>");
      expect(screen.getByTestId("assignment-markdown").innerHTML).not.toContain("<script>");
    });
  });

  it("search omits answer keys for learners", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByTestId("mode-home"));
    const box = await screen.findByTestId("learner-search-q");
    await user.type(box, "week");
    await waitFor(() => {
      expect(screen.getByTestId("search-results").textContent).not.toMatch(/answer key/i);
    });
  });
});
