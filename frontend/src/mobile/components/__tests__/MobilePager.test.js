import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MobilePager from "../MobilePager.vue";

const props = (overrides = {}) => ({ page: 1, pageSize: 20, total: 100, ...overrides });

describe("MobilePager", () => {
  it("首页上一页禁用、末页下一页禁用", () => {
    const first = mount(MobilePager, { props: props() });
    expect(first.find("[data-test='pager-prev']").attributes("disabled")).toBeDefined();
    expect(first.find("[data-test='pager-next']").attributes("disabled")).toBeUndefined();

    const last = mount(MobilePager, { props: props({ page: 5 }) });
    expect(last.find("[data-test='pager-prev']").attributes("disabled")).toBeUndefined();
    expect(last.find("[data-test='pager-next']").attributes("disabled")).toBeDefined();
  });

  it("点下一页发出 change", async () => {
    const wrapper = mount(MobilePager, { props: props() });
    await wrapper.find("[data-test='pager-next']").trigger("click");
    expect(wrapper.emitted("change")[0]).toEqual([2]);
  });

  it("输入页码跳转", async () => {
    const wrapper = mount(MobilePager, { props: props() });
    await wrapper.find("[data-test='pager-input']").setValue("3");
    await wrapper.find("[data-test='pager-go']").trigger("click");
    expect(wrapper.emitted("change")[0]).toEqual([3]);
  });

  it("超出范围钳制到末页", async () => {
    const wrapper = mount(MobilePager, { props: props() });
    await wrapper.find("[data-test='pager-input']").setValue("99");
    await wrapper.find("[data-test='pager-go']").trigger("click");
    expect(wrapper.emitted("change")[0]).toEqual([5]);
  });

  it("非数字输入不触发 change", async () => {
    const wrapper = mount(MobilePager, { props: props() });
    await wrapper.find("[data-test='pager-input']").setValue("abc");
    await wrapper.find("[data-test='pager-go']").trigger("click");
    expect(wrapper.emitted("change")).toBeUndefined();
  });
});
