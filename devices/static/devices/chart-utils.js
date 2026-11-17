(function (root, factory) {
    "use strict";
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.ChartUtils = factory();
    }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function dataBounds(datasets) {
        let min = Infinity;
        let max = -Infinity;
        (datasets || []).forEach(function (dataset) {
            const data = (dataset && dataset.data) || [];
            data.forEach(function (point) {
                if (!point || typeof point.x !== "number") {
                    return;
                }
                if (point.x < min) {
                    min = point.x;
                }
                if (point.x > max) {
                    max = point.x;
                }
            });
        });
        if (!isFinite(min) || !isFinite(max) || max <= min) {
            return null;
        }
        return { min: min, max: max };
    }

    function clampSpan(range, factor, minSpan, maxSpan) {
        if (!isFinite(range) || range <= 0 || !isFinite(factor) || factor <= 0) {
            return minSpan;
        }
        const next = range * factor;
        if (!isFinite(next) || next <= 0) {
            return minSpan;
        }
        return Math.max(minSpan, Math.min(maxSpan, next));
    }

    function clampWindow(min, max, dataMin, dataMax, margin) {
        const span = max - min;
        if (!isFinite(span) || span <= 0) {
            return { min: min, max: max };
        }
        if (!isFinite(dataMin) || !isFinite(dataMax) || dataMax <= dataMin) {
            return { min: min, max: max };
        }
        const pad = isFinite(margin) ? Math.max(0, margin) : 0;
        const lo = dataMin - pad;
        const hi = dataMax + pad;
        const maxSpan = hi - lo;
        let nextSpan = span;
        if (nextSpan > maxSpan) {
            nextSpan = maxSpan;
        }
        let nextMin = (min + max) / 2 - nextSpan / 2;
        let nextMax = nextMin + nextSpan;
        if (nextMin < lo) {
            nextMin = lo;
            nextMax = lo + nextSpan;
        }
        if (nextMax > hi) {
            nextMax = hi;
            nextMin = hi - nextSpan;
        }
        return { min: nextMin, max: nextMax };
    }

    function gridStepHours(spanHours, maxTicks) {
        const limit = Math.max(1, maxTicks || 1);
        if (!isFinite(spanHours) || spanHours <= 0) {
            return 1;
        }
        return Math.max(1, Math.ceil(spanHours / limit));
    }

    function labelEvery(gridCount, targetLabels) {
        const target = Math.max(1, targetLabels || 1);
        if (!isFinite(gridCount) || gridCount <= 0) {
            return 1;
        }
        return Math.max(1, Math.ceil(gridCount / target));
    }

    function resolveResetRange(mode, baseline, dataMin, dataMax, padding) {
        if (
            mode === "report" &&
            baseline &&
            isFinite(baseline.min) &&
            isFinite(baseline.max) &&
            baseline.max > baseline.min
        ) {
            return { min: baseline.min, max: baseline.max };
        }
        if (isFinite(dataMin) && isFinite(dataMax) && dataMax > dataMin) {
            const span = dataMax - dataMin;
            const pad = isFinite(padding) ? Math.max(0, padding) : 0;
            return { min: dataMin, max: dataMax + span * pad };
        }
        return null;
    }

    return {
        dataBounds: dataBounds,
        clampSpan: clampSpan,
        clampWindow: clampWindow,
        gridStepHours: gridStepHours,
        labelEvery: labelEvery,
        resolveResetRange: resolveResetRange
    };
});
