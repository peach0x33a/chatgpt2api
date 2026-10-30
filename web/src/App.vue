<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import ToastHost from "@/components/ToastHost.vue";
import AppLayout from "@/layouts/AppLayout.vue";

const route = useRoute();

// 登录页、404 使用无导航的空白布局。
const layout = computed(() => (route.meta.layout === "blank" ? "blank" : "app"));
</script>

<template>
    <ToastHost />
    <AppLayout v-if="layout === 'app'">
        <RouterView />
    </AppLayout>
    <RouterView v-else />
</template>
