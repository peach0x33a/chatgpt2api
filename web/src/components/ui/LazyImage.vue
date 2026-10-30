<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

/**
 * 懒加载图片。
 *
 * 浏览器原生的 loading="lazy" 在固定高度容器里判断很激进，
 * 常常一次预载几十张。这里用 IntersectionObserver 自己控制：
 * 只有真正接近视口时才设置 src，离得远时保持占位。
 */
const props = withDefaults(
    defineProps<{
        src: string;
        alt?: string;
        /** 提前多少像素开始加载。 */
        rootMargin?: string;
        /** 加载完成后的额外类名。 */
        imgClass?: string;
        /** 未加载完成时显示的占位底色类名。 */
        placeholderClass?: string;
    }>(),
    { rootMargin: "400px", imgClass: "", placeholderClass: "bg-border/30" },
);

const emit = defineEmits<{ click: [MouseEvent] }>();

const container = ref<HTMLElement | null>(null);
const loaded = ref(false);
const failed = ref(false);
const visible = ref(false);

let observer: IntersectionObserver | null = null;

function observe() {
    const el = container.value;
    if (!el) {
        return;
    }
    // 不支持时直接放行，避免图片永远不加载。
    if (typeof IntersectionObserver === "undefined") {
        visible.value = true;
        return;
    }
    observer = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    visible.value = true;
                    observer?.disconnect();
                    observer = null;
                    break;
                }
            }
        },
        { rootMargin: props.rootMargin },
    );
    observer.observe(el);
}

onMounted(observe);

onBeforeUnmount(() => {
    observer?.disconnect();
    observer = null;
});

// src 变化（例如切换会话）时重置状态。
watch(
    () => props.src,
    () => {
        loaded.value = false;
        failed.value = false;
        if (!visible.value) {
            observe();
        }
    },
);
</script>

<template>
    <div ref="container" class="relative size-full">
        <!-- 占位：加载完成前保持同一块区域，避免布局跳动 -->
        <div
            v-if="!loaded && !failed"
            :class="['absolute inset-0', placeholderClass]"
            aria-hidden="true"
        />
        <img
            v-if="visible && !failed"
            :src="src"
            :alt="alt || ''"
            :class="[
                'size-full object-contain transition-opacity duration-300',
                loaded ? 'opacity-100' : 'opacity-0',
                imgClass,
            ]"
            @load="loaded = true"
            @error="failed = true"
            @click="emit('click', $event)"
        />
        <div
            v-else-if="failed"
            class="absolute inset-0 flex items-center justify-center"
        >
            <span class="meta-xs">图片加载失败</span>
        </div>
    </div>
</template>
