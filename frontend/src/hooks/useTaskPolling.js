import { useState, useRef, useEffect } from "react";
import api from "../services/api";
import { showToast } from "../services/toast";

export function useTaskPolling() {
    const [activeTasks, setActiveTasks] = useState({});
    const intervalsRef = useRef({});

    const timeoutsRef = useRef({});

    // Cleanup intervals and timeouts on unmount
    useEffect(() => {
        return () => {
            Object.values(intervalsRef.current).forEach(clearInterval);
            Object.values(timeoutsRef.current).forEach(clearTimeout);
        };
    }, []);

    const pollTask = (taskId, successMsg, callback) => {
        if (activeTasks[taskId]) return;

        showToast("Background operation started...", "info");
        setActiveTasks((prev) => ({
            ...prev,
            [taskId]: {
                task_id: taskId,
                name: "Loading operation details...",
                status: "running",
                progress: "Initializing..."
            }
        }));

        const checkTask = async () => {
            try {
                const task = await api.getTaskStatus(taskId);

                setActiveTasks((prev) => {
                    if (!prev[taskId]) return prev;
                    return { ...prev, [taskId]: task };
                });

                if (task.status === "completed") {
                    clearInterval(intervalsRef.current[taskId]);
                    delete intervalsRef.current[taskId];
                    setActiveTasks((prev) => {
                        const next = { ...prev };
                        delete next[taskId];
                        return next;
                    });
                    showToast(successMsg, "success");
                    if (callback) callback(task.result);
                    return true;
                } else if (task.status === "failed") {
                    clearInterval(intervalsRef.current[taskId]);
                    delete intervalsRef.current[taskId];
                    setActiveTasks((prev) => {
                        const next = { ...prev };
                        delete next[taskId];
                        return next;
                    });
                    showToast(`Operation failed: ${task.error}`, "error");
                    if (callback) callback(null, task.error);
                    return true;
                }
            } catch (error) {
                clearInterval(intervalsRef.current[taskId]);
                delete intervalsRef.current[taskId];
                setActiveTasks((prev) => {
                    const next = { ...prev };
                    delete next[taskId];
                    return next;
                });
                showToast(`Task tracking error: ${error.message}`, "error");
                return true;
            }
            return false;
        };

        checkTask().then((finished) => {
            if (finished) return;
            const interval = setInterval(checkTask, 2000);
            intervalsRef.current[taskId] = interval;
        });
    };

    const pollTaskWithDelay = (taskId, successMsg, callback, delayMs = 0) => {
        if (activeTasks[taskId]) return;

        if (delayMs > 0) {
            const timeoutId = setTimeout(() => {
                delete timeoutsRef.current[taskId];
                pollTask(taskId, successMsg, callback);
            }, delayMs);
            timeoutsRef.current[taskId] = timeoutId;
        } else {
            pollTask(taskId, successMsg, callback);
        }
    };

    return {
        pollTask,
        pollTaskWithDelay,
        isPolling: Object.keys(activeTasks).length > 0,
        activeTasks
    };
}
