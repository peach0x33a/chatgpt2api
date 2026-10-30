<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, Download, Tag, Trash2, X } from "lucide-vue-next";

import AppBadge from "@/components/ui/AppBadge.vue";
import AppButton from "@/components/ui/AppButton.vue";
import LazyImage from "@/components/ui/LazyImage.vue";
import ImageLightbox, { type LightboxItem } from "@/components/ImageLightbox.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
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
    setImageTags,
    type ImageStorageStats,
    type ManagedImage,
} from "@/lib/api";
import { assetUrl } from "@/lib/request";
import { useToast } from "@/lib/toast";
import { formatBytes } from "@/lib/utils";

const toast = useToast();

const items = ref<ManagedImage[]>([]);
const loading = ref(false);
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

/* 预览 */
const previewIndex = ref<number | null>(null);

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

onMounted(async () => {
    await Promise.all([load(), loadTags(), loadStorage()]);
});

async function load() {
    loading.value = true;
    loadError.value = "";
    try {
        const data = await fetchManagedImages({
            start_date: startDate.value,
            end_date: endDate.value,
        });
        items.value = data.items;
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

function openPreview(item: ManagedImage) {
    const index = paged.value.findIndex((entry) => entry.rel === item.rel);
    if (index >= 0) {
        previewIndex.value = index;
    }
}
</script>

<template>
    <div class="space-y-6">
        <div class="flex flex-wrap items-baseline justify-between gap-4 border-b border-border pb-4">
            <div>
                <h1 class="text-2xl font-bold text-ink" style="font-family: var(--font-prose)">
                    图片
                </h1>
            </div>
            <div v-if="selectedPaths.size > 0" class="flex items-center gap-3">
                <span class="meta-xs">已选 {{ selectedPaths.size }}</span>
                <button class="bracket-button" @click="downloadSelected">[下载]</button>
                <button class="bracket-button" @click="removeSelected">[删除]</button>
                <button class="bracket-button" @click="selectedPaths = new Set()">[取消选择]</button>
            </div>
        </div>

        <!--
            一行骨架：左侧读数，右侧操作。与号池页共用同一节奏，
            切换页面时控件位置不跳动。
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
                <div class="aspect-square w-full cursor-zoom-in">
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

                <!-- 悬停操作 -->
                <div
                    class="absolute inset-x-0 bottom-0 flex items-center justify-end gap-1 bg-gradient-to-t from-ink/70 to-transparent p-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100"
                >
                    <button
                        class="rounded-sm bg-surface p-1.5 text-ink"
                        aria-label="编辑标签"
                        @click.stop="tagTarget = item; tagInput = (item.tags || []).join(', ')"
                    >
                        <Tag class="size-3" />
                    </button>
                    <button
                        class="rounded-sm bg-surface p-1.5 text-ink"
                        aria-label="下载"
                        @click.stop="downloadSingleImage(item.rel)"
                    >
                        <Download class="size-3" />
                    </button>
                    <button
                        class="rounded-sm bg-surface p-1.5 text-ink"
                        aria-label="删除"
                        @click.stop="removeOne(item)"
                    >
                        <Trash2 class="size-3" />
                    </button>
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
