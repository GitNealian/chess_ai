import { describe, expect, it, vi, beforeEach } from "vitest";
import { intentStream } from "../index";

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

function mockFetchChunks(chunks) {
  let i = 0;
  const body = {
    getReader: () => ({
      read: async () =>
        i < chunks.length ? { done: false, value: chunks[i++] } : { done: true, value: undefined },
    }),
  };
  global.fetch = vi.fn(async () => ({ ok: true, status: 200, body }));
}

describe("intentStream", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("按事件类型分发 rank/threat/bait/done（忽略 ping）", async () => {
    mockFetchStream([
      JSON.stringify({ type: "ping", elapsed_ms: 5 }),
      JSON.stringify({ type: "rank", best: { chinese: "士四进五" }, list: [] }),
      JSON.stringify({ type: "threat", line: [], outcome: null, hint: "你正被将军，必须应将" }),
      JSON.stringify({
        type: "bait",
        bait: { chinese: "车二进五", reason: "贪吃" },
        line: [],
        outcome: {},
      }),
      JSON.stringify({ type: "done", time_ms: 1234 }),
    ]);
    const ranks = [];
    const threats = [];
    const baits = [];
    const dones = [];
    const errors = [];
    await intentStream(
      {},
      {
        onRank: (m) => ranks.push(m),
        onThreat: (m) => threats.push(m),
        onBait: (m) => baits.push(m),
        onDone: (m) => dones.push(m),
        onError: (e) => errors.push(e),
      }
    );
    expect(ranks).toHaveLength(1);
    expect(ranks[0].best.chinese).toBe("士四进五");
    expect(threats).toHaveLength(1);
    expect(threats[0].hint).toBe("你正被将军，必须应将");
    expect(baits).toHaveLength(1);
    expect(baits[0].bait.chinese).toBe("车二进五");
    expect(dones).toHaveLength(1);
    expect(dones[0].time_ms).toBe(1234);
    expect(errors).toEqual([]);
  });

  it("多个 bait 事件逐条分发", async () => {
    mockFetchStream([
      JSON.stringify({
        type: "bait",
        bait: { chinese: "车二进五", reason: "贪吃" },
        line: [],
        outcome: {},
      }),
      JSON.stringify({
        type: "bait",
        bait: { chinese: "炮五进四", reason: "贪攻" },
        line: [],
        outcome: {},
      }),
      JSON.stringify({ type: "done", time_ms: 10 }),
    ]);
    const baits = [];
    await intentStream({}, { onBait: (m) => baits.push(m) });
    expect(baits.map((b) => b.bait.chinese)).toEqual(["车二进五", "炮五进四"]);
  });

  it("HTTP 错误响应触发 onError", async () => {
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ error: "boom" }),
    }));
    const errors = [];
    await intentStream({}, { onError: (e) => errors.push(e.message) });
    expect(errors).toEqual(["boom"]);
  });

  it("流内 error 事件触发 onError", async () => {
    mockFetchStream([JSON.stringify({ type: "error", message: "参数错误" })]);
    const errors = [];
    await intentStream({}, { onError: (e) => errors.push(e.message) });
    expect(errors).toEqual(["参数错误"]);
  });

  it("abort 不触发 onError", async () => {
    const abortError = new Error("aborted");
    abortError.name = "AbortError";
    global.fetch = vi.fn(async () => {
      throw abortError;
    });
    const errors = [];
    await intentStream({}, { onError: (e) => errors.push(e) });
    expect(errors).toEqual([]);
  });

  it("跨 chunk 的半个 JSON 行能正确拼接", async () => {
    const encoder = new TextEncoder();
    mockFetchChunks([
      encoder.encode('{"type":"ran'),
      encoder.encode('k","best":{"chinese":"士四进五"}}\n'),
    ]);
    const ranks = [];
    await intentStream({}, { onRank: (m) => ranks.push(m) });
    expect(ranks[0].best.chinese).toBe("士四进五");
  });

  it("最后一个 chunk 的半个中文字符由下一 chunk 补全", async () => {
    const encoder = new TextEncoder();
    const full = encoder.encode('{"type":"threat","hint":"你正被将军"}\n');
    mockFetchChunks([full.slice(0, full.length - 4), full.slice(full.length - 4)]);
    const threats = [];
    await intentStream({}, { onThreat: (m) => threats.push(m) });
    expect(threats[0].hint).toBe("你正被将军");
  });

  it("无法解析的行被跳过", async () => {
    mockFetchStream([
      "not json",
      JSON.stringify({ type: "rank", best: { chinese: "马八进七" }, list: [] }),
    ]);
    const ranks = [];
    const errors = [];
    await intentStream({}, { onRank: (m) => ranks.push(m), onError: (e) => errors.push(e) });
    expect(ranks).toHaveLength(1);
    expect(ranks[0].best.chinese).toBe("马八进七");
    expect(errors).toEqual([]);
  });
});
