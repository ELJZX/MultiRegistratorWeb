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

    function zoomWindow(current, factor, focalRatio, data, margin, minSpan, maxSpan) {
        const range = current && current.max - current.min;
        if (!isFinite(range) || range <= 0 || !isFinite(factor) || factor <= 0) {
            return {
                min: current ? current.min : NaN,
                max: current ? current.max : NaN
            };
        }
        const ratio = isFinite(focalRatio) ? Math.max(0, Math.min(1, focalRatio)) : 0.5;
        const focal = current.min + ratio * range;
        const nextRange = clampSpan(range, factor, minSpan, maxSpan);
        if (factor > 1 && nextRange <= range) {
            // Zooming out must never shrink the visible window (for example when
            // the current view is already larger than the maximum span).
            return { min: current.min, max: current.max };
        }
        let nextMin = focal - ratio * nextRange;
        let nextMax = nextMin + nextRange;
        if (factor < 1 && data &&
            isFinite(data.min) && isFinite(data.max) && data.max > data.min) {
            const pad = isFinite(margin) ? Math.max(0, margin) : 0;
            const clamped = clampWindow(nextMin, nextMax, data.min, data.max, pad);
            nextMin = clamped.min;
            nextMax = clamped.max;
        }
        return { min: nextMin, max: nextMax };
    }

    function niceAxis(min, max, targetTicks) {
        let lo = isFinite(min) ? min : 0;
        let hi = isFinite(max) ? max : 10;
        if (hi < lo) {
            const swap = lo;
            lo = hi;
            hi = swap;
        }
        if (!(hi - lo > 1e-9)) {
            if (Math.abs(lo) < 1e-9) {
                return { min: 0, max: 1, step: 1, precision: 0 };
            }
            const pad = Math.max(Math.abs(lo) * 0.001, 1);
            lo -= pad;
            hi += pad;
        }
        const target = Math.max(2, targetTicks || 6);
        const raw = (hi - lo) / (target - 1);
        const power = Math.pow(10, Math.floor(Math.log10(raw)));
        const norm = raw / power;
        let factor = 10;
        if (norm <= 1) {
            factor = 1;
        } else if (norm <= 2) {
            factor = 2;
        } else if (norm <= 5) {
            factor = 5;
        }
        const step = factor * power;
        const axisMin = Math.floor(lo / step) * step;
        const axisMax = Math.ceil(hi / step) * step;
        const precision = Math.max(0, Math.min(6, -Math.floor(Math.log10(step))));
        return { min: axisMin, max: axisMax, step: step, precision: precision };
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
        zoomWindow: zoomWindow,
        niceAxis: niceAxis,
        gridStepHours: gridStepHours,
        labelEvery: labelEvery,
        resolveResetRange: resolveResetRange
    };
});
