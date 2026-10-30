<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import AppButton from "@/components/ui/AppButton.vue";
import AppInput from "@/components/ui/AppInput.vue";
import { useToast } from "@/lib/toast";
import { defaultRouteForRole, useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const toast = useToast();

const authKey = ref("");
const error = ref("");
const submitting = ref(false);

onMounted(async () => {
    if (!auth.ready) {
        await auth.restore();
    }
    if (auth.session) {
        await router.replace(defaultRouteForRole(auth.session.role));
    }
});

async function submit() {
    const key = authKey.value.trim();
    if (!key) {
        error.value = "请输入访问密钥";
        return;
    }
    error.value = "";
    submitting.value = true;
    try {
        const data = await auth.login(key);
        toast.success(`欢迎，${data.name || "已登录"}`);
        const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "";
        await router.replace(redirect || defaultRouteForRole(data.role));
    } catch (exc) {
        error.value = exc instanceof Error ? exc.message : "登录失败";
    } finally {
        submitting.value = false;
    }
}
</script>

<template>
    <div class="flex min-h-dvh items-center justify-center px-4" style="background: var(--bg)">
        <div class="w-full max-w-sm" style="animation: ink-in 400ms ease-out both">
            <!-- 标题区：大字文楷，克制的说明文字 -->
            <div class="mb-10">
                <p class="meta-xs mb-3">CHATGPT2API</p>
                <h1
                    class="text-3xl font-bold leading-tight text-ink"
                    style="font-family: var(--font-prose)"
                >
                    号池控制台
                </h1>
                <p class="mt-2 text-sm leading-relaxed text-muted">
                    输入访问密钥以继续。
                </p>
            </div>

            <form class="space-y-5" @submit.prevent="submit">
                <div class="space-y-2">
                    <label for="auth-key" class="meta block">访问密钥</label>
                    <AppInput
                        id="auth-key"
                        v-model="authKey"
                        type="password"
                        placeholder="sk-..."
                        mono
                        :invalid="Boolean(error)"
                        :disabled="submitting"
                        autofocus
                        @enter="submit"
                    />
                    <p v-if="error" class="text-sm text-error">{{ error }}</p>
                </div>

                <AppButton type="submit" variant="primary" block :loading="submitting">
                    进入控制台
                </AppButton>
            </form>

            <p class="mt-12 meta-xs">密钥仅存于本机浏览器</p>
        </div>
    </div>
</template>
