import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合并 Tailwind 类名，后者覆盖前者。 */
export function cn(...inputs: ClassValue[]): string {
    return twMerge(clsx(inputs));
}

/** 格式化字节数为可读大小。 */
export function formatBytes(bytes: number): string {
    if (!Number.isFinite(bytes) || bytes <= 0) {
        return "0 B";
    }
    const units = ["B", "KB", "MB", "GB", "TB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / 1024 ** index;
    return `${value >= 10 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

/** 把时间戳或字符串格式化成简短时间。 */
export function formatTime(value?: string | null): string {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value);
    }
    return date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

/** 复制文本到剪贴板，失败时回退到临时 textarea。 */
export async function copyText(text: string): Promise<boolean> {
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            return true;
        }
    } catch {
        // 落到下面的回退实现。
    }
    try {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(area);
        return ok;
    } catch {
        return false;
    }
}

/** 生成短随机 ID。 */
export function createId(prefix = ""): string {
    const random =
        typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
            : Math.random().toString(36).slice(2, 18);
    return prefix ? `${prefix}${random}` : random;
}

/** 延时函数，供轮询使用。 */
export function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
