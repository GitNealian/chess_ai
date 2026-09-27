import { beforeEach, describe, expect, it } from "vitest";
import { loadSettings, saveSettings } from "../settings";

describe("移动端设置存储", () => {
  beforeEach(() => localStorage.clear());

  it("默认全部关闭且难度普通", () => {
    expect(loadSettings()).toEqual({ score: false, intent: false, level: "normal" });
  });

  it("保存后可读回", () => {
    saveSettings({ score: true, intent: false, level: "hard" });
    expect(loadSettings()).toEqual({ score: true, intent: false, level: "hard" });
  });

  it("非法 JSON 回退默认", () => {
    localStorage.setItem("chess:mobile-settings", "{bad");
    expect(loadSettings()).toEqual({ score: false, intent: false, level: "normal" });
  });

  it("字段非法时回退默认", () => {
    localStorage.setItem(
      "chess:mobile-settings",
      JSON.stringify({ score: 1, level: "insane" })
    );
    expect(loadSettings()).toEqual({ score: false, intent: false, level: "normal" });
  });
});
