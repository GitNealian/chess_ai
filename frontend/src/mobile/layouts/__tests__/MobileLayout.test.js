import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import router from "../../../router";
import MobileLayout from "../MobileLayout.vue";

describe("MobileLayout 顶栏", () => {
  it("打开/设置图标按钮点击派发事件", async () => {
    await router.push("/m");
    await router.isReady();
    const open = vi.fn();
    const settings = vi.fn();
    window.addEventListener("mobile-open", open);
    window.addEventListener("mobile-settings", settings);
    const wrapper = mount(MobileLayout, { global: { plugins: [router] } });
    await flushPromises();
    await wrapper.find("[data-test='header-open']").trigger("click");
    await wrapper.find("[data-test='header-settings']").trigger("click");
    window.removeEventListener("mobile-open", open);
    window.removeEventListener("mobile-settings", settings);
    expect(open).toHaveBeenCalledTimes(1);
    expect(settings).toHaveBeenCalledTimes(1);
  });
});
