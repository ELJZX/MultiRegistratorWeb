const test = require("node:test");
const assert = require("node:assert/strict");

const utils = require("../../static/devices/chart-utils.js");

test("dataBounds: empty datasets", function () {
    assert.equal(utils.dataBounds([]), null);
    assert.equal(utils.dataBounds(null), null);
    assert.equal(utils.dataBounds([{ data: [] }]), null);
});

test("dataBounds: ignores invalid points and finds min/max", function () {
    const datasets = [
        { data: [{ x: 300, y: 1 }, { x: 100, y: 2 }, { x: null, y: 3 }] },
        { data: [{ x: 500, y: 4 }, { x: 200, y: 5 }] }
    ];
    assert.deepEqual(utils.dataBounds(datasets), { min: 100, max: 500 });
});

test("dataBounds: a single point has no width", function () {
    assert.equal(utils.dataBounds([{ data: [{ x: 100, y: 1 }] }]), null);
});

test("clampSpan: zooms in and out within limits", function () {
    assert.equal(utils.clampSpan(60000, 2, 1000, 7200000), 120000);
    assert.equal(utils.clampSpan(1000, 2, 1000, 7200000), 2000);
});

test("clampSpan: respects minimum and maximum", function () {
    assert.equal(utils.clampSpan(1000, 0.1, 1000, 7200000), 1000);
    assert.equal(utils.clampSpan(6000000, 10, 1000, 7200000), 7200000);
});

test("clampSpan: invalid input falls back to minimum", function () {
    assert.equal(utils.clampSpan(NaN, 2, 1000, 7200000), 1000);
    assert.equal(utils.clampSpan(1000, NaN, 1000, 7200000), 1000);
    assert.equal(utils.clampSpan(-1, 2, 1000, 7200000), 1000);
});

test("clampSpan: maximum zoom-out is three days", function () {
    const threeDays = 3 * 24 * 3600 * 1000;
    assert.equal(utils.clampSpan(86400000, 10, 1000, threeDays), threeDays);
});

test("clampWindow: keeps the live padding window unchanged", function () {
    // 60 s of data, 20% margin on each side = 84 s allowed.
    const result = utils.clampWindow(0, 72000, 0, 60000, 12000);
    assert.equal(result.min, 0);
    assert.equal(result.max, 72000);
});

test("clampWindow: shrinks oversized windows to the data extent", function () {
    const result = utils.clampWindow(0, 7200000, 0, 60000, 12000);
    assert.equal(result.max - result.min, 84000);
});

test("clampWindow: centers a smaller window", function () {
    const result = utils.clampWindow(25000, 35000, 0, 60000, 6000);
    assert.equal(result.min, 25000);
    assert.equal(result.max, 35000);
});

test("clampWindow: clamps to the left and right edges", function () {
    const left = utils.clampWindow(-50000, -40000, 0, 60000, 12000);
    assert.equal(left.min, -12000);
    assert.equal(left.max - left.min, 10000);

    const right = utils.clampWindow(90000, 100000, 0, 60000, 12000);
    assert.equal(right.max, 72000);
    assert.equal(right.max - right.min, 10000);
});

test("clampWindow: invalid data bounds leave the window unchanged", function () {
    assert.deepEqual(utils.clampWindow(1, 2, NaN, NaN, 1), { min: 1, max: 2 });
    assert.deepEqual(utils.clampWindow(1, 2, 5, 5, 1), { min: 1, max: 2 });
});

test("niceAxis: rounds large ranges to readable steps", function () {
    const axis = utils.niceAxis(0, 73803, 8);
    assert.equal(axis.min, 0);
    assert.equal(axis.max, 80000);
    assert.equal(axis.step, 20000);
    assert.equal(axis.precision, 0);
});

test("niceAxis: keeps small value ranges readable", function () {
    const axis = utils.niceAxis(24.16, 28.04, 8);
    assert.equal(axis.min, 24);
    assert.equal(axis.max, 29);
    assert.equal(axis.step, 1);
    assert.equal(axis.precision, 0);
});

test("niceAxis: supports fractional steps", function () {
    const axis = utils.niceAxis(0.0012, 0.0048, 6);
    assert.ok(axis.step <= 0.001);
    assert.ok(axis.precision >= 3);
    assert.ok(axis.max > 0.0048);
});

test("niceAxis: zero values get a unit range", function () {
    const axis = utils.niceAxis(0, 0, 6);
    assert.deepEqual(axis, { min: 0, max: 1, step: 1, precision: 0 });
});

test("niceAxis: constant values get a window around them", function () {
    const axis = utils.niceAxis(61444, 61444, 6);
    assert.ok(axis.min < 61444);
    assert.ok(axis.max > 61444);
    assert.ok(axis.step > 0);
});

test("gridStepHours: stays hourly up to 600 hours", function () {
    assert.equal(utils.gridStepHours(1, 600), 1);
    assert.equal(utils.gridStepHours(24, 600), 1);
    assert.equal(utils.gridStepHours(600, 600), 1);
});

test("gridStepHours: grows for larger spans", function () {
    assert.equal(utils.gridStepHours(601, 600), 2);
    assert.equal(utils.gridStepHours(8760, 600), 15);
});

test("gridStepHours: invalid input uses one hour", function () {
    assert.equal(utils.gridStepHours(0, 600), 1);
    assert.equal(utils.gridStepHours(NaN, 600), 1);
});

test("labelEvery: small grids keep every label", function () {
    assert.equal(utils.labelEvery(10, 12), 1);
    assert.equal(utils.labelEvery(12, 12), 1);
});

test("labelEvery: thins dense labels", function () {
    assert.equal(utils.labelEvery(48, 12), 4);
    assert.equal(utils.labelEvery(360, 12), 30);
});

test("labelEvery: invalid input uses every label", function () {
    assert.equal(utils.labelEvery(0, 12), 1);
    assert.equal(utils.labelEvery(NaN, 12), 1);
});

test("zoomWindow: zooming out grows the window without shrinking to data", function () {
    // Live view is 72 s wide, but only 60 s of data are loaded (84 s with margin).
    const result = utils.zoomWindow(
        { min: 0, max: 72000 }, 1.2, 0.5,
        { min: 0, max: 60000 }, 12000, 1000, 3 * 24 * 3600 * 1000
    );
    assert.equal(result.max - result.min, 86400);
    assert.equal(result.min, -7200);
});

test("zoomWindow: zooming out from a sparse live window never shrinks it", function () {
    // 30 s of data in a 72 s live view: the old data clamp produced a 42 s window.
    let view = { min: 0, max: 72000 };
    const data = { min: 0, max: 30000 };
    const max = 3 * 24 * 3600 * 1000;
    for (let i = 0; i < 10; i += 1) {
        view = utils.zoomWindow(view, 0.8, 0.5, data, 6000, 1000, max);
    }
    for (let i = 0; i < 40; i += 1) {
        view = utils.zoomWindow(view, 1.25, 0.5, data, 6000, 1000, max);
    }
    assert.ok(view.max - view.min >= 72000, "zoom-out returned below the start view");
});

test("zoomWindow: zooming out at the maximum span keeps the current view", function () {
    const threeDays = 3 * 24 * 3600 * 1000;
    const fourDays = 4 * 24 * 3600 * 1000;
    const result = utils.zoomWindow(
        { min: 0, max: fourDays }, 1.2, 0.5,
        { min: 0, max: fourDays }, 0, 1000, threeDays
    );
    assert.equal(result.min, 0);
    assert.equal(result.max, fourDays);
});

test("zoomWindow: zooming in still clamps to the loaded data", function () {
    const result = utils.zoomWindow(
        { min: 0, max: 60000 }, 0.5, 0, { min: 0, max: 60000 }, 12000, 1000,
        3 * 24 * 3600 * 1000
    );
    assert.equal(result.min, 0);
    assert.equal(result.max, 30000);
});

test("zoomWindow: a view wider than the limit stays zoomable and reversible", function () {
    // chart.js raises the limit to the initial report span, so a four-day
    // report can be zoomed in and restored without being cut to three days.
    const fourDays = 4 * 24 * 3600 * 1000;
    let view = { min: 0, max: fourDays };
    const data = { min: 0, max: fourDays };
    view = utils.zoomWindow(view, 0.8, 0.5, data, 0, 1000, fourDays);
    assert.ok(view.max - view.min < fourDays, "zoom-in did not work");
    view = utils.zoomWindow(view, 1.25, 0.5, data, 0, 1000, fourDays);
    assert.ok(
        Math.abs((view.max - view.min) - fourDays) < 1,
        "zoom-out did not return to the initial four-day view"
    );
});

test("zoomWindow: a limit below the current span never shrinks it", function () {
    const threeDays = 3 * 24 * 3600 * 1000;
    const fourDays = 4 * 24 * 3600 * 1000;
    const result = utils.zoomWindow(
        { min: 0, max: fourDays }, 1.25, 0.5, { min: 0, max: fourDays },
        0, 1000, threeDays
    );
    assert.equal(result.min, 0);
    assert.equal(result.max, fourDays);
});

test("zoomWindow: keeps the cursor focal point inside the data", function () {
    const result = utils.zoomWindow(
        { min: 0, max: 60000 }, 0.5, 0.5, { min: 0, max: 60000 }, 6000, 1000,
        3 * 24 * 3600 * 1000
    );
    assert.equal(result.min, 15000);
    assert.equal(result.max, 45000);
});

test("zoomWindow: invalid input leaves the window untouched", function () {
    const current = { min: 10, max: 20 };
    assert.deepEqual(utils.zoomWindow(current, NaN, 0.5, null, 0, 1, 100), {
        min: 10, max: 20
    });
    assert.deepEqual(utils.zoomWindow({ min: 5, max: 5 }, 2, 0.5, null, 0, 1, 100), {
        min: 5, max: 5
    });
});

test("resolveResetRange: report returns the last built range", function () {
    const result = utils.resolveResetRange("report", { min: 100, max: 900 }, 0, 1000, 0);
    assert.deepEqual(result, { min: 100, max: 900 });
});

test("resolveResetRange: report without baseline fits the data", function () {
    const result = utils.resolveResetRange("report", null, 100, 900, 0);
    assert.deepEqual(result, { min: 100, max: 900 });
});

test("resolveResetRange: live fits data and keeps right padding", function () {
    const result = utils.resolveResetRange("live", null, 0, 60000, 0.2);
    assert.equal(result.min, 0);
    assert.equal(result.max, 72000);
});

test("resolveResetRange: live prefers the last live window over loaded data", function () {
    const result = utils.resolveResetRange(
        "live", { min: 0, max: 72000 }, 0, 3 * 24 * 3600 * 1000, 0.2
    );
    assert.deepEqual(result, { min: 0, max: 72000 });
});

test("resolveResetRange: invalid baseline falls back to data", function () {
    const result = utils.resolveResetRange("report", { min: 5, max: 5 }, 100, 900, 0);
    assert.deepEqual(result, { min: 100, max: 900 });
});

test("resolveResetRange: no data returns null", function () {
    assert.equal(utils.resolveResetRange("live", null, NaN, NaN, 0.2), null);
    assert.equal(utils.resolveResetRange("report", null, 0, 0, 0), null);
});
