const test = require('node:test');
const assert = require('node:assert/strict');
const Zoom = require('../zoom.js');

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} is not ${b}`);

test('clamp keeps the scale inside the limits', () => {
  assert.equal(Zoom.clamp(100), Zoom.MAX_SCALE);
  assert.equal(Zoom.clamp(0), Zoom.MIN_SCALE);
  assert.equal(Zoom.clamp(2), 2);
});

test('zoomAt keeps the point under the cursor fixed', () => {
  const view = { scale: 1.5, x: 30, y: -10 };
  const [cx, cy] = [200, 120];
  const contentX = (cx - view.x) / view.scale;
  const contentY = (cy - view.y) / view.scale;
  const next = Zoom.zoomAt(view, 2, cx, cy);
  near(next.scale, 3);
  near(next.x + contentX * next.scale, cx);
  near(next.y + contentY * next.scale, cy);
});

test('zoomAt never leaves the scale limits', () => {
  let view = Zoom.initial();
  for (let i = 0; i < 50; i++) view = Zoom.zoomAt(view, 2, 0, 0);
  assert.equal(view.scale, Zoom.MAX_SCALE);
  for (let i = 0; i < 100; i++) view = Zoom.zoomAt(view, 0.5, 0, 0);
  assert.equal(view.scale, Zoom.MIN_SCALE);
});

test('panBy moves the view and keeps the scale', () => {
  assert.deepEqual(Zoom.panBy({ scale: 2, x: 1, y: 2 }, 5, -3), { scale: 2, x: 6, y: -1 });
});

test('fit centres content and respects the margin', () => {
  const v = Zoom.fit(400, 200, 800, 400, 0);
  near(v.scale, 2);
  near(v.x, 0);
  near(v.y, 0);
  const small = Zoom.fit(100, 100, 400, 200, 0);
  near(small.scale, 2);
  near(small.x, 100);
});

test('fit returns the initial view for empty content', () => {
  assert.deepEqual(Zoom.fit(0, 0, 800, 400), Zoom.initial());
});

test('wheel up zooms in and wheel down zooms out', () => {
  assert.ok(Zoom.wheelFactor(-100) > 1);
  assert.ok(Zoom.wheelFactor(100) < 1);
  near(Zoom.wheelFactor(-100) * Zoom.wheelFactor(100), 1);
});

test('toCss formats a transform', () => {
  assert.equal(Zoom.toCss({ scale: 2, x: 3, y: 4 }), 'translate(3px, 4px) scale(2)');
});
