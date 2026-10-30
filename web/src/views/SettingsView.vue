<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import BackupManager from "@/components/settings/BackupManager.vue";
import SettingRow from "@/components/settings/SettingRow.vue";
import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import AppSwitch from "@/components/ui/AppSwitch.vue";
import {
    createUserKey,
    deleteUserKey,
    fetchSettingsConfig,
    fetchUserKeys,
    syncImageStorage,
    testBackupConnection,
    testImageStorageConnection,
    testProxy,
    updateSettingsConfig,
    updateUserKey,
    type SettingsConfig,
    type UserKey,
} from "@/lib/api";
import { useToast } from "@/lib/toast";
import { copyText, formatTime } from "@/lib/utils";

const toast = useToast();

type Tab = "general" | "image" | "proxy" | "keys" | "backup";

const TABS: Array<{ value: Tab; label: string }> = [
    { value: "general", label: "通用" },
    { value: "image", label: "生图" },
    { value: "proxy", label: "代理" },
    { value: "keys", label: "密钥" },
    { value: "backup", label: "备份" },
];

const tab = ref<Tab>("general");
const loading = ref(true);
const saving = ref(false);
const config = ref<SettingsConfig | null>(null);

/* 密钥 */
const keys = ref<UserKey[]>([]);
const newKeyName = ref("");
const createdKey = ref("");

/* 备份 */
const backupBusy = ref(false);
const backupTest = ref<{ ok: boolean; status: number } | null>(null);

/* 代理测试 */
const proxyTesting = ref(false);
const proxyResult = ref<{ ok: boolean; latency_ms: number; status: number; error: string | null } | null>(null);

/* 图片存储测试 */
const storageTesting = ref(false);
const storageSyncing = ref(false);

const sensitiveText = ref("");

const logLevels = ["debug", "info", "warning", "error"];

const EFFORT_OPTIONS = [
    { value: "auto", label: "自动" },
    { value: "standard", label: "标准" },
    { value: "extended", label: "扩展" },
    { value: "max", label: "最大" },
];

const ACCOUNT_SCHEDULE_OPTIONS = [
    { value: "round_robin", label: "轮询" },
    { value: "sequential", label: "顺序" },
];

const STORAGE_MODE_OPTIONS = [
    { value: "local", label: "仅本地" },
    { value: "webdav", label: "仅 WebDAV" },
    { value: "both", label: "两者都存" },
];

const EGRESS_OPTIONS = [
    { value: "direct", label: "直连" },
    { value: "single_proxy", label: "单代理" },
];

const CLEARANCE_OPTIONS = [
    { value: "none", label: "不处理" },
    { value: "manual", label: "手动填写" },
    { value: "flaresolverr", label: "FlareSolverr" },
];

const backup = computed(() => config.value?.backup);

/** 备份内容清单：显式列出，避免动态索引带来的类型问题。 */
const INCLUDE_LABELS: Record<string, string> = {
    config: "配置",
    cpa: "CPA 配置",
    sub2api: "sub2api 配置",
    logs: "日志",
    image_tasks: "生图任务",
    accounts_snapshot: "账号快照",
    auth_keys_snapshot: "密钥快照",
    images: "图片文件",
};

const includeEntries = computed(() => {
    const include = config.value?.backup?.include;
    if (!include) {
        return [];
    }
    return Object.keys(include).map((key) => ({
        key,
        label: INCLUDE_LABELS[key] || key,
        get value() {
            return Boolean(include[key as keyof typeof include]);
        },
        set value(next: boolean) {
            (include as Record<string, boolean>)[key] = next;
        },
    }));
});

onMounted(async () => {
    await Promise.all([load(), loadKeys()]);
});

async function load() {
    loading.value = true;
    try {
        const data = await fetchSettingsConfig();
        config.value = data.config;
        sensitiveText.value = (data.config.sensitive_words || []).join("\n");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "加载设置失败");
    } finally {
        loading.value = false;
    }
}

async function loadKeys() {
    try {
        const data = await fetchUserKeys();
        keys.value = data.items;
    } catch {
        keys.value = [];
    }
}

async function save() {
    if (!config.value) {
        return;
    }
    saving.value = true;
    try {
        // 敏感词从多行文本还原成数组。
        config.value.sensitive_words = sensitiveText.value
            .split(/\n+/)
            .map((word) => word.trim())
            .filter(Boolean);
        const data = await updateSettingsConfig(config.value);
        config.value = data.config;
        toast.success("设置已保存");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
        saving.value = false;
    }
}

async function doTestProxy() {
    const url = String(config.value?.proxy || "").trim();
    if (!url) {
        toast.error("请先填写代理地址");
        return;
    }
    proxyTesting.value = true;
    proxyResult.value = null;
    try {
        const data = await testProxy(url);
        proxyResult.value = data.result;
        if (data.result.ok) {
            toast.success(`代理可用（${data.result.latency_ms}ms）`);
        } else {
            toast.error(`代理不可用：${data.result.error || "未知错误"}`);
        }
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "测试失败");
    } finally {
        proxyTesting.value = false;
    }
}

async function doTestStorage() {
    storageTesting.value = true;
    try {
        const data = await testImageStorageConnection();
        if (data.result.ok) {
            toast.success("存储连接正常");
        } else {
            toast.error(`存储连接失败：${data.result.error || "未知错误"}`);
        }
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "测试失败");
    } finally {
        storageTesting.value = false;
    }
}

async function doSyncStorage() {
    storageSyncing.value = true;
    try {
        const data = await syncImageStorage();
        toast.success(
            `已上传 ${data.result.uploaded}，跳过 ${data.result.skipped}，失败 ${data.result.failed}`,
        );
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "同步失败");
    } finally {
        storageSyncing.value = false;
    }
}

async function doTestBackup() {
    backupBusy.value = true;
    backupTest.value = null;
    try {
        const data = await testBackupConnection();
        backupTest.value = data.result;
        toast.success("备份连接正常");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "测试失败");
    } finally {
        backupBusy.value = false;
    }
}

async function createKey() {
    const name = newKeyName.value.trim();
    if (!name) {
        toast.error("请输入密钥名称");
        return;
    }
    try {
        const data = await createUserKey(name);
        keys.value = data.items;
        createdKey.value = data.key;
        newKeyName.value = "";
        toast.success("密钥已创建，请立即复制");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "创建失败");
    }
}

async function toggleKey(key: UserKey) {
    try {
        const data = await updateUserKey(key.id, { enabled: !key.enabled });
        keys.value = data.items;
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "更新失败");
    }
}

async function removeKey(key: UserKey) {
    if (!window.confirm(`删除密钥「${key.name}」？`)) {
        return;
    }
    try {
        const data = await deleteUserKey(key.id);
        keys.value = data.items;
        toast.success("已删除");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function copy(value: string) {
    if (await copyText(value)) {
        toast.success("已复制");
    } else {
        toast.error("复制失败");
    }
}

function toggleLogLevel(level: string) {
    if (!config.value) {
        return;
    }
    const current = new Set(config.value.log_levels || []);
    if (current.has(level)) {
        current.delete(level);
    } else {
        current.add(level);
    }
    config.value.log_levels = [...current];
}
</script>

<template>
    <div class="space-y-6">
        <div class="flex flex-wrap items-baseline justify-between gap-4 border-b border-border pb-4">
            <div>
                <h1 class="text-2xl font-bold text-ink" style="font-family: var(--font-prose)">
                    设置
                </h1>
            </div>
            <AppButton variant="primary" size="sm" :loading="saving" :disabled="!config" @click="save">
                保存全部
            </AppButton>
        </div>

        <!-- 标签切换：与日志页同一套墨色反转 -->
        <div class="flex flex-wrap gap-1">
            <button
                v-for="item in TABS"
                :key="item.value"
                :class="[
                    'flex h-8 items-center rounded-sm border px-3 font-mono text-xs transition-colors duration-150',
                    tab === item.value
                        ? 'border-ink bg-ink text-bg'
                        : 'border-border bg-bg text-muted hover:text-ink',
                ]"
                @click="tab = item.value"
            >
                {{ item.label }}
            </button>
        </div>

        <div v-if="loading" class="border border-dashed border-border py-16 text-center">
            <p class="meta">加载中</p>
        </div>

        <template v-else-if="config">
            <!-- ── 通用 ── -->
            <section v-if="tab === 'general'" class="space-y-6">
                <div class="space-y-5 border-b border-dashed border-border pb-6">
                    <p class="meta">对外地址</p>
                    <SettingRow label="公开访问地址" hint="写进图片 URL 的前缀；留空则按请求头推导">
                        <AppInput v-model="config.base_url" placeholder="https://api.example.com" mono />
                    </SettingRow>
                </div>

                <div class="space-y-5 border-b border-dashed border-border pb-6">
                    <p class="meta">上游模型</p>
                    <SettingRow label="默认上游模型" hint="生图请求实际使用的 ChatGPT 模型">
                        <AppInput v-model="config.default_upstream_model_name" placeholder="gpt-5-5" mono />
                    </SettingRow>
                    <SettingRow label="默认思考强度" hint="影响上游推理深度与耗时">
                        <AppSelect
                            v-model="config.default_thinking_effort as string"
                            :options="EFFORT_OPTIONS"
                            width="10rem"
                        />
                    </SettingRow>
                    <SettingRow label="全局系统提示词" hint="会前置到每次对话，留空表示不注入" block>
                        <textarea
                            v-model="config.global_system_prompt"
                            rows="3"
                            class="w-full resize-none rounded-sm border border-border bg-bg px-3 py-2 text-sm text-ink outline-none placeholder:text-muted/70 focus:border-ink"
                            placeholder="可选"
                        />
                    </SettingRow>
                </div>

                <div class="space-y-5 border-b border-dashed border-border pb-6">
                    <p class="meta">内容过滤</p>
                    <SettingRow label="敏感词" hint="每行一个；命中即拒绝，不请求上游" block>
                        <textarea
                            v-model="sensitiveText"
                            rows="4"
                            class="w-full resize-none rounded-sm border border-border bg-bg px-3 py-2 font-mono text-xs text-ink outline-none placeholder:text-muted/70 focus:border-ink"
                            placeholder="每行一个词"
                        />
                    </SettingRow>

                    <SettingRow label="启用 AI 审核" hint="用外部模型判断请求是否合规">
                        <AppSwitch v-model="config.ai_review!.enabled!" />
                    </SettingRow>
                    <template v-if="config.ai_review?.enabled">
                        <AppInput v-model="config.ai_review!.base_url!" placeholder="审核服务地址" mono />
                        <AppInput v-model="config.ai_review!.api_key!" type="password" placeholder="审核服务密钥" mono />
                        <AppInput v-model="config.ai_review!.model!" placeholder="审核模型" mono />
                    </template>
                </div>

                <div class="space-y-5">
                    <p class="meta">日志</p>
                    <SettingRow label="记录级别" hint="多选；影响日志文件体积">
                        <div class="flex flex-wrap gap-1">
                            <button
                                v-for="level in logLevels"
                                :key="level"
                                :class="[
                                    'flex h-8 items-center rounded-sm border px-2.5 font-mono text-xs transition-colors duration-150',
                                    (config.log_levels || []).includes(level)
                                        ? 'border-ink bg-ink text-bg'
                                        : 'border-border bg-bg text-muted hover:text-ink',
                                ]"
                                @click="toggleLogLevel(level)"
                            >
                                {{ level }}
                            </button>
                        </div>
                    </SettingRow>
                </div>
            </section>

            <!-- ── 生图 ── -->
            <section v-else-if="tab === 'image'" class="space-y-5">
                <p class="meta">调度与并发</p>
                <SettingRow label="单账号并发数" hint="同一账号同时进行的生图数量上限">
                    <AppInput v-model="config.image_account_concurrency" type="number" mono />
                </SettingRow>
                <SettingRow
                    label="账号调度"
                    hint="轮询：请求依次分散到号池各账号；顺序：先用靠前的账号，额度用尽或并发占满后再用后面的"
                >
                    <AppSelect
                        v-model="config.image_account_schedule_mode as string"
                        :options="ACCOUNT_SCHEDULE_OPTIONS"
                        width="10rem"
                    />
                </SettingRow>
                <SettingRow label="多图并行生成" hint="关闭后改为串行，节省上游压力">
                    <AppSwitch v-model="config.image_parallel_generation!" />
                </SettingRow>

                <div class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-5">超时与重试</p>
                    <div class="space-y-5">
                        <SettingRow label="轮询超时（秒）" hint="等待图片结果的最长时间">
                            <AppInput v-model="config.image_poll_timeout_secs" type="number" mono />
                        </SettingRow>
                        <SettingRow label="超时后额外等待（秒）" hint="用户点「继续等待」时追加的时长">
                            <AppInput v-model="config.image_timeout_retry_secs" type="number" mono />
                        </SettingRow>
                    </div>
                </div>

                <div class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-5">结果校验</p>
                    <div class="space-y-5">
                        <SettingRow label="二次确认" hint="发现图片后等待片刻再确认，避免拿到不完整结果">
                            <AppSwitch v-model="config.image_settle_enabled!" />
                        </SettingRow>
                        <SettingRow v-if="config.image_settle_enabled" label="确认等待（秒）">
                            <AppInput v-model="config.image_settle_secs" type="number" mono />
                        </SettingRow>
                        <SettingRow label="先检查再命中" hint="连续两次轮询结果一致才返回">
                            <AppSwitch v-model="config.image_check_before_hit_enabled!" />
                        </SettingRow>
                    </div>
                </div>

                <div class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-5">清理与保留</p>
                    <div class="space-y-5">
                        <SettingRow label="图片保留天数" hint="超过后由定时任务删除">
                            <AppInput v-model="config.image_retention_days" type="number" mono />
                        </SettingRow>
                        <SettingRow label="成功后删除上游会话" hint="避免在 ChatGPT 侧堆积对话">
                            <AppSwitch v-model="config.image_remove_conversation_after_result!" />
                        </SettingRow>
                        <SettingRow label="总是删除上游会话" hint="无论成功失败都清理">
                            <AppSwitch v-model="config.image_remove_conversation_always!" />
                        </SettingRow>
                    </div>
                </div>

                <div class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-5">账号维护</p>
                    <div class="space-y-5">
                        <SettingRow label="刷新间隔（分钟）" hint="定时检查限流账号并刷新额度">
                            <AppInput v-model="config.refresh_account_interval_minute" type="number" mono />
                        </SettingRow>
                        <SettingRow label="自动移除失效账号">
                            <AppSwitch v-model="config.auto_remove_invalid_accounts!" />
                        </SettingRow>
                        <SettingRow label="自动移除限流账号">
                            <AppSwitch v-model="config.auto_remove_rate_limited_accounts!" />
                        </SettingRow>
                        <SettingRow label="刷新后自动重登" hint="需要账号保存了密码">
                            <AppSwitch v-model="config.auto_relogin_after_refresh!" />
                        </SettingRow>
                    </div>
                </div>

                <div class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-5">图片存储</p>
                    <div class="space-y-5">
                        <SettingRow label="启用外部存储" hint="除本地外，再同步一份到 WebDAV">
                            <AppSwitch v-model="config.image_storage!.enabled!" />
                        </SettingRow>
                        <SettingRow label="存储模式">
                            <AppSelect
                                v-model="config.image_storage!.mode as string"
                                :options="STORAGE_MODE_OPTIONS"
                                width="10rem"
                            />
                        </SettingRow>
                        <template v-if="config.image_storage!.mode !== 'local'">
                            <AppInput v-model="config.image_storage!.webdav_url" placeholder="WebDAV 地址" mono />
                            <div class="grid gap-2 sm:grid-cols-2">
                                <AppInput v-model="config.image_storage!.webdav_username" placeholder="用户名" />
                                <AppInput
                                    v-model="config.image_storage!.webdav_password"
                                    type="password"
                                    placeholder="密码"
                                />
                            </div>
                            <AppInput v-model="config.image_storage!.webdav_root_path" placeholder="根路径" mono />
                            <div class="flex gap-2">
                                <AppButton variant="secondary" size="sm" :loading="storageTesting" @click="doTestStorage">
                                    测试连接
                                </AppButton>
                                <AppButton variant="secondary" size="sm" :loading="storageSyncing" @click="doSyncStorage">
                                    同步现有图片
                                </AppButton>
                            </div>
                        </template>
                    </div>
                </div>
            </section>

            <!-- ── 代理 ── -->
            <section v-else-if="tab === 'proxy'" class="space-y-5">
                <p class="meta">出口代理</p>
                <SettingRow label="代理地址" hint="支持 HTTP / HTTPS / SOCKS5，留空表示直连">
                    <div class="flex gap-2">
                        <AppInput v-model="config.proxy" placeholder="http://127.0.0.1:7890" mono />
                        <AppButton variant="secondary" size="sm" :loading="proxyTesting" @click="doTestProxy">
                            测试
                        </AppButton>
                    </div>
                </SettingRow>

                <div v-if="proxyResult" class="border-l-4 border-border py-1 pl-3">
                    <p class="meta-xs">
                        {{ proxyResult.ok ? "可用" : "不可用" }} ·
                        {{ proxyResult.latency_ms }}ms · HTTP {{ proxyResult.status }}
                        <span v-if="proxyResult.error"> · {{ proxyResult.error }}</span>
                    </p>
                </div>

                <div v-if="config.proxy_runtime" class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-5">稳定代理运行时</p>
                    <div class="space-y-5">
                        <SettingRow label="启用运行时" hint="为上游请求单独走一条稳定出口">
                            <AppSwitch v-model="config.proxy_runtime.enabled" />
                        </SettingRow>
                        <SettingRow label="出口模式">
                            <AppSelect
                                v-model="config.proxy_runtime.egress_mode as string"
                                :options="EGRESS_OPTIONS"
                                width="10rem"
                            />
                        </SettingRow>
                        <AppInput v-model="config.proxy_runtime.proxy_url" placeholder="运行时代理地址" mono />
                        <AppInput v-model="config.proxy_runtime.resource_proxy_url" placeholder="资源代理地址（可选）" mono />
                        <SettingRow label="跳过 TLS 校验" hint="仅在你清楚风险时开启">
                            <AppSwitch v-model="config.proxy_runtime.skip_ssl_verify" />
                        </SettingRow>
                    </div>

                    <div class="mt-6 border-t border-dashed border-border pt-5">
                        <p class="meta mb-5">Cloudflare clearance</p>
                        <div class="space-y-5">
                            <SettingRow label="启用 clearance">
                                <AppSwitch v-model="config.proxy_runtime.clearance.enabled" />
                            </SettingRow>
                            <SettingRow label="获取方式">
                                <AppSelect
                                    v-model="config.proxy_runtime.clearance.mode as string"
                                    :options="CLEARANCE_OPTIONS"
                                    width="10rem"
                                />
                            </SettingRow>
                            <AppInput
                                v-if="config.proxy_runtime.clearance.mode === 'flaresolverr'"
                                v-model="config.proxy_runtime.clearance.flaresolverr_url"
                                placeholder="http://flaresolverr:8191"
                                mono
                            />
                            <AppInput
                                v-if="config.proxy_runtime.clearance.mode === 'manual'"
                                v-model="config.proxy_runtime.clearance.cf_cookies"
                                placeholder="CF cookies"
                                mono
                            />
                        </div>
                    </div>
                </div>
            </section>

            <!-- ── 密钥 ── -->
            <section v-else-if="tab === 'keys'" class="space-y-5">
                <div class="rounded-sm border-l-4 border-border bg-bg p-4">
                    <p class="text-sm leading-relaxed text-muted">
                        管理员密钥在部署配置中设置，不在此页展示。
                    </p>
                </div>

                <div class="flex flex-wrap items-end gap-2 border-b border-dashed border-border pb-4">
                    <div class="min-w-48 flex-1">
                        <p class="meta-xs mb-1.5">新建密钥</p>
                        <AppInput v-model="newKeyName" placeholder="给密钥起个名字" />
                    </div>
                    <AppButton variant="primary" size="sm" @click="createKey">创建</AppButton>
                </div>

                <div v-if="createdKey" class="border border-ink p-4">
                    <p class="meta-xs mb-2">新密钥只显示一次，请立即复制</p>
                    <div class="flex items-center gap-2">
                        <code class="min-w-0 flex-1 truncate font-mono text-xs text-ink">{{ createdKey }}</code>
                        <button class="bracket-button" @click="copy(createdKey)">[复制]</button>
                        <button class="bracket-button" @click="createdKey = ''">[关闭]</button>
                    </div>
                </div>

                <div v-if="keys.length === 0" class="border border-dashed border-border py-12 text-center">
                    <p class="text-sm text-muted">还没有普通用户密钥</p>
                </div>
                <div v-else class="divide-y divide-border">
                    <div
                        v-for="key in keys"
                        :key="key.id"
                        class="flex items-center gap-3 py-3"
                    >
                        <div class="min-w-0 flex-1">
                            <p class="truncate text-sm text-ink">{{ key.name }}</p>
                            <p class="meta-xs">
                                创建 {{ formatTime(key.created_at) }} · 最近使用
                                {{ formatTime(key.last_used_at) }}
                            </p>
                        </div>
                        <AppBadge :tone="key.enabled ? 'success' : 'neutral'">
                            {{ key.enabled ? "启用" : "停用" }}
                        </AppBadge>
                        <button class="bracket-button" @click="toggleKey(key)">
                            {{ key.enabled ? "[停用]" : "[启用]" }}
                        </button>
                        <button class="bracket-button" @click="removeKey(key)">[删除]</button>
                    </div>
                </div>
            </section>

            <!-- ── 备份 ── -->
            <section v-else-if="tab === 'backup' && backup" class="space-y-5">
                <!-- 备份历史与手动触发放在最前：先看能不能用，再改配置 -->
                <BackupManager />

                <div class="border-t border-dashed border-border pt-5">
                    <SettingRow label="启用自动备份" hint="定时把配置与数据打包到对象存储">
                        <AppSwitch v-model="backup.enabled" />
                    </SettingRow>
                </div>

                <div class="border-t border-dashed border-border pt-5">
                    <div class="space-y-5">
                        <AppInput v-model="backup.account_id" placeholder="账户 ID" mono />
                        <AppInput v-model="backup.access_key_id" placeholder="Access Key" mono />
                        <AppInput v-model="backup.secret_access_key" type="password" placeholder="Secret Key" mono />
                        <AppInput v-model="backup.bucket" placeholder="Bucket 名称" mono />
                        <div class="grid gap-2 sm:grid-cols-2">
                            <AppInput v-model="backup.prefix" placeholder="对象前缀" mono />
                            <AppInput v-model="backup.interval_minutes" type="number" placeholder="间隔（分钟）" mono />
                        </div>
                        <AppInput v-model="backup.rotation_keep" type="number" placeholder="保留份数" mono />
                    </div>
                </div>

                <div class="border-t border-dashed border-border pt-5">
                    <p class="meta mb-4">备份内容</p>
                    <div class="grid grid-cols-2 gap-2">
                        <label
                            v-for="entry in includeEntries"
                            :key="entry.key"
                            class="flex cursor-pointer items-center gap-2 text-sm text-ink"
                        >
                            <input
                                v-model="entry.value"
                                type="checkbox"
                                class="size-3.5 accent-ink"
                            />
                            {{ entry.label }}
                        </label>
                    </div>
                </div>

                <div class="flex items-center gap-3 border-t border-dashed border-border pt-5">
                    <AppButton variant="secondary" size="sm" :loading="backupBusy" @click="doTestBackup">
                        测试连接
                    </AppButton>
                    <span v-if="backupTest" class="meta-xs">
                        状态 {{ backupTest.ok ? "正常" : "异常" }} · HTTP {{ backupTest.status }}
                    </span>
                </div>

            </section>

            <div class="flex justify-end border-t border-border pt-4">
                <AppButton variant="primary" size="sm" :loading="saving" @click="save">
                    保存全部
                </AppButton>
            </div>
        </template>
    </div>
</template>
