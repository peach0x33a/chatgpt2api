import { defineStore } from "pinia";
import localforage from "localforage";

import type { ImageModel } from "@/lib/api";

export type ConversationMode = "generate" | "edit";

export type StoredReferenceImage = {
    name: string;
    type: string;
    dataUrl: string;
};

export type StoredImage = {
    id: string;
    taskId?: string;
    status?: "loading" | "success" | "error";
    taskStatus?: "queued" | "running";
    progress?: string;
    b64_json?: string;
    url?: string;
    revised_prompt?: string;
    error?: string;
    startTime?: number;
    elapsedSecs?: number;
    durationMs?: number;
};

export type TurnStatus = "queued" | "generating" | "success" | "error";

export type Turn = {
    id: string;
    prompt: string;
    model: ImageModel;
    mode: ConversationMode;
    referenceImages: StoredReferenceImage[];
    count: number;
    size: string;
    ratio: string;
    tier: string;
    quality: string;
    images: StoredImage[];
    createdAt: string;
    status: TurnStatus;
    error?: string;
};

export type Conversation = {
    id: string;
    title: string;
    createdAt: string;
    updatedAt: string;
    turns: Turn[];
};

const storage = localforage.createInstance({
    name: "chatgpt2api",
    storeName: "image_conversations",
});

const STORAGE_KEY = "items";

/** 串行化写入，避免多标签页或快速操作互相覆盖。 */
let writeQueue: Promise<void> = Promise.resolve();

function enqueueWrite(task: () => Promise<void>): Promise<void> {
    writeQueue = writeQueue.then(task, task);
    return writeQueue;
}

function normalizeConversation(raw: unknown): Conversation | null {
    if (!raw || typeof raw !== "object") {
        return null;
    }
    const item = raw as Partial<Conversation>;
    const id = String(item.id || "").trim();
    if (!id) {
        return null;
    }
    const turns = Array.isArray(item.turns) ? (item.turns as Turn[]) : [];
    const createdAt = String(item.createdAt || new Date().toISOString());
    return {
        id,
        title: String(item.title || "未命名会话"),
        createdAt,
        updatedAt: String(item.updatedAt || createdAt),
        turns,
    };
}

function sortConversations(items: Conversation[]): Conversation[] {
    return [...items].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}

export const useConversationStore = defineStore("conversations", {
    state: () => ({
        items: [] as Conversation[],
        loaded: false,
    }),

    getters: {
        sorted: (state) => sortConversations(state.items),
        byId: (state) => (id: string | null) =>
            id ? state.items.find((item) => item.id === id) ?? null : null,
    },

    actions: {
        async load() {
            try {
                const raw = await storage.getItem<unknown[]>(STORAGE_KEY);
                const items = Array.isArray(raw)
                    ? raw.map(normalizeConversation).filter((item): item is Conversation => item !== null)
                    : [];
                this.items = sortConversations(items);
            } catch {
                this.items = [];
            } finally {
                this.loaded = true;
            }
        },

        async persist() {
            const snapshot = JSON.parse(JSON.stringify(this.items)) as Conversation[];
            await enqueueWrite(async () => {
                await storage.setItem(STORAGE_KEY, snapshot);
            });
        },

        async save(conversation: Conversation) {
            conversation.updatedAt = new Date().toISOString();
            const index = this.items.findIndex((item) => item.id === conversation.id);
            if (index >= 0) {
                this.items[index] = conversation;
            } else {
                this.items.unshift(conversation);
            }
            this.items = sortConversations(this.items);
            await this.persist();
        },

        async remove(id: string) {
            this.items = this.items.filter((item) => item.id !== id);
            await this.persist();
        },

        async rename(id: string, title: string) {
            const target = this.items.find((item) => item.id === id);
            if (!target) {
                return;
            }
            target.title = title.trim() || target.title;
            target.updatedAt = new Date().toISOString();
            this.items = sortConversations(this.items);
            await this.persist();
        },

        async clear() {
            this.items = [];
            await enqueueWrite(async () => {
                await storage.removeItem(STORAGE_KEY);
            });
        },
    },
});
