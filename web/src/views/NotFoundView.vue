<script setup lang="ts">
import { RouterLink, useRouter } from "vue-router";

import AppButton from "@/components/ui/AppButton.vue";

const router = useRouter();
</script>

<template>
    <div class="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center" style="background: var(--bg)">
        <p class="meta-xs">404</p>
        <p class="text-lg font-bold text-ink" style="font-family: var(--font-prose)">
            这页不存在
        </p>
        <AppButton variant="primary" size="sm" @click="router.replace('/image')">
            回到画图
        </AppButton>
    </div>
</template>
