export const GENERAL_IT_SECTION_ID = "sec_alpha_git_w01";
export const GENERAL_IT_ASSIGNMENT_ID = "general_it_w01";
export const GENERAL_IT_MODULE_ID = "GENERAL_IT";

export type WeeklyReader = {
  mode: "dc-course" | "git-course";
  trackId: string;
  label: string;
  assignmentId: string;
};

export function weeklyReaderForCourse(title: string): WeeklyReader | null {
  const normalized = title.toLowerCase();
  if (normalized.includes("digital confidence")) {
    return {
      mode: "dc-course",
      trackId: "DIGITAL_CONFIDENCE",
      label: "Open Digital Confidence weekly reader",
      assignmentId: "digital_confidence_w01",
    };
  }
  if (normalized.includes("general it")) {
    return {
      mode: "git-course",
      trackId: "IT_SUPPORT_HARDWARE",
      label: "Open General IT weekly reader",
      assignmentId: GENERAL_IT_ASSIGNMENT_ID,
    };
  }
  return null;
}
