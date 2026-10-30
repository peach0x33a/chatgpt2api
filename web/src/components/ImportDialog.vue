<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Plus, X } from "lucide-vue-next";

import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import AppInput from "@/components/ui/AppInput.vue";
import {
    createImportSource,
    deleteImportSource,
    fetchImportCandidates,
    fetchImportJob,
    fetchImportSources,
    runImport,
    type ImportCandidate,
    type ImportCredentialMode,
    type ImportJob,
    type ImportSource,
    type ImportSourceKind,
} from "@/lib/api";
import { useToast } from "@/lib/toast";
import { sleep } from "@/lib/utils";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ "update:open": [boolean]; imported: [] }>();

const toast = useToast();

const sources = ref<ImportSource[]>([]);
const loadingSources = ref(false);
const activeSource = ref<ImportSource | null>(null);

const creating = ref(false);
const form = ref({
    kind: "cpa" as ImportSourceKind,
    name: "",
    base_url: "",
    secret_key: "",
    email: "",
    password: "",
    api_key: "",
    group_id: "",
});

const candidates = ref<ImportCandidate[]>([]);
const loadingCandidates = ref(false);
const selected = ref<Set<string>>(new Set());
const credentialMode = ref<ImportCredentialMode>("auto");
const job = ref<ImportJob | null>(null);
const running = ref(false);

const canCreate = computed(() => {
    if (!form.value.base_url.trim()) {
        return false;
    }
    if (form.value.kind === "cpa") {
        return Boolean(form.value.secret_key.trim());
    }
    return Boolean(
        form.value.api_key.trim() || (form.value.email.trim() && form.value.password.trim()),
    );
});

const progressPercent = computed(() => {
    if (!job.value || job.value.total === 0) {
        return 0;
    }
    return Math.round((job.value.completed / job.value.total) * 100);
});

const selectedCount = computed(() => selected.value.size);

watch(
    () => props.open,
    async (open) => {
        if (open) {
            await loadSources();
        } else {
            activeSource.value = null;
            candidates.value = [];
            selected.value = new Set();
            job.value = null;
            creating.value = false;
        }
    },
);

async function loadSources() {
    loadingSources.value = true;
    try {
        const result = await fetchImportSources();
        sources.value = result.sources;
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "加载来源失败");
    } finally {
        loadingSources.value = false;
    }
}

async function createSource() {
    if (!canCreate.value) {
        return;
    }
    try {
        const result = await createImportSource({
            kind: form.value.kind,
            name: form.value.name,
            base_url: form.value.base_url,
            ...(form.value.kind === "cpa"
                ? { secret_key: form.value.secret_key }
                : {
                      email: form.value.email,
                      password: form.value.password,
                      api_key: form.value.api_key,
                      group_id: form.value.group_id,
                  }),
        });
        sources.value = result.sources;
        creating.value = false;
        form.value = {
            kind: "cpa",
            name: "",
            base_url: "",
            secret_key: "",
            email: "",
            password: "",
            api_key: "",
            group_id: "",
        };
        toast.success("来源已添加");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "添加失败");
    }
}

async function removeSource(source: ImportSource) {
    try {
        const result = await deleteImportSource(source.kind, source.id);
        sources.value = result.sources;
        if (activeSource.value?.id === source.id) {
            activeSource.value = null;
            candidates.value = [];
            selected.value = new Set();
        }
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function selectSource(source: ImportSource) {
    activeSource.value = source;
    candidates.value = [];
    selected.value = new Set();
    job.value = null;
    loadingCandidates.value = true;
    try {
        const result = await fetchImportCandidates(source.kind, source.id);
        candidates.value = result.candidates;
        selected.value = new Set(result.candidates.map((item) => item.id));
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "读取远端列表失败");
    } finally {
        loadingCandidates.value = false;
    }
}

function toggle(id: string) {
    const next = new Set(selected.value);
    if (next.has(id)) {
        next.delete(id);
    } else {
        next.add(id);
    }
    selected.value = next;
}

function toggleAll() {
    selected.value =
        selected.value.size === candidates.value.length
            ? new Set()
            : new Set(candidates.value.map((item) => item.id));
}

async function startImport() {
    if (!activeSource.value || selected.value.size === 0) {
        return;
    }
    running.value = true;
    try {
        const created = await runImport(
            activeSource.value.kind,
            activeSource.value.id,
            [...selected.value],
            credentialMode.value,
        );
        job.value = created.job;

        while (job.value && (job.value.status === "pending" || job.value.status === "running")) {
            await sleep(1200);
            const latest = await fetchImportJob(job.value.job_id);
            job.value = latest.job;
        }

        if (job.value?.status === "completed") {
            toast.success(`导入完成：新增 ${job.value.added}，跳过 ${job.value.skipped}`);
            emit("imported");
        } else {
            toast.error("导入失败，查看下方明细");
        }
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "导入失败");
    } finally {
        running.value = false;
    }
}

const credentialOptions: Array<{ value: ImportCredentialMode; label: string; hint: string }> = [
    { value: "auto", label: "自动", hint: "优先 refresh_token，缺失时用 access_token" },
    { value: "refresh_token", label: "仅 refresh_token", hint: "由后端立即换取新的 access_token" },
    { value: "access_token", label: "仅 access_token", hint: "直接使用远端提供的 access_token" },
];
</script>

<template>
    <AppDialog
        :open="open"
        title="导入账号"
        description="统一管理 CPA 与 sub2api 来源，支持只提供 refresh_token"
        size="lg"
        @update:open="emit('update:open', $event)"
    >
        <div class="space-y-6">
            <!-- 来源 -->
            <section>
                <div class="mb-3 flex items-center justify-between">
                    <span class="meta">导入来源</span>
                    <button class="bracket-button" @click="creating = !creating">
                        {{ creating ? "[取消]" : "[添加来源]" }}
                    </button>
                </div>

                <div v-if="creating" class="mb-4 space-y-2 border border-dashed border-border p-4">
                    <div class="flex gap-1">
                        <button
                            v-for="kind in (['cpa', 'sub2api'] as ImportSourceKind[])"
                            :key="kind"
                            :class="[
                                'flex h-8 flex-1 items-center justify-center rounded-sm border px-3 font-mono text-xs transition-colors duration-150',
                                form.kind === kind
                                    ? 'border-ink bg-ink text-bg'
                                    : 'border-border bg-bg text-muted hover:text-ink',
                            ]"
                            @click="form.kind = kind"
                        >
                            {{ kind === "cpa" ? "CPA" : "sub2api" }}
                        </button>
                    </div>

                    <AppInput v-model="form.name" placeholder="备注名称（可选）" />
                    <AppInput v-model="form.base_url" placeholder="服务地址 https://…" mono />

                    <template v-if="form.kind === 'cpa'">
                        <AppInput v-model="form.secret_key" type="password" placeholder="secret_key" mono />
                    </template>
                    <template v-else>
                        <AppInput v-model="form.api_key" type="password" placeholder="API Key（可替代账号密码）" mono />
                        <div class="grid gap-2 sm:grid-cols-2">
                            <AppInput v-model="form.email" placeholder="邮箱" />
                            <AppInput v-model="form.password" type="password" placeholder="密码" />
                        </div>
                        <AppInput v-model="form.group_id" placeholder="分组 ID（可选）" mono />
                    </template>

                    <div class="flex justify-end pt-1">
                        <AppButton variant="primary" size="sm" :disabled="!canCreate" @click="createSource">
                            保存来源
                        </AppButton>
                    </div>
                </div>

                <div v-if="loadingSources" class="py-6 text-center">
                    <p class="meta">读取中</p>
                </div>
                <div
                    v-else-if="sources.length === 0"
                    class="border border-dashed border-border py-8 text-center"
                >
                    <p class="text-sm text-muted">还没有导入来源</p>
                </div>
                <div v-else class="divide-y divide-border border-y border-border">
                    <div
                        v-for="source in sources"
                        :key="`${source.kind}:${source.id}`"
                        :class="[
                            'group flex cursor-pointer items-center gap-3 border-l-2 py-2.5 pl-3 pr-2 transition-colors duration-150',
                            activeSource?.id === source.id
                                ? 'border-l-ink bg-border/20'
                                : 'border-l-transparent hover:bg-border/20',
                        ]"
                        @click="selectSource(source)"
                    >
                        <div class="min-w-0 flex-1">
                            <p class="truncate text-sm text-ink">{{ source.name || source.base_url }}</p>
                            <p class="meta-xs truncate">{{ source.kind }} · {{ source.base_url }}</p>
                        </div>
                        <AppBadge :tone="source.has_secret ? 'success' : 'warning'">
                            {{ source.has_secret ? "已配置" : "缺凭据" }}
                        </AppBadge>
                        <button
                            class="opacity-0 transition-opacity duration-150 group-hover:opacity-60 hover:!opacity-100"
                            aria-label="删除来源"
                            @click.stop="removeSource(source)"
                        >
                            <X class="size-3.5" />
                        </button>
                    </div>
                </div>
            </section>

            <!-- 候选 -->
            <section v-if="activeSource">
                <div class="mb-3 flex items-center justify-between">
                    <span class="meta">
                        可导入 · {{ selectedCount }}/{{ candidates.length }}
                    </span>
                    <button
                        v-if="candidates.length > 0"
                        class="bracket-button"
                        @click="toggleAll"
                    >
                        {{ selected.size === candidates.length ? "[取消全选]" : "[全选]" }}
                    </button>
                </div>

                <div v-if="loadingCandidates" class="py-6 text-center">
                    <p class="meta">读取远端列表</p>
                </div>
                <div
                    v-else-if="candidates.length === 0"
                    class="border border-dashed border-border py-8 text-center"
                >
                    <p class="text-sm text-muted">远端没有可导入的账号</p>
                </div>
                <div v-else class="max-h-52 overflow-y-auto border-y border-border">
                    <label
                        v-for="item in candidates"
                        :key="item.id"
                        class="flex cursor-pointer items-center gap-2.5 border-b border-border/50 px-1 py-2 last:border-0 transition-colors duration-150 hover:bg-border/20"
                    >
                        <input
                            type="checkbox"
                            :checked="selected.has(item.id)"
                            class="size-3.5 accent-ink"
                            @change="toggle(item.id)"
                        />
                        <span class="min-w-0 flex-1 truncate text-sm text-ink">
                            {{ item.email || item.name }}
                        </span>
                        <AppBadge v-if="item.plan_type" tone="accent">{{ item.plan_type }}</AppBadge>
                        <AppBadge v-if="item.has_refresh_token" tone="success">RT</AppBadge>
                    </label>
                </div>
            </section>

            <!-- 凭证模式 -->
            <section v-if="activeSource && candidates.length > 0">
                <p class="meta mb-3">导入方式</p>
                <div class="space-y-1.5">
                    <label
                        v-for="option in credentialOptions"
                        :key="option.value"
                        :class="[
                            'flex cursor-pointer items-start gap-2.5 border border-border p-2.5 transition-colors duration-150',
                            credentialMode === option.value
                                ? 'border-ink bg-border/20'
                                : 'hover:bg-border/10',
                        ]"
                    >
                        <input
                            type="radio"
                            :value="option.value"
                            :checked="credentialMode === option.value"
                            class="mt-1 size-3.5 accent-ink"
                            @change="credentialMode = option.value"
                        />
                        <div class="min-w-0">
                            <p class="text-sm text-ink">{{ option.label }}</p>
                            <p class="meta-xs mt-0.5">{{ option.hint }}</p>
                        </div>
                    </label>
                </div>
            </section>

            <!-- 进度 -->
            <section v-if="job" class="space-y-3">
                <div class="flex items-baseline justify-between">
                    <span class="meta">
                        {{ job.status === "completed" ? "导入完成" : job.status === "failed" ? "导入失败" : "导入中" }}
                    </span>
                    <span class="meta-xs">{{ job.completed }} / {{ job.total }}</span>
                </div>
                <div class="h-px overflow-hidden bg-border">
                    <div
                        class="h-full bg-ink transition-[width] duration-300"
                        :style="{ width: `${progressPercent}%` }"
                    />
                </div>
                <div v-if="job.status === 'completed'" class="flex flex-wrap gap-2">
                    <AppBadge tone="success">新增 {{ job.added }}</AppBadge>
                    <AppBadge tone="neutral">跳过 {{ job.skipped }}</AppBadge>
                    <AppBadge v-if="job.refreshed" tone="accent">刷新 {{ job.refreshed }}</AppBadge>
                    <AppBadge v-if="job.failed" tone="danger">失败 {{ job.failed }}</AppBadge>
                </div>
                <div v-if="job.errors.length > 0" class="max-h-32 space-y-1 overflow-y-auto">
                    <p
                        v-for="(error, index) in job.errors"
                        :key="index"
                        class="text-xs leading-relaxed"
                        :style="{ color: 'var(--color-error)' }"
                    >
                        <span class="font-mono">{{ error.name }}</span> — {{ error.error }}
                    </p>
                </div>
            </section>

            <div class="flex items-center justify-end gap-3 border-t border-border pt-4">
                <button class="bracket-button" @click="emit('update:open', false)">[关闭]</button>
                <AppButton
                    variant="primary"
                    size="sm"
                    :disabled="!activeSource || selectedCount === 0 || running"
                    :loading="running"
                    @click="startImport"
                >
                    开始导入（{{ selectedCount }}）
                </AppButton>
            </div>
        </div>
    </AppDialog>
</template>
