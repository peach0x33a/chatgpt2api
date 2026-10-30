<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Pencil, Trash2 } from "lucide-vue-next";

import AccountEditDialog from "@/components/AccountEditDialog.vue";
import ImportDialog from "@/components/ImportDialog.vue";
import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import {
    deleteAccounts,
    fetchAccounts,
    fetchReLoginProgress,
    fetchRefreshProgress,
    reLoginAccounts,
    refreshAccounts,
    type Account,
    type RefreshProgressResponse,
} from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatTime, sleep } from "@/lib/utils";

const toast = useToast();

const STATUS_OPTIONS = [
    { value: "", label: "全部状态" },
    { value: "正常", label: "正常" },
    { value: "限流", label: "限流" },
    { value: "异常", label: "异常" },
    { value: "禁用", label: "禁用" },
];

const accounts = ref<Account[]>([]);
const loading = ref(false);
/** 加载失败原因。与「空列表」区分开，避免把请求失败显示成没有账号。 */
const loadError = ref("");
const keyword = ref("");
const statusFilter = ref("");
const selected = ref<Set<string>>(new Set());
const importOpen = ref(false);
/** 正在编辑的账号；null 表示对话框关闭。 */
const editingAccount = ref<Account | null>(null);

const progress = ref<RefreshProgressResponse | null>(null);
const progressLabel = ref("");

const filtered = computed(() => {
    const text = keyword.value.trim().toLowerCase();
    return accounts.value.filter((item) => {
        if (statusFilter.value && item.status !== statusFilter.value) {
            return false;
        }
        if (!text) {
            return true;
        }
        return (
            (item.email || "").toLowerCase().includes(text) ||
            (item.type || "").toLowerCase().includes(text) ||
            item.access_token.toLowerCase().includes(text)
        );
    });
});

const stats = computed(() => ({
    total: accounts.value.length,
    normal: accounts.value.filter((item) => item.status === "正常").length,
    limited: accounts.value.filter((item) => item.status === "限流").length,
    quota: accounts.value.reduce((sum, item) => sum + (item.quota || 0), 0),
}));

const allSelected = computed(
    () => filtered.value.length > 0 && filtered.value.every((item) => selected.value.has(item.access_token)),
);

onMounted(load);

async function load() {
    loading.value = true;
    loadError.value = "";
    try {
        const result = await fetchAccounts();
        accounts.value = result.items;
    } catch (error) {
        loadError.value = error instanceof Error ? error.message : "加载失败";
    } finally {
        loading.value = false;
    }
}

function toggle(accessToken: string) {
    const next = new Set(selected.value);
    if (next.has(accessToken)) {
        next.delete(accessToken);
    } else {
        next.add(accessToken);
    }
    selected.value = next;
}

function toggleAll() {
    selected.value = allSelected.value
        ? new Set()
        : new Set(filtered.value.map((item) => item.access_token));
}

function statusTone(status: string) {
    switch (status) {
        case "正常":
            return "success";
        case "限流":
            return "warning";
        case "异常":
            return "danger";
        default:
            return "neutral";
    }
}

/** 凭据来源：codex / web。与套餐拼成 "codex:free" 这类标签显示。 */
function sourceLabel(source?: string | null) {
    return (source || "web").trim().toLowerCase();
}

async function doRefresh() {
    const targets = [...selected.value];
    if (targets.length === 0) {
        toast.info("请先选择账号");
        return;
    }
    progressLabel.value = "刷新额度";
    try {
        const { progress_id } = await refreshAccounts(targets);
        await pollProgress(progress_id, fetchRefreshProgress);
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "刷新失败");
    } finally {
        progress.value = null;
    }
}

async function doReLogin() {
    const targets = [...selected.value];
    if (targets.length === 0) {
        toast.info("请先选择账号");
        return;
    }
    progressLabel.value = "重新登录";
    try {
        const { progress_id } = await reLoginAccounts(targets);
        await pollProgress(progress_id, fetchReLoginProgress);
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "重新登录失败");
    } finally {
        progress.value = null;
    }
}

async function pollProgress(
    progressId: string,
    fetcher: (id: string) => Promise<RefreshProgressResponse>,
) {
    for (let attempt = 0; attempt < 300; attempt += 1) {
        const data = await fetcher(progressId);
        progress.value = data;
        if (data.done) {
            if (data.error) {
                toast.error(data.error);
            } else {
                toast.success(`${progressLabel.value}完成`);
            }
            return;
        }
        await sleep(800);
    }
}

async function doDelete() {
    const targets = [...selected.value];
    if (targets.length === 0) {
        toast.info("请先选择账号");
        return;
    }
    if (!window.confirm(`确定删除 ${targets.length} 个账号？`)) {
        return;
    }
    try {
        const result = await deleteAccounts(targets);
        selected.value = new Set();
        toast.success(`已删除 ${result.removed ?? targets.length} 个`);
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}
</script>

<template>
    <div class="space-y-8">
        <!-- 标题区 -->
        <div class="flex flex-wrap items-baseline justify-between gap-4 border-b border-border pb-4">
            <div>
                <h1 class="text-2xl font-bold text-ink" style="font-family: var(--font-prose)">
                    号池
                </h1>
            </div>
            <AppButton variant="primary" size="sm" @click="importOpen = true">导入账号</AppButton>
        </div>

        <!--
            统计不做成四张卡：用一行等宽数字 + 竖线分隔，
            密度更低、更像「读数」而不是仪表盘。
        -->
        <!--
            统计与筛选同处一行：左侧是读数，右侧是操作。
            两者共用一条虚线边界，避免两行各自成段造成纵向割裂。
        -->
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-dashed border-border pb-3">
            <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">总数</span>
                    <span class="text-xl font-bold tabular-nums text-ink" style="font-family: var(--font-mono)">
                        {{ loadError ? "—" : stats.total }}
                    </span>
                </div>
                <div class="h-5 w-px bg-border" />
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">正常</span>
                    <span
                        class="text-xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400"
                        style="font-family: var(--font-mono)"
                    >
                        {{ loadError ? "—" : stats.normal }}
                    </span>
                </div>
                <div class="h-5 w-px bg-border" />
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">限流</span>
                    <span
                        class="text-xl font-bold tabular-nums"
                        :style="{ color: 'var(--color-warning)', fontFamily: 'var(--font-mono)' }"
                    >
                        {{ loadError ? "—" : stats.limited }}
                    </span>
                </div>
                <div class="h-5 w-px bg-border" />
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">额度</span>
                    <span class="text-xl font-bold tabular-nums text-ink" style="font-family: var(--font-mono)">
                        {{ loadError ? "—" : stats.quota }}
                    </span>
                </div>
            </div>

            <div class="ml-auto flex flex-wrap items-center gap-2">
                <div
                    v-if="selected.size > 0"
                    class="mr-1 flex items-center gap-3 border-r border-border pr-3"
                >
                    <span class="meta-xs">已选 {{ selected.size }}</span>
                    <button class="bracket-button" @click="doRefresh">[刷新额度]</button>
                    <button class="bracket-button" @click="doReLogin">[重新登录]</button>
                    <button class="bracket-button" @click="doDelete">
                        <Trash2 class="mr-0.5 inline size-3" />[删除]
                    </button>
                </div>

                <input
                    v-model="keyword"
                    placeholder="搜索邮箱或类型"
                    class="h-8 w-52 rounded-sm border border-border bg-bg px-3 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-muted/70 focus:border-ink"
                />
                <AppSelect v-model="statusFilter" :options="STATUS_OPTIONS" size="sm" width="6.5rem" />
                <button class="bracket-button" :disabled="loading" @click="load">[刷新列表]</button>
            </div>
        </div>

        <!-- 进度 -->
        <div v-if="progress" class="space-y-2">
            <div class="flex items-baseline justify-between">
                <span class="meta">{{ progressLabel }}</span>
                <span class="meta-xs">{{ progress.processed }} / {{ progress.total }}</span>
            </div>
            <div class="h-px overflow-hidden bg-border">
                <div
                    class="h-full bg-ink transition-[width] duration-300"
                    :style="{
                        width: progress.total
                            ? `${Math.round((progress.processed / progress.total) * 100)}%`
                            : '40%',
                    }"
                />
            </div>
        </div>

        <!-- 表格：纸色表头 + 50% 发丝线分行，无卡片容器 -->
        <div>
            <div v-if="loading" class="py-16 text-center">
                <p class="meta">加载中</p>
            </div>
            <div
                v-else-if="loadError"
                class="border border-dashed border-border py-16 text-center"
            >
                <p class="text-sm" :style="{ color: 'var(--color-error)' }">账号列表读取失败</p>
                <p class="meta-xs mt-2">{{ loadError }}</p>
                <button class="bracket-button mt-4" @click="load">[重试]</button>
            </div>
            <div v-else-if="filtered.length === 0" class="border border-dashed border-border py-16 text-center">
                <p class="text-sm text-muted">
                    {{ accounts.length === 0 ? "号池为空，先导入账号" : "没有匹配的账号" }}
                </p>
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
                            <th class="py-2 font-normal"><span class="meta">账号</span></th>
                            <th class="py-2 font-normal"><span class="meta">类型</span></th>
                            <th class="py-2 font-normal"><span class="meta">状态</span></th>
                            <th class="w-20 py-2 pr-6 text-right font-normal"><span class="meta">额度</span></th>
                            <th class="w-24 py-2 pr-6 text-right font-normal"><span class="meta">成功/失败</span></th>
                            <th class="w-24 py-2 font-normal"><span class="meta">最近使用</span></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="item in filtered"
                            :key="item.access_token"
                            class="group/row border-b border-border/50 transition-colors duration-150 hover:bg-border/20"
                        >
                            <td class="py-2.5">
                                <input
                                    type="checkbox"
                                    :checked="selected.has(item.access_token)"
                                    class="size-3.5 accent-ink"
                                    @change="toggle(item.access_token)"
                                />
                            </td>
                            <td class="max-w-56 py-2.5 pr-3">
                                <p class="truncate text-ink">{{ item.email || "未知邮箱" }}</p>
                                <p class="meta-xs truncate">
                                    {{ item.access_token.slice(0, 14) }}…
                                </p>
                            </td>
                            <td class="py-2.5 pr-3">
                                <AppBadge
                                    :tone="item.source_type === 'codex' ? 'accent' : 'neutral'"
                                >
                                    {{ sourceLabel(item.source_type) }}:{{ item.type }}
                                </AppBadge>
                            </td>
                            <td class="py-2.5 pr-3">
                                <AppBadge :tone="statusTone(item.status)">{{ item.status }}</AppBadge>
                            </td>
                            <td
                                class="py-2.5 pr-6 text-right tabular-nums text-ink"
                                style="font-family: var(--font-mono); font-size: 0.8125rem"
                            >
                                {{ item.quota }}
                            </td>
                            <td
                                class="py-2.5 pr-6 text-right tabular-nums"
                                style="font-family: var(--font-mono); font-size: 0.8125rem"
                            >
                                <span class="text-emerald-600 dark:text-emerald-400">{{ item.success }}</span>
                                <span class="text-muted">/</span>
                                <span class="text-muted">{{ item.fail }}</span>
                            </td>
                            <td class="py-2.5">
                                <div class="flex items-center gap-2">
                                    <span class="meta-xs">{{ formatTime(item.last_used_at) }}</span>
                                    <button
                                        class="opacity-0 transition-opacity duration-150 hover:opacity-100 group-hover/row:opacity-60"
                                        aria-label="编辑账号"
                                        @click="editingAccount = item"
                                    >
                                        <Pencil class="size-3" />
                                    </button>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <ImportDialog v-model:open="importOpen" @imported="load" />
        <AccountEditDialog
            v-model:account="editingAccount"
            @saved="load"
        />
    </div>
</template>
