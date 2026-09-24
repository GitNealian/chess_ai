import { beforeEach, describe, expect, it, vi } from "vitest";
import { analyzeStream } from "../index";

function mockFetchStatus(status) {
  global.fetch = vi.fn(async () => ({
    ok: status === 200,
    status,
    body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
  }));
}

describe("401 统一处理", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("analyzeStream 收到 401 派发 app-unauthorized", async () => {
    mockFetchStatus(401);
    const onUnauthorized = vi.fn();
    window.addEventListener("app-unauthorized", onUnauthorized);
    await analyzeStream({ fen: "x" }, { onError: () => {} });
    expect(onUnauthorized).toHaveBeenCalled();
    window.removeEventListener("app-unauthorized", onUnauthorized);
  });
});
