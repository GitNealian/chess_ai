import { beforeEach, describe, expect, it } from "vitest";
import { loadSettings, saveSettings } from "../settings";

describe("移动端设置存储", () => {
  beforeEach(() => localStorage.clear());

  it("默认全部关闭", () => {
    expect(loadSettings()).toEqual({ score: false, intent: false });
  });

  it("保存后可读回", () => {
    saveSettings({ score: true, intent: false });
    expect(loadSettings()).toEqual({ score: true, intent: false });
  });

  it("非法 JSON 回退默认", () => {
    localStorage.setItem("chess:mobile-settings", "{bad");
    expect(loadSettings()).toEqual({ score: false, intent: false });
  });

  it("字段非布尔时按关闭处理", () => {
    localStorage.setItem("chess:mobile-settings", JSON.stringify({ score: 1 }));
    expect(loadSettings()).toEqual({ score: false, intent: false });
  });
});
