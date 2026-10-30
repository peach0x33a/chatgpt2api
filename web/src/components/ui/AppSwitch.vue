<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; disabled?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [boolean] }>();

function toggle() {
    if (props.disabled) {
        return;
    }
    emit("update:modelValue", !props.modelValue);
}
</script>

<template>
    <!--
        开关用墨色填充表达「开」，不用绿色 ——
        这套系统里彩色各有职责，状态一致比颜色直觉更重要。
    -->
    <button
        type="button"
        role="switch"
        :aria-checked="modelValue"
        :disabled="disabled"
        :class="[
            'relative h-5 w-9 rounded-full border transition-colors duration-150 disabled:opacity-50',
            modelValue ? 'border-ink bg-ink' : 'border-border bg-bg',
        ]"
        @click="toggle"
    >
        <span
            :class="[
                'absolute top-0.5 size-3.5 rounded-full transition-[left,background-color] duration-150',
                modelValue ? 'left-[1.1rem] bg-bg' : 'left-0.5 bg-muted',
            ]"
        />
    </button>
</template>
