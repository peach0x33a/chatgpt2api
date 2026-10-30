<script setup lang="ts">
import { computed } from "vue";

import { cn } from "@/lib/utils";

const props = withDefaults(
    defineProps<{
        tone?: "neutral" | "success" | "warning" | "danger" | "info";
        /** 0-100，进行中的进度。 */
        value?: number;
        indeterminate?: boolean;
    }>(),
    { tone: "neutral", value: 0, indeterminate: false },
);

const toneClass = {
    neutral: "bg-primary",
    success: "bg-emerald-500",
    warning: "bg-amber-500",
    danger: "bg-red-500",
    info: "bg-sky-500",
};

const clamped = computed(() => Math.max(0, Math.min(100, props.value)));
</script>

<template>
    <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
            :class="[
                'h-full rounded-full transition-[width] duration-300',
                toneClass[tone],
                indeterminate && 'animate-pulse',
            ]"
            :style="indeterminate ? { width: '40%' } : { width: `${clamped}%` }"
        />
    </div>
</template>
