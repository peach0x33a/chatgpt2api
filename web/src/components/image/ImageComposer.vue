<script setup lang="ts">
import { computed, ref } from "vue";
import { ImagePlus, Send, X } from "lucide-vue-next";

import AppButton from "@/components/ui/AppButton.vue";
import AppSelect, { type SelectOption } from "@/components/ui/AppSelect.vue";
import type { ImageModel } from "@/lib/api";
import type { StoredReferenceImage } from "@/stores/conversations";

const props = defineProps<{
    modelValue: string;
    mode: "generate" | "edit";
    count: string;
    ratio: string;
    tier: string;
    quality: string;
    model: ImageModel;
    models: ImageModel[];
    references: StoredReferenceImage[];
    submitting: boolean;
    disabled?: boolean;
}>();

const emit = defineEmits<{
    "update:modelValue": [string];
    "update:count": [string];
    "update:ratio": [string];
    "update:tier": [string];
    "update:quality": [string];
    "update:model": [string];
    "add-references": [File[]];
    "remove-reference": [number];
    "submit": [];
}>();

const fileInput = ref<HTMLInputElement | null>(null);

const RATIOS: SelectOption[] = [
    { value: "auto", label: "自动" },
    { value: "1:1", label: "1:1" },
    { value: "3:2", label: "3:2" },
    { value: "2:3", label: "2:3" },
    { value: "16:9", label: "16:9" },
    { value: "9:16", label: "9:16" },
];

const TIERS: SelectOption[] = [
    { value: "1k", label: "1K" },
    { value: "2k", label: "2K" },
    { value: "4k", label: "4K" },
];

const QUALITIES: SelectOption[] = [
    { value: "auto", label: "自动" },
    { value: "low", label: "快速" },
    { value: "medium", label: "标准" },
    { value: "high", label: "精细" },
];

const COUNTS: SelectOption[] = [
    { value: "1", label: "1 张" },
    { value: "2", label: "2 张" },
    { value: "3", label: "3 张" },
    { value: "4", label: "4 张" },
];

const MODEL_OPTIONS = computed<SelectOption[]>(() =>
    props.models.map((item) => ({ value: item, label: item })),
);

const canSubmit = computed(
    () => props.modelValue.trim().length > 0 && !props.submitting && !props.disabled,
);

const placeholder = computed(() =>
    props.mode === "edit" ? "描述要如何修改这张图…" : "描述你想要的画面…",
);

function pickFiles() {
    fileInput.value?.click();
}

function onFilesPicked(event: Event) {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files || []);
    if (files.length > 0) {
        emit("add-references", files);
    }
    input.value = "";
}

function onPaste(event: ClipboardEvent) {
    const files = Array.from(event.clipboardData?.files || []).filter((file) =>
        file.type.startsWith("image/"),
    );
    if (files.length > 0) {
        event.preventDefault();
        emit("add-references", files);
    }
}

function onKeydown(event: KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && canSubmit.value) {
        event.preventDefault();
        emit("submit");
    }
}
</script>

<template>
    <!--
        输入区是「纸上的一个凹槽」：容器 8px 圆角、内部无阴影。
        参数控件全部压成一行等宽小字，让提示词始终是视觉主体。
    -->
    <div class="rounded-md border border-border bg-surface">
        <div v-if="references.length > 0" class="flex flex-wrap gap-2 border-b border-border p-3">
            <div
                v-for="(item, index) in references"
                :key="index"
                class="group relative size-14 overflow-hidden rounded-sm border border-border"
            >
                <img :src="item.dataUrl" :alt="item.name" class="size-full object-cover" />
                <button
                    class="absolute right-0 top-0 bg-ink/70 p-0.5 text-bg opacity-0 transition-opacity duration-150 group-hover:opacity-100"
                    aria-label="移除参考图"
                    @click="emit('remove-reference', index)"
                >
                    <X class="size-3" />
                </button>
            </div>
        </div>

        <textarea
            :value="modelValue"
            :placeholder="placeholder"
            rows="3"
            :disabled="disabled"
            class="w-full resize-none bg-transparent px-4 py-3 text-base leading-relaxed text-ink outline-none placeholder:text-muted/70 disabled:opacity-50"
            style="font-family: var(--font-prose)"
            @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
            @paste="onPaste"
            @keydown="onKeydown"
        />

        <!-- 参数栏：全部 mono 小字，与正文形成「元数据 / 内容」的分界 -->
        <div class="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2">
            <AppSelect
                :model-value="model"
                :options="MODEL_OPTIONS"
                size="sm"
                width="9rem"
                :disabled="disabled"
                @update:model-value="emit('update:model', $event)"
            />

            <AppSelect
                :model-value="ratio"
                :options="RATIOS"
                size="sm"
                width="5rem"
                @update:model-value="emit('update:ratio', $event)"
            />

            <AppSelect
                :model-value="tier"
                :options="TIERS"
                size="sm"
                width="4.5rem"
                @update:model-value="emit('update:tier', $event)"
            />

            <AppSelect
                :model-value="quality"
                :options="QUALITIES"
                size="sm"
                width="5rem"
                @update:model-value="emit('update:quality', $event)"
            />

            <AppSelect
                :model-value="count"
                :options="COUNTS"
                size="sm"
                width="5rem"
                @update:model-value="emit('update:count', $event)"
            />

            <button
                class="ml-auto flex h-8 items-center gap-1.5 px-2 font-mono text-xs text-muted transition-colors duration-150 hover:text-ink"
                :disabled="disabled"
                @click="pickFiles"
            >
                <ImagePlus class="size-3.5" />
                参考图
            </button>

            <AppButton
                variant="primary"
                size="sm"
                :disabled="!canSubmit"
                :loading="submitting"
                @click="emit('submit')"
            >
                <Send v-if="!submitting" class="size-3.5" />
                生成
            </AppButton>
        </div>

        <input
            ref="fileInput"
            type="file"
            accept="image/*"
            multiple
            class="hidden"
            @change="onFilesPicked"
        />
    </div>
</template>
