<script setup lang="ts">
import { X } from "lucide-vue-next";

import { useToast } from "@/lib/toast";

const { items, dismiss } = useToast();
</script>

<template>
    <!--
        Toast 是反转的胶囊：墨色填充、纸色文字、12px 圆角 ——
        系统里唯一使用 12px 的元素，也是唯一「黑底」的提示。
    -->
    <div class="pointer-events-none fixed inset-x-0 top-4 z-80 flex flex-col items-center gap-2 px-4">
        <TransitionGroup
            enter-active-class="transition duration-200 ease-out"
            enter-from-class="opacity-0 translate-y-[5px]"
            leave-active-class="transition duration-150 ease-in"
            leave-to-class="opacity-0"
        >
            <div
                v-for="item in items"
                :key="item.id"
                class="pointer-events-auto flex max-w-md items-start gap-2 rounded-lg px-5 py-3 shadow-[var(--shadow-2xl)]"
                :style="{
                    background: 'var(--text)',
                    color: 'var(--bg)',
                    border: '1px solid rgba(255,255,255,0.1)',
                }"
                role="status"
            >
                <span class="flex-1 text-sm leading-snug">{{ item.message }}</span>
                <button
                    class="mt-0.5 opacity-50 transition-opacity duration-150 hover:opacity-100"
                    aria-label="关闭"
                    @click="dismiss(item.id)"
                >
                    <X class="size-3.5" />
                </button>
            </div>
        </TransitionGroup>
    </div>
</template>
