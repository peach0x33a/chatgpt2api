<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Trash2 } from "lucide-vue-next";

import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import {
    deleteSystemLogs,
    fetchSystemLogs,
    type SystemLog,
} from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatTime } from "@/lib/utils";

const toast = useToast();

const LOG_TYPES = [
    { value: "call", label: "调用日志" },
    { value: "account", label: "账号日志" },
];

const items = ref<SystemLog[]>([]);
const loading = ref(false);
/** 加载失败原因：与「没有日志」区分开。 */
const loadError = ref("");
const type = ref("call");
const startDate = ref("");
const endDate = ref("");
const keyword = ref("");
const selectedIds = ref<Set<string>>(new Set());
const detail = ref<SystemLog | null>(null);

const filtered = computed(() => {
    const text = keyword.value.trim().toLowerCase();
    if (!text) {
        return items.value;
    }
    return items.value.filter((item) => {
        const haystack = JSON.stringify(item).toLowerCase();
        return haystack.includes(text);
    });
});

/** 失败条目数：作为可扫读的读数放在左侧。 */
const failedCount = computed(
    () => filtered.value.filter((item) => item.detail?.status === "failed").length,
);

const allSelected = computed(
    () => filtered.value.length > 0 && filtered.value.every((item) => selectedIds.value.has(item.id)),
);

onMounted(load);
watch(type, load);

async function load() {
    loading.value = true;
    loadError.value = "";
    try {
        const data = await fetchSystemLogs({
            type: type.value,
            start_date: startDate.value,
            end_date: endDate.value,
        });
        items.value = data.items;
        // 只保留仍存在的选中项。
        const existing = new Set(data.items.map((item) => item.id));
        selectedIds.value = new Set([...selectedIds.value].filter((id) => existing.has(id)));
    } catch (error) {
        loadError.value = error instanceof Error ? error.message : "加载日志失败";
    } finally {
        loading.value = false;
    }
}

function toggle(id: string) {
    const next = new Set(selectedIds.value);
    if (next.has(id)) {
        next.delete(id);
    } else {
        next.add(id);
    }
    selectedIds.value = next;
}

function toggleAll() {
    selectedIds.value = allSelected.value
        ? new Set()
        : new Set(filtered.value.map((item) => item.id));
}

async function removeSelected() {
    const ids = [...selectedIds.value];
    if (ids.length === 0) {
        return;
    }
    if (!window.confirm(`删除 ${ids.length} 条日志？`)) {
        return;
    }
    try {
        const result = await deleteSystemLogs(ids);
        toast.success(`已删除 ${result.removed} 条`);
        selectedIds.value = new Set();
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

/* ── 详情字段提取 ── */

function detailValue(item: SystemLog, key: string): string {
    const value = item.detail?.[key];
    if (typeof value === "string" || typeof value === "number") {
        return String(value);
    }
    return "-";
}

function statusOf(item: SystemLog): { label: string; tone: "success" | "danger" | "neutral" } {
    const status = item.detail?.status;
    if (status === "success") {
        return { label: "成功", tone: "success" };
    }
    if (status === "failed") {
        return { label: "失败", tone: "danger" };
    }
    return { label: "-", tone: "neutral" };
}

function durationOf(item: SystemLog): string {
    const value = item.detail?.duration_ms;
    return typeof value === "number" ? `${(value / 1000).toFixed(2)}s` : "-";
}

const detailJson = computed(() => {
    if (!detail.value) {
        return "";
    }
    return JSON.stringify(detail.value.detail ?? {}, null, 2);
});
</script>

<template>
    <div class="space-y-6">
        <div class="flex flex-wrap items-baseline justify-between gap-4 border-b border-border pb-4">
            <h1 class="text-2xl font-bold text-ink" style="font-family: var(--font-prose)">
                日志
            </h1>
        </div>

        <!--
            一行骨架：左侧读数，右侧筛选与操作。
            与号池、图片页保持同一节奏。
        -->
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-dashed border-border pb-3">
            <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">记录</span>
                    <span class="text-xl font-bold tabular-nums text-ink" style="font-family: var(--font-mono)">
                        {{ loadError ? "—" : filtered.length }}
                    </span>
                </div>
                <div class="h-5 w-px bg-border" />
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">失败</span>
                    <span
                        class="text-xl font-bold tabular-nums"
                        :style="{
                            color: failedCount > 0 ? 'var(--color-error)' : 'var(--text-muted)',
                            fontFamily: 'var(--font-mono)',
                        }"
                    >
                        {{ loadError ? "—" : failedCount }}
                    </span>
                </div>
            </div>

            <div class="ml-auto flex flex-wrap items-center gap-2">
                <button
                    v-if="selectedIds.size > 0"
                    class="bracket-button mr-1 border-r border-border pr-3"
                    @click="removeSelected"
                >
                    [删除选中 {{ selectedIds.size }}]
                </button>

                <div class="flex gap-1">
                    <button
                        v-for="option in LOG_TYPES"
                        :key="option.value"
                        :class="[
                            'flex h-8 items-center rounded-sm border px-2.5 font-mono text-xs transition-colors duration-150',
                            type === option.value
                                ? 'border-ink bg-ink text-bg'
                                : 'border-border bg-bg text-muted hover:text-ink',
                        ]"
                        @click="type = option.value"
                    >
                        {{ option.label }}
                    </button>
                </div>

                <input
                    v-model="startDate"
                    type="date"
                    class="h-8 rounded-sm border border-border bg-bg px-2 font-mono text-xs text-ink outline-none focus:border-ink"
                />
                <span class="meta-xs">至</span>
                <input
                    v-model="endDate"
                    type="date"
                    class="h-8 rounded-sm border border-border bg-bg px-2 font-mono text-xs text-ink outline-none focus:border-ink"
                />
                <input
                    v-model="keyword"
                    placeholder="筛选内容"
                    class="h-8 w-40 rounded-sm border border-border bg-bg px-2 text-xs text-ink outline-none placeholder:text-muted/70 focus:border-ink"
                />
                <button class="bracket-button" :disabled="loading" @click="load">[查询]</button>
            </div>
        </div>

        <!-- 列表 -->
        <div v-if="loading" class="border border-dashed border-border py-16 text-center">
            <p class="meta">加载中</p>
        </div>
        <div v-else-if="loadError" class="border border-dashed border-border py-16 text-center">
            <p class="text-sm" :style="{ color: 'var(--color-error)' }">日志读取失败</p>
            <p class="meta-xs mt-2">{{ loadError }}</p>
            <button class="bracket-button mt-4" @click="load">[重试]</button>
        </div>
        <div v-else-if="filtered.length === 0" class="border border-dashed border-border py-16 text-center">
            <p class="text-sm text-muted">没有日志</p>
        </div>
        <div v-else class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b border-border text-left">
                        <th class="w-8 py-2">
                            <input
                                type="checkbox"
                                :checked="allSelected"
                                class="size-3.5 accent-ink"
                                @change="toggleAll"
                            />
                        </th>
                        <th class="w-20 py-2 font-normal"><span class="meta">状态</span></th>
                        <th class="py-2 font-normal"><span class="meta">摘要</span></th>
                        <th class="py-2 font-normal"><span class="meta">模型</span></th>
                        <th class="py-2 font-normal"><span class="meta">接口</span></th>
                        <th class="w-20 py-2 text-right font-normal"><span class="meta">耗时</span></th>
                        <th class="w-28 py-2 font-normal"><span class="meta">时间</span></th>
                    </tr>
                </thead>
                <tbody>
                    <tr
                        v-for="item in filtered"
                        :key="item.id"
                        class="cursor-pointer border-b border-border/50 transition-colors duration-150 hover:bg-border/20"
                        @click="detail = item"
                    >
                        <td class="py-2.5" @click.stop>
                            <input
                                type="checkbox"
                                :checked="selectedIds.has(item.id)"
                                class="size-3.5 accent-ink"
                                @change="toggle(item.id)"
                            />
                        </td>
                        <td class="py-2.5 pr-3">
                            <AppBadge :tone="statusOf(item).tone">{{ statusOf(item).label }}</AppBadge>
                        </td>
                        <td class="max-w-64 py-2.5 pr-3">
                            <p class="truncate text-ink">{{ item.summary || "-" }}</p>
                            <p
                                v-if="detailValue(item, 'request_text') !== '-'"
                                class="meta-xs truncate"
                            >
                                {{ detailValue(item, "request_text") }}
                            </p>
                        </td>
                        <td class="py-2.5 pr-3">
                            <span class="meta-xs">{{ detailValue(item, "model") }}</span>
                        </td>
                        <td class="py-2.5 pr-3">
                            <span class="meta-xs">{{ detailValue(item, "endpoint") }}</span>
                        </td>
                        <td
                            class="py-2.5 pr-3 text-right tabular-nums"
                            style="font-family: var(--font-mono); font-size: 0.75rem"
                        >
                            {{ durationOf(item) }}
                        </td>
                        <td class="py-2.5">
                            <span class="meta-xs">{{ formatTime(item.time) }}</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- 详情 -->
        <AppDialog
            :open="detail !== null"
            :title="detail?.summary || '日志详情'"
            :description="detail ? formatTime(detail.time) : ''"
            size="lg"
            @update:open="detail = null"
        >
            <div v-if="detail" class="space-y-4">
                <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <div>
                        <p class="meta-xs">状态</p>
                        <p class="mt-0.5 text-sm text-ink">{{ statusOf(detail).label }}</p>
                    </div>
                    <div>
                        <p class="meta-xs">模型</p>
                        <p class="mt-0.5 font-mono text-xs text-ink">{{ detailValue(detail, "model") }}</p>
                    </div>
                    <div>
                        <p class="meta-xs">耗时</p>
                        <p class="mt-0.5 font-mono text-xs text-ink">{{ durationOf(detail) }}</p>
                    </div>
                    <div>
                        <p class="meta-xs">账号</p>
                        <p class="mt-0.5 truncate text-sm text-ink">
                            {{ detailValue(detail, "account_email") }}
                        </p>
                    </div>
                    <div>
                        <p class="meta-xs">接口</p>
                        <p class="mt-0.5 font-mono text-xs text-ink">
                            {{ detailValue(detail, "endpoint") }}
                        </p>
                    </div>
                    <div>
                        <p class="meta-xs">操作者</p>
                        <p class="mt-0.5 text-sm text-ink">{{ detailValue(detail, "key_name") }}</p>
                    </div>
                </div>

                <div v-if="detailJson !== '{}'" class="border-t border-border pt-3">
                    <p class="meta-xs mb-2">原始数据</p>
                    <pre
                        class="max-h-64 overflow-auto rounded-sm border border-border bg-bg p-3 font-mono text-[11px] leading-relaxed text-muted"
                    >{{ detailJson }}</pre>
                </div>
            </div>
        </AppDialog>
    </div>
</template>
