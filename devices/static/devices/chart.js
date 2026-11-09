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
    const readoutEl = document.getElementById("chart-readout");
    const statusEl = document.getElementById("chart-status");
    const legendEl = document.getElementById("chart-legend");
    const periodEl = document.getElementById("chart-period");
    const reportDateEl = document.getElementById("report-date");
    const liveEl = document.getElementById("live-mode");
    const autoscaleEl = document.getElementById("autoscale");
    const gridEl = document.getElementById("show-grid");
    const toggles = Array.from(document.querySelectorAll(".channel-toggle"));

    const palette = [
        "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed",
        "#0891b2", "#db2777", "#65a30d", "#ca8a04", "#4f46e5"
    ];

    const LIVE_PADDING = 0.2;
    const TOP_PADDING = 0.2;

    let chart = null;
    let units = {};
    let liveTimer = null;
    let userAdjustedX = false;
    let activePoint = null;
    let pointerDown = null;

    if (!window.Chart) {
        setStatus("Не удалось загрузить библиотеку графиков (Chart.js).", true);
        return;
    }

    function setStatus(text, isError) {
        statusEl.textContent = text || "";
        statusEl.classList.toggle("error", Boolean(isError));
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

    function currentSpanMs() {
        const startMs = startInput.value ? new Date(startInput.value).getTime() : NaN;
        const endMs = endInput.value ? new Date(endInput.value).getTime() : NaN;
        if (!isNaN(startMs) && !isNaN(endMs) && endMs > startMs) {
            return endMs - startMs;
        }
        return 3600 * 1000;
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

    function visibleBounds() {
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
                min = Math.min(min, point.y);
                max = Math.max(max, point.y);
            });
        });
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
            const item = document.createElement("span");
            item.className = "legend-item";
            item.style.opacity = dataset.hidden ? "0.35" : "1";
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
        const grid = gridEl.checked;
        chart.options.scales.x.grid.display = grid;
        chart.options.scales.y.grid.display = grid;

        const bounds = visibleBounds();
        if (!bounds) {
            chart.options.scales.y.min = 0;
            chart.options.scales.y.max = 10;
            return;
        }

        let span = bounds.max - bounds.min;
        if (!(span > 0)) {
            span = Math.max(Math.abs(bounds.max) * 0.2, 1);
        }
        const top = span * TOP_PADDING;
        if (autoscaleEl.checked) {
            chart.options.scales.y.min = bounds.min;
            chart.options.scales.y.max = bounds.max + top;
        } else {
            chart.options.scales.y.min = bounds.min - span * 0.05;
            chart.options.scales.y.max = bounds.max + top;
        }
    }

    function buildChart() {
        if (chart) {
            chart.destroy();
        }
        chart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: { datasets: [] },
            options: {
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
                            enabled: true,
                            mode: "x",
                            threshold: 5,
                            onPanComplete: function () {
                                userAdjustedX = true;
                            }
                        },
                        zoom: {
                            wheel: { enabled: true, speed: 0.12 },
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
                        grid: { display: true },
                        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 16 },
                        time: {
                            tooltipFormat: "HH:mm:ss",
                            displayFormats: {
                                millisecond: "HH:mm:ss.SSS",
                                second: "HH:mm:ss",
                                minute: "HH:mm:ss",
                                hour: "HH:mm:ss",
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
        if (typeof chart.resetZoom === "function") {
            chart.resetZoom();
        } else {
            delete chart.options.scales.x.min;
            delete chart.options.scales.x.max;
            chart.update("none");
        }
        userAdjustedX = false;
    }

    function applyXRange(startMs, endMs) {
        if (!chart || userAdjustedX) {
            return;
        }
        chart.options.scales.x.min = startMs;
        chart.options.scales.x.max = endMs;
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

    function hideActiveReadout() {
        activePoint = null;
        bandEl.style.display = "none";
        readoutEl.style.display = "none";
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

    function onMouseDown(event) {
        if (event.button !== 0) {
            return;
        }
        const point = toCanvasPoint(event);
        if (!insideChartArea(point)) {
            hideActiveReadout();
            return;
        }
        pointerDown = { x: point.x, y: point.y, moved: false };
        activePoint = { x: point.x, y: point.y };
        canvas.style.cursor = "grabbing";
        refreshActiveReadout();
    }

    function onMouseMove(event) {
        if (!pointerDown) {
            return;
        }
        const point = toCanvasPoint(event);
        if (Math.abs(point.x - pointerDown.x) > 3 || Math.abs(point.y - pointerDown.y) > 3) {
            pointerDown.moved = true;
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
        canvas.style.cursor = "grab";
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
                pointHitRadius: 8,
                tension: 0.15,
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
            setStatus("Точек на графике: " + total + ". Обновлено: " + formatTime(new Date()));
        }
        periodEl.textContent = (startInput.value || "—") + "  →  " + (endInput.value || "—");
    }

    function fetchData(resetAfter, displayRange) {
        const start = toIso(startInput.value);
        const end = toIso(endInput.value);
        if (!start || !end) {
            setStatus("Укажите корректный период.", true);
            return Promise.resolve();
        }
        const url = "/api/devices/" + encodeURIComponent(deviceId) + "/data?start=" +
            encodeURIComponent(start) + "&end=" + encodeURIComponent(end);
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
        reportDateEl.textContent = new Date().toLocaleString("ru-RU");
    }

    function liveTick() {
        const span = currentSpanMs();
        const now = Date.now();
        const startMs = now - span;
        const displayEndMs = now + span * LIVE_PADDING;
        startInput.value = toLocalInput(new Date(startMs));
        endInput.value = toLocalInput(new Date(now));
        fetchData(false, { startMs: startMs, endMs: displayEndMs });
    }

    function startLiveMode() {
        liveEl.checked = true;
        liveEl.classList.add("active");
        hideActiveReadout();
        resetZoom();
        userAdjustedX = false;
        if (liveTimer) {
            clearInterval(liveTimer);
        }
        liveTick();
        liveTimer = setInterval(liveTick, 1000);
    }

    function stopLiveMode() {
        liveEl.checked = false;
        liveEl.classList.remove("active");
        if (liveTimer) {
            clearInterval(liveTimer);
            liveTimer = null;
        }
    }

    function toggleLiveMode() {
        if (liveEl.checked) {
            startLiveMode();
        } else {
            stopLiveMode();
        }
    }

    function buildReport() {
        stopLiveMode();
        fetchData(true, null);
    }

    document.getElementById("build-chart").addEventListener("click", buildReport);
    document.querySelectorAll(".quick-range .btn").forEach(function (button) {
        button.addEventListener("click", function () {
            setHours(Number(button.dataset.hours));
            buildReport();
        });
    });
    toggles.forEach(function (toggle) {
        toggle.addEventListener("change", applyVisibility);
    });
    autoscaleEl.addEventListener("change", function () {
        applyScaleOptions();
        if (chart) {
            chart.update("none");
        }
    });
    gridEl.addEventListener("change", function () {
        applyScaleOptions();
        if (chart) {
            chart.update("none");
        }
    });
    liveEl.addEventListener("change", toggleLiveMode);
    document.getElementById("reset-zoom").addEventListener("click", function () {
        resetZoom();
    });
    document.getElementById("print-chart").addEventListener("click", function () {
        updateReportDate();
        if (chart) {
            chart.resize();
        }
        window.print();
    });

    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("blur", function () {
        pointerDown = null;
        hideActiveReadout();
    });
    canvas.addEventListener("dblclick", resetZoom);
    canvas.style.cursor = "grab";

    updateReportDate();
    loadDeviceConfig().then(startLiveMode);
})();
