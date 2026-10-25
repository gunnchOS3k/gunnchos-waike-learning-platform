import { describe, expect, it } from "vitest";
import { GENERAL_IT_ASSIGNMENT_ID, weeklyReaderForCourse } from "./secondTrack";

describe("second canonical track reader", () => {
  it("opens General IT from the on-disk course title and keeps Digital Confidence on its own reader", () => {
    const general = weeklyReaderForCourse("General IT — Operator to Support Specialist");
    expect(general).toEqual({
      mode: "git-course",
      trackId: "IT_SUPPORT_HARDWARE",
      label: "Open General IT weekly reader",
      assignmentId: GENERAL_IT_ASSIGNMENT_ID,
    });
    expect(weeklyReaderForCourse("Digital Confidence — Alpha")?.mode).toBe("dc-course");
    expect(weeklyReaderForCourse("Software Builder")).toBeNull();
  });
});
