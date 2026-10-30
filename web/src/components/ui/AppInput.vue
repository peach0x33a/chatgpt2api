<script setup lang="ts">
import { computed } from "vue";

import { cn } from "@/lib/utils";

const props = withDefaults(
    defineProps<{
        modelValue?: string | number;
        type?: string;
        placeholder?: string;
        disabled?: boolean;
        invalid?: boolean;
        autofocus?: boolean;
        /** 是否使用等宽字体（用于 token、URL 等输入）。 */
        mono?: boolean;
    }>(),
    { type: "text", disabled: false, invalid: false, autofocus: false, mono: false },
);

const emit = defineEmits<{
    "update:modelValue": [string];
    enter: [KeyboardEvent];
}>();

/*
 * 输入框是「纸上的一处凹槽」：浅底、无内阴影、4px 圆角。
 * 聚焦时边框转墨色，不加发光环 —— 这是系统对「克制」的一贯选择。
 */
const classes = computed(() =>
    cn(
        "h-10 w-full rounded-sm border bg-bg px-3 text-sm text-ink",
        "placeholder:text-muted/70",
        "outline-none transition-[border-color] duration-150",
        "focus:border-ink",
        "disabled:cursor-not-allowed disabled:opacity-50",
        props.mono && "font-mono text-xs",
        props.invalid ? "border-error" : "border-border",
    ),
);

function onInput(event: Event) {
    emit("update:modelValue", (event.target as HTMLInputElement).value);
}
</script>

<template>
    <input
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :autofocus="autofocus"
        :class="classes"
        @input="onInput"
        @keydown.enter="emit('enter', $event as KeyboardEvent)"
    />
</template>
