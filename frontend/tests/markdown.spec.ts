import { describe, expect, it } from "vitest";
import { renderMarkdown } from "@/utils/markdown";

describe("markdown rendering", () => {
  it("renders headings, lists and GFM tables", () => {
    const html = renderMarkdown("# Report\n\n- one\n- two\n\n| a | b |\n| - | - |\n| 1 | 2 |");

    expect(html).toContain("<h1>Report</h1>");
    expect(html).toContain("<li>one</li>");
    expect(html).toContain("<table>");
  });

  it("strips scripts, event handlers and javascript: links", () => {
    const html = renderMarkdown(
      [
        "# Safe",
        "<script>window.__xss = true</script>",
        '<img src="x" onerror="window.__xss = true">',
        "[click](javascript:alert(1))",
        '<iframe src="https://evil.example"></iframe>',
      ].join("\n\n"),
    );

    expect(html).toContain("<h1>Safe</h1>");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("onerror");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("<iframe");
  });

  it("returns an empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
