<script setup lang="ts">
import {
    DialogClose,
    DialogContent,
    DialogDescription,
    DialogOverlay,
    DialogPortal,
    DialogRoot,
    DialogTitle,
} from "reka-ui";
import { X } from "lucide-vue-next";

withDefaults(
    defineProps<{
        open: boolean;
        title?: string;
        description?: string;
        size?: "sm" | "md" | "lg" | "xl";
    }>(),
    { size: "md" },
);

const emit = defineEmits<{ "update:open": [boolean] }>();

const widthClass = {
    sm: "max-w-sm",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
};

/*
 * 遮罩用「纸色 80% + 4px 模糊」，而不是纯黑 ——
 * 这样暗色模式下遮罩也跟着变深，不会突然出现一块黑。
 */
</script>

<template>
    <DialogRoot :open="open" @update:open="emit('update:open', $event)">
        <DialogPortal>
            <DialogOverlay
                class="fixed inset-0 z-60 backdrop-blur-[4px]"
                :style="{ background: 'var(--color-overlay)' }"
            />
            <DialogContent
                :class="[
                    'fixed left-1/2 top-1/2 z-60 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2',
                    'max-h-[88vh] overflow-y-auto rounded-sm border border-border bg-surface p-6',
                    'shadow-[var(--shadow-2xl)]',
                    widthClass[size],
                ]"
                :style="{ animation: 'ink-in 400ms ease-out both' }"
            >
                <div v-if="title || description" class="mb-5 pr-6">
                    <DialogTitle
                        v-if="title"
                        class="text-xl font-bold leading-tight text-ink"
                        style="font-family: var(--font-prose)"
                    >
                        {{ title }}
                    </DialogTitle>
                    <DialogDescription v-if="description" class="mt-1.5 text-sm leading-relaxed text-muted">
                        {{ description }}
                    </DialogDescription>
                </div>

                <slot />

                <DialogClose
                    class="absolute right-4 top-4 rounded-sm p-1 text-muted transition-colors duration-150 hover:bg-bg hover:text-ink"
                    aria-label="关闭"
                >
                    <X class="size-5" />
                </DialogClose>
            </DialogContent>
        </DialogPortal>
    </DialogRoot>
</template>
