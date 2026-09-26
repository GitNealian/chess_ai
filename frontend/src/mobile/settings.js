const KEY = "chess:mobile-settings";
const DEFAULTS = { score: false, intent: false };

export function loadSettings() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULTS };
    const data = JSON.parse(raw);
    return {
      score: data?.score === true,
      intent: data?.intent === true,
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ score: settings?.score === true, intent: settings?.intent === true })
    );
  } catch {
    // 写入失败（如隐私模式）静默
  }
}
