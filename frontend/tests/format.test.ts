import { describe, expect, it } from "vitest";
import {
  fileLanguageOf,
  formatNumber,
  formatRelative,
  languageColor,
  parseErrorParams,
  statusLabel,
  themeTypeLabel,
} from "../lib/format";

describe("formatNumber", () => {
  it("formats small numbers as-is", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber(999)).toBe("999");
  });

  it("abbreviates thousands and millions", () => {
    expect(formatNumber(1500)).toBe("1.5k");
    expect(formatNumber(2_500_000)).toBe("2.5M");
  });

  it("handles null and undefined", () => {
    expect(formatNumber(null)).toBe("0");
    expect(formatNumber(undefined)).toBe("0");
  });
});

describe("formatRelative", () => {
  it("returns a fallback for missing values", () => {
    expect(formatRelative(null)).toBe("—");
    expect(formatRelative("not-a-date")).toBe("—");
  });

  it("renders recent timestamps as minutes ago", () => {
    const recent = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelative(recent)).toBe("5m ago");
  });
});

describe("labels", () => {
  it("labels detection status", () => {
    expect(statusLabel("detected")).toBe("Detected");
    expect(statusLabel("not_detected")).toBe("Not Detected");
    expect(statusLabel("unknown")).toBe("Unknown");
  });

  it("labels theme types", () => {
    expect(themeTypeLabel("child")).toBe("Child Theme");
    expect(themeTypeLabel("custom")).toBe("Custom Theme");
    expect(themeTypeLabel("known")).toBe("Installed Theme");
    expect(themeTypeLabel("mystery")).toBe("Unknown");
  });
});

describe("languageColor", () => {
  it("returns known colors and a fallback", () => {
    expect(languageColor("PHP")).toBe("#8892bf");
    expect(languageColor("css")).toBe("#519aba");
    expect(languageColor("cobol")).toBe("#8b949e");
    expect(languageColor(null)).toBe("#8b949e");
  });
});

describe("parseErrorParams", () => {
  it("maps known OAuth error codes", () => {
    expect(parseErrorParams(new URLSearchParams("error=github_denied"))).toMatch(/declined/);
    expect(parseErrorParams(new URLSearchParams("error=invalid_state"))).toMatch(/verified/);
  });

  it("returns null without an error and a generic message otherwise", () => {
    expect(parseErrorParams(new URLSearchParams(""))).toBeNull();
    expect(parseErrorParams(new URLSearchParams("error=mystery"))).toMatch(/failed/i);
  });
});

describe("fileLanguageOf", () => {
  it("prefers the provided language", () => {
    expect(fileLanguageOf("a.php", "php")).toBe("php");
  });

  it("falls back to extension mapping", () => {
    expect(fileLanguageOf("style.css")).toBe("css");
    expect(fileLanguageOf("main.tsx")).toBe("tsx");
    expect(fileLanguageOf("README.md")).toBe("markdown");
    expect(fileLanguageOf("archive.zip")).toBeNull();
  });

  it("treats generic text/binary as a pass-through to extensions", () => {
    expect(fileLanguageOf("template.html", "text")).toBe("markup");
    expect(fileLanguageOf("script.js", "binary")).toBe("javascript");
  });
});
