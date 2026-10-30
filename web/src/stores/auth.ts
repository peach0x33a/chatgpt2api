import { defineStore } from "pinia";
import localforage from "localforage";

import { login, type LoginResponse } from "@/lib/api";

export type AuthRole = "admin" | "user";

export type AuthSession = {
    key: string;
    role: AuthRole;
    subjectId: string;
    name: string;
};

const AUTH_KEY_STORAGE = "chatgpt2api_auth_key";
const AUTH_SESSION_STORAGE = "chatgpt2api_auth_session";

const authStorage = localforage.createInstance({
    name: "chatgpt2api",
    storeName: "auth",
});

/** 读取持久化的密钥，供请求拦截器同步使用。 */
export async function getStoredAuthKey(): Promise<string> {
    const value = await authStorage.getItem<string>(AUTH_KEY_STORAGE);
    return String(value || "").trim();
}

function normalizeSession(value: unknown, fallbackKey = ""): AuthSession | null {
    if (!value || typeof value !== "object") {
        return null;
    }
    const candidate = value as Partial<AuthSession>;
    const key = String(candidate.key || fallbackKey || "").trim();
    const role = candidate.role === "admin" || candidate.role === "user" ? candidate.role : null;
    if (!key || !role) {
        return null;
    }
    return {
        key,
        role,
        subjectId: String(candidate.subjectId || "").trim(),
        name: String(candidate.name || "").trim(),
    };
}

/** 不同角色的默认落地页。 */
export function defaultRouteForRole(role: AuthRole): string {
    return role === "admin" ? "/accounts" : "/image";
}

export const useAuthStore = defineStore("auth", {
    state: () => ({
        session: null as AuthSession | null,
        /** 是否已完成一次会话校验，路由守卫据此决定是否需要等待。 */
        ready: false,
        loading: false,
    }),

    getters: {
        isAdmin: (state) => state.session?.role === "admin",
        isAuthenticated: (state) => Boolean(state.session),
    },

    actions: {
        /** 从本地读取会话（不做远程校验）。 */
        async restore() {
            const [storedKey, storedSession] = await Promise.all([
                authStorage.getItem<string>(AUTH_KEY_STORAGE),
                authStorage.getItem<AuthSession>(AUTH_SESSION_STORAGE),
            ]);
            this.session = normalizeSession(storedSession, String(storedKey || ""));
            this.ready = true;
            return this.session;
        },

        /** 用密钥登录，成功后持久化会话。 */
        async login(authKey: string): Promise<LoginResponse> {
            this.loading = true;
            try {
                const data = await login(authKey);
                await this.persist({
                    key: authKey.trim(),
                    role: data.role,
                    subjectId: data.subject_id,
                    name: data.name,
                });
                return data;
            } finally {
                this.loading = false;
            }
        },

        /**
         * 校验本地会话是否仍然有效。
         *
         * 与 restore 的区别：这里会真的打一次后端。路由守卫用它，
         * 以免持有已被吊销的密钥进入页面。
         */
        async validate(): Promise<AuthSession | null> {
            if (!this.session) {
                this.ready = true;
                return null;
            }
            try {
                const data = await login(this.session.key);
                await this.persist({
                    key: this.session.key,
                    role: data.role,
                    subjectId: data.subject_id,
                    name: data.name,
                });
                return this.session;
            } catch {
                await this.clearSession();
                return null;
            }
        },

        async persist(session: AuthSession) {
            const normalized = normalizeSession(session);
            if (!normalized) {
                await this.clearSession();
                return;
            }
            this.session = normalized;
            this.ready = true;
            await Promise.all([
                authStorage.setItem(AUTH_KEY_STORAGE, normalized.key),
                authStorage.setItem(AUTH_SESSION_STORAGE, normalized),
            ]);
        },

        async clearSession() {
            this.session = null;
            this.ready = true;
            await Promise.all([
                authStorage.removeItem(AUTH_KEY_STORAGE),
                authStorage.removeItem(AUTH_SESSION_STORAGE),
            ]);
        },

        /** 当前密钥，供需要显示或复制的地方使用。 */
        async authKey(): Promise<string> {
            return this.session?.key || (await getStoredAuthKey());
        },
    },
});
