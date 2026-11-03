<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Check, Download, Info, Tag, Trash2, X } from "lucide-vue-next";

import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import LazyImage from "@/components/ui/LazyImage.vue";
import ImageLightbox, { type LightboxItem } from "@/components/ImageLightbox.vue";
import {
    compressAllImages,
    deleteImageTag,
    deleteManagedImages,
    deleteToTarget,
    downloadImages,
    downloadSingleImage,
    fetchImageStorage,
    fetchImageTags,
    fetchManagedImages,
    fetchSystemLogs,
    setImageTags,
    type ImageStorageStats,
    type ManagedImage,
    type SystemLog,
} from "@/lib/api";
import { assetUrl } from "@/lib/request";
import { useToast } from "@/lib/toast";
import { formatBytes, formatTime, imageRelFromUrl } from "@/lib/utils";

/*
 * 图片面板。
 *
 * 与调用日志同处一页：图片不再是孤立的文件，而是能回到产生它的那次请求。
 * 图库本身只存文件，请求信息来自日志里的 urls 字段，两边按相对路径对齐。
 */

const props = defineProps<{
    /** 从日志详情跳过来时要直接展开的那张图。 */
    focusImageRel?: string | null;
    /** 当前视图是否可见；切走时收起弹窗，避免它浮在另一个视图上。 */
    active?: boolean;
}>();

const emit = defineEmits<{
    "open-log": [SystemLog];
    "focus-consumed": [];
}>();

const toast = useToast();

const items = ref<ManagedImage[]>([]);
const loading = ref(false);
/** 至少成功加载过一次，用来判断「跳转目标还没出现」还是「确实不存在」。 */
const loadedOnce = ref(false);
/** 加载失败原因：与「没有图片」区分开。 */
const loadError = ref("");
const startDate = ref("");
const endDate = ref("");
const selectedPaths = ref<Set<string>>(new Set());
const page = ref(1);
const PAGE_SIZE = 24;

/* 标签 */
const allTags = ref<string[]>([]);
const activeTags = ref<Set<string>>(new Set());
const tagTarget = ref<ManagedImage | null>(null);
const tagInput = ref("");

/* 存储 */
const storage = ref<ImageStorageStats | null>(null);
const storageBusy = ref(false);
const targetFreeMb = ref(500);
const storageOpen = ref(false);

/* 预览与详情 */
const previewIndex = ref<number | null>(null);
const detail = ref<ManagedImage | null>(null);

/* 请求记录：只取调用日志，建立「图片 → 请求」索引 */
const callLogs = ref<SystemLog[]>([]);

const filtered = computed(() => {
    if (activeTags.value.size === 0) {
        return items.value;
    }
    return items.value.filter((item) =>
        (item.tags || []).some((tag) => activeTags.value.has(tag)),
    );
});

const paged = computed(() => filtered.value.slice(0, page.value * PAGE_SIZE));
const hasMore = computed(() => paged.value.length < filtered.value.length);

const totalSize = computed(() => filtered.value.reduce((sum, item) => sum + (item.size || 0), 0));

const logByRel = computed(() => {
    const map = new Map<string, SystemLog>();
    for (const log of callLogs.value) {
        const urls = log.detail?.urls;
        if (!Array.isArray(urls)) {
            continue;
        }
        for (const url of urls) {
            if (typeof url !== "string") {
                continue;
            }
            const rel = imageRelFromUrl(url);
            // 同一张图只认最早的一条（列表按时间倒序，先到先得即最新一次）。
            if (rel && !map.has(rel)) {
                map.set(rel, log);
            }
        }
    }
    return map;
});

const detailLog = computed(() => (detail.value ? logByRel.value.get(detail.value.rel) ?? null : null));

const detailJson = computed(() => {
    if (!detailLog.value) {
        return "";
    }
    return JSON.stringify(detailLog.value.detail ?? {}, null, 2);
});

onMounted(async () => {
    await Promise.all([load(), loadTags(), loadStorage(), loadLogs()]);
});

// 切到日志视图时收起详情：弹窗被传送到 body，隐藏父级收不住它。
watch(
    () => props.active,
    (value) => {
        if (value === false) {
            detail.value = null;
        }
    },
);

watch(
    () => [props.focusImageRel, items.value] as const,
    () => {
        const rel = props.focusImageRel;
        if (!rel) {
            return;
        }
        const target = items.value.find((item) => item.rel === rel);
        if (!target) {
            // 列表已经加载完还是没有这张图：说明它已被删除或不在当前范围，
            // 交回意图，避免下次刷新列表时又弹一次空详情。
            if (loadedOnce.value) {
                toast.info("没有找到对应的图片，可能已被清理");
                emit("focus-consumed");
            }
            return;
        }
        detail.value = target;
        emit("focus-consumed");
    },
    { immediate: true },
);

async function load() {
    loading.value = true;
    loadError.value = "";
    try {
        const data = await fetchManagedImages({
            start_date: startDate.value,
            end_date: endDate.value,
        });
        items.value = data.items;
        loadedOnce.value = true;
        page.value = 1;
        // 清掉已不存在的选中项。
        const existing = new Set(data.items.map((item) => item.rel));
        selectedPaths.value = new Set(
            [...selectedPaths.value].filter((path) => existing.has(path)),
        );
    } catch (error) {
        loadError.value = error instanceof Error ? error.message : "加载图片失败";
    } finally {
        loading.value = false;
    }
}

/** 请求记录只用来补充信息，失败时静默降级为「没有对应记录」。 */
async function loadLogs() {
    try {
        const data = await fetchSystemLogs({ type: "call" });
        callLogs.value = data.items;
    } catch {
        callLogs.value = [];
    }
}

async function loadTags() {
    try {
        const data = await fetchImageTags();
        allTags.value = data.tags;
    } catch {
        allTags.value = [];
    }
}

async function loadStorage() {
    try {
        storage.value = await fetchImageStorage();
    } catch {
        storage.value = null;
    }
}

function toggleSelect(rel: string) {
    const next = new Set(selectedPaths.value);
    if (next.has(rel)) {
        next.delete(rel);
    } else {
        next.add(rel);
    }
    selectedPaths.value = next;
}

function toggleTagFilter(tag: string) {
    const next = new Set(activeTags.value);
    if (next.has(tag)) {
        next.delete(tag);
    } else {
        next.add(tag);
    }
    activeTags.value = next;
    page.value = 1;
}

async function removeSelected() {
    const paths = [...selectedPaths.value];
    if (paths.length === 0) {
        return;
    }
    if (!window.confirm(`删除 ${paths.length} 张图片？此操作不可撤销。`)) {
        return;
    }
    try {
        const result = await deleteManagedImages({ paths });
        toast.success(`已删除 ${result.removed} 张`);
        selectedPaths.value = new Set();
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function removeOne(item: ManagedImage) {
    if (!window.confirm("删除这张图片？")) {
        return;
    }
    try {
        await deleteManagedImages({ paths: [item.rel] });
        toast.success("已删除");
        await load();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function removeByDate() {
    if (!startDate.value && !endDate.value) {
        toast.info("请先选择日期范围");
        return;
    }
    if (!window.confirm("删除该日期范围内的全部图片？")) {
        return;
    }
    try {
        const result = await deleteManagedImages({
            start_date: startDate.value,
            end_date: endDate.value,
            all_matching: true,
        });
        toast.success(`已删除 ${result.removed} 张`);
        await load();
        await loadStorage();
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function downloadSelected() {
    const paths = [...selectedPaths.value];
    if (paths.length === 0) {
        toast.info("请先选择图片");
        return;
    }
    try {
        await downloadImages(paths);
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "下载失败");
    }
}

async function saveTags() {
    if (!tagTarget.value) {
        return;
    }
    const tags = tagInput.value
        .split(/[,，\s]+/)
        .map((tag) => tag.trim())
        .filter(Boolean);
    try {
        const result = await setImageTags(tagTarget.value.rel, tags);
        const target = items.value.find((item) => item.rel === tagTarget.value?.rel);
        if (target) {
            target.tags = result.tags;
        }
        tagTarget.value = null;
        tagInput.value = "";
        await loadTags();
        toast.success("标签已保存");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "保存失败");
    }
}

async function removeTag(tag: string) {
    if (!window.confirm(`删除标签「${tag}」？会从所有图片上移除。`)) {
        return;
    }
    try {
        await deleteImageTag(tag);
        activeTags.value.delete(tag);
        await Promise.all([loadTags(), load()]);
        toast.success("标签已删除");
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "删除失败");
    }
}

async function compress() {
    storageBusy.value = true;
    try {
        const result = await compressAllImages();
        // 后端字段可能缺失，统一按数值兜底，避免渲染时抛错。
        const count = Number(result?.compressed ?? 0);
        const saved = Number(result?.saved_mb ?? 0);
        toast.success(`压缩 ${count} 张，节省 ${saved.toFixed(1)} MB`);
        await loadStorage();
        storageOpen.value = false;
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "压缩失败");
    } finally {
        storageBusy.value = false;
    }
}

async function cleanupToTarget() {
    storageBusy.value = true;
    try {
        const result = await deleteToTarget(targetFreeMb.value);
        const removed = Number(result?.removed ?? 0);
        const freed = Number(result?.freed_mb ?? 0);
        if (removed === 0) {
            toast.success("可用空间已达标，无需清理");
        } else {
            toast.success(`释放 ${freed} MB，删除 ${removed} 张`);
        }
        await Promise.all([loadStorage(), load()]);
        storageOpen.value = false;
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "清理失败");
    } finally {
        storageBusy.value = false;
    }
}

/** 灯箱数据：当前列表全部可看图，支持左右翻页。 */
const lightboxItems = computed<LightboxItem[]>(() =>
    paged.value.map((item) => ({
        src: assetUrl(item.url),
        alt: item.name,
        filename: item.name,
    })),
);

/** 打开灯箱；目标在图库更靠后的位置时先展开到那一页，否则翻不过去。 */
function openPreview(item: ManagedImage) {
    const index = filtered.value.findIndex((entry) => entry.rel === item.rel);
    if (index < 0) {
        return;
    }
    if (index >= paged.value.length) {
        page.value = Math.ceil((index + 1) / PAGE_SIZE);
    }
    previewIndex.value = index;
}

function openDetail(item: ManagedImage) {
    detail.value = item;
}

function openDetailLog() {
    const log = detailLog.value;
    if (!log) {
        return;
    }
    detail.value = null;
    emit("open-log", log);
}

/** 请求信息里的常用字段，避免模板里重复取值。 */
function logValue(key: string): string {
    const value = detailLog.value?.detail?.[key];
    if (typeof value === "string" || typeof value === "number") {
        return String(value);
    }
    return "-";
}

function logDuration(): string {
    const value = detailLog.value?.detail?.duration_ms;
    return typeof value === "number" ? `${(value / 1000).toFixed(2)}s` : "-";
}

function logStatus(): { label: string; tone: "success" | "danger" | "neutral" } {
    const status = detailLog.value?.detail?.status;
    if (status === "success") {
        return { label: "成功", tone: "success" };
    }
    if (status === "failed") {
        return { label: "失败", tone: "danger" };
    }
    return { label: "-", tone: "neutral" };
}
</script>

<template>
    <div class="space-y-6">
        <!--
            一行骨架：左侧读数，右侧操作。与号池、日志面板共用同一节奏，
            切换视图时控件位置不跳动。
        -->
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-dashed border-border pb-3">
            <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
                <div v-if="storage" class="flex items-baseline gap-1.5">
                    <span class="meta-xs">磁盘可用</span>
                    <span class="text-xl font-bold tabular-nums text-ink" style="font-family: var(--font-mono)">
                        {{ storage.disk_free_mb.toFixed(0) }}
                    </span>
                    <span class="meta-xs">MB</span>
                </div>
                <div v-if="storage" class="h-5 w-px bg-border" />
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">图片</span>
                    <span class="text-xl font-bold tabular-nums text-ink" style="font-family: var(--font-mono)">
                        {{ loadError ? "—" : filtered.length }}
                    </span>
                </div>
                <div class="h-5 w-px bg-border" />
                <div class="flex items-baseline gap-1.5">
                    <span class="meta-xs">占用</span>
                    <span class="text-xl font-bold tabular-nums text-ink" style="font-family: var(--font-mono)">
                        {{ loadError ? "—" : formatBytes(totalSize) }}
                    </span>
                </div>
                <div class="h-5 w-px bg-border" />
                <!-- 存储维护是低频高危操作，收进二级菜单，不在工具栏常驻。 -->
                <button
                    class="bracket-button"
                    :disabled="storageBusy"
                    @click="storageOpen = true"
                >
                    [存储维护]
                </button>
            </div>

            <div class="ml-auto flex flex-wrap items-center gap-2">
                <template v-if="selectedPaths.size > 0">
                    <span class="meta-xs">已选 {{ selectedPaths.size }}</span>
                    <button class="bracket-button" @click="downloadSelected">[下载]</button>
                    <button class="bracket-button" @click="removeSelected">[删除]</button>
                    <button class="bracket-button" @click="selectedPaths = new Set()">[取消选择]</button>
                    <div class="h-5 w-px bg-border" />
                </template>

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
                <button class="bracket-button" :disabled="loading" @click="load">[查询]</button>
                <button class="bracket-button" @click="removeByDate">[按日期删除]</button>
            </div>
        </div>

        <!-- 标签：单独一行，数量不定 -->
        <div v-if="allTags.length > 0" class="flex flex-wrap items-center gap-2">
            <span class="meta-xs">标签</span>
            <span
                v-for="tag in allTags"
                :key="tag"
                :class="[
                    'group inline-flex cursor-pointer items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-[11px] transition-colors duration-150',
                    activeTags.has(tag)
                        ? 'border-ink bg-ink text-bg'
                        : 'border-border bg-bg text-muted hover:text-ink',
                ]"
                @click="toggleTagFilter(tag)"
            >
                {{ tag }}
                <X
                    class="size-2.5 opacity-0 transition-opacity group-hover:opacity-70"
                    @click.stop="removeTag(tag)"
                />
            </span>
        </div>

        <!-- 网格 -->
        <div v-if="loading" class="border border-dashed border-border py-16 text-center">
            <p class="meta">加载中</p>
        </div>
        <div v-else-if="loadError" class="border border-dashed border-border py-16 text-center">
            <p class="text-sm" :style="{ color: 'var(--color-error)' }">图片列表读取失败</p>
            <p class="meta-xs mt-2">{{ loadError }}</p>
            <button class="bracket-button mt-4" @click="load">[重试]</button>
        </div>
        <div v-else-if="filtered.length === 0" class="border border-dashed border-border py-16 text-center">
            <p class="text-sm text-muted">没有图片</p>
        </div>
        <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <div
                v-for="item in paged"
                :key="item.rel"
                :class="[
                    'group relative overflow-hidden rounded-md border bg-surface transition-colors duration-150',
                    selectedPaths.has(item.rel) ? 'border-ink' : 'border-border',
                ]"
            >
                <!--
                    缩略图与浮层单独包一层：操作条必须贴在图片底边，
                    落在卡片底边会盖住下方的日期和大小。
                -->
                <div class="relative aspect-square w-full">
                    <div class="size-full cursor-zoom-in">
                        <LazyImage
                            :src="assetUrl(item.thumbnail_url || item.url)"
                            :alt="item.name"
                            img-class="object-cover"
                            @click="openPreview(item)"
                        />
                    </div>

                    <!-- 选中标记 -->
                    <button
                        class="absolute left-2 top-2 flex size-5 items-center justify-center rounded-sm border transition-colors duration-150"
                        :class="
                            selectedPaths.has(item.rel)
                                ? 'border-ink bg-ink text-bg'
                                : 'border-border bg-surface/90 text-transparent hover:text-muted'
                        "
                        :aria-label="selectedPaths.has(item.rel) ? '取消选中' : '选中'"
                        @click.stop="toggleSelect(item.rel)"
                    >
                        <Check class="size-3" />
                    </button>

                    <!-- 详情入口常驻：触摸设备没有悬停，也能进到请求信息 -->
                    <button
                        class="absolute right-2 top-2 flex size-5 items-center justify-center rounded-sm border bg-surface/90 transition-colors duration-150 hover:border-ink hover:text-ink"
                        :class="logByRel.has(item.rel) ? 'border-border text-muted' : 'border-transparent text-muted/70'"
                        :aria-label="logByRel.has(item.rel) ? '查看请求详情' : '查看图片详情'"
                        :title="logByRel.has(item.rel) ? '查看请求详情' : '查看图片详情'"
                        @click.stop="openDetail(item)"
                    >
                        <Info class="size-3" />
                    </button>

                    <!--
                        操作条：一块自带边框的小面板，不用渐变遮罩 ——
                        暗色下 ink 是浅色，渐变会糊成一条灰带。
                        桌面悬停出现，触摸设备常显。
                    -->
                    <div
                        class="absolute bottom-2 right-2 flex items-center gap-1 rounded-sm border border-border bg-surface/95 p-1 shadow-[var(--shadow-lg)] opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 touch-visible"
                    >
                        <button
                            class="rounded-sm p-1.5 text-muted transition-colors duration-150 hover:bg-border/40 hover:text-ink"
                            aria-label="编辑标签"
                            title="编辑标签"
                            @click.stop="tagTarget = item; tagInput = (item.tags || []).join(', ')"
                        >
                            <Tag class="size-3" />
                        </button>
                        <button
                            class="rounded-sm p-1.5 text-muted transition-colors duration-150 hover:bg-border/40 hover:text-ink"
                            aria-label="下载"
                            title="下载"
                            @click.stop="downloadSingleImage(item.rel)"
                        >
                            <Download class="size-3" />
                        </button>
                        <button
                            class="rounded-sm p-1.5 text-muted transition-colors duration-150 hover:bg-border/40 hover:text-ink"
                            aria-label="删除"
                            title="删除"
                            @click.stop="removeOne(item)"
                        >
                            <Trash2 class="size-3" />
                        </button>
                    </div>
                </div>

                <!-- 元数据 -->
                <div class="space-y-1 border-t border-border px-2 py-1.5">
                    <p class="meta-xs truncate">{{ item.date }}</p>
                    <div class="flex items-center justify-between gap-1">
                        <span class="meta-xs">{{ formatBytes(item.size) }}</span>
                        <span v-if="item.tags?.length" class="flex gap-1">
                            <AppBadge v-for="tag in item.tags.slice(0, 2)" :key="tag" tone="accent">
                                {{ tag }}
                            </AppBadge>
                        </span>
                    </div>
                </div>
            </div>
        </div>

        <div v-if="hasMore" class="pt-2 text-center">
            <AppButton variant="secondary" size="sm" @click="page += 1">
                加载更多（{{ filtered.length - paged.length }}）
            </AppButton>
        </div>

        <!--
            图片详情：先看文件本身，再顺着日志把那次请求还原出来。
            没有记录的旧图不编造信息，只说明「找不到」。
        -->
        <AppDialog
            :open="detail !== null"
            title="图片详情"
            :description="detail ? `${detail.date} · ${formatBytes(detail.size)}` : ''"
            size="lg"
            @update:open="detail = null"
        >
            <div v-if="detail" class="space-y-5">
                <div class="flex flex-col gap-4 sm:flex-row">
                    <button
                        class="group relative w-full shrink-0 overflow-hidden rounded-sm border border-border bg-bg sm:w-52"
                        title="看大图"
                        @click="openPreview(detail)"
                    >
                        <span class="block aspect-square w-full">
                            <LazyImage
                                :src="assetUrl(detail.thumbnail_url || detail.url)"
                                :alt="detail.name"
                                img-class="object-cover transition-opacity duration-150 group-hover:opacity-85"
                            />
                        </span>
                        <span class="absolute bottom-2 right-2 rounded-sm bg-surface/90 px-1.5 py-0.5 font-mono text-[10px] text-ink">
                            看大图
                        </span>
                    </button>

                    <div class="grid flex-1 grid-cols-2 gap-3">
                        <div class="col-span-2">
                            <p class="meta-xs">文件</p>
                            <p class="mt-0.5 truncate font-mono text-xs text-ink" :title="detail.name">
                                {{ detail.name }}
                            </p>
                        </div>
                        <div>
                            <p class="meta-xs">尺寸</p>
                            <p class="mt-0.5 font-mono text-xs text-ink">
                                {{ detail.width && detail.height ? `${detail.width} × ${detail.height}` : "-" }}
                            </p>
                        </div>
                        <div>
                            <p class="meta-xs">日期</p>
                            <p class="mt-0.5 font-mono text-xs text-ink">{{ detail.date }}</p>
                        </div>
                        <div v-if="detail.tags?.length" class="col-span-2">
                            <p class="meta-xs">标签</p>
                            <div class="mt-1 flex flex-wrap gap-1">
                                <AppBadge v-for="tag in detail.tags" :key="tag" tone="accent">
                                    {{ tag }}
                                </AppBadge>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="border-t border-border pt-4">
                    <div class="flex items-center justify-between gap-3">
                        <p class="meta-xs">请求记录</p>
                        <button v-if="detailLog" class="bracket-button" @click="openDetailLog">[查看日志]</button>
                    </div>

                    <template v-if="detailLog">
                        <p class="mt-2 text-sm text-ink">{{ detailLog.summary || "调用记录" }}</p>
                        <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                            <div>
                                <p class="meta-xs">状态</p>
                                <p class="mt-0.5">
                                    <AppBadge :tone="logStatus().tone">{{ logStatus().label }}</AppBadge>
                                </p>
                            </div>
                            <div>
                                <p class="meta-xs">模型</p>
                                <p class="mt-0.5 font-mono text-xs text-ink">{{ logValue("model") }}</p>
                            </div>
                            <div>
                                <p class="meta-xs">耗时</p>
                                <p class="mt-0.5 font-mono text-xs text-ink">{{ logDuration() }}</p>
                            </div>
                            <div>
                                <p class="meta-xs">接口</p>
                                <p class="mt-0.5 font-mono text-xs text-ink">{{ logValue("endpoint") }}</p>
                            </div>
                            <div>
                                <p class="meta-xs">账号</p>
                                <p class="mt-0.5 truncate text-sm text-ink">{{ logValue("account_email") }}</p>
                            </div>
                            <div>
                                <p class="meta-xs">操作者</p>
                                <p class="mt-0.5 text-sm text-ink">{{ logValue("key_name") }}</p>
                            </div>
                        </div>

                        <div v-if="logValue('request_text') !== '-'" class="mt-3">
                            <p class="meta-xs mb-1.5">提示词</p>
                            <p class="max-h-40 overflow-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">
                                {{ logValue("request_text") }}
                            </p>
                        </div>

                        <p class="meta-xs mt-3">请求时间 {{ formatTime(detailLog.time) }}</p>
                    </template>
                    <p v-else class="mt-2 text-xs leading-relaxed text-muted">
                        没有找到这张图对应的调用记录（可能已超出日志保留范围，或图片是手动放入的）。
                    </p>
                </div>

                <div v-if="detailJson !== '{}'" class="border-t border-border pt-4">
                    <p class="meta-xs mb-2">原始数据</p>
                    <pre
                        class="max-h-56 overflow-auto rounded-sm border border-border bg-bg p-3 font-mono text-[11px] leading-relaxed text-muted"
                    >{{ detailJson }}</pre>
                </div>

                <div class="flex justify-end gap-3 border-t border-border pt-3">
                    <button class="bracket-button" @click="detail = null">[关闭]</button>
                    <AppButton variant="secondary" size="sm" @click="openPreview(detail)">看大图</AppButton>
                </div>
            </div>
        </AppDialog>

        <!-- 存储维护：低频操作集中在弹窗内，避免误触 -->
        <AppDialog
            :open="storageOpen"
            title="存储维护"
            description="压缩会重写全部图片，清理会删除最旧的图片"
            size="sm"
            @update:open="storageOpen = false"
        >
            <div class="space-y-5">
                <div v-if="storage" class="grid grid-cols-2 gap-4 border-b border-border pb-4">
                    <div>
                        <p class="meta-xs">磁盘可用</p>
                        <p class="mt-1 font-mono text-lg font-bold tabular-nums text-ink">
                            {{ storage.disk_free_mb.toFixed(0) }}
                            <span class="meta-xs font-normal">MB</span>
                        </p>
                    </div>
                    <div>
                        <p class="meta-xs">图片占用</p>
                        <p class="mt-1 font-mono text-lg font-bold tabular-nums text-ink">
                            {{ storage.image_size_mb.toFixed(1) }}
                            <span class="meta-xs font-normal">MB</span>
                        </p>
                    </div>
                </div>

                <div class="space-y-2">
                    <p class="text-sm text-ink">压缩图片</p>
                    <p class="meta-xs leading-relaxed">
                        按原分辨率重写为优化后的 PNG，耗时较长，不会删除任何图片。
                    </p>
                    <AppButton
                        variant="secondary"
                        size="sm"
                        :loading="storageBusy"
                        :disabled="storageBusy"
                        @click="compress"
                    >
                        开始压缩
                    </AppButton>
                </div>

                <div class="space-y-2 border-t border-dashed border-border pt-4">
                    <p class="text-sm text-ink">清理到指定可用空间</p>
                    <p class="meta-xs leading-relaxed">
                        从最旧的图片开始删除，直到磁盘可用空间达到目标值。此操作不可撤销。
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="meta-xs">保留可用</span>
                        <input
                            v-model.number="targetFreeMb"
                            type="number"
                            class="h-8 w-20 rounded-sm border border-border bg-bg px-2 font-mono text-xs text-ink outline-none focus:border-ink"
                        />
                        <span class="meta-xs mr-1">MB</span>
                        <AppButton
                            variant="secondary"
                            size="sm"
                            :loading="storageBusy"
                            :disabled="storageBusy"
                            @click="cleanupToTarget"
                        >
                            开始清理
                        </AppButton>
                    </div>
                </div>

                <div class="flex justify-end border-t border-border pt-3">
                    <button class="bracket-button" @click="storageOpen = false">[关闭]</button>
                </div>
            </div>
        </AppDialog>

        <!-- 标签编辑 -->
        <AppDialog
            :open="tagTarget !== null"
            title="编辑标签"
            description="用逗号或空格分隔多个标签"
            size="sm"
            @update:open="tagTarget = null"
        >
            <div class="space-y-4">
                <input
                    v-model="tagInput"
                    placeholder="风景, 人像"
                    class="h-10 w-full rounded-sm border border-border bg-bg px-3 font-mono text-sm text-ink outline-none focus:border-ink"
                    @keydown.enter="saveTags"
                />
                <div class="flex justify-end gap-3">
                    <button class="bracket-button" @click="tagTarget = null">[取消]</button>
                    <AppButton variant="primary" size="sm" @click="saveTags">保存</AppButton>
                </div>
            </div>
        </AppDialog>

        <!-- 大图预览 -->
        <ImageLightbox v-model:index="previewIndex" :items="lightboxItems" />
    </div>
</template>

<style scoped>
/*
 * 触摸设备没有悬停，操作按钮必须常显，否则用户永远够不到标签、下载与删除。
 * 用 hover:none 而不是按屏宽判断：带触摸屏的笔记本也能正确取舍。
 */
@media (hover: none) {
    .touch-visible {
        opacity: 1;
    }
}
</style>
