import axios, { AxiosError, type AxiosRequestConfig } from "axios";

import { getStoredAuthKey, useAuthStore } from "@/stores/auth";

export const API_BASE: string = import.meta.env.VITE_API_URL ?? "";

type RequestConfig = AxiosRequestConfig & {
    /** 401 时是否跳转登录页。轮询类请求通常应设为 false。 */
    redirectOnUnauthorized?: boolean;
};

type ErrorPayload = {
    detail?: unknown;
    error?: unknown;
    message?: string;
};

/** 递归提取后端错误体里的可读文案。 */
function errorMessageFrom(value: unknown): string {
    if (typeof value === "string") {
        return value;
    }
    if (!value || typeof value !== "object") {
        return "";
    }
    const item = value as { error?: unknown; message?: unknown };
    if (typeof item.message === "string" && item.message) {
        return item.message;
    }
    return errorMessageFrom(item.error);
}

export const request = axios.create({
    baseURL: API_BASE.replace(/\/$/, ""),
});

request.interceptors.request.use(async (config) => {
    const next = { ...config };
    const authKey = await getStoredAuthKey();
    const headers = { ...(next.headers || {}) } as Record<string, string>;
    if (authKey && !headers.Authorization) {
        headers.Authorization = `Bearer ${authKey}`;
    }
    // @ts-expect-error axios 的 headers 类型过窄，这里按普通对象处理。
    next.headers = headers;
    return next;
});

request.interceptors.response.use(
    (response) => response,
    async (error: AxiosError<ErrorPayload>) => {
        const status = error.response?.status;
        const shouldRedirect =
            (error.config as RequestConfig | undefined)?.redirectOnUnauthorized !== false;

        if (status === 401 && shouldRedirect) {
            const auth = useAuthStore();
            await auth.clearSession();
            // 交给路由守卫处理跳转，避免整页刷新丢失状态。
            if (!window.location.pathname.startsWith("/login")) {
                window.location.assign("/login");
            }
            return new Promise(() => {});
        }

        const payload = error.response?.data;
        const message =
            errorMessageFrom(payload?.detail) ||
            errorMessageFrom(payload?.error) ||
            payload?.message ||
            error.message ||
            `请求失败 (${status || 500})`;
        return Promise.reject(new Error(message));
    },
);

export type RequestOptions = {
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
    redirectOnUnauthorized?: boolean;
    signal?: AbortSignal;
};

/** 统一的请求入口，返回已解包的业务数据。 */
export async function httpRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, headers, redirectOnUnauthorized = true, signal } = options;
    const config: RequestConfig = {
        url: path,
        method,
        data: body,
        headers,
        redirectOnUnauthorized,
        signal,
    };
    const response = await request.request<T>(config);
    return response.data;
}

/** 构造静态资源（图片、文件）的完整地址。 */
export function assetUrl(path: string): string {
    if (!path) {
        return "";
    }
    if (path.startsWith("data:") || path.startsWith("blob:")) {
        return path;
    }
    if (/^https?:\/\//.test(path)) {
        return normalizeAssetOrigin(path);
    }
    const base = API_BASE.replace(/\/$/, "");
    return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

/**
 * 把后端返回的绝对地址归一化。
 *
 * 后端的图片 URL 是「按请求 Host 推导」的。经过反向代理或从其他设备访问时，
 * 后端看到的 Host 可能是 127.0.0.1:8090 这类内部地址 —— 客户端拿到这种地址
 * 就会去连自己的机器，图片必然失败。这里统一改成同源相对路径，
 * 由当前页面的源去转发，从而在任何访问方式下都能加载。
 */
function normalizeAssetOrigin(url: string): string {
    try {
        const parsed = new URL(url, window.location.origin);
        const current = window.location;
        const isSameOrigin = parsed.origin === current.origin;

        // 指向本机回环但端口不同，或端口是后端端口：视为内部地址，改走同源。
        const isLoopback =
            parsed.hostname === "127.0.0.1" ||
            parsed.hostname === "localhost" ||
            parsed.hostname === "0.0.0.0";

        if (isSameOrigin) {
            return parsed.pathname + parsed.search;
        }
        if (isLoopback) {
            return parsed.pathname + parsed.search;
        }
        return url;
    } catch {
        return url;
    }
}
