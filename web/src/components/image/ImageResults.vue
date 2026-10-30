<script setup lang="ts">
import { ref } from "vue";
import { Clock, Download, X } from "lucide-vue-next";

import AppButton from "@/components/ui/AppButton.vue";
import LazyImage from "@/components/ui/LazyImage.vue";
import { assetUrl } from "@/lib/request";
import type { StoredImage } from "@/stores/conversations";

const props = defineProps<{
    images: StoredImage[];
    count: number;
}>();

const emit = defineEmits<{
    "open-preview": [index: number];
    "continue-wait": [taskId: string];
    "retry": [index: number];
    "remove": [index: number];
}>();

function imageSrc(image: StoredImage): string {
    if (image.url) {
        return assetUrl(image.url);
    }
    if (image.b64_json) {
        return `data:image/png;base64,${image.b64_json}`;
    }
    return "";
}

function isTimeout(image: StoredImage) {
    return Boolean(image.error && image.error.includes("超时") && image.taskId);
}

function download(image: StoredImage, index: number) {
    const src = imageSrc(image);
    if (!src) {
        return;
    }
    if (!src.startsWith("data:")) {
        window.open(src, "_blank", "noopener");
        return;
    }
    const anchor = document.createElement("a");
    anchor.href = src;
    anchor.download = `image-${index + 1}.png`;
    anchor.click();
}
</script>

<template>
    <!--
        展示区固定高度：容器尺寸不随图片比例变化，避免每条结果都撑出
        不同高度、把输入框推来推去。图片在框内按比例 contain 缩放，
        完整可见、不裁剪。
    -->
    <div class="grid gap-3" :class="count > 1 ? 'sm:grid-cols-2' : ''">
        <div
            v-for="(image, index) in images"
            :key="image.id"
            :class="[
                'group relative flex items-center justify-center overflow-hidden rounded-md border border-border bg-bg',
                // 固定高度：图片比例不影响布局。列数越多单张越矮，整行始终齐平。
                count > 1 ? 'h-[clamp(12rem,30vh,20rem)]' : 'h-[clamp(16rem,46vh,28rem)]',
            ]"
        >
            <!-- 成功 -->
            <template v-if="image.status === 'success'">
                <LazyImage
                    :src="imageSrc(image)"
                    :alt="`结果 ${index + 1}`"
                    img-class="cursor-zoom-in"
                    @click="emit('open-preview', index)"
                />
                <!--
                    操作条在桌面悬停出现，触摸设备常显（用 hover:none 判断）。
                    translate 而非仅改透明度，触屏上也有明确的出现感。
                -->
                <div
                    class="absolute inset-x-0 bottom-0 flex items-center justify-end gap-1 bg-gradient-to-t from-ink/70 to-transparent p-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 touch-visible"
                >
                    <button
                        class="rounded-sm bg-surface p-2 text-ink transition-opacity hover:opacity-80"
                        aria-label="下载"
                        @click.stop="download(image, index)"
                    >
                        <Download class="size-3.5" />
                    </button>
                    <button
                        class="rounded-sm bg-surface p-2 text-ink transition-opacity hover:opacity-80"
                        aria-label="移除"
                        @click.stop="emit('remove', index)"
                    >
                        <X class="size-3.5" />
                    </button>
                </div>
            </template>

            <!-- 进行中：紧凑高度，不用 aspect-square 撑满 -->
            <div
                v-else-if="image.status === 'loading'"
                class="flex size-full flex-col items-center justify-center gap-2.5 px-5 text-center"
            >
                <div class="h-px w-16 overflow-hidden bg-border">
                    <div class="h-full w-1/2 animate-pulse bg-ink" />
                </div>
                <p class="meta-xs">{{ image.progress || "生成中" }}</p>
                <p v-if="image.elapsedSecs" class="meta-xs opacity-60">{{ image.elapsedSecs }}s</p>
            </div>

            <!-- 超时：可继续等待 -->
            <div
                v-else-if="isTimeout(image)"
                class="flex size-full flex-col items-center justify-center gap-2.5 px-5 text-center"
            >
                <Clock class="size-5" :style="{ color: 'var(--color-warning)' }" />
                <p class="text-xs leading-relaxed text-muted">{{ image.error }}</p>
                <AppButton
                    variant="secondary"
                    size="sm"
                    @click="emit('continue-wait', image.taskId!)"
                >
                    继续等待
                </AppButton>
            </div>

            <!-- 失败 -->
            <div
                v-else
                class="flex size-full flex-col items-center justify-center gap-2.5 px-5 text-center"
            >
                <p class="meta-xs" :style="{ color: 'var(--color-error)' }">生成失败</p>
                <p class="line-clamp-3 text-xs leading-relaxed text-muted">
                    {{ image.error || "未知错误" }}
                </p>
                <AppButton variant="secondary" size="sm" @click="emit('retry', index)">重试</AppButton>
            </div>
        </div>
    </div>
</template>

<style scoped>
/*
 * 触摸设备没有悬停，操作按钮必须常显，否则用户永远够不到下载与删除。
 * 用 hover:none 而不是按屏宽判断：带触摸屏的笔记本也能正确取舍。
 */
@media (hover: none) {
    .touch-visible {
        opacity: 1;
    }
}
</style>
