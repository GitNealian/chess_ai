import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useLibraryStore } from "../library";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: {
    listGames: vi.fn(),
    stats: vi.fn(),
    deleteGame: vi.fn(),
  },
}));

describe("library store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  it("fetchGames 竞态保护：慢请求后返回不覆盖快请求结果", async () => {
    let resolveSlow;
    const slow = new Promise((resolve) => {
      resolveSlow = resolve;
    });
    const fast = Promise.resolve({ items: [{ id: 2, name: "B" }] });

    api.listGames
      .mockImplementationOnce(() => slow)
      .mockImplementationOnce(() => fast);

    const store = useLibraryStore();

    const pendingSlow = store.fetchGames({ keyword: "A" });
    const pendingFast = store.fetchGames({ keyword: "B" });

    await pendingFast;
    expect(store.games).toEqual([{ id: 2, name: "B" }]);

    resolveSlow({ items: [{ id: 1, name: "A" }] });
    await pendingSlow;

    expect(store.games).toEqual([{ id: 2, name: "B" }]);
    expect(store.loading).toBe(false);
  });
});
