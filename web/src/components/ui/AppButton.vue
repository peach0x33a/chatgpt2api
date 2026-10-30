<script setup lang="ts">
import { computed } from "vue";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "bracket" | "danger";
type Size = "sm" | "md" | "icon";

const props = withDefaults(
    defineProps<{
        variant?: Variant;
        size?: Size;
        type?: "button" | "submit" | "reset";
        disabled?: boolean;
        loading?: boolean;
        block?: boolean;
    }>(),
    {
        variant: "secondary",
        size: "md",
        type: "button",
        disabled: false,
        loading: false,
        block: false,
    },
);

const emit = defineEmits<{ click: [MouseEvent] }>();

/*
 * 括号按钮单独处理：它没有背景与边框，是这套系统的签名式交互。
 * 其余变体共用 4px 圆角（控件档），与容器的 8px 形成清晰分工。
 */
const variantClass: Record<Variant, string> = {
    primary:
        "bg-ink text-bg font-bold hover:opacity-90 disabled:opacity-50 border border-transparent",
    secondary:
        "bg-surface text-ink border border-border hover:bg-bg disabled:opacity-50",
    ghost:
        "bg-transparent text-muted border border-transparent hover:bg-bg hover:text-ink",
    danger:
        "bg-transparent text-error border border-error/40 hover:bg-error/10",
    bracket: "bracket-button",
};

const sizeClass: Record<Size, string> = {
    sm: "h-8 px-3 text-sm",
    md: "h-10 px-4 text-sm",
    icon: "size-9",
};

const classes = computed(() => {
    if (props.variant === "bracket") {
        return cn(variantClass.bracket, props.block && "w-full");
    }
    return cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm font-medium",
        "transition-[background-color,color,opacity,border-color] duration-150",
        "disabled:cursor-not-allowed",
        "[&_svg]:shrink-0",
        variantClass[props.variant],
        sizeClass[props.size],
        props.block && "w-full",
    );
});
</script>

<template>
    <button
        :type="type"
        :class="classes"
        :disabled="disabled || loading"
        @click="emit('click', $event)"
    >
        <span
            v-if="loading"
            class="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
            aria-hidden="true"
        />
        <slot />
    </button>
</template>
