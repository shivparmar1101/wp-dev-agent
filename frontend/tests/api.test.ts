import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, request } from "../lib/api";

const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn() as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("performs GET requests with credentials and query params", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(jsonResponse({ repositories: [], page: 1 }));

    const result = await api.repositories({ page: 2, q: "wp" });

    expect(result.repositories).toEqual([]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/repositories");
    expect(String(url)).toContain("page=2");
    expect(String(url)).toContain("q=wp");
    expect(init.credentials).toBe("include");
    expect(init.method).toBeUndefined();
  });

  it("sends JSON bodies for POST requests", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(jsonResponse({ conversation_id: "c1" }));

    await api.chat("acme", "site", "hello", [{ role: "user", content: "hi" }]);

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toMatchObject({ message: "hello" });
  });

  it("throws ApiError with the backend detail message", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ detail: "Not authenticated", kind: "unauthenticated" }, 401),
      ),
    );

    await expect(api.me()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Not authenticated",
    });
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
  });

  it("normalizes list-valued error details", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: ["field required", "invalid value"] }, 422)),
    );

    await expect(request("/api/whatever")).rejects.toThrow("field required invalid value");
  });

  it("wraps network failures in ApiError", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(api.health()).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
    });
  });

  it("starts scans with a POST body", async () => {
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(jsonResponse({ scan_id: "s1", status: "pending" }));

    await api.startScan("acme", "site", "dev");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ branch: "dev" });
  });
});
