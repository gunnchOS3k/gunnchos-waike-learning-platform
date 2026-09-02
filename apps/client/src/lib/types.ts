export type TrustStatus = {
  pack_id: string;
  module_id: string;
  title: string;
  verification_status: string;
  content_root_sha256: string;
  source_commit: string;
  trusted: boolean;
  reason?: string | null;
};

export type LessonInfo = {
  lesson_id: string;
  title: string;
  path: string;
  week?: number | null;
  order?: number | null;
};

export type LessonContent = {
  lesson_id: string;
  title: string;
  path: string;
  markdown: string;
  resume_scroll_offset: number;
};

export type ModuleView = {
  pack_id: string;
  module_id: string;
  title: string;
  lessons: LessonInfo[];
  trust: TrustStatus;
};
