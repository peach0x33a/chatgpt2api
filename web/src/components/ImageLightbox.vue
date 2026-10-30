<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ChevronLeft, ChevronRight, Download, X, ZoomIn, ZoomOut } from "lucide-vue-next";

export type LightboxItem = {
    src: string;
    alt?: string;
    /** 下载时的文件名。 */
    filename?: string;
};

const props = defineProps<{
    items: LightboxItem[];
    /** 当前索引；null 表示关闭。 */
    index: number | null;
}>();

const emit = defineEmits<{ "update:index": [number | null] }>();

const scale = ref(1);
const offsetX = ref(0);
const offsetY = ref(0);

/* 拖拽状态 */
let dragging = false;
let dragStartX = 0;
let dragStartY = 0;
let startOffsetX = 0;
let startOffsetY = 0;

/* 双指缩放状态 */
let pinchStartDistance = 0;
let pinchStartScale = 1;

const open = computed(() => props.index !== null && props.items.length > 0);

const current = computed(() => {
    if (props.index === null) {
        return null;
    }
    return props.items[props.index] ?? null;
});

const hasPrev = computed(() => props.index !== null && props.index > 0);
const hasNext = computed(() => props.index !== null && props.index < props.items.length - 1);

/** 切换图片时重置视图变换。 */
function resetView() {
    scale.value = 1;
    offsetX.value = 0;
    offsetY.value = 0;
}

function close() {
    resetView();
    emit("update:index", null);
}

function go(delta: number) {
    if (props.index === null) {
        return;
    }
    const next = props.index + delta;
    if (next < 0 || next >= props.items.length) {
        return;
    }
    resetView();
    emit("update:index", next);
}

function zoomBy(delta: number) {
    const next = Math.min(5, Math.max(1, Number((scale.value + delta).toFixed(2))));
    scale.value = next;
    // 回到 1 倍时同时复位位移，避免图片停在偏移位置。
    if (next === 1) {
        offsetX.value = 0;
        offsetY.value = 0;
    }
}

function toggleZoom() {
    if (scale.value > 1) {
        resetView();
    } else {
        scale.value = 2;
    }
}

function download() {
    const item = current.value;
    if (!item) {
        return;
    }
    const anchor = document.createElement("a");
    anchor.href = item.src;
    anchor.download = item.filename || "image.png";
    // 远程图片直接新开，跨域时 download 属性无效。
    if (!item.src.startsWith("data:")) {
        window.open(item.src, "_blank", "noopener");
        return;
    }
    anchor.click();
}

/* ── 键盘 ── */
function onKeydown(event: KeyboardEvent) {
    if (!open.value) {
        return;
    }
    switch (event.key) {
        case "Escape":
            close();
            break;
        case "ArrowLeft":
            go(-1);
            break;
        case "ArrowRight":
            go(1);
            break;
        case "+":
        case "=":
            zoomBy(0.5);
            break;
        case "-":
            zoomBy(-0.5);
            break;
        case "0":
            resetView();
            break;
        default:
            return;
    }
    event.preventDefault();
}

/* ── 滚轮缩放 ── */
function onWheel(event: WheelEvent) {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 0.25 : -0.25);
}

/* ── 拖拽平移（缩放后才有意义） ── */
function onPointerDown(event: PointerEvent) {
    if (scale.value <= 1) {
        return;
    }
    dragging = true;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    startOffsetX = offsetX.value;
    startOffsetY = offsetY.value;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
    if (!dragging) {
        return;
    }
    offsetX.value = startOffsetX + (event.clientX - dragStartX);
    offsetY.value = startOffsetY + (event.clientY - dragStartY);
}

function onPointerUp(event: PointerEvent) {
    if (!dragging) {
        return;
    }
    dragging = false;
    (event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId);
}

/* ── 双指缩放 ── */
function touchDistance(touches: TouchList): number {
    const [a, b] = [touches[0], touches[1]];
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}

function onTouchStart(event: TouchEvent) {
    if (event.touches.length === 2) {
        pinchStartDistance = touchDistance(event.touches);
        pinchStartScale = scale.value;
    }
}

function onTouchMove(event: TouchEvent) {
    if (event.touches.length !== 2 || pinchStartDistance === 0) {
        return;
    }
    event.preventDefault();
    const ratio = touchDistance(event.touches) / pinchStartDistance;
    scale.value = Math.min(5, Math.max(1, Number((pinchStartScale * ratio).toFixed(2))));
}

function onTouchEnd() {
    pinchStartDistance = 0;
    if (scale.value <= 1) {
        offsetX.value = 0;
        offsetY.value = 0;
    }
}

/* 打开时挂键盘监听，关闭时移除。 */
watch(open, (value) => {
    if (value) {
        window.addEventListener("keydown", onKeydown);
        document.body.style.overflow = "hidden";
    } else {
        window.removeEventListener("keydown", onKeydown);
        document.body.style.overflow = "";
    }
});

onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown);
    document.body.style.overflow = "";
});
</script>

<template>
    <Teleport to="body">
        <Transition
            enter-active-class="transition-opacity duration-200"
            enter-from-class="opacity-0"
            leave-active-class="transition-opacity duration-150"
            leave-to-class="opacity-0"
        >
            <div
                v-if="open"
                class="fixed inset-0 z-[90] flex flex-col"
                :style="{ background: 'var(--color-overlay)', backdropFilter: 'blur(8px)' }"
                @wheel="onWheel"
            >
                <!-- 顶栏：计数、缩放、下载、关闭 -->
                <div class="flex shrink-0 items-center justify-between gap-3 px-4 py-3">
                    <span class="meta">
                        {{ (index ?? 0) + 1 }} / {{ items.length }}
                        <span v-if="scale > 1" class="ml-2">{{ Math.round(scale * 100) }}%</span>
                    </span>
                    <div class="flex items-center gap-1">
                        <button
                            class="rounded-sm p-2 text-muted transition-colors hover:text-ink"
                            aria-label="缩小"
                            @click="zoomBy(-0.5)"
                        >
                            <ZoomOut class="size-4" />
                        </button>
                        <button
                            class="rounded-sm p-2 text-muted transition-colors hover:text-ink"
                            aria-label="放大"
                            @click="zoomBy(0.5)"
                        >
                            <ZoomIn class="size-4" />
                        </button>
                        <button
                            class="rounded-sm p-2 text-muted transition-colors hover:text-ink"
                            aria-label="下载"
                            @click="download"
                        >
                            <Download class="size-4" />
                        </button>
                        <button
                            class="rounded-sm p-2 text-muted transition-colors hover:text-ink"
                            aria-label="关闭"
                            @click="close"
                        >
                            <X class="size-4" />
                        </button>
                    </div>
                </div>

                <!-- 图片区 -->
                <div class="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
                    <img
                        v-if="current"
                        :src="current.src"
                        :alt="current.alt || ''"
                        class="max-h-full max-w-full select-none object-contain"
                        :class="[
                            scale > 1 ? 'cursor-grab active:cursor-grabbing' : 'cursor-zoom-in',
                            dragging && 'cursor-grabbing',
                        ]"
                        :style="{
                            transform: `scale(${scale}) translate(${offsetX / scale}px, ${offsetY / scale}px)`,
                            transition: dragging ? 'none' : 'transform 150ms ease-out',
                            touchAction: 'none',
                        }"
                        @click="toggleZoom"
                        @pointerdown="onPointerDown"
                        @pointermove="onPointerMove"
                        @pointerup="onPointerUp"
                        @pointercancel="onPointerUp"
                        @touchstart="onTouchStart"
                        @touchmove="onTouchMove"
                        @touchend="onTouchEnd"
                    />

                    <!-- 左右翻页 -->
                    <button
                        v-if="hasPrev"
                        class="absolute left-2 rounded-full p-2 text-muted transition-colors hover:text-ink disabled:opacity-30"
                        aria-label="上一张"
                        @click.stop="go(-1)"
                    >
                        <ChevronLeft class="size-6" />
                    </button>
                    <button
                        v-if="hasNext"
                        class="absolute right-2 rounded-full p-2 text-muted transition-colors hover:text-ink disabled:opacity-30"
                        aria-label="下一张"
                        @click.stop="go(1)"
                    >
                        <ChevronRight class="size-6" />
                    </button>
                </div>

                <!-- 底部提示 -->
                <div class="shrink-0 px-4 py-3 text-center">
                    <p class="meta-xs">
                        ← → 翻页 · 滚轮缩放 · 双击还原 · Esc 关闭
                    </p>
                </div>
            </div>
        </Transition>
    </Teleport>
</template>
