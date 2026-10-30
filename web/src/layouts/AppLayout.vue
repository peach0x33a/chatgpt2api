<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Menu, Moon, Sun, X } from "lucide-vue-next";

import AppButton from "@/components/ui/AppButton.vue";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const theme = useTheme();
const mobileOpen = ref(false);

const adminNav = [
    { to: "/image", label: "生图" },
    { to: "/accounts", label: "号池" },
    { to: "/image-manager", label: "图片" },
    { to: "/logs", label: "日志" },
    { to: "/settings", label: "设置" },
];

const userNav = [{ to: "/image", label: "画图" }];

const navItems = computed(() => (auth.isAdmin ? adminNav : userNav));

function isActive(path: string) {
    return route.path === path;
}

async function logout() {
    await auth.clearSession();
    await router.replace("/login");
}
</script>

<template>
    <div class="min-h-dvh" style="background: var(--bg)">
        <!--
            导航栏：纸色 80% + 12px 模糊 + 底部发丝线。
            高度固定 4rem，桌面端必须在一行内放下。
        -->
        <header
            class="sticky top-0 z-40 h-16 border-b border-border backdrop-blur-[12px]"
            :style="{ background: 'var(--color-overlay)' }"
        >
            <div class="mx-auto flex h-full max-w-5xl items-center gap-6 px-4">
                <button
                    class="rounded-sm p-2 text-muted transition-colors duration-150 hover:bg-bg hover:text-ink lg:hidden"
                    aria-label="打开菜单"
                    @click="mobileOpen = true"
                >
                    <Menu class="size-5" />
                </button>

                <RouterLink to="/image" class="flex items-center gap-2">
                    <span
                        class="text-lg font-bold tracking-wide text-ink"
                        style="font-family: var(--font-prose)"
                    >
                        ChatGPT2API
                    </span>
                </RouterLink>

                <nav class="hidden items-center gap-5 lg:flex">
                    <RouterLink
                        v-for="item in navItems"
                        :key="item.to"
                        :to="item.to"
                        :class="
                            cn(
                                'text-sm transition-colors duration-150',
                                isActive(item.to)
                                    ? 'font-bold text-ink'
                                    : 'text-muted hover:text-ink',
                            )
                        "
                    >
                        {{ item.label }}
                    </RouterLink>
                </nav>

                <div class="ml-auto flex items-center gap-3">
                    <button
                        class="rounded-sm p-1.5 text-muted transition-colors duration-150 hover:text-ink"
                        :aria-label="theme.isDark.value ? '切换到浅色' : '切换到深色'"
                        @click="theme.toggle()"
                    >
                        <Sun v-if="theme.isDark.value" class="size-5" />
                        <Moon v-else class="size-5" />
                    </button>

                    <span class="meta hidden max-w-28 truncate sm:inline">
                        {{ auth.session?.name || "未登录" }}
                    </span>

                    <button
                        class="bracket-button hidden sm:inline"
                        @click="logout"
                    >
                        [登出]
                    </button>
                </div>
            </div>
        </header>

        <main class="mx-auto max-w-5xl px-4 py-8">
            <slot />
        </main>

        <!-- 移动端抽屉 -->
        <Transition
            enter-active-class="transition-opacity duration-200"
            enter-from-class="opacity-0"
            leave-active-class="transition-opacity duration-150"
            leave-to-class="opacity-0"
        >
            <div v-if="mobileOpen" class="fixed inset-0 z-60 lg:hidden">
                <div
                    class="absolute inset-0 backdrop-blur-[4px]"
                    :style="{ background: 'var(--color-overlay)' }"
                    @click="mobileOpen = false"
                />
                <aside class="absolute inset-y-0 left-0 w-64 border-r border-border bg-surface p-6">
                    <div class="mb-8 flex items-center justify-between">
                        <span class="meta">导航</span>
                        <button
                            class="rounded-sm p-1 text-muted hover:text-ink"
                            aria-label="关闭菜单"
                            @click="mobileOpen = false"
                        >
                            <X class="size-4" />
                        </button>
                    </div>
                    <nav class="flex flex-col gap-4">
                        <RouterLink
                            v-for="item in navItems"
                            :key="item.to"
                            :to="item.to"
                            :class="
                                cn(
                                    'text-base transition-colors',
                                    isActive(item.to)
                                        ? 'font-bold text-ink'
                                        : 'text-muted hover:text-ink',
                                )
                            "
                            @click="mobileOpen = false"
                        >
                            {{ item.label }}
                        </RouterLink>
                    </nav>
                    <button class="bracket-button mt-8" @click="logout">[登出]</button>
                </aside>
            </div>
        </Transition>
    </div>
</template>
