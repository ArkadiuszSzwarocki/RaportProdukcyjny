(function (global) {
    'use strict';

    if (global.dashboardScheduler) {
        return;
    }

    function createScheduler() {
        var tasks = new Map();
        var timerId = null;
        var tickMs = 250;

        function runTask(task, now) {
            if (!task.enabled || task.running || now < task.nextRunAt) {
                return;
            }

            task.nextRunAt = now + task.intervalMs;
            task.running = true;

            try {
                var result = task.callback({
                    now: now,
                    name: task.name,
                    scheduler: api,
                });
                if (result && typeof result.finally === 'function') {
                    result.finally(function () {
                        task.running = false;
                    });
                    return;
                }
            } catch (error) {
                console.error('[dashboard.scheduler] task failed:', task.name, error);
            }

            task.running = false;
        }

        function tick() {
            var now = Date.now();
            tasks.forEach(function (task) {
                runTask(task, now);
            });
        }

        var api = {
            addTask: function (name, intervalMs, callback, options) {
                if (!name || typeof callback !== 'function') {
                    return;
                }

                var normalizedOptions = options || {};
                var normalizedInterval = Math.max(250, Number(intervalMs) || 1000);
                var now = Date.now();
                tasks.set(name, {
                    name: name,
                    intervalMs: normalizedInterval,
                    callback: callback,
                    enabled: normalizedOptions.enabled !== false,
                    running: false,
                    nextRunAt: normalizedOptions.runImmediately === false ? now + normalizedInterval : now,
                });
            },
            removeTask: function (name) {
                tasks.delete(name);
            },
            start: function () {
                if (timerId !== null) {
                    return;
                }
                timerId = global.setInterval(tick, tickMs);
            },
            stop: function () {
                if (timerId === null) {
                    return;
                }
                global.clearInterval(timerId);
                timerId = null;
            },
        };

        return api;
    }

    global.dashboardScheduler = createScheduler();
    global.dashboardScheduler.start();
})(window);