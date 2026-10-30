import { createRouter, createWebHistory } from "vue-router";

import { defaultRouteForRole, useAuthStore } from "@/stores/auth";

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {
            path: "/login",
            name: "login",
            component: () => import("@/views/LoginView.vue"),
            meta: { public: true, layout: "blank" },
        },
        {
            path: "/",
            redirect: "/image",
        },
        {
            path: "/image",
            name: "image",
            component: () => import("@/views/ImageWorkbenchView.vue"),
            meta: { title: "画图" },
        },
        {
            path: "/accounts",
            name: "accounts",
            component: () => import("@/views/AccountsView.vue"),
            meta: { title: "号池管理", adminOnly: true },
        },
        {
            path: "/image-manager",
            name: "image-manager",
            component: () => import("@/views/ImageManagerView.vue"),
            meta: { title: "图片管理", adminOnly: true },
        },
        {
            path: "/logs",
            name: "logs",
            component: () => import("@/views/LogsView.vue"),
            meta: { title: "日志管理", adminOnly: true },
        },
        {
            path: "/settings",
            name: "settings",
            component: () => import("@/views/SettingsView.vue"),
            meta: { title: "设置", adminOnly: true },
        },
        {
            path: "/:pathMatch(.*)*",
            name: "not-found",
            component: () => import("@/views/NotFoundView.vue"),
            meta: { public: true, layout: "blank" },
        },
    ],
    scrollBehavior(_to, _from, saved) {
        return saved ?? { top: 0 };
    },
});

router.beforeEach(async (to) => {
    const auth = useAuthStore();

    // 首次进入时先恢复本地会话，避免刷新后闪回登录页。
    if (!auth.ready) {
        await auth.restore();
    }

    if (to.meta.public) {
        // 已登录用户访问登录页时直接送到默认页。
        if (to.name === "login" && auth.session) {
            return defaultRouteForRole(auth.session.role);
        }
        return true;
    }

    if (!auth.session) {
        return { name: "login", query: { redirect: to.fullPath } };
    }

    if (to.meta.adminOnly && !auth.isAdmin) {
        return "/image";
    }

    return true;
});

export { router };
