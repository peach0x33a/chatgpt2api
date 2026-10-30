<script setup lang="ts">
import { computed } from "vue";

import { cn } from "@/lib/utils";

type Tone = "neutral" | "success" | "warning" | "danger" | "accent" | "featured";

const props = withDefaults(
    defineProps<{
        tone?: Tone;
        /** xs 用于表格内状态，sm 用于说明性标签。 */
        size?: "xs" | "sm";
    }>(),
    { tone: "neutral", size: "xs" },
);

/*
 * 徽标文字一律 10-12px 等宽粗体，比标题安静。
 * 底色用低透明度，避免彩色抢占视觉重心。
 */
const toneClass: Record<Tone, string> = {
    neutral: "bg-border/40 text-muted border-border/60",
    success: "bg-emerald-500/10 text-emerald-700 border-emerald-500/25 dark:text-emerald-400",
    warning: "bg-warning-wash text-warning-text border-warning/30",
    danger: "bg-error/10 text-error border-error/25",
    accent: "bg-accent-wash text-accent-text border-accent/25",
    featured: "bg-featured-wash text-featured border-amber-500/40",
};

const classes = computed(() =>
    cn(
        "status-badge",
        props.size === "sm" && "text-xs font-medium px-2 py-0.5",
        toneClass[props.tone],
    ),
);
</script>

<template>
    <span :class="classes"><slot /></span>
</template>
