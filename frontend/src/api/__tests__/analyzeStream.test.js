import { describe, expect, it, vi, beforeEach } from "vitest";
import { analyzeStream } from "../index";

function mockFetchStream(lines, { ok = true, status = 200 } = {}) {
  const encoder = new TextEncoder();
  const chunks = lines.map((l) => encoder.encode(l + "\n"));
  let i = 0;
  const body = {
    getReader: () => ({
      read: async () =>
        i < chunks.length ? { done: false, value: chunks[i++] } : { done: true, value: undefined },
    }),
  };
  global.fetch = vi.fn(async () => ({ ok, status, body }));
}

function mockFetchChunks(chunks, { ok = true, status = 200 } = {}) {
  let i = 0;
  const body = {
    getReader: () => ({
      read: async () =>
        i < chunks.length ? { done: false, value: chunks[i++] } : { done: true, value: undefined },
    }),
  };
  global.fetch = vi.fn(async () => ({ ok, status, body }));
}

describe("analyzeStream", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("逐行解析并回调（跳过 ping）", async () => {
    mockFetchStream([
      JSON.stringify({ type: "ping", elapsed_ms: 100 }),
      JSON.stringify({ type: "result", depth: 6, score_red: 12 }),
      JSON.stringify({ type: "result", depth: 7, score_red: 20 }),
      JSON.stringify({ type: "done", reason: "time" }),
    ]);
    const results = [];
    const done = [];
    await analyzeStream(
      { fen: "x" },
      { onResult: (r) => results.push(r), onDone: (d) => done.push(d) }
    );
    expect(results.map((r) => r.depth)).toEqual([6, 7]);
    expect(done[0].reason).toBe("time");
  });

  it("错误行触发 onError", async () => {
    mockFetchStream([JSON.stringify({ type: "error", message: "bad" })]);
    const errors = [];
    await analyzeStream({ fen: "x" }, { onError: (e) => errors.push(e.message) });
    expect(errors).toEqual(["bad"]);
  });

  it("abort 不触发 onError", async () => {
    const abortError = new Error("aborted");
    abortError.name = "AbortError";
    global.fetch = vi.fn(async () => {
      throw abortError;
    });
    const errors = [];
    await analyzeStream({ fen: "x" }, { onError: (e) => errors.push(e) });
    expect(errors).toEqual([]);
  });

  it("HTTP 错误触发 onError", async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ error: "boom" }),
    }));
    const errors = [];
    await analyzeStream({ fen: "x" }, { onError: (e) => errors.push(e.message) });
    expect(errors).toEqual(["boom"]);
  });

  it("跨 chunk 的半个 JSON 行能正确拼接", async () => {
    const encoder = new TextEncoder();
    mockFetchChunks([encoder.encode('{"type":"res'), encoder.encode('ult","depth":4}\n')]);
    const results = [];
    await analyzeStream({ fen: "x" }, { onResult: (r) => results.push(r) });
    expect(results.map((r) => r.depth)).toEqual([4]);
  });

  it("无法解析的行被跳过", async () => {
    mockFetchStream(["not json", JSON.stringify({ type: "result", depth: 3 })]);
    const results = [];
    await analyzeStream({ fen: "x" }, { onResult: (r) => results.push(r) });
    expect(results.map((r) => r.depth)).toEqual([3]);
  });
});
