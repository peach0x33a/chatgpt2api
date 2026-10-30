import { fetchImageTasks, resumeImagePoll, type ImageTask } from "@/lib/api";
import { sleep } from "@/lib/utils";

export type TaskPhase =
    | { kind: "queued" }
    | { kind: "running"; progress: string; elapsedSecs: number }
    | { kind: "success"; data: NonNullable<ImageTask["data"]>; durationMs: number }
    | { kind: "error"; message: string; recoverable: boolean; taskId: string }
    | { kind: "timeout"; message: string; taskId: string; conversationId?: string };

/**
 * 判断一个失败任务是否可以「继续等待」。
 *
 * 判定条件与后端保持一致：错误文案含「超时」且有会话 ID。
 * 没有会话 ID 时无法复用上游会话，只能重新生成。
 */
export function isRecoverableTimeout(task: ImageTask): boolean {
    if (task.status !== "error") {
        return false;
    }
    const message = task.error || "";
    return message.includes("超时") && Boolean(task.conversation_id);
}

/** 把后端任务映射成视图需要的状态。 */
export function taskToPhase(task: ImageTask): TaskPhase {
    switch (task.status) {
        case "queued":
            return { kind: "queued" };
        case "running":
            return {
                kind: "running",
                progress: task.progress || "",
                elapsedSecs: task.elapsed_secs ?? 0,
            };
        case "success":
            return {
                kind: "success",
                data: task.data || [],
                durationMs: task.duration_ms ?? 0,
            };
        default:
            if (isRecoverableTimeout(task)) {
                return {
                    kind: "timeout",
                    message: task.error || "生图超时",
                    taskId: task.id,
                    conversationId: task.conversation_id,
                };
            }
            return {
                kind: "error",
                message: task.error || "生成失败",
                recoverable: Boolean(task.conversation_id),
                taskId: task.id,
            };
    }
}

export type PollOptions = {
    /** 轮询间隔，默认 2 秒。 */
    intervalMs?: number;
    /** 单次轮询的整体超时，默认 20 分钟。 */
    timeoutMs?: number;
    signal?: AbortSignal;
    onUpdate: (tasks: ImageTask[]) => void;
    onMissing?: (taskIds: string[]) => void;
};

/**
 * 轮询一批图片任务直到全部进入终态。
 *
 * 关键设计：
 * - 用 setTimeout 递归而非 setInterval，避免请求堆积。
 * - 连续失败时退避，但不放弃——上游抖动很常见。
 * - 任务在后端消失（missing_ids）时回调，由调用方决定是否重新提交。
 */
export async function pollTasks(taskIds: string[], options: PollOptions): Promise<void> {
    const {
        intervalMs = 2000,
        timeoutMs = 20 * 60 * 1000,
        signal,
        onUpdate,
        onMissing,
    } = options;

    const pending = new Set(taskIds.filter(Boolean));
    if (pending.size === 0) {
        return;
    }

    const deadline = Date.now() + timeoutMs;
    let consecutiveErrors = 0;

    while (pending.size > 0 && Date.now() < deadline) {
        if (signal?.aborted) {
            return;
        }

        try {
            const result = await fetchImageTasks([...pending], signal);
            consecutiveErrors = 0;

            if (result.items.length > 0) {
                onUpdate(result.items);
                for (const task of result.items) {
                    if (task.status === "success" || task.status === "error") {
                        pending.delete(task.id);
                    }
                }
            }

            if (result.missing_ids.length > 0 && onMissing) {
                // 后端已清理这些任务，从待轮询集合移除避免死循环。
                onMissing(result.missing_ids);
                for (const id of result.missing_ids) {
                    pending.delete(id);
                }
            }
        } catch (error) {
            if (signal?.aborted) {
                return;
            }
            consecutiveErrors += 1;
            // 连续失败后逐步拉长间隔，最多 10 秒。
            if (consecutiveErrors >= 3) {
                await sleep(Math.min(intervalMs * consecutiveErrors, 10_000));
                continue;
            }
        }

        if (pending.size === 0) {
            break;
        }
        await sleep(intervalMs);
    }
}

/**
 * 请求「继续等待」：让后端在原会话上继续轮询。
 *
 * 与重新提交不同，这不会消耗新的生图额度。
 */
export async function resumeTask(taskId: string, extraTimeoutSecs = 30): Promise<ImageTask> {
    return resumeImagePoll(taskId, extraTimeoutSecs);
}
