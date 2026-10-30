<script setup lang="ts">
/**
 * 设置项的统一外壳。
 *
 * 默认左右分栏：标签与说明在左，控件右对齐。这样几十项设置排下来
 * 控件形成一条整齐的竖列，扫读时不必在每个标题下方寻找输入框。
 *
 * 唯一例外是 `block`：多行文本、标签组这类内容本身需要宽度的控件
 * 占满整行，控件放在标签下方。
 */
withDefaults(
    defineProps<{
        label: string;
        hint?: string;
        /** 控件需要整行宽度（多行文本、按钮组）时使用。 */
        block?: boolean;
    }>(),
    { block: false },
);
</script>

<template>
    <div
        :class="
            block
                ? 'space-y-2'
                : 'flex flex-wrap items-start justify-between gap-x-8 gap-y-2'
        "
    >
        <div class="min-w-0 flex-1 basis-48">
            <p class="text-sm text-ink">{{ label }}</p>
            <p v-if="hint" class="meta-xs mt-1 leading-relaxed">{{ hint }}</p>
        </div>
        <div :class="block ? '' : 'shrink-0'">
            <slot />
        </div>
    </div>
</template>
