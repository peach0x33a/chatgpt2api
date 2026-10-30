<script setup lang="ts">
import { computed, ref, watch } from "vue";

import AppButton from "@/components/ui/AppButton.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import { updateAccount, type Account, type AccountStatus } from "@/lib/api";
import { useToast } from "@/lib/toast";

const props = defineProps<{ account: Account | null }>();
const emit = defineEmits<{
    "update:account": [Account | null];
    saved: [];
}>();

const toast = useToast();
const saving = ref(false);

const TYPE_OPTIONS = [
    { value: "free", label: "free" },
    { value: "Plus", label: "Plus" },
    { value: "Team", label: "Team" },
    { value: "Pro", label: "Pro" },
    { value: "Enterprise", label: "Enterprise" },
];

const STATUS_OPTIONS: Array<{ value: AccountStatus; label: string }> = [
    { value: "正常", label: "正常" },
    { value: "限流", label: "限流" },
    { value: "异常", label: "异常" },
    { value: "禁用", label: "禁用" },
];

/* 表单副本：编辑不影响列表，取消即丢弃。 */
const type = ref("");
const status = ref<AccountStatus>("正常");
const quota = ref(0);
const proxy = ref("");

const open = computed({
    get: () => props.account !== null,
    set: (value: boolean) => {
        if (!value) {
            emit("update:account", null);
        }
    },
});

watch(
    () => props.account,
    (account) => {
        if (!account) {
            return;
        }
        type.value = account.type || "free";
        status.value = account.status;
        quota.value = account.quota || 0;
        proxy.value = account.proxy || "";
    },
    { immediate: true },
);

const dirty = computed(() => {
    const account = props.account;
    if (!account) {
        return false;
    }
    return (
        type.value !== (account.type || "free") ||
        status.value !== account.status ||
        Number(quota.value) !== (account.quota || 0) ||
        proxy.value.trim() !== (account.proxy || "")
    );
});

async function save() {
    const account = props.account;
    if (!account) {
        return;
    }
    if (!dirty.value) {
        toast.info("没有改动");
        return;
    }
    saving.value = true;
    try {
        // 只提交真正变化的字段，避免覆盖掉并发刷新写入的值。
        const updates: Record<string, unknown> = {};
        if (type.value !== (account.type || "free")) {
            updates.type = type.value;
        }
        if (status.value !== account.status) {
            updates.status = status.value;
        }
        if (Number(quota.value) !== (account.quota || 0)) {
            updates.quota = Number(quota.value);
        }
        if (proxy.value.trim() !== (account.proxy || "")) {
            updates.proxy = proxy.value.trim();
        }
        await updateAccount(account.access_token, updates);
        toast.success("账号已更新");
        emit("saved");
        emit("update:account", null);
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
        saving.value = false;
    }
}
</script>

<template>
    <AppDialog
        v-model:open="open"
        title="编辑账号"
        :description="account?.email || account?.access_token.slice(0, 16) + '…'"
        size="sm"
    >
        <div class="space-y-5">
            <div class="space-y-1.5">
                <label class="meta-xs block">套餐类型</label>
                <AppSelect v-model="type" :options="TYPE_OPTIONS" width="100%" />
                <p class="meta-xs">影响可用模型与可选账号池</p>
            </div>

            <div class="space-y-1.5">
                <label class="meta-xs block">状态</label>
                <AppSelect v-model="status" :options="STATUS_OPTIONS" width="100%" />
                <p class="meta-xs">设为「禁用」后不再参与调度</p>
            </div>

            <div class="space-y-1.5">
                <label class="meta-xs block">额度</label>
                <AppInput v-model.number="quota" type="number" mono />
                <p class="meta-xs">手动校正剩余生图次数</p>
            </div>

            <div class="space-y-1.5">
                <label class="meta-xs block">专属代理</label>
                <AppInput v-model="proxy" placeholder="留空则使用全局代理" mono />
                <p class="meta-xs">该账号的请求优先走这条线路</p>
            </div>

            <div class="flex items-center justify-end gap-3 border-t border-border pt-4">
                <button class="bracket-button" @click="emit('update:account', null)">[取消]</button>
                <AppButton
                    variant="primary"
                    size="sm"
                    :loading="saving"
                    :disabled="!dirty"
                    @click="save"
                >
                    保存
                </AppButton>
            </div>
        </div>
    </AppDialog>
</template>
