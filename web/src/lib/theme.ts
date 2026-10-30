import { ref } from "vue";

const STORAGE_KEY = "chatgpt2api-theme";

function apply(dark: boolean) {
    document.documentElement.classList.toggle("dark", dark);
    try {
        localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
    } catch {
        // 隐私模式下 localStorage 可能不可用，忽略即可。
    }
}

const isDark = ref(document.documentElement.classList.contains("dark"));

/**
 * 主题切换。
 *
 * 首屏由 index.html 的内联脚本决定初始值，这里只负责后续切换，
 * 因此不会出现闪白。
 */
export function useTheme() {
    return {
        isDark,
        toggle() {
            isDark.value = !isDark.value;
            apply(isDark.value);
        },
        set(value: boolean) {
            isDark.value = value;
            apply(value);
        },
    };
}
