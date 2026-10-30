<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Download, Trash2 } from "lucide-vue-next";

import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import {
    deleteBackup,
    fetchBackupDetail,
    fetchBackups,
    getBackupDownloadUrl,
    runBackupNow,
    type BackupDetail,
    type BackupItem,
    type BackupState,
} from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatBytes, formatTime } from "@/lib/utils";

const toast = useToast();

const items = ref<BackupItem[]>([]);
const state = ref<BackupState | null>(null);
const loading = ref(false);
const running = ref(false);
const loadError = ref("");

/* 详情 */
const detailOpen = ref(false);
const detail = ref<BackupDetail | null>(null);
const detailLoading = ref(false);

const hasItems = computed(() => items.value.length > 0);

onMounted(load);

async function load() {
    loading.value = true;
    loadError.value = "";
    try {
        const data = await fetchBackups();
        items.value = data.items;
        state.value = data.state;
    } catch (error) {
        // 未配置对象存储时这里是正常报错，按失败态展示而不是空列表。
        loadError.value = error instanceof Error ? error.message : "读取备份列表失败";
    } finally {
        loading.value = false;
    }
}

async function runNow() {
    running.value = true;
    try {
        const data = await runBackupNow();
        toast.success(`备份完成：${formatBytes(data.result.size)}`);
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "备份失败");
    } finally {
        running.value = false;
    }
}

async function remove(item: BackupItem) {
    if (!window.confirm(`删除备份 ${item.name}？`)) {
        return;
    }
    try {
        await deleteBackup(item.key);
        toast.success("已删除");
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function openDetail(item: BackupItem) {
    detailOpen.value = true;
    detailLoading.value = true;
    detail.value = null;
    try {
        const data = await fetchBackupDetail(item.key);
        detail.value = data.item;
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "读取详情失败");
        detailOpen.value = false;
    } finally {
        detailLoading.value = false;
    }
}

function download(item: BackupItem) {
    window.open(getBackupDownloadUrl(item.key), "_blank", "noopener");
}
</script>

<template>
    <section class="space-y-5">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-dashed border-border pb-3">
            <div class="flex items-baseline gap-2">
                <span class="meta-xs">已有备份</span>
                <span
                    class="text-xl font-bold tabular-nums text-ink"
                    style="font-family: var(--font-mono)"
                >
                    {{ loadError ? "—" : items.length }}
                </span>
            </div>
            <div class="flex items-center gap-3">
                <button class="bracket-button" :disabled="loading" @click="load">[刷新]</button>
                <AppButton
                    variant="secondary"
                    size="sm"
                    :loading="running"
                    :disabled="running"
                    @click="runNow"
                >
                    立即备份
                </AppButton>
            </div>
        </div>

        <!-- 上次执行状态 -->
        <div v-if="state && (state.last_started_at || state.last_error)" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
                <p class="meta-xs">上次开始</p>
                <p class="mt-0.5 text-sm text-ink">{{ formatTime(state.last_started_at) }}</p>
            </div>
            <div>
                <p class="meta-xs">上次完成</p>
                <p class="mt-0.5 text-sm text-ink">{{ formatTime(state.last_finished_at) }}</p>
            </div>
            <div>
                <p class="meta-xs">结果</p>
                <p class="mt-0.5">
                    <AppBadge
                        :tone="
                            state.last_status === 'success'
                                ? 'success'
                                : state.last_status
                                  ? 'danger'
                                  : 'neutral'
                        "
                    >
                        {{ state.last_status || "-" }}
                    </AppBadge>
                </p>
            </div>
            <div class="min-w-0">
                <p class="meta-xs">错误</p>
                <p class="mt-0.5 truncate text-sm" :style="{ color: state.last_error ? 'var(--color-error)' : undefined }">
                    {{ state.last_error || "-" }}
                </p>
            </div>
        </div>

        <!-- 列表 -->
        <div v-if="loading" class="border border-dashed border-border py-12 text-center">
            <p class="meta">读取中</p>
        </div>
        <div v-else-if="loadError" class="border border-dashed border-border py-12 text-center">
            <p class="text-sm" :style="{ color: 'var(--color-error)' }">备份列表读取失败</p>
            <p class="meta-xs mt-2">{{ loadError }}</p>
            <button class="bracket-button mt-4" @click="load">[重试]</button>
        </div>
        <div v-else-if="!hasItems" class="border border-dashed border-border py-12 text-center">
            <p class="text-sm text-muted">还没有备份</p>
            <p class="meta-xs mt-2">填好配置后点「立即备份」生成第一份</p>
        </div>
        <div v-else class="divide-y divide-border">
            <div
                v-for="item in items"
                :key="item.key"
                class="group flex items-center gap-3 py-2.5"
            >
                <button class="min-w-0 flex-1 text-left" @click="openDetail(item)">
                    <p class="truncate font-mono text-xs text-ink">{{ item.name }}</p>
                    <p class="meta-xs mt-0.5">
                        {{ formatTime(item.updated_at) }} · {{ formatBytes(item.size) }}
                        <span v-if="item.encrypted"> · 已加密</span>
                    </p>
                </button>
                <button
                    class="opacity-0 transition-opacity duration-150 group-hover:opacity-60 hover:!opacity-100"
                    aria-label="下载"
                    @click="download(item)"
                >
                    <Download class="size-3.5" />
                </button>
                <button
                    class="opacity-0 transition-opacity duration-150 group-hover:opacity-60 hover:!opacity-100"
                    aria-label="删除"
                    @click="remove(item)"
                >
                    <Trash2 class="size-3.5" />
                </button>
            </div>
        </div>

        <!-- 详情 -->
        <AppDialog
            v-model:open="detailOpen"
            :title="detail?.name || '备份详情'"
            size="lg"
        >
            <div v-if="detailLoading" class="py-8 text-center">
                <p class="meta">读取中</p>
            </div>
            <div v-else-if="detail" class="space-y-5">
                <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div>
                        <p class="meta-xs">创建时间</p>
                        <p class="mt-0.5 text-sm text-ink">{{ formatTime(detail.created_at) }}</p>
                    </div>
                    <div>
                        <p class="meta-xs">触发方式</p>
                        <p class="mt-0.5 text-sm text-ink">{{ detail.trigger || "-" }}</p>
                    </div>
                    <div>
                        <p class="meta-xs">版本</p>
                        <p class="mt-0.5 font-mono text-xs text-ink">{{ detail.app_version || "-" }}</p>
                    </div>
                    <div>
                        <p class="meta-xs">加密</p>
                        <p class="mt-0.5">
                            <AppBadge :tone="detail.encrypted ? 'accent' : 'neutral'">
                                {{ detail.encrypted ? "是" : "否" }}
                            </AppBadge>
                        </p>
                    </div>
                </div>

                <div v-if="detail.files.length > 0" class="border-t border-border pt-3">
                    <p class="meta-xs mb-2">包含文件</p>
                    <div class="space-y-1">
                        <div
                            v-for="file in detail.files"
                            :key="file.name"
                            class="flex items-center justify-between gap-3 text-xs"
                        >
                            <span class="truncate font-mono text-ink">{{ file.name }}</span>
                            <span class="shrink-0 meta-xs">
                                {{ file.exists ? formatBytes(file.size) : "缺失" }}
                            </span>
                        </div>
                    </div>
                </div>

                <div v-if="detail.snapshots.length > 0" class="border-t border-border pt-3">
                    <p class="meta-xs mb-2">快照</p>
                    <div class="flex flex-wrap gap-2">
                        <AppBadge v-for="snap in detail.snapshots" :key="snap.name" tone="neutral">
                            {{ snap.name }} · {{ snap.count }}
                        </AppBadge>
                    </div>
                </div>
            </div>
        </AppDialog>
    </section>
</template>
