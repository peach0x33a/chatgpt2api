<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { Check, ChevronDown } from "lucide-vue-next";

export type SelectOption = {
    value: string;
    label: string;
};

const props = withDefaults(
    defineProps<{
        modelValue: string;
        options: SelectOption[];
        placeholder?: string;
        disabled?: boolean;
        /** 触发器的视觉密度，参数栏用 sm。 */
        size?: "sm" | "md";
        /** 触发器宽度；留空按内容自适应。 */
        width?: string;
        align?: "start" | "end";
    }>(),
    { size: "md", align: "start" },
);

const emit = defineEmits<{ "update:modelValue": [string] }>();

const open = ref(false);
const trigger = ref<HTMLElement | null>(null);
const list = ref<HTMLElement | null>(null);
const activeIndex = ref(-1);
/** 面板坐标：fixed 定位，由触发器位置推导，避免被父级 overflow 裁剪。 */
const panelStyle = ref<Record<string, string>>({});

const current = computed(
    () => props.options.find((option) => option.value === props.modelValue) ?? null,
);

const triggerClass = computed(() =>
    // 两档高度与 AppButton / AppInput 严格对应：
    // sm = 32px（工具栏），md = 40px（表单）。
    props.size === "sm"
        ? "h-8 gap-1 rounded-sm px-2.5 font-mono text-xs"
        : "h-10 gap-1.5 rounded-sm px-3 text-xs",
);

function toggle() {
    if (props.disabled) {
        return;
    }
    open.value = !open.value;
}

function choose(value: string) {
    emit("update:modelValue", value);
    open.value = false;
    trigger.value?.focus();
}

function onKeydown(event: KeyboardEvent) {
    if (props.disabled) {
        return;
    }
    if (!open.value && (event.key === "Enter" || event.key === " " || event.key === "ArrowDown")) {
        event.preventDefault();
        open.value = true;
        return;
    }
    if (!open.value) {
        return;
    }
    switch (event.key) {
        case "Escape":
            open.value = false;
            break;
        case "ArrowDown":
            event.preventDefault();
            activeIndex.value = Math.min(activeIndex.value + 1, props.options.length - 1);
            break;
        case "ArrowUp":
            event.preventDefault();
            activeIndex.value = Math.max(activeIndex.value - 1, 0);
            break;
        case "Enter":
        case " ":
            event.preventDefault();
            if (activeIndex.value >= 0 && props.options[activeIndex.value]) {
                choose(props.options[activeIndex.value].value);
            }
            break;
    }
}

/** 点外部关闭。用 pointerdown 以便触摸设备同样生效。 */
function onDocumentPointerDown(event: PointerEvent) {
    const target = event.target as Node;
    if (trigger.value?.contains(target) || list.value?.contains(target)) {
        return;
    }
    open.value = false;
}

/** 按触发器位置算出面板坐标；空间不足时向上展开。 */
function positionPanel() {
    const rect = trigger.value?.getBoundingClientRect();
    if (!rect) {
        return;
    }
    const estimated = Math.min(props.options.length * 30 + 10, 240);
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUpward = spaceBelow < estimated + 8;

    panelStyle.value = {
        position: "fixed",
        left: `${rect.left}px`,
        width: `${Math.max(rect.width, 112)}px`,
        zIndex: "80",
        ...(openUpward
            ? { bottom: `${window.innerHeight - rect.top + 4}px` }
            : { top: `${rect.bottom + 4}px` }),
    };
}

watch(open, async (value) => {
    if (value) {
        activeIndex.value = props.options.findIndex((option) => option.value === props.modelValue);
        document.addEventListener("pointerdown", onDocumentPointerDown);
        window.addEventListener("scroll", positionPanel, true);
        window.addEventListener("resize", positionPanel);
        positionPanel();
        await nextTick();
        list.value?.querySelector<HTMLElement>("[data-active='true']")?.scrollIntoView({
            block: "nearest",
        });
    } else {
        document.removeEventListener("pointerdown", onDocumentPointerDown);
        window.removeEventListener("scroll", positionPanel, true);
        window.removeEventListener("resize", positionPanel);
    }
});

onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", onDocumentPointerDown);
    window.removeEventListener("scroll", positionPanel, true);
    window.removeEventListener("resize", positionPanel);
});
</script>

<template>
    <!--
        自绘下拉：原生的 select 弹层由系统绘制，无法跟随主题，
        深色界面下会出现一块亮色面板和系统蓝高亮，与整体割裂。
    -->
    <div class="relative" :style="width ? { width } : undefined">
        <button
            ref="trigger"
            type="button"
            :class="[
                'flex w-full items-center justify-between border border-border bg-bg text-ink',
                'outline-none transition-colors duration-150 focus:border-ink disabled:opacity-50',
                triggerClass,
            ]"
            :disabled="disabled"
            :aria-expanded="open"
            aria-haspopup="listbox"
            @click="toggle"
            @keydown="onKeydown"
        >
            <span class="truncate">{{ current?.label || placeholder || "请选择" }}</span>
            <ChevronDown
                :class="[
                    'size-3 shrink-0 text-muted transition-transform duration-150',
                    open && 'rotate-180',
                ]"
            />
        </button>

        <!-- Teleport 必须在 Transition 外层，否则过渡侦测不到子元素变化。 -->
        <Teleport to="body">
            <Transition
                enter-active-class="transition duration-150 ease-out"
                enter-from-class="opacity-0 -translate-y-1"
                leave-active-class="transition duration-100 ease-in"
                leave-to-class="opacity-0"
            >
            <div
                v-if="open"
                ref="list"
                role="listbox"
                class="max-h-60 overflow-y-auto rounded-sm border border-border bg-surface py-1 shadow-[var(--shadow-lg)]"
                :style="panelStyle"
            >
                <button
                    v-for="(option, index) in options"
                    :key="option.value"
                    type="button"
                    role="option"
                    :aria-selected="option.value === modelValue"
                    :data-active="index === activeIndex"
                    :class="[
                        'flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-xs transition-colors duration-100',
                        option.value === modelValue ? 'text-ink' : 'text-muted',
                        index === activeIndex ? 'bg-border/40' : 'hover:bg-border/30',
                    ]"
                    @click="choose(option.value)"
                    @mouseenter="activeIndex = index"
                >
                    <span class="truncate">{{ option.label }}</span>
                    <Check v-if="option.value === modelValue" class="size-3 shrink-0" />
                </button>
            </div>
            </Transition>
        </Teleport>
    </div>
</template>
