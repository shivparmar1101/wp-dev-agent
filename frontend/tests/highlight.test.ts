import { describe, expect, it } from "vitest";
import { escapeHtml, highlight } from "../lib/highlight";

describe("escapeHtml", () => {
  it("escapes markup characters", () => {
    expect(escapeHtml('<a href="x">&</a>')).toBe(
      "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;",
    );
  });
});

describe("highlight", () => {
  it("highlights PHP with token spans", () => {
    const { html, language } = highlight("<?php echo 'hi';", "php");
    expect(language).toBe("php");
    expect(html).toContain("<span");
    expect(html).toContain("echo");
  });

  it("maps aliases and extensions", () => {
    expect(highlight("body {}", "css").language).toBe("css");
    expect(highlight("const a = 1;", "ts").language).toBe("typescript");
    expect(highlight("<div></div>", "html").language).toBe("markup");
  });

  it("falls back to escaped plain text for unknown languages", () => {
    const { html, language } = highlight("<script>alert(1)</script>", "brainfuck");
    expect(language).toBe("text");
    expect(html).toBe("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  it("falls back when no language is provided", () => {
    const { html, language } = highlight("<b>x</b>", null);
    expect(language).toBe("text");
    expect(html).toBe("&lt;b&gt;x&lt;/b&gt;");
  });
});
