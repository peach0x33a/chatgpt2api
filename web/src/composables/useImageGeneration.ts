import { onScopeDispose, ref } from "vue";

import {
    createImageEditTask,
    createImageGenerationTask,
    fetchImageTasks,
    type ImageTask,
} from "@/lib/api";
import { pollTasks, resumeTask, taskToPhase } from "@/lib/image-tasks";
import { createId } from "@/lib/utils";
import type { StoredImage, Turn } from "@/stores/conversations";

export type SubmitPayload = {
    turn: Turn;
    files?: File[];
};

/**
 * 生图任务的提交与轮询。
 *
 * 把「提交 → 轮询 → 回填结果」抽出来，页面只关心如何渲染 turn。
 * 组件卸载时会中止在途轮询，避免泄漏。
 */
export function useImageGeneration() {
    const controller = ref<AbortController | null>(null);
    const submitting = ref(false);

    onScopeDispose(() => {
        controller.value?.abort();
    });

    function abort() {
        controller.value?.abort();
        controller.value = null;
    }

    /**
     * 提交一次生成或编辑，并把状态写回 turn。
     *
     * onTurnChange 在每个状态变化时回调，由调用方负责持久化。
     */
    async function submit(
        payload: SubmitPayload,
        onTurnChange: (turn: Turn) => void,
    ): Promise<void> {
        const { turn, files } = payload;
        abort();
        const current = new AbortController();
        controller.value = current;
        submitting.value = true;

        try {
            // 每张图对应一个独立任务，这样可以并行生成。
            const tasks: ImageTask[] = [];
            for (const image of turn.images) {
                const taskId = image.taskId || createId("t");
                // 关键：任务 ID 必须回写到图片上，否则后续轮询与刷新恢复
                // 都无法把任务和图片对应起来，界面会永远停在「提交中」。
                image.taskId = taskId;
                const task = files && files.length > 0
                    ? await createImageEditTask(
                        taskId,
                        files,
                        turn.prompt,
                        turn.model,
                        turn.size,
                        turn.quality,
                    )
                    : await createImageGenerationTask(
                        taskId,
                        turn.prompt,
                        turn.model,
                        turn.size,
                        turn.quality,
                    );
                tasks.push(task);
            }

            applyTasks(turn, tasks);
            turn.status = "generating";
            // 先落盘一次：保证刷新页面时能拿回任务 ID 继续轮询。
            onTurnChange(turn);

            const taskIds = turn.images.map((image) => image.taskId).filter((id): id is string => Boolean(id));
            await pollTasks(taskIds, {
                signal: current.signal,
                onUpdate: (items) => {
                    applyTasks(turn, items);
                    updateTurnStatus(turn);
                    onTurnChange(turn);
                },
            });

            updateTurnStatus(turn);
            onTurnChange(turn);
        } finally {
            submitting.value = false;
            if (controller.value === current) {
                controller.value = null;
            }
        }
    }

    /** 在失败任务上继续等待，不重新消耗额度。 */
    async function continueWait(
        turn: Turn,
        taskId: string,
        onTurnChange: (turn: Turn) => void,
    ): Promise<void> {
        abort();
        const current = new AbortController();
        controller.value = current;

        const target = turn.images.find((image) => image.taskId === taskId);
        if (!target) {
            return;
        }
        target.status = "loading";
        target.error = undefined;
        turn.status = "generating";
        onTurnChange(turn);

        try {
            await resumeTask(taskId, 30);
            await pollTasks([taskId], {
                signal: current.signal,
                onUpdate: (items) => {
                    applyTasks(turn, items);
                    updateTurnStatus(turn);
                    onTurnChange(turn);
                },
            });
            updateTurnStatus(turn);
            onTurnChange(turn);
        } finally {
            if (controller.value === current) {
                controller.value = null;
            }
        }
    }

    /**
     * 接管页面加载前就已提交、但尚未结束的任务。
     * 返回后所有相关 turn 都会被回填到最新状态。
     */
    async function resumePending(
        turns: Array<{ turn: Turn; taskIds: string[] }>,
        onTurnChange: (turn: Turn) => void,
    ): Promise<void> {
        return resumePendingTasks(turns, onTurnChange);
    }

    return { submitting, submit, continueWait, resumePending, abort };
}

/**
 * 接管页面加载前就已提交、但还没结束的任务。
 *
 * 任务状态会被持久化到 localStorage，用户刷新或切走再回来时，
 * 界面上仍是「提交中」。如果没有这一步，那些任务永远停在等待态——
 * 后端其实已经完成，只是没人再去问了。
 */
async function resumePendingTasks(
    turns: Array<{ turn: Turn; taskIds: string[] }>,
    onTurnChange: (turn: Turn) => void,
): Promise<void> {
    const candidates = turns.flatMap((entry) => entry.taskIds).filter(Boolean);
    if (candidates.length === 0) {
        return;
    }

    let items: ImageTask[] = [];
    try {
        const result = await fetchImageTasks(candidates);
        items = result.items;
    } catch {
        return;
    }
    if (items.length === 0) {
        return;
    }

    // 先按任务 ID 建索引，方便把结果回填到对应的 turn。
    const byId = new Map(items.map((task) => [task.id, task]));
    for (const { turn, taskIds } of turns) {
        const related = taskIds
            .map((id) => byId.get(id))
            .filter((task): task is ImageTask => task !== undefined);
        if (related.length === 0) {
            continue;
        }
        applyTasks(turn, related);
        updateTurnStatus(turn);
        onTurnChange(turn);
    }

    // 仍有在途任务的，继续轮询到终态。
    const stillPending = items
        .filter((task) => task.status === "queued" || task.status === "running")
        .map((task) => task.id);
    if (stillPending.length === 0) {
        return;
    }

    const pendingSet = new Set(stillPending);
    await pollTasks(stillPending, {
        onUpdate: (updates) => {
            for (const { turn } of turns) {
                const related = updates.filter((task) =>
                    turn.images.some((image) => image.taskId === task.id && pendingSet.has(task.id)),
                );
                if (related.length === 0) {
                    continue;
                }
                applyTasks(turn, related);
                updateTurnStatus(turn);
                onTurnChange(turn);
            }
        },
    });
}

/** 把后端任务状态合并进 turn 的 images。 */
function applyTasks(turn: Turn, tasks: ImageTask[]) {
    for (const task of tasks) {
        const image = turn.images.find((item) => item.taskId === task.id);
        if (!image) {
            continue;
        }
        const phase = taskToPhase(task);
        switch (phase.kind) {
            case "queued":
                image.status = "loading";
                image.taskStatus = "queued";
                image.progress = "排队中";
                break;
            case "running":
                image.status = "loading";
                image.taskStatus = "running";
                image.progress = phase.progress || "生成中";
                image.elapsedSecs = phase.elapsedSecs;
                break;
            case "success": {
                image.status = "success";
                image.taskStatus = undefined;
                image.progress = undefined;
                image.error = undefined;
                image.durationMs = phase.durationMs;
                const first = phase.data[0];
                if (first) {
                    image.b64_json = first.b64_json;
                    image.url = first.url;
                    image.revised_prompt = first.revised_prompt;
                }
                break;
            }
            case "timeout":
                image.status = "error";
                image.taskStatus = undefined;
                image.progress = undefined;
                image.error = phase.message;
                image.taskId = phase.taskId;
                break;
            case "error":
                image.status = "error";
                image.taskStatus = undefined;
                image.progress = undefined;
                image.error = phase.message;
                break;
        }
    }
}

/** 汇总 turn 的整体状态。 */
function updateTurnStatus(turn: Turn) {
    const images = turn.images as StoredImage[];
    if (images.length === 0) {
        turn.status = "error";
        return;
    }
    if (images.some((image) => image.status === "loading")) {
        turn.status = "generating";
        return;
    }
    if (images.every((image) => image.status === "error")) {
        turn.status = "error";
        turn.error = images[0]?.error || "生成失败";
        return;
    }
    turn.status = "success";
    turn.error = undefined;
}
