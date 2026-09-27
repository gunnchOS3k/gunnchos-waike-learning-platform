import { renderSafeMarkdown } from "../../lib/product/safeMarkdown";

export function SafeMarkdown({ markdown, testId = "safe-markdown" }: { markdown: string; testId?: string }) {
  return (
    <div
      className="safe-markdown"
      data-testid={testId}
      dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(markdown) }}
    />
  );
}
