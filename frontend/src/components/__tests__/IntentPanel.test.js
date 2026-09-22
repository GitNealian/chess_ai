import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import IntentPanel from "../IntentPanel.vue";

const baseIntent = {
  status: "done",
  rank: { best: { chinese: "士四进五", iccs: "a1b2" }, list: [] },
  threat: { line: [], outcome: null, hint: null },
  baits: [],
  error: "",
};

describe("IntentPanel", () => {
  it("running 显示推演中", () => {
    const wrapper = mount(IntentPanel, { props: { intent: { status: "running" } } });
    expect(wrapper.find('[data-test="intent-status"]').text()).toBe("推演中…");
  });

  it("error 显示错误行", () => {
    const wrapper = mount(IntentPanel, {
      props: { intent: { status: "error", error: "参数错误" } },
    });
    expect(wrapper.find('[data-test="intent-error"]').text()).toContain("参数错误");
  });

  it("done + hint 优先显示提示，不显示若不理会", () => {
    const wrapper = mount(IntentPanel, {
      props: {
        intent: {
          ...baseIntent,
          threat: { line: [], outcome: null, hint: "你正被将军，必须应将" },
        },
      },
    });
    expect(wrapper.find('[data-test="intent-hint"]').text()).toBe("你正被将军，必须应将");
    expect(wrapper.find('[data-test="intent-threat"]').exists()).toBe(false);
  });

  it("done + threat line 显示若不理会与绝杀标注", () => {
    const wrapper = mount(IntentPanel, {
      props: {
        intent: {
          ...baseIntent,
          threat: {
            line: [
              { chinese: "炮8平3", iccs: "h3c3" },
              { chinese: "帅五进一", iccs: "e1e2" },
            ],
            outcome: { mate: 3, loss_piece: null, score_red: null },
            hint: null,
          },
        },
      },
    });
    const text = wrapper.find('[data-test="intent-threat"]').text();
    expect(text).toContain("若不理会：炮8平3 → 帅五进一");
    expect(text).toContain("绝杀（3 步内）");
  });

  it("loss_piece 标注白丢车", () => {
    const wrapper = mount(IntentPanel, {
      props: {
        intent: {
          ...baseIntent,
          threat: { line: [{ chinese: "车9进9" }], outcome: { loss_piece: "车" }, hint: null },
        },
      },
    });
    expect(wrapper.find('[data-test="intent-threat"]').text()).toContain("白丢车");
  });

  it("score_red 正数红优/负数黑优/接近 0 均势/空则无标注", () => {
    const make = (score_red) =>
      mount(IntentPanel, {
        props: {
          intent: {
            ...baseIntent,
            threat: { line: [{ chinese: "车9进9" }], outcome: { score_red }, hint: null },
          },
        },
      });
    expect(make(150).find('[data-test="intent-threat"]').text()).toContain("红优 +150");
    expect(make(-200).find('[data-test="intent-threat"]').text()).toContain("黑优 200");
    expect(make(0.5).find('[data-test="intent-threat"]').text()).toContain("均势");
    expect(make(null).find('[data-test="intent-threat"]').text()).not.toContain("均势");
  });

  it("baits 逐条渲染贪吃提醒与结局标注", () => {
    const wrapper = mount(IntentPanel, {
      props: {
        intent: {
          ...baseIntent,
          baits: [
            {
              bait: { chinese: "车二进五", reason: "贪吃" },
              line: [{ chinese: "炮8平3" }],
              outcome: { mate: 2 },
            },
          ],
        },
      },
    });
    const baits = wrapper.findAll('[data-test="intent-bait"]');
    expect(baits).toHaveLength(1);
    expect(baits[0].text()).toContain("若你走 车二进五（贪吃）：炮8平3");
    expect(baits[0].text()).toContain("绝杀（2 步内）");
  });

  it("rank.best 显示正着参考", () => {
    const wrapper = mount(IntentPanel, { props: { intent: baseIntent } });
    expect(wrapper.find('[data-test="intent-best"]').text()).toBe("正着参考：士四进五");
  });

  it("idle 时无内容行", () => {
    const wrapper = mount(IntentPanel, { props: { intent: { status: "idle" } } });
    expect(wrapper.findAll(".intent-item")).toHaveLength(0);
  });
});
