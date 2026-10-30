<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { Pencil, Plus, Trash2 } from "lucide-vue-next";

import ImageLightbox, { type LightboxItem } from "@/components/ImageLightbox.vue";
import ImageComposer from "@/components/image/ImageComposer.vue";
import ImageResults from "@/components/image/ImageResults.vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppDialog from "@/components/ui/AppDialog.vue";
import { useImageGeneration } from "@/composables/useImageGeneration";
import { fetchAccounts, fetchModels, type Model } from "@/lib/api";
import { assetUrl } from "@/lib/request";
import { useToast } from "@/lib/toast";
import { createId } from "@/lib/utils";
import {
    useConversationStore,
    type Conversation,
    type StoredReferenceImage,
    type Turn,
} from "@/stores/conversations";

const toast = useToast();
const store = useConversationStore();
const { submitting, submit, continueWait, resumePending } = useImageGeneration();

const activeId = ref<string | null>(null);
const previewIndex = ref<number | null>(null);

const prompt = ref("");
const count = ref(localStorage.getItem("qi:count") || "1");
const ratio = ref(localStorage.getItem("qi:ratio") || "auto");
const tier = ref(localStorage.getItem("qi:tier") || "1k");
const quality = ref(localStorage.getItem("qi:quality") || "auto");
const model = ref(localStorage.getItem("qi:model") || "gpt-image-2");
const references = ref<StoredReferenceImage[]>([]);

const models = ref<string[]>(["gpt-image-2"]);
const availableQuota = ref<number | null>(null);

const active = computed(() => store.byId(activeId.value));
const turns = computed(() => active.value?.turns ?? []);

function resolveSize(): string {
    const base = tier.value === "4k" ? 2048 : tier.value === "2k" ? 1536 : 1024;
    switch (ratio.value) {
        case "1:1":
            return `${base}x${base}`;
        case "3:2":
            return `${Math.round(base * 1.5)}x${base}`;
        case "2:3":
            return `${base}x${Math.round(base * 1.5)}`;
        case "16:9":
            return `${Math.round(base * 1.78)}x${base}`;
        case "9:16":
            return `${base}x${Math.round(base * 1.78)}`;
        default:
            return "";
    }
}

async function loadMeta() {
    try {
        const result = await fetchModels();
        const imageModels = result.data
            .map((item: Model) => item.id)
            .filter((id) => id.includes("image") || id === "auto");
        if (imageModels.length > 0) {
            models.value = imageModels;
            if (!imageModels.includes(model.value)) {
                model.value = imageModels[0];
            }
        }
    } catch {
        // 模型目录不可用时保留默认值。
    }
    try {
        const accounts = await fetchAccounts();
        availableQuota.value = accounts.items.reduce((sum, item) => sum + (item.quota || 0), 0);
    } catch {
        availableQuota.value = null;
    }
}

onMounted(async () => {
    if (!store.loaded) {
        await store.load();
    }
    const savedId = localStorage.getItem("qi:active");
    if (savedId && store.byId(savedId)) {
        activeId.value = savedId;
    } else if (store.sorted.length > 0) {
        activeId.value = store.sorted[0].id;
    }
    await loadMeta();
    // 接管刷新前未结束的任务，否则它们会永远停在「提交中」。
    void resumeInFlight();
});

/**
 * 把所有会话里仍在等待的图片任务重新接上。
 *
 * 任务状态持久化在本地，但轮询随页面卸载而中止。没有这一步，
 * 用户刷新后看到的是一个永远不动的「提交中」。
 */
async function resumeInFlight() {
    const groups: Array<{ turn: Turn; taskIds: string[] }> = [];
    /** 没有任务 ID 的残留加载态：既无法查询也无法恢复，只能如实标为失败。 */
    const orphans: Array<{ conversation: Conversation; turn: Turn }> = [];
    let orphanCount = 0;

    for (const conversation of store.items) {
        for (const turn of conversation.turns) {
            const loading = turn.images.filter((image) => image.status === "loading");
            if (loading.length === 0) {
                continue;
            }
            const taskIds = loading
                .filter((image) => image.taskId)
                .map((image) => image.taskId as string);
            if (taskIds.length > 0) {
                groups.push({ turn, taskIds });
            }
            const broken = loading.filter((image) => !image.taskId);
            if (broken.length > 0) {
                for (const image of broken) {
                    image.status = "error";
                    image.progress = undefined;
                    image.error = "任务已中断，请重新生成";
                }
                orphanCount += broken.length;
                orphans.push({ conversation, turn });
            }
        }
    }

    if (orphans.length > 0) {
        for (const { conversation, turn } of orphans) {
            const stillLoading = turn.images.some((image) => image.status === "loading");
            if (!stillLoading) {
                turn.status = "error";
            }
            await store.save(conversation);
        }
        toast.info(`${orphanCount} 张图片的任务记录已失效，请重新生成`);
    }

    if (groups.length === 0) {
        return;
    }

    // 找到每组所属的会话，回填后逐个保存。
    await resumePending(groups, (turn) => {
        const owner = store.items.find((conversation) =>
            conversation.turns.some((item) => item.id === turn.id),
        );
        if (owner) {
            void store.save(owner);
        }
    });
}

/* ── 滚动位置记忆 ── */
const SCROLL_KEY = "qi:scroll";

function loadScrollMap(): Record<string, number> {
    try {
        return JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "{}") as Record<string, number>;
    } catch {
        return {};
    }
}

function saveScrollMap(map: Record<string, number>) {
    try {
        sessionStorage.setItem(SCROLL_KEY, JSON.stringify(map));
    } catch {
        // 存储不可用时忽略，不影响主流程。
    }
}

const scrollMap = loadScrollMap();
const contentRef = ref<HTMLElement | null>(null);

watch(activeId, async (value, previous) => {
    // 离开前记录上一个会话的滚动位置。
    if (previous && contentRef.value) {
        scrollMap[previous] = contentRef.value.scrollTop;
        saveScrollMap(scrollMap);
    }
    if (value) {
        localStorage.setItem("qi:active", value);
    } else {
        localStorage.removeItem("qi:active");
    }
    // 恢复目标会话的位置；等 DOM 更新后再设置。
    await nextTick();
    if (contentRef.value) {
        contentRef.value.scrollTop = scrollMap[value ?? ""] ?? 0;
    }
});

watch([count, ratio, tier, quality, model], () => {
    localStorage.setItem("qi:count", count.value);
    localStorage.setItem("qi:ratio", ratio.value);
    localStorage.setItem("qi:tier", tier.value);
    localStorage.setItem("qi:quality", quality.value);
    localStorage.setItem("qi:model", model.value);
});

async function addReferences(files: File[]) {
    for (const file of files) {
        if (!file.type.startsWith("image/")) {
            continue;
        }
        const dataUrl = await readAsDataUrl(file);
        references.value.push({ name: file.name, type: file.type, dataUrl });
    }
}

function readAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

function dataUrlToFile(dataUrl: string, name: string, type: string): File {
    const [header, payload] = dataUrl.split(",", 2);
    const mime = header.match(/data:(.*?);/)?.[1] || type || "image/png";
    const binary = atob(payload || "");
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new File([bytes], name || "image.png", { type: mime });
}

function newConversation(): Conversation {
    const now = new Date().toISOString();
    return { id: createId("c"), title: "新会话", createdAt: now, updatedAt: now, turns: [] };
}

function buildTitle(text: string): string {
    const clean = text.trim().replace(/\s+/g, " ");
    return clean.length > 22 ? `${clean.slice(0, 22)}…` : clean || "新会话";
}

async function onSubmit() {
    const text = prompt.value.trim();
    if (!text) {
        return;
    }

    let conversation = active.value;
    if (!conversation) {
        conversation = newConversation();
        store.items.unshift(conversation);
        activeId.value = conversation.id;
    }

    const total = Math.max(1, Math.min(4, Number(count.value) || 1));
    const mode = references.value.length > 0 ? "edit" : "generate";
    const turn: Turn = {
        id: createId("turn"),
        prompt: text,
        model: model.value,
        mode,
        referenceImages: [...references.value],
        count: total,
        size: resolveSize(),
        ratio: ratio.value,
        tier: tier.value,
        quality: quality.value,
        images: Array.from({ length: total }, () => ({
            id: createId("img"),
            status: "loading" as const,
            progress: "提交中",
        })),
        createdAt: new Date().toISOString(),
        status: "queued",
    };

    if (conversation.turns.length === 0) {
        conversation.title = buildTitle(text);
    }
    conversation.turns.push(turn);
    await store.save(conversation);

    const files =
        mode === "edit"
            ? references.value.map((item) => dataUrlToFile(item.dataUrl, item.name, item.type))
            : undefined;

    prompt.value = "";
    references.value = [];

    try {
        await submit({ turn, files }, () => {
            void store.save(conversation!);
        });
        const failed = turn.images.filter((image) => image.status === "error");
        if (failed.length > 0) {
            toast.error(`${failed.length} 张图未完成`);
        }
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "提交失败");
        turn.status = "error";
        await store.save(conversation);
    }
}

async function onContinueWait(taskId: string) {
    const conversation = active.value;
    const turn = conversation?.turns.find((item) => item.images.some((img) => img.taskId === taskId));
    if (!conversation || !turn) {
        return;
    }
    try {
        await continueWait(turn, taskId, () => {
            void store.save(conversation);
        });
    } catch (error) {
        toast.error(error instanceof Error ? error.message : "继续等待失败");
    }
}

function onRetry(index: number) {
    const conversation = active.value;
    if (!conversation || conversation.turns.length === 0) {
        return;
    }
    const turn = conversation.turns[conversation.turns.length - 1];
    const target = turn.images[index];
    if (!target) {
        return;
    }
    target.status = "loading";
    target.error = undefined;
    target.progress = "提交中";
    void store.save(conversation);
    toast.info("已重新排队该张图片");
}

function onRemoveImage(index: number) {
    const conversation = active.value;
    const turn = conversation?.turns[conversation.turns.length - 1];
    if (!conversation || !turn) {
        return;
    }
    turn.images.splice(index, 1);
    void store.save(conversation);
}

const previewTurn = ref<Turn | null>(null);

/** 当前轮次的全部可看图片，供灯箱左右翻页。 */
const lightboxItems = computed<LightboxItem[]>(() => {
    if (!previewTurn.value) {
        return [];
    }
    return previewTurn.value.images
        .filter((image) => image.status === "success")
        .map((image) => ({
            src: image.url
                ? assetUrl(image.url)
                : image.b64_json
                  ? `data:image/png;base64,${image.b64_json}`
                  : "",
            alt: image.revised_prompt || "",
            filename: `image-${image.id.slice(0, 8)}.png`,
        }))
        .filter((item) => item.src);
});

function openPreview(turn: Turn, index: number) {
    previewTurn.value = turn;
    // 索引要映射到「成功图片」的序号，而不是原数组下标。
    const target = turn.images[index];
    const success = turn.images.filter((image) => image.status === "success");
    const resolved = success.findIndex((image) => image.id === target?.id);
    previewIndex.value = resolved >= 0 ? resolved : 0;
}

async function startNewConversation() {
    const conversation = newConversation();
    store.items.unshift(conversation);
    activeId.value = conversation.id;
    await store.save(conversation);
}

/* ── 重命名 ── */
const renameOpen = ref(false);
const renameTarget = ref<Conversation | null>(null);
const renameInput = ref("");

function openRename(conversation: Conversation) {
    renameTarget.value = conversation;
    renameInput.value = conversation.title;
    renameOpen.value = true;
}

async function submitRename() {
    const target = renameTarget.value;
    const title = renameInput.value.trim();
    if (!target || !title) {
        renameOpen.value = false;
        return;
    }
    await store.rename(target.id, title);
    renameOpen.value = false;
    renameTarget.value = null;
}

/** 清空全部会话历史。不可撤销，需二次确认。 */
async function clearAll() {
    if (!window.confirm(`清空全部 ${store.sorted.length} 个会话？此操作不可撤销。`)) {
        return;
    }
    await store.clear();
    activeId.value = null;
    toast.success("历史已清空");
}

async function deleteConversation(id: string) {
    await store.remove(id);
    if (activeId.value === id) {
        activeId.value = store.sorted[0]?.id ?? null;
    }
}
</script>

<template>
    <!--
        固定高度布局：外层锁定视口剩余高度，只有中间内容区滚动，
        输入框始终停在底部同一位置，不随图片数量或尺寸移动。
        用 dvh 而非 vh，避免移动端地址栏导致高度跳动。
    -->
    <div class="grid gap-6 lg:grid-cols-[11rem_1fr] lg:h-[calc(100dvh-8rem)]">
        <aside class="hidden min-h-0 lg:flex lg:flex-col">
            <div class="mb-3 flex items-center justify-between">
                <span class="meta">会话</span>
                <button class="bracket-button" @click="startNewConversation">[新建]</button>
            </div>
            <div class="min-h-0 flex-1 space-y-0.5 overflow-y-auto border-t border-border pt-2">
                <div
                    v-for="item in store.sorted"
                    :key="item.id"
                    :class="[
                        'group flex cursor-pointer items-center gap-2 border-l-2 py-1.5 pl-2.5 pr-1 transition-colors duration-150',
                        item.id === activeId
                            ? 'border-l-ink text-ink'
                            : 'border-l-transparent text-muted hover:text-ink',
                    ]"
                    @click="activeId = item.id"
                >
                    <span class="flex-1 truncate text-sm">{{ item.title }}</span>
                    <button
                        class="opacity-0 transition-opacity duration-150 group-hover:opacity-60 hover:!opacity-100"
                        aria-label="重命名会话"
                        @click.stop="openRename(item)"
                    >
                        <Pencil class="size-3" />
                    </button>
                    <button
                        class="opacity-0 transition-opacity duration-150 group-hover:opacity-60 hover:!opacity-100"
                        aria-label="删除会话"
                        @click.stop="deleteConversation(item.id)"
                    >
                        <Trash2 class="size-3" />
                    </button>
                </div>
                <p v-if="store.sorted.length === 0" class="py-4 text-xs text-muted">还没有会话</p>
            </div>
            <button
                v-if="store.sorted.length > 0"
                class="mt-2 shrink-0 text-left"
                @click="clearAll"
            >
                <span class="bracket-button">[清空历史]</span>
            </button>
        </aside>

        <div class="flex min-h-0 min-w-0 flex-col gap-4">
            <div class="flex shrink-0 items-baseline justify-between gap-3 border-b border-border pb-3">
                <button
                    v-if="active"
                    class="group flex min-w-0 items-baseline gap-2 text-left"
                    title="点击重命名"
                    @click="openRename(active)"
                >
                    <h1
                        class="truncate text-xl font-bold text-ink"
                        style="font-family: var(--font-prose)"
                    >
                        {{ active.title }}
                    </h1>
                    <Pencil
                        class="size-3 shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-60"
                    />
                </button>
                <h1
                    v-else
                    class="truncate text-xl font-bold text-ink"
                    style="font-family: var(--font-prose)"
                >
                    画图
                </h1>
                <div class="flex shrink-0 items-center gap-3">
                    <button class="bracket-button lg:hidden" @click="startNewConversation">[新建]</button>
                    <span v-if="availableQuota !== null" class="meta-xs">
                        额度 {{ availableQuota }}
                    </span>
                </div>
            </div>

            <!-- 唯一可滚动区域：图片再多也只在内部滚动，不会推动输入框 -->
            <div ref="contentRef" class="min-h-0 flex-1 space-y-8 overflow-y-auto pr-1">
                <div v-if="turns.length === 0" class="flex min-h-40 items-center justify-center border border-dashed border-border py-16 text-center">
                    <div>
                        <p class="text-sm text-muted">描述你想要的画面</p>
                        <p class="meta-xs mt-2">支持参考图编辑 · Cmd/Ctrl + Enter 提交</p>
                    </div>
                </div>

                <section v-for="turn in turns" :key="turn.id" class="space-y-3">
                    <p
                        class="text-sm leading-relaxed text-muted"
                        style="font-family: var(--font-prose)"
                    >
                        {{ turn.prompt }}
                    </p>
                    <ImageResults
                        :images="turn.images"
                        :count="turn.count"
                        @open-preview="(index) => openPreview(turn, index)"
                        @continue-wait="onContinueWait"
                        @retry="onRetry"
                        @remove="onRemoveImage"
                    />
                </section>
            </div>

            <div class="shrink-0">
            <ImageComposer
                v-model="prompt"
                :mode="references.length > 0 ? 'edit' : 'generate'"
                :count="count"
                :ratio="ratio"
                :tier="tier"
                :quality="quality"
                :model="model"
                :models="models"
                :references="references"
                :submitting="submitting"
                @update:count="count = $event"
                @update:ratio="ratio = $event"
                @update:tier="tier = $event"
                @update:quality="quality = $event"
                @update:model="model = $event"
                @add-references="addReferences"
                @remove-reference="references.splice($event, 1)"
                @submit="onSubmit"
            />
            </div>
        </div>

        <AppDialog
            v-model:open="renameOpen"
            title="重命名会话"
            size="sm"
        >
            <div class="space-y-4">
                <input
                    v-model="renameInput"
                    placeholder="会话名称"
                    class="h-10 w-full rounded-sm border border-border bg-bg px-3 text-sm text-ink outline-none focus:border-ink"
                    @keydown.enter="submitRename"
                />
                <div class="flex justify-end gap-3">
                    <button class="bracket-button" @click="renameOpen = false">[取消]</button>
                    <AppButton variant="primary" size="sm" @click="submitRename">保存</AppButton>
                </div>
            </div>
        </AppDialog>

        <ImageLightbox v-model:index="previewIndex" :items="lightboxItems" />
    </div>
</template>
