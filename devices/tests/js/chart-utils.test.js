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
