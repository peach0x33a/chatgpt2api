import { ref } from "vue";

export type ToastTone = "success" | "error" | "info";

export type ToastItem = {
    id: number;
    message: string;
    tone: ToastTone;
};

/**
 * 极简的全局提示。
 *
 * 原项目用 sonner，这里不引入额外依赖：提示本身很简单，
 * 自己实现反而能保证样式与设计 token 一致。
 */
const items = ref<ToastItem[]>([]);
let nextId = 1;

function push(message: string, tone: ToastTone, duration = 3200) {
    const id = nextId++;
    items.value = [...items.value, { id, message, tone }];
    window.setTimeout(() => {
        items.value = items.value.filter((item) => item.id !== id);
    }, duration);
}

export function useToast() {
    return {
        items,
        success: (message: string) => push(message, "success"),
        error: (message: string) => push(message, "error", 4800),
        info: (message: string) => push(message, "info"),
        dismiss: (id: number) => {
            items.value = items.value.filter((item) => item.id !== id);
        },
    };
}
