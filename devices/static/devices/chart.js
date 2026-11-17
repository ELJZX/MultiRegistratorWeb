(function () {
    "use strict";

    const app = document.getElementById("chart-app");
    if (!app) {
        return;
    }

    const deviceId = app.dataset.deviceId;
    const startInput = document.getElementById("period-start");
    const endInput = document.getElementById("period-end");
    const canvas = document.getElementById("chart-canvas");
    const wrap = canvas.parentElement;
    const bandEl = document.getElementById("chart-select-band");
    const markersEl = document.getElementById("chart-markers");
    const readoutEl = document.getElementById("chart-readout");
    const statusEl = document.getElementById("chart-status");
    const statusPrefixEl = document.getElementById("status-prefix");
    const statusValueEl = document.getElementById("status-value");
    const legendEl = document.getElementById("chart-legend");
    const periodEl = document.getElementById("chart-period");
    const reportDateEl = document.getElementById("report-date");
    const liveBtn = document.getElementById("live-toggle");
    const gridEl = document.getElementById("grid-toggle");
    const toggles = Array.from(document.querySelectorAll(".channel-toggle"));
    const csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
    const utils = window.ChartUtils;

    const palette = [
        "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed",
        "#0891b2", "#db2777", "#65a30d", "#ca8a04", "#4f46e5"
    ];

    const LIVE_PADDING = 0.2;
    const TOP_PADDING = 0.2;
    const MIN_X_SPAN = 1000;
    const MAX_TICK_STEP = 3600 * 1000;
    const MAX_X_SPAN = 3 * 24 * 3600 * 1000;

    let chart = null;
    let units = {};
    let liveTimer = null;
    let userAdjustedX = false;
    let activePoint = null;
    let pointerDown = null;
    let panFrame = null;
    let baselineMode = "live";
    let baselineRange = null;

    if (!window.Chart) {
        setStatus("Не удалось загрузить библиотеку графиков (Chart.js).", true);
        return;
    }

    if (!utils) {
        setStatus("Не удалось загрузить модуль масштабирования графика.", true);
        return;
    }

    function setStatus(text, isError) {
        if (statusPrefixEl) {
            statusPrefixEl.style.display = "none";
        }
        if (statusValueEl) {
            statusValueEl.textContent = text || "";
        }
        statusEl.classList.toggle("error", Boolean(isError));
    }

    function setUpdated() {
        if (statusPrefixEl) {
            statusPrefixEl.style.display = "";
        }
        if (statusValueEl) {
            statusValueEl.textContent = formatTime(new Date());
        }
        statusEl.classList.remove("error");
    }

    function pad(value) {
        return String(value).padStart(2, "0");
    }

    function toLocalInput(date) {
        return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
            "T" + pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
    }

    function toIso(value) {
        if (!value) {
            return "";
        }
        const parsed = new Date(value);
        return isNaN(parsed.getTime()) ? "" : parsed.toISOString();
    }

    function formatTime(value) {
        const date = value instanceof Date ? value : new Date(value);
        if (isNaN(date.getTime())) {
            return "—";
        }
        return date.toLocaleTimeString("ru-RU", { hour12: false });
    }

    function formatPeriodValue(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (isNaN(date.getTime())) {
            return "—";
        }
        return pad(date.getDate()) + "." + pad(date.getMonth() + 1) + "." +
            String(date.getFullYear()).slice(-2) + " " +
            pad(date.getHours()) + ":" + pad(date.getMinutes());
    }

    function currentSpanMs() {
        const startMs = startInput.value ? new Date(startInput.value).getTime() : NaN;
        const endMs = endInput.value ? new Date(endInput.value).getTime() : NaN;
        if (!isNaN(startMs) && !isNaN(endMs) && endMs > startMs) {
            return endMs - startMs;
        }
        return 60 * 1000;
    }

    function setHours(hours) {
        const end = new Date();
        const start = new Date(end.getTime() - hours * 3600 * 1000);
        startInput.value = toLocalInput(start);
        endInput.value = toLocalInput(end);
    }

    function getToggle(name) {
        return toggles.find(function (item) {
            return item.value === name;
        });
    }

    function channelUnit(name) {
        return units[name] || "";
    }

    function currentXRange() {
        const options = chart.options.scales.x;
        const scale = chart.scales.x;
        let min = options.min !== undefined ? options.min : scale.min;
        let max = options.max !== undefined ? options.max : scale.max;
        if (!isFinite(min) || !isFinite(max) || max <= min) {
            return null;
        }
        return { min: min, max: max };
    }

    function visibleBounds() {
        const range = currentXRange();
        let min = Infinity;
        let max = -Infinity;
        chart.data.datasets.forEach(function (dataset) {
            if (dataset.hidden) {
                return;
            }
            dataset.data.forEach(function (point) {
                if (typeof point.y !== "number") {
                    return;
                }
                if (range && (point.x < range.min || point.x > range.max)) {
                    return;
                }
                min = Math.min(min, point.y);
                max = Math.max(max, point.y);
            });
        });
        if (min === Infinity || max === -Infinity) {
            chart.data.datasets.forEach(function (dataset) {
                if (dataset.hidden) {
                    return;
                }
                dataset.data.forEach(function (point) {
                    if (typeof point.y !== "number") {
                        return;
                    }
                    min = Math.min(min, point.y);
                    max = Math.max(max, point.y);
                });
            });
        }
        if (min === Infinity || max === -Infinity) {
            return null;
        }
        return { min: min, max: max };
    }

    function applyVisibility() {
        if (!chart) {
            return;
        }
        chart.data.datasets.forEach(function (dataset) {
            const toggle = getToggle(dataset.label);
            if (toggle) {
                dataset.hidden = !toggle.checked;
            }
        });
        renderLegend();
        applyScaleOptions();
        chart.update("none");
    }

    function renderLegend() {
        if (!chart) {
            legendEl.innerHTML = "";
            return;
        }
        legendEl.innerHTML = "";
        chart.data.datasets.forEach(function (dataset) {
            if (dataset.hidden) {
                return;
            }
            const item = document.createElement("span");
            item.className = "legend-item";
            const swatch = document.createElement("span");
            swatch.className = "legend-swatch";
            swatch.style.background = dataset.borderColor;
            const label = document.createElement("span");
            label.textContent = dataset.label + (channelUnit(dataset.label) ? " (" + channelUnit(dataset.label) + ")" : "");
            item.appendChild(swatch);
            item.appendChild(label);
            item.addEventListener("click", function () {
                const toggle = getToggle(dataset.label);
                if (toggle) {
                    toggle.checked = !toggle.checked;
                }
                applyVisibility();
            });
            legendEl.appendChild(item);
        });
    }

    function applyScaleOptions() {
        if (!chart) {
            return;
        }
        const grid = gridEl ? gridEl.classList.contains("active") : true;
        chart.options.scales.x.grid.display = grid;
        chart.options.scales.y.grid.display = grid;

        const yScale = chart.options.scales.y;
        const bounds = visibleBounds();
        if (!bounds) {
            yScale.min = 0;
            yScale.max = 10;
            applyYTickStep();
            return;
        }

        let span = bounds.max - bounds.min;
        if (!(span > 0)) {
            span = Math.max(Math.abs(bounds.max) * 0.2, 1);
        }
        const top = span * TOP_PADDING;
        let yMin = Math.floor(bounds.min);
        let yMax = Math.ceil(bounds.max + top);
        if (!(yMax > yMin)) {
            yMax = yMin + 1;
        }
        yScale.min = yMin;
        yScale.max = yMax;
        applyYTickStep();
    }

    function applyYTickStep() {
        if (!chart) {
            return;
        }
        const y = chart.options.scales.y;
        let min = y.min !== undefined ? y.min : chart.scales.y.min;
        let max = y.max !== undefined ? y.max : chart.scales.y.max;
        const range = max - min;
        let step = 1;
        if (isFinite(range) && range > 20) {
            const raw = range / 10;
            const power = Math.pow(10, Math.floor(Math.log10(raw)));
            const candidates = [1, 2, 3, 5, 10].map(function (factor) {
                return factor * power;
            });
            step = candidates.find(function (value) {
                return value >= raw;
            }) || candidates[candidates.length - 1];
            step = Math.max(1, Math.round(step));
        }
        y.ticks.stepSize = step;
        y.ticks.precision = 0;
    }

    const tickDatePlugin = {
        id: "tickDates",
        afterDraw: function (chartInstance) {
            const scale = chartInstance.scales.x;
            if (!scale || !scale.ticks || !scale.ticks.length) {
                return;
            }
            const span = scale.max - scale.min;
            if (!(span >= 48 * 3600 * 1000)) {
                return;
            }
            const items = typeof scale.getLabelItems === "function" ? scale.getLabelItems() : null;
            if (!items || !items.length) {
                return;
            }
            const ctx = chartInstance.ctx;
            const firstFont = items[0].font || {};
            ctx.save();
            ctx.fillStyle = "#6e6e73";
            ctx.font = "9px " + (firstFont.family || "sans-serif");
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            items.forEach(function (item, index) {
                const tick = scale.ticks[index];
                if (!tick || tick.value === undefined) {
                    return;
                }
                const label = item.label;
                const text = Array.isArray(label) ? label.join("") : String(label || "");
                if (!text) {
                    return;
                }
                const opts = item.options || {};
                const translation = opts.translation || [0, 0];
                const x = translation[0];
                if (x < chartInstance.chartArea.left || x > chartInstance.chartArea.right) {
                    return;
                }
                const fontSize = (item.font && item.font.size) || 12;
                const anchorY = translation[1] + (item.textOffset || 0);
                let bottom;
                switch (opts.textBaseline) {
                    case "top":
                        bottom = anchorY + fontSize;
                        break;
                    case "bottom":
                        bottom = anchorY;
                        break;
                    case "alphabetic":
                        bottom = anchorY + fontSize * 0.2;
                        break;
                    default:
                        bottom = anchorY + fontSize / 2;
                        break;
                }
                const date = new Date(tick.value);
                ctx.fillText(
                    pad(date.getDate()) + ":" + pad(date.getMonth() + 1) + ":" +
                        String(date.getFullYear()).slice(-2),
                    x,
                    bottom + 1
                );
            });
            ctx.restore();
        }
    };

    function buildChart() {
        if (chart) {
            chart.destroy();
        }
        chart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: { datasets: [] },
            plugins: [tickDatePlugin],
            options: {
                layout: { padding: { bottom: 16 } },
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                parsing: false,
                normalized: true,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    zoom: {
                        pan: {
                            enabled: false,
                            mode: "x"
                        },
                        zoom: {
                            wheel: { enabled: false },
                            pinch: { enabled: true },
                            drag: { enabled: false },
                            mode: "x",
                            onZoomComplete: function () {
                                userAdjustedX = true;
                            }
                        },
                        limits: { x: { minRange: 1000 } }
                    }
                },
                scales: {
                    x: {
                        type: "time",
                        beforeBuildTicks: function (scale) {
                            const span = scale.max - scale.min;
                            const time = scale.options.time;
                            const ticks = scale.options.ticks;
                            if (isFinite(span) && span > MAX_TICK_STEP) {
                                const spanHours = span / 3600000;
                                time.unit = "hour";
                                ticks.stepSize = utils.gridStepHours(spanHours, 600);
                                ticks.autoSkip = false;
                                ticks.maxTicksLimit = 1000;
                            } else {
                                time.unit = false;
                                ticks.stepSize = undefined;
                                ticks.autoSkip = true;
                                ticks.maxTicksLimit = 16;
                            }
                        },
                        grid: { display: true },
                        ticks: {
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 16,
                            callback: function (value, index) {
                                const span = this.max - this.min;
                                if (!isFinite(span) || span <= 0) {
                                    return "";
                                }
                                const date = new Date(value);
                                if (span <= MAX_TICK_STEP) {
                                    return pad(date.getHours()) + ":" +
                                        pad(date.getMinutes()) + ":" + pad(date.getSeconds());
                                }
                                const gridStep = (this.options.ticks && this.options.ticks.stepSize) || 1;
                                const gridCount = (span / 3600000) / gridStep;
                                const targetLabels = span >= 48 * 3600 * 1000 ? 12 : 24;
                                const labelEvery = utils.labelEvery(gridCount, targetLabels);
                                if (labelEvery > 1 && index % labelEvery !== 0) {
                                    return "";
                                }
                                return pad(date.getHours()) + ":" + pad(date.getMinutes());
                            }
                        },
                        time: {
                            minUnit: "second",
                            tooltipFormat: "HH:mm:ss",
                            displayFormats: {
                                second: "HH:mm:ss",
                                minute: "HH:mm:ss",
                                hour: "HH:mm",
                                day: "dd.MM.yyyy",
                                week: "dd.MM.yyyy",
                                month: "MM.yyyy",
                                quarter: "MM.yyyy",
                                year: "yyyy"
                            }
                        }
                    },
                    y: {
                        grid: { display: true },
                        ticks: {}
                    }
                }
            }
        });
        wrap.dataset.zoom = typeof chart.zoomScale === "function" ? "1" : "0";
        applyScaleOptions();
    }

    function resetZoom() {
        hideActiveReadout();
        if (!chart) {
            userAdjustedX = false;
            return;
        }
        delete chart.options.scales.x.min;
        delete chart.options.scales.x.max;
        chart.update("none");
        applyScaleOptions();
        chart.update("none");
        userAdjustedX = false;
    }

    function applyXRange(startMs, endMs) {
        if (!chart || userAdjustedX || pointerDown) {
            return;
        }
        chart.options.scales.x.min = startMs;
        chart.options.scales.x.max = endMs;
        applyScaleOptions();
        chart.update("none");
    }

    function nearestPoint(data, targetX) {
        if (!data || !data.length) {
            return null;
        }
        let low = 0;
        let high = data.length - 1;
        while (low < high) {
            const mid = Math.floor((low + high) / 2);
            if (data[mid].x < targetX) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }
        let best = data[low];
        if (low > 0 && Math.abs(data[low - 1].x - targetX) < Math.abs(best.x - targetX)) {
            best = data[low - 1];
        }
        return best;
    }

    function clearMarkers() {
        if (markersEl) {
            markersEl.innerHTML = "";
        }
    }

    function renderMarkers() {
        if (!markersEl || !chart || !activePoint) {
            return;
        }
        clearMarkers();
        const xValue = chart.scales.x.getValueForPixel(activePoint.x);
        if (xValue === undefined || xValue === null || isNaN(xValue)) {
            return;
        }
        chart.data.datasets.forEach(function (dataset) {
            if (dataset.hidden || !dataset.data || !dataset.data.length) {
                return;
            }
            const point = nearestPoint(dataset.data, xValue);
            if (!point || typeof point.y !== "number") {
                return;
            }
            const px = chart.scales.x.getPixelForValue(point.x);
            const py = chart.scales.y.getPixelForValue(point.y);
            const dot = document.createElement("span");
            dot.className = "chart-marker";
            dot.style.left = px + "px";
            dot.style.top = py + "px";
            dot.style.background = dataset.borderColor;
            markersEl.appendChild(dot);
        });
    }

    function hideActiveReadout() {
        activePoint = null;
        bandEl.style.display = "none";
        readoutEl.style.display = "none";
        clearMarkers();
    }

    function showMarker(px) {
        const area = chart.chartArea;
        bandEl.style.display = "block";
        bandEl.style.left = px + "px";
        bandEl.style.top = area.top + "px";
        bandEl.style.height = (area.bottom - area.top) + "px";
    }

    function updateReadout(px, py) {
        const area = chart.chartArea;
        const timeValue = chart.scales.x.getValueForPixel(px);
        if (timeValue === undefined || timeValue === null || isNaN(timeValue)) {
            readoutEl.style.display = "none";
            return;
        }

        const rows = [];
        chart.data.datasets.forEach(function (dataset) {
            if (dataset.hidden) {
                return;
            }
            const point = nearestPoint(dataset.data, timeValue);
            if (!point) {
                return;
            }
            const unit = channelUnit(dataset.label);
            const numeric = typeof point.y === "number" ? point.y.toFixed(2) : "—";
            rows.push({
                label: dataset.label,
                value: numeric + (unit ? " " + unit : "")
            });
        });

        let html = '<div class="ro-time">' + formatTime(timeValue) + "</div>";
        rows.forEach(function (row) {
            html += '<div class="ro-row"><span>' + row.label + "</span><span>" + row.value + "</span></div>";
        });
        readoutEl.innerHTML = html;
        readoutEl.style.display = "block";

        const wrapRect = wrap.getBoundingClientRect();
        const width = readoutEl.offsetWidth;
        const height = readoutEl.offsetHeight;
        let left = px + 14;
        if (left + width > wrapRect.width - 6) {
            left = px - width - 14;
        }
        left = Math.max(6, Math.min(left, wrapRect.width - width - 6));
        let top = py - height - 14;
        if (top < area.top) {
            top = py + 14;
        }
        top = Math.max(area.top, Math.min(top, wrapRect.height - height - 6));
        readoutEl.style.left = left + "px";
        readoutEl.style.top = top + "px";
    }

    function refreshActiveReadout() {
        if (!chart || !activePoint || !insideChartArea(activePoint)) {
            if (activePoint) {
                hideActiveReadout();
            }
            return;
        }
        showMarker(activePoint.x);
        updateReadout(activePoint.x, activePoint.y);
        renderMarkers();
    }

    function toCanvasPoint(event) {
        const rect = wrap.getBoundingClientRect();
        return {
            x: event.clientX - rect.left,
            y: event.clientY - rect.top
        };
    }

    function insideChartArea(point) {
        if (!chart || !chart.chartArea) {
            return false;
        }
        const area = chart.chartArea;
        return point.x >= area.left && point.x <= area.right &&
            point.y >= area.top && point.y <= area.bottom;
    }

    function distanceToSegment(px, py, ax, ay, bx, by) {
        const dx = bx - ax;
        const dy = by - ay;
        const len2 = dx * dx + dy * dy;
        let t = len2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        const cx = ax + t * dx;
        const cy = ay + t * dy;
        const ddx = px - cx;
        const ddy = py - cy;
        return Math.sqrt(ddx * ddx + ddy * ddy);
    }

    function isOnGraph(point) {
        if (!chart || !chart.chartArea || !insideChartArea(point)) {
            return false;
        }
        const xValue = chart.scales.x.getValueForPixel(point.x);
        if (xValue === undefined || xValue === null || isNaN(xValue)) {
            return false;
        }
        const threshold = 12;
        let best = Infinity;
        chart.data.datasets.forEach(function (dataset) {
            if (dataset.hidden || !dataset.data || !dataset.data.length) {
                return;
            }
            const data = dataset.data;
            let low = 0;
            let high = data.length - 1;
            while (low < high) {
                const mid = Math.floor((low + high) / 2);
                if (data[mid].x < xValue) {
                    low = mid + 1;
                } else {
                    high = mid;
                }
            }
            let index = low;
            if (index > 0 &&
                Math.abs(data[index - 1].x - xValue) < Math.abs(data[index].x - xValue)) {
                index -= 1;
            }
            const candidates = [index];
            if (index > 0) {
                candidates.push(index - 1);
            }
            if (index < data.length - 1) {
                candidates.push(index + 1);
            }
            candidates.forEach(function (idx) {
                const p = data[idx];
                if (!p || typeof p.y !== "number") {
                    return;
                }
                const px = chart.scales.x.getPixelForValue(p.x);
                const py = chart.scales.y.getPixelForValue(p.y);
                const dx = px - point.x;
                const dy = py - point.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                if (distance < best) {
                    best = distance;
                }
            });
            const startIndex = Math.max(0, index - 1);
            const endIndex = Math.min(data.length - 1, index + 1);
            for (let k = startIndex; k < endIndex; k += 1) {
                const a = data[k];
                const b = data[k + 1];
                if (!a || !b || typeof a.y !== "number" || typeof b.y !== "number") {
                    continue;
                }
                const ax = chart.scales.x.getPixelForValue(a.x);
                const ay = chart.scales.y.getPixelForValue(a.y);
                const bx = chart.scales.x.getPixelForValue(b.x);
                const by = chart.scales.y.getPixelForValue(b.y);
                const d = distanceToSegment(point.x, point.y, ax, ay, bx, by);
                if (d < best) {
                    best = d;
                }
            }
        });
        return best <= threshold;
    }

    function beginPan(point) {
        const xScale = chart.scales.x;
        const yScale = chart.scales.y;
        pointerDown = {
            mode: "pan",
            startX: point.x,
            startY: point.y,
            startXMin: xScale.min,
            startXMax: xScale.max,
            startYMin: yScale.min,
            startYMax: yScale.max,
            areaWidth: chart.chartArea.right - chart.chartArea.left,
            areaHeight: chart.chartArea.bottom - chart.chartArea.top
        };
        hideActiveReadout();
        stopLiveMode();
    }

    function schedulePanUpdate() {
        if (panFrame !== null) {
            return;
        }
        panFrame = window.requestAnimationFrame(function () {
            panFrame = null;
            if (chart) {
                chart.update("none");
            }
        });
    }

    function onWheel(event) {
        const point = toCanvasPoint(event);
        if (!chart || !insideChartArea(point)) {
            return;
        }
        event.preventDefault();
        const scale = chart.scales.x;
        const options = chart.options.scales.x;
        let min = options.min !== undefined ? options.min : scale.min;
        let max = options.max !== undefined ? options.max : scale.max;
        if (!isFinite(min) || !isFinite(max) || max <= min) {
            return;
        }
        const range = max - min;
        let delta = event.deltaY || 0;
        if (event.deltaMode === 1) {
            delta *= 16;
        } else if (event.deltaMode === 2) {
            delta *= 100;
        }
        delta = Math.max(-300, Math.min(300, delta));
        if (!delta) {
            return;
        }
        const factor = Math.exp(delta * 0.0015);
        let newRange = utils.clampSpan(range, factor, MIN_X_SPAN, MAX_X_SPAN);
        if (Math.abs(newRange - range) < 0.5) {
            return;
        }
        let focal = scale.getValueForPixel(point.x);
        if (focal === undefined || focal === null || isNaN(focal)) {
            focal = (min + max) / 2;
        }
        const ratio = (focal - min) / range;
        let newMin = focal - ratio * newRange;
        let newMax = newMin + newRange;
        const data = utils.dataBounds(chart.data.datasets);
        if (data) {
            const dataSpan = data.max - data.min;
            const margin = Math.max(dataSpan * 0.2, MIN_X_SPAN);
            const clamped = utils.clampWindow(newMin, newMax, data.min, data.max, margin);
            newMin = clamped.min;
            newMax = clamped.max;
        }
        options.min = newMin;
        options.max = newMax;

        const yScale = chart.scales.y;
        const yOptions = chart.options.scales.y;
        let yMin = yOptions.min !== undefined ? yOptions.min : yScale.min;
        let yMax = yOptions.max !== undefined ? yOptions.max : yScale.max;
        const yRange = yMax - yMin;
        if (factor < 1 && isFinite(yMin) && isFinite(yMax) && yRange > 0) {
            const newYRange = Math.max(1, yRange * factor);
            let yFocal = yScale.getValueForPixel(point.y);
            if (yFocal === undefined || yFocal === null || isNaN(yFocal)) {
                yFocal = (yMin + yMax) / 2;
            }
            const topRatio = (yMax - yFocal) / yRange;
            const newYMax = yFocal + topRatio * newYRange;
            const newYMin = newYMax - newYRange;
            yOptions.min = Math.floor(newYMin);
            yOptions.max = Math.ceil(newYMax);
            if (!(yOptions.max > yOptions.min)) {
                yOptions.max = yOptions.min + 1;
            }
        }
        applyYTickStep();
        stopLiveMode();
        userAdjustedX = true;
        chart.update("none");
    }

    function onMouseDown(event) {
        if (event.button !== 0) {
            return;
        }
        const point = toCanvasPoint(event);
        if (!insideChartArea(point)) {
            hideActiveReadout();
            return;
        }
        if (isOnGraph(point)) {
            pointerDown = { mode: "readout", x: point.x, y: point.y };
            activePoint = { x: point.x, y: point.y };
            refreshActiveReadout();
        } else {
            beginPan(point);
        }
    }

    function onMouseMove(event) {
        if (!pointerDown) {
            return;
        }
        const point = toCanvasPoint(event);
        if (pointerDown.mode === "pan") {
            const dx = point.x - pointerDown.startX;
            const rangeX = pointerDown.startXMax - pointerDown.startXMin;
            if (pointerDown.areaWidth > 0 && rangeX > 0) {
                const dt = (dx / pointerDown.areaWidth) * rangeX;
                let nextMin = pointerDown.startXMin - dt;
                let nextMax = pointerDown.startXMax - dt;
                const data = utils.dataBounds(chart.data.datasets);
                if (data) {
                    const dataSpan = data.max - data.min;
                    const margin = Math.max(dataSpan * 0.2, MIN_X_SPAN);
                    const clamped = utils.clampWindow(nextMin, nextMax, data.min, data.max, margin);
                    nextMin = clamped.min;
                    nextMax = clamped.max;
                }
                chart.options.scales.x.min = nextMin;
                chart.options.scales.x.max = nextMax;
                userAdjustedX = true;
            }
            const dy = point.y - pointerDown.startY;
            const rangeY = pointerDown.startYMax - pointerDown.startYMin;
            if (pointerDown.areaHeight > 0 && rangeY > 0) {
                const dv = (dy / pointerDown.areaHeight) * rangeY;
                chart.options.scales.y.min = pointerDown.startYMin + dv;
                chart.options.scales.y.max = pointerDown.startYMax + dv;
            }
            schedulePanUpdate();
            return;
        }
        const area = chart.chartArea;
        activePoint = {
            x: Math.max(area.left, Math.min(area.right, point.x)),
            y: Math.max(area.top, Math.min(area.bottom, point.y))
        };
        refreshActiveReadout();
    }

    function onMouseUp() {
        if (!pointerDown) {
            return;
        }
        pointerDown = null;
        hideActiveReadout();
    }

    function updateChart(payload) {
        if (!chart) {
            buildChart();
        }
        const names = Object.keys(payload.channels);
        const datasets = names.map(function (name, index) {
            const series = payload.channels[name];
            const points = [];
            for (let i = 0; i < series.times.length; i += 1) {
                const stamp = new Date(series.times[i]).getTime();
                if (!isNaN(stamp)) {
                    points.push({ x: stamp, y: series.values[i] });
                }
            }
            return {
                label: name,
                data: points,
                borderColor: palette[index % palette.length],
                backgroundColor: palette[index % palette.length],
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 0,
                pointHoverBorderWidth: 0,
                pointHitRadius: 8,
                tension: 0,
                spanGaps: true,
                hidden: false
            };
        });
        chart.data.datasets = datasets;
        applyVisibility();

        const total = datasets.reduce(function (sum, dataset) {
            return sum + dataset.data.length;
        }, 0);
        if (total === 0) {
            setStatus("Нет данных за выбранный период.");
        } else {
            setUpdated();
        }
        periodEl.textContent = formatPeriodValue(startInput.value) +
            " - " + formatPeriodValue(endInput.value);
    }

    function fetchData(reason, resetAfter, displayRange) {
        const start = toIso(startInput.value);
        const end = toIso(endInput.value);
        if (!start || !end) {
            setStatus("Укажите корректный период.", true);
            return Promise.resolve();
        }
        const url = "/api/devices/" + encodeURIComponent(deviceId) + "/data?start=" +
            encodeURIComponent(start) + "&end=" + encodeURIComponent(end) +
            "&reason=" + encodeURIComponent(reason || "manual");
        setStatus("Загрузка данных...");
        return fetch(url, { headers: { "Accept": "application/json" } })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                return response.json();
            })
            .then(function (payload) {
                updateChart(payload);
                if (resetAfter) {
                    resetZoom();
                }
                if (displayRange) {
                    applyXRange(displayRange.startMs, displayRange.endMs);
                }
                refreshActiveReadout();
            })
            .catch(function (error) {
                setStatus("Ошибка загрузки данных: " + error.message, true);
            });
    }

    function loadDeviceConfig() {
        return fetch("/api/devices/" + encodeURIComponent(deviceId), {
            headers: { "Accept": "application/json" }
        })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(function (payload) {
                if (!payload || !payload.config) {
                    return;
                }
                units = {};
                payload.config.registers.forEach(function (register) {
                    units[register.name] = register.unit || "";
                });
            })
            .catch(function () {
                units = {};
            });
    }

    function updateReportDate() {
        const now = new Date();
        reportDateEl.textContent = pad(now.getDate()) + "." + pad(now.getMonth() + 1) + "." +
            now.getFullYear() + " " +
            pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds());
    }

    function liveTick() {
        if (pointerDown) {
            return;
        }
        const span = currentSpanMs();
        const now = Date.now();
        const startMs = now - span;
        const displayEndMs = now + span * LIVE_PADDING;
        startInput.value = toLocalInput(new Date(startMs));
        endInput.value = toLocalInput(new Date(now));
        fetchData("live", false, { startMs: startMs, endMs: displayEndMs });
    }

    function setLiveButtonState(active) {
        if (!liveBtn) {
            return;
        }
        liveBtn.classList.toggle("active", active);
        liveBtn.setAttribute("aria-pressed", active ? "true" : "false");
    }

    function startLiveMode() {
        baselineMode = "live";
        baselineRange = null;
        const liveEnd = new Date();
        const liveStart = new Date(liveEnd.getTime() - 60 * 1000);
        const span = liveEnd.getTime() - liveStart.getTime();
        startInput.value = toLocalInput(liveStart);
        endInput.value = toLocalInput(liveEnd);
        setLiveButtonState(true);
        hideActiveReadout();
        userAdjustedX = false;
        if (chart) {
            chart.options.scales.x.min = liveStart.getTime();
            chart.options.scales.x.max = liveEnd.getTime() + span * LIVE_PADDING;
            applyScaleOptions();
            chart.update("none");
        }
        if (liveTimer) {
            clearInterval(liveTimer);
        }
        liveTick();
        liveTimer = setInterval(liveTick, 1000);
    }

    function stopLiveMode() {
        setLiveButtonState(false);
        if (liveTimer) {
            clearInterval(liveTimer);
            liveTimer = null;
        }
    }

    function toggleLiveMode() {
        if (liveTimer) {
            stopLiveMode();
        } else {
            startLiveMode();
        }
    }

    function buildReport() {
        stopLiveMode();
        baselineMode = "report";
        baselineRange = null;
        fetchData("manual", true, null).then(function () {
            if (chart && isFinite(chart.scales.x.min) && isFinite(chart.scales.x.max)) {
                baselineRange = { min: chart.scales.x.min, max: chart.scales.x.max };
            }
        });
    }

    function resetToDefault() {
        hideActiveReadout();
        stopLiveMode();
        if (!chart) {
            return;
        }
        const data = utils.dataBounds(chart.data.datasets);
        const padding = baselineMode === "live" ? LIVE_PADDING : 0;
        const range = utils.resolveResetRange(
            baselineMode,
            baselineRange,
            data ? data.min : NaN,
            data ? data.max : NaN,
            padding
        );
        if (!range) {
            return;
        }
        chart.options.scales.x.min = range.min;
        chart.options.scales.x.max = range.max;
        startInput.value = toLocalInput(new Date(range.min));
        endInput.value = toLocalInput(new Date(range.max));
        userAdjustedX = true;
        applyScaleOptions();
        chart.update("none");
        periodEl.textContent = formatPeriodValue(startInput.value) +
            " - " + formatPeriodValue(endInput.value);
    }

    function logPrint() {
        const channels = toggles
            .filter(function (item) {
                return item.checked;
            })
            .map(function (item) {
                return item.value;
            });
        const body = JSON.stringify({
            device_id: deviceId,
            start: startInput.value,
            end: endInput.value,
            channels: channels
        });
        const headers = { "Content-Type": "application/json" };
        if (csrfToken) {
            headers["X-CSRFToken"] = csrfToken;
        }
        fetch("/api/log/print", {
            method: "POST",
            headers: headers,
            body: body,
            keepalive: true
        }).catch(function () {
        });
    }

    document.getElementById("build-chart").addEventListener("click", buildReport);
    toggles.forEach(function (toggle) {
        toggle.addEventListener("change", applyVisibility);
    });
    if (gridEl) {
        gridEl.addEventListener("click", function () {
            const on = gridEl.classList.toggle("active");
            gridEl.setAttribute("aria-pressed", on ? "true" : "false");
            applyScaleOptions();
            if (chart) {
                chart.update("none");
            }
        });
    }
    if (liveBtn) {
        liveBtn.addEventListener("click", toggleLiveMode);
    }
    document.getElementById("reset-zoom").addEventListener("click", function () {
        resetToDefault();
    });
    document.getElementById("print-chart").addEventListener("click", function () {
        logPrint();
        updateReportDate();
        if (chart) {
            chart.resize();
        }
        window.print();
    });

    [startInput, endInput].forEach(function (input) {
        if (!input) {
            return;
        }
        input.addEventListener("focus", function () {
            stopLiveMode();
        });
    });

    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("blur", function () {
        pointerDown = null;
        hideActiveReadout();
    });
    canvas.addEventListener("dblclick", resetToDefault);

    updateReportDate();
    loadDeviceConfig().then(startLiveMode);
})();
