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

    let chart = null;
    let units = {};
    let liveTimer = null;
    let lastPayload = null;

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
            "T" + pad(date.getHours()) + ":" + pad(date.getMinutes());
    }

    function toIso(value) {
        if (!value) {
            return "";
        }
        const parsed = new Date(value);
        return isNaN(parsed.getTime()) ? "" : parsed.toISOString();
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
        chart.update();
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

        if (autoscaleEl.checked) {
            delete chart.options.scales.y.min;
            delete chart.options.scales.y.max;
        } else {
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
            if (min === Infinity) {
                min = 0;
                max = 10;
            }
            const span = Math.max(max - min, 1);
            chart.options.scales.y.min = min - span * 0.05;
            chart.options.scales.y.max = max + span * 0.15;
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
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const unit = channelUnit(context.dataset.label);
                                const value = context.parsed.y;
                                return context.dataset.label + ": " +
                                    (value === null || value === undefined ? "—" : Number(value).toFixed(2)) +
                                    (unit ? " " + unit : "");
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: "time",
                        grid: { display: true },
                        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 16 },
                        time: { tooltipFormat: "dd.MM.yyyy HH:mm:ss" }
                    },
                    y: {
                        grid: { display: true },
                        ticks: {}
                    }
                }
            }
        });
        applyScaleOptions();
    }

    function updateChart(payload) {
        lastPayload = payload;
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
            setStatus("Точек на графике: " + total + ". Обновлено: " + new Date().toLocaleTimeString("ru-RU"));
        }
        periodEl.textContent = (startInput.value || "—") + "  →  " + (endInput.value || "—");
    }

    function fetchData() {
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

    function toggleLiveMode() {
        const active = liveEl.checked;
        liveEl.classList.toggle("active", active);
        if (liveTimer) {
            clearInterval(liveTimer);
            liveTimer = null;
        }
        if (active) {
            if (!startInput.value || !endInput.value) {
                setHours(1);
            }
            fetchData();
            liveTimer = setInterval(fetchData, 2000);
        }
    }

    document.getElementById("build-chart").addEventListener("click", fetchData);
    document.querySelectorAll(".quick-range .btn").forEach(function (button) {
        button.addEventListener("click", function () {
            setHours(Number(button.dataset.hours));
            fetchData();
        });
    });
    toggles.forEach(function (toggle) {
        toggle.addEventListener("change", applyVisibility);
    });
    autoscaleEl.addEventListener("change", function () {
        applyScaleOptions();
        if (chart) {
            chart.update();
        }
    });
    gridEl.addEventListener("change", function () {
        applyScaleOptions();
        if (chart) {
            chart.update();
        }
    });
    liveEl.addEventListener("change", toggleLiveMode);
    document.getElementById("print-chart").addEventListener("click", function () {
        updateReportDate();
        if (chart) {
            chart.resize();
        }
        window.print();
    });

    updateReportDate();
    loadDeviceConfig().then(fetchData);
})();
