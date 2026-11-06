import DOMPurify from "dompurify";
import { marked } from "marked";

const MARKDOWN_OPTIONS = {
  async: false,
  gfm: true,
  breaks: false,
} as const;

const PURIFY_OPTIONS = {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form"],
  FORBID_ATTR: ["style"],
};

/**
 * Render untrusted Markdown for `v-html`. Raw HTML is parsed by `marked` and
 * then sanitized by DOMPurify, so report bodies can never inject scripts or
 * event handlers into the page.
 */
export function renderMarkdown(source: string): string {
  if (!source) return "";
  const html = marked.parse(source, MARKDOWN_OPTIONS) as string;
  return DOMPurify.sanitize(html, PURIFY_OPTIONS);
}
