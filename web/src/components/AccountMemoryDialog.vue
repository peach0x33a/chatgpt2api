<script setup lang="ts">
import { computed, ref, watch } from "vue";

import AppBadge from "@/components/ui/AppBadge.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import AppSwitch from "@/components/ui/AppSwitch.vue";
import { fetchAccountMemories, toggleAccountMemory, type Account, type AccountMemories } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatTime } from "@/lib/utils";

/*
 * 账号记忆查看。
 *
 * 记忆与自定义指令是账户级上下文：上游会把它们注入该账号的每一次对话，
 * 包括生图链路。所以「模型为什么这样理解我的提示词」这类问题，先看这里。
 */
const props = defineProps<{ account: Account | null }>();
const emit = defineEmits<{ "update:account": [Account | null] }>();

const toast = useToast();
const loading = ref(false);
const error = ref("");
const data = ref<AccountMemories | null>(null);
const toggling = ref(false);

const open = computed(() => props.account !== null);

/** 记忆开关（上游内部代号 m3m）。 */
const memoryEnabled = computed(() => data.value?.memory_enabled ?? false);
const memories = computed(() => data.value?.memories.memories ?? []);
const instructions = computed(() => data.value?.instructions);

/** 自定义指令里只有非空字段才值得展示。 */
const instructionFields = computed(() => {
    const value = instructions.value;
    if (!value) {
        return [];
    }
    const labels: Array<[keyof typeof value, string]> = [
        ["name_user_message", "称呼"],
        ["role_user_message", "身份"],
        ["about_user_message", "关于你"],
        ["about_model_message", "希望模型如何回应"],
        ["traits_model_message", "性格特征"],
        ["other_user_message", "其他要求"],
        ["personality_type_selection", "人格预设"],
    ];
    return labels
        .map(([key, label]) => ({ label, value: String(value[key] ?? "").trim() }))
        .filter((item) => item.value.length > 0);
});

const tokenUsage = computed(() => {
    const value = data.value?.memories;
    const used = value?.memory_num_tokens;
    const max = value?.memory_max_tokens;
    if (typeof used !== "number" || typeof max !== "number" || max <= 0) {
        return "";
    }
    return `${used} / ${max}`;
});

watch(
    () => props.account,
    async (account) => {
        data.value = null;
        error.value = "";
        if (!account) {
            return;
        }
        loading.value = true;
        try {
            data.value = await fetchAccountMemories(account.access_token);
        } catch (exc) {
            error.value = exc instanceof Error ? exc.message : "读取账号记忆失败";
        } finally {
            loading.value = false;
        }
    },
    { immediate: true },
);

function close() {
    emit("update:account", null);
}

async function toggleMemory(next: boolean) {
    if (!props.account || toggling.value) {
        return;
    }
    toggling.value = true;
    const previous = memoryEnabled.value;
    // 先本地翻转，失败再回滚，避免开关卡在旧状态上抖动。
    if (data.value) {
        data.value = { ...data.value, memory_enabled: next };
    }
    try {
        const result = await toggleAccountMemory(props.account.access_token, next);
        if (data.value) {
            data.value = { ...data.value, memory_enabled: result.memory_enabled };
        }
        toast.success(result.memory_enabled ? "已开启记忆" : "已关闭记忆");
    } catch (exc) {
        if (data.value) {
            data.value = { ...data.value, memory_enabled: previous };
        }
        toast.error(exc instanceof Error ? exc.message : "切换失败");
    } finally {
        toggling.value = false;
    }
}
</script>

<template>
    <AppDialog
        :open="open"
        title="账号记忆"
        :description="account?.email || account?.access_token.slice(0, 14) || ''"
        size="lg"
        @update:open="close"
    >
        <div v-if="loading" class="border border-dashed border-border py-14 text-center">
            <p class="meta">读取中</p>
        </div>

        <div v-else-if="error" class="border border-dashed border-border py-14 text-center">
            <p class="text-sm" :style="{ color: 'var(--color-error)' }">读取失败</p>
            <p class="meta-xs mt-2">{{ error }}</p>
        </div>

        <div v-else-if="data" class="space-y-5">
            <!-- 记忆开关 -->
            <section class="flex items-start justify-between gap-4 border-b border-border pb-4">
                <div>
                    <p class="text-sm text-ink">记忆功能</p>
                    <p class="meta-xs mt-1">
                        关闭后该账号不再读写记忆，可用容量从 5000000 降到 2000 token
                    </p>
                </div>
                <AppSwitch
                    :model-value="memoryEnabled"
                    :disabled="toggling"
                    @update:model-value="toggleMemory"
                />
            </section>

            <!-- 记忆条目 -->
            <section>
                <div class="mb-2 flex items-baseline gap-2">
                    <p class="meta">记忆条目</p>
                    <span class="meta-xs">{{ memories.length }} 条</span>
                    <span v-if="tokenUsage" class="meta-xs">· token {{ tokenUsage }}</span>
                </div>
                <div v-if="memories.length === 0" class="border border-dashed border-border py-8 text-center">
                    <p class="text-sm text-muted">这个账号没有保存记忆</p>
                </div>
                <ul v-else class="divide-y divide-border/60 border border-border">
                    <li v-for="item in memories" :key="item.id || item.content" class="px-3 py-2.5">
                        <p class="whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">
                            {{ item.content }}
                        </p>
                        <p v-if="item.updated_at || item.created_at" class="meta-xs mt-1">
                            {{ formatTime(String(item.updated_at || item.created_at)) }}
                        </p>
                    </li>
                </ul>
            </section>

            <!-- 自定义指令 -->
            <section class="border-t border-border pt-4">
                <div class="mb-2 flex items-center gap-2">
                    <p class="meta">自定义指令</p>
                    <AppBadge :tone="instructions?.enabled ? 'success' : 'neutral'">
                        {{ instructions?.enabled ? "已启用" : "未启用" }}
                    </AppBadge>
                </div>
                <div v-if="instructionFields.length === 0" class="border border-dashed border-border py-8 text-center">
                    <p class="text-sm text-muted">没有填写自定义指令</p>
                </div>
                <dl v-else class="space-y-3">
                    <div v-for="item in instructionFields" :key="item.label">
                        <dt class="meta-xs">{{ item.label }}</dt>
                        <dd class="mt-0.5 whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">
                            {{ item.value }}
                        </dd>
                    </div>
                </dl>
                <div v-if="instructions?.disabled_tools?.length" class="mt-3">
                    <p class="meta-xs">已禁用工具</p>
                    <div class="mt-1 flex flex-wrap gap-1.5">
                        <AppBadge
                            v-for="tool in instructions.disabled_tools"
                            :key="tool"
                            tone="warning"
                        >
                            {{ tool }}
                        </AppBadge>
                    </div>
                </div>
            </section>
        </div>
    </AppDialog>
</template>
