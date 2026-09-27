/** Conservative Markdown → safe HTML. No raw HTML/script execution. */

const DANGEROUS_PROTO = /^(javascript|data|vbscript|file):/i;

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeHref(href: string): string | null {
  const trimmed = href.trim();
  if (!trimmed || DANGEROUS_PROTO.test(trimmed)) return null;
  if (trimmed.startsWith("//")) return null;
  return trimmed;
}

function inline(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label: string, href: string) => {
    const safe = safeHref(href);
    if (!safe) return label;
    return `<a href="${escapeHtml(safe)}" rel="noopener noreferrer">${label}</a>`;
  });
  return out;
}

function isTableRow(line: string): boolean {
  return /^\s*\|.+\|\s*$/.test(line);
}

function isTableDivider(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

export function renderSafeMarkdown(markdown: string): string {
  const src = (markdown || "").replace(/\r\n/g, "\n");
  const lines = src.split("\n");
  const html: string[] = [];
  let i = 0;
  let inCode = false;
  let codeLang = "";
  let code: string[] = [];
  let listType: "ul" | "ol" | null = null;

  const closeList = () => {
    if (listType) {
      html.push(listType === "ul" ? "</ul>" : "</ol>");
      listType = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code class="language-${escapeHtml(codeLang)}">${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
        inCode = false;
        codeLang = "";
      } else {
        closeList();
        inCode = true;
        codeLang = line.slice(3).trim().replace(/[^a-zA-Z0-9_-]/g, "") || "text";
      }
      i += 1;
      continue;
    }
    if (inCode) {
      code.push(line);
      i += 1;
      continue;
    }

    if (!line.trim()) {
      closeList();
      i += 1;
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    const callout = /^>\s*\[!(NOTE|TIP|WARNING|IMPORTANT|CAUTION)\]\s*(.*)$/i.exec(line);
    if (callout) {
      closeList();
      html.push(
        `<aside class="md-callout md-callout-${callout[1].toLowerCase()}" role="note"><strong>${escapeHtml(callout[1])}</strong> ${inline(callout[2])}</aside>`,
      );
      i += 1;
      continue;
    }

    if (line.startsWith("> ")) {
      closeList();
      html.push(`<blockquote>${inline(line.slice(2))}</blockquote>`);
      i += 1;
      continue;
    }

    const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(line.trim());
    if (image) {
      closeList();
      const srcSafe = safeHref(image[2]);
      const alt = escapeHtml(image[1] || "");
      if (srcSafe) {
        html.push(`<img src="${escapeHtml(srcSafe)}" alt="${alt}" />`);
      } else {
        html.push(`<p>${alt || "Image omitted (unsafe source)"}</p>`);
      }
      i += 1;
      continue;
    }

    if (isTableRow(line) && i + 1 < lines.length && isTableDivider(lines[i + 1])) {
      closeList();
      const header = line.split("|").slice(1, -1).map((c) => inline(c.trim()));
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i]) && !isTableDivider(lines[i])) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => inline(c.trim())));
        i += 1;
      }
      html.push("<table><thead><tr>");
      header.forEach((c) => html.push(`<th scope="col">${c}</th>`));
      html.push("</tr></thead><tbody>");
      for (const row of rows) {
        html.push("<tr>");
        row.forEach((c) => html.push(`<td>${c}</td>`));
        html.push("</tr>");
      }
      html.push("</tbody></table>");
      continue;
    }

    const ul = /^\s*[-*]\s+(.*)$/.exec(line);
    const ol = /^\s*\d+\.\s+(.*)$/.exec(line);
    if (ul || ol) {
      const nextType = ul ? "ul" : "ol";
      if (listType && listType !== nextType) closeList();
      if (!listType) {
        html.push(nextType === "ul" ? "<ul>" : "<ol>");
        listType = nextType;
      }
      html.push(`<li>${inline((ul || ol)?.[1] || "")}</li>`);
      i += 1;
      continue;
    }

    closeList();
    html.push(`<p>${inline(line)}</p>`);
    i += 1;
  }
  if (inCode) {
    html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  }
  closeList();
  return html.join("\n");
}

export function containsUnsafeHtml(markdown: string): boolean {
  return /<(script|iframe|object|embed|svg)\b/i.test(markdown);
}
