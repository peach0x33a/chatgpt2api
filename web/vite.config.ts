import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const target = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
    plugins: [vue(), tailwindcss()],
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    server: {
        host: "0.0.0.0",
        port: 5173,
        // 开发时把 API 请求代理到后端，避免 CORS 与手动改 base URL。
        proxy: {
            // 登录接口在 /auth/* 下，不在 /api 前缀内，必须单独代理。
            "/auth": {
                target: target,
                // 改写 Host 为后端自身：后端生成的图片 URL 会是稳定可预测的内部地址，
                // 前端 assetUrl 再把它归一化成同源路径，避免内网 IP 泄漏到客户端。
                changeOrigin: true,
            },
            "/api": {
                target: target,
                // 改写 Host 为后端自身：后端生成的图片 URL 会是稳定可预测的内部地址，
                // 前端 assetUrl 再把它归一化成同源路径，避免内网 IP 泄漏到客户端。
                changeOrigin: true,
            },
            "/v1": {
                target: target,
                // 改写 Host 为后端自身：后端生成的图片 URL 会是稳定可预测的内部地址，
                // 前端 assetUrl 再把它归一化成同源路径，避免内网 IP 泄漏到客户端。
                changeOrigin: true,
            },
            "/images": {
                target: target,
                // 改写 Host 为后端自身：后端生成的图片 URL 会是稳定可预测的内部地址，
                // 前端 assetUrl 再把它归一化成同源路径，避免内网 IP 泄漏到客户端。
                changeOrigin: true,
            },
            "/image-thumbnails": {
                target: target,
                // 改写 Host 为后端自身：后端生成的图片 URL 会是稳定可预测的内部地址，
                // 前端 assetUrl 再把它归一化成同源路径，避免内网 IP 泄漏到客户端。
                changeOrigin: true,
            },
            "/files": {
                target: target,
                // 改写 Host 为后端自身：后端生成的图片 URL 会是稳定可预测的内部地址，
                // 前端 assetUrl 再把它归一化成同源路径，避免内网 IP 泄漏到客户端。
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "dist",
        // 单页应用，交由后端做 fallback。
        sourcemap: false,
    },
});
