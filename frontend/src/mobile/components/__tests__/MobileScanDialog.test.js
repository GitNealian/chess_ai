import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import MobileBoardEditor from "../MobileBoardEditor.vue";
import MobileScanDialog from "../MobileScanDialog.vue";

vi.mock("../../../api", () => ({
  api: { recognize: vi.fn() },
}));

import { api } from "../../../api";

const boardResult = {
  pieces: [
    { x: 0, y: 9, side: "black", kind: "R" },
    { x: 4, y: 0, side: "red", kind: "K" },
  ],
  layout: ["r" + ".".repeat(8), ...Array(9).fill(".".repeat(9))],
  warnings: [],
  stats: { pose_ms: 5, classify_ms: 90, keypoint_scores: [0.9, 0.9, 0.9, 0.9] },
};

function selectFile(wrapper, selector = "[data-test='scan-album'] input") {
  const input = wrapper.find(selector);
  Object.defineProperty(input.element, "files", {
    value: [new File(["x"], "board.jpg", { type: "image/jpeg" })],
    configurable: true,
  });
  return input.trigger("change");
}

describe("MobileScanDialog", () => {
  beforeEach(() => {
    api.recognize.mockReset();
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 800, height: 600, close: vi.fn() }))
    );
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: vi.fn(),
    });
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) =>
      callback(new Blob(["x"], { type: "image/jpeg" }))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("初始显示拍照与相册入口", () => {
    const wrapper = mount(MobileScanDialog);
    expect(wrapper.find("[data-test='scan-card']").exists()).toBe(true);
    expect(wrapper.find("[data-test='scan-camera']").text()).toContain("拍照");
    expect(wrapper.find("[data-test='scan-album']").text()).toContain("相册");
    expect(
      wrapper.find("[data-test='scan-camera'] input").attributes("capture")
    ).toBe("environment");
    expect(
      wrapper.find("[data-test='scan-album'] input").attributes("capture")
    ).toBeUndefined();
  });

  it("识别成功后进入识别结果编辑", async () => {
    api.recognize.mockResolvedValue(boardResult);
    const wrapper = mount(MobileScanDialog);
    await selectFile(wrapper);
    await flushPromises();

    expect(api.recognize).toHaveBeenCalledTimes(1);
    const form = api.recognize.mock.calls[0][0];
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("image")).toBeInstanceOf(Blob);

    const editor = wrapper.findComponent(MobileBoardEditor);
    expect(editor.exists()).toBe(true);
    expect(editor.props("title")).toBe("识别结果");
    expect(editor.props("pieces")).toHaveLength(2);
    expect(editor.props("pieces")[0]).toMatchObject({
      x: 0,
      y: 9,
      side: "black",
      kind: "R",
      label: "车",
    });
  });

  it("识别警告显示在提示中", async () => {
    api.recognize.mockResolvedValue({
      ...boardResult,
      warnings: ["2 个格子识别置信度较低，请核对"],
    });
    const wrapper = mount(MobileScanDialog);
    await selectFile(wrapper);
    await flushPromises();
    expect(wrapper.find("[data-test='editor-notice']").text()).toContain(
      "2 个格子识别置信度较低，请核对"
    );
  });

  it("识别失败显示错误并可重试", async () => {
    api.recognize.mockRejectedValue({
      response: { data: { error: "未检测到棋盘，请让棋盘完整入镜后重试" } },
    });
    const wrapper = mount(MobileScanDialog);
    await selectFile(wrapper);
    await flushPromises();
    expect(wrapper.find("[data-test='scan-error']").text()).toBe(
      "未检测到棋盘，请让棋盘完整入镜后重试"
    );
    expect(wrapper.findComponent(MobileBoardEditor).exists()).toBe(false);
  });

  it("识别中显示进度", async () => {
    let resolveRecognize;
    api.recognize.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRecognize = resolve;
        })
    );
    const wrapper = mount(MobileScanDialog);
    await selectFile(wrapper);
    await flushPromises();
    expect(wrapper.find("[data-test='scan-loading']").exists()).toBe(true);
    expect(wrapper.find("[data-test='scan-camera']").exists()).toBe(false);

    resolveRecognize(boardResult);
    await flushPromises();
    expect(wrapper.findComponent(MobileBoardEditor).exists()).toBe(true);
  });

  it("关闭发出 cancel", async () => {
    const wrapper = mount(MobileScanDialog);
    await wrapper.find("[data-test='scan-cancel']").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });

  it("识别结果应用后透传 apply", async () => {
    api.recognize.mockResolvedValue(boardResult);
    const wrapper = mount(MobileScanDialog);
    await selectFile(wrapper);
    await flushPromises();
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("apply", boardResult.pieces, "fen");
    expect(wrapper.emitted("apply")[0]).toEqual([boardResult.pieces, "fen"]);
  });

  it("识别结果取消后透传 cancel", async () => {
    api.recognize.mockResolvedValue(boardResult);
    const wrapper = mount(MobileScanDialog);
    await selectFile(wrapper);
    await flushPromises();
    await wrapper.findComponent(MobileBoardEditor).vm.$emit("cancel");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
