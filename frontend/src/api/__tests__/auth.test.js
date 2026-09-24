import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, analyzeStream, intentStream } from "../index";

const mocks = vi.hoisted(() => ({ http: { instance: null } }));

vi.mock("axios", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    default: new Proxy(actual.default, {
      get(target, prop, receiver) {
        if (prop === "create") {
          return (config) => {
            const instance = target.create(config);
            mocks.http.instance = instance;
            return instance;
          };
        }
        return Reflect.get(target, prop, receiver);
      },
    }),
  };
});

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

  it("analyzeStream 收到 401 不派发 app-toast", async () => {
    mockFetchStatus(401);
    const onToast = vi.fn();
    window.addEventListener("app-toast", onToast);
    await analyzeStream({ fen: "x" }, { onError: () => {} });
    expect(onToast).not.toHaveBeenCalled();
    window.removeEventListener("app-toast", onToast);
  });

  it("intentStream 收到 401 派发 app-unauthorized", async () => {
    mockFetchStatus(401);
    const onUnauthorized = vi.fn();
    window.addEventListener("app-unauthorized", onUnauthorized);
    await intentStream({}, { onError: () => {} });
    expect(onUnauthorized).toHaveBeenCalled();
    window.removeEventListener("app-unauthorized", onUnauthorized);
  });

  it("login 失败（401）不派发 app-toast 与 app-unauthorized", async () => {
    const instance = mocks.http.instance;
    instance.defaults.adapter = (config) => {
      const error = new Error("Request failed with status code 401");
      error.config = config;
      error.response = {
        status: 401,
        data: { error: "密码错误" },
        headers: {},
        config,
        statusText: "Unauthorized",
      };
      error.isAxiosError = true;
      return Promise.reject(error);
    };
    const onToast = vi.fn();
    const onUnauthorized = vi.fn();
    window.addEventListener("app-toast", onToast);
    window.addEventListener("app-unauthorized", onUnauthorized);
    await expect(api.login("bad")).rejects.toThrow("401");
    expect(onToast).not.toHaveBeenCalled();
    expect(onUnauthorized).not.toHaveBeenCalled();
    window.removeEventListener("app-toast", onToast);
    window.removeEventListener("app-unauthorized", onUnauthorized);
  });
});
