<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import ImagesPanel from "@/components/records/ImagesPanel.vue";
import LogsPanel from "@/components/records/LogsPanel.vue";
import type { SystemLog } from "@/lib/api";
import { imageRelFromUrl } from "@/lib/utils";

/*
 * 记录页：调用日志与图片图库合到一页，用页内选项卡切换。
 *
 * 两者本来就是一条链路的两端 —— 请求产生了图片，图片又能反查回请求。
 * 分成两个页面时，用户只能靠记忆在两边对时间和提示词；放在一起后
 * 一次点击就能互相跳转。视图状态记在地址栏（?view=images），
 * 刷新或分享链接后仍停在同一个视图。
 */

type View = "logs" | "images";

const TABS: Array<{ value: View; label: string }> = [
    { value: "logs", label: "日志" },
    { value: "images", label: "图片" },
];

const route = useRoute();
const router = useRouter();

const view = computed<View>(() => (route.query.view === "images" ? "images" : "logs"));

/** 面板首次进入才挂载，之后常驻：切回来时筛选条件、选中项都还在。 */
const mounted = ref<Record<View, boolean>>({ logs: true, images: false });

/* 跨面板跳转：日志 → 图片，或图片 → 日志。 */
const focusLog = ref<SystemLog | null>(null);
/** 同一个对象再次跳转时引用不变，靠这个序号让面板重新响应。 */
const focusLogSeq = ref(0);
const focusImageRel = ref<string | null>(null);

watch(
    view,
    (value) => {
        mounted.value[value] = true;
    },
    { immediate: true },
);

function setView(next: View) {
    focusLog.value = null;
    focusImageRel.value = null;
    mounted.value[next] = true;
    if (next === view.value) {
        return;
    }
    void router.replace({
        name: "records",
        query: next === "images" ? { view: "images" } : {},
    });
}

/** 日志详情里的产物缩略图：切到图片视图并展开对应图片的详情。 */
function openImage(url: string) {
    const rel = imageRelFromUrl(url);
    if (!rel) {
        return;
    }
    focusImageRel.value = rel;
    mounted.value.images = true;
    void router.replace({ name: "records", query: { view: "images" } });
}

/** 图片详情里的「查看日志」：切回日志视图并展开那条记录。 */
function openLog(item: SystemLog) {
    focusLog.value = item;
    focusLogSeq.value += 1;
    mounted.value.logs = true;
    void router.replace({ name: "records", query: {} });
}

/** 图片面板已经消费掉跳转意图，清掉引用，避免刷新列表时又弹一次。 */
function clearFocusImage() {
    focusImageRel.value = null;
}
</script>

<template>
    <div class="space-y-6">
        <div class="flex flex-wrap items-end justify-between gap-4 border-b border-border">
            <div class="flex items-end gap-6">
                <h1 class="pb-3 text-2xl font-bold text-ink" style="font-family: var(--font-prose)">
                    记录
                </h1>

                <!-- 页内视图切换：下划线标出当前位置，与工具条里的墨色按钮区分开。 -->
                <nav class="-mb-px flex items-center gap-5" aria-label="视图">
                    <button
                        v-for="tab in TABS"
                        :key="tab.value"
                        type="button"
                        :class="[
                            'border-b-2 pb-3 pt-1 text-sm transition-colors duration-150',
                            view === tab.value
                                ? 'border-ink font-bold text-ink'
                                : 'border-transparent text-muted hover:text-ink',
                        ]"
                        :aria-current="view === tab.value ? 'page' : undefined"
                        @click="setView(tab.value)"
                    >
                        {{ tab.label }}
                    </button>
                </nav>
            </div>
        </div>

        <!-- 用 v-show 保活：两个面板的滚动位置、筛选与选中状态互相独立且不丢。 -->
        <LogsPanel
            v-show="view === 'logs'"
            :focus-log="focusLog"
            :focus-seq="focusLogSeq"
            :active="view === 'logs'"
            @open-image="openImage"
        />
        <ImagesPanel
            v-if="mounted.images"
            v-show="view === 'images'"
            :focus-image-rel="focusImageRel"
            :active="view === 'images'"
            @open-log="openLog"
            @focus-consumed="clearFocusImage"
        />
    </div>
</template>
