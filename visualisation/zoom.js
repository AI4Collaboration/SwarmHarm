// Zoom and pan arithmetic. The code does not use the DOM. Node can test it.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Zoom = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const MIN_SCALE = 0.1;
  const MAX_SCALE = 8;
  const STEP = 1.25;

  const clamp = (scale) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

  function initial() {
    return { scale: 1, x: 0, y: 0 };
  }

  // Zoom by `factor`. The content point under (cx, cy) does not move.
  function zoomAt(view, factor, cx, cy) {
    const scale = clamp(view.scale * factor);
    const ratio = scale / view.scale;
    return { scale, x: cx - (cx - view.x) * ratio, y: cy - (cy - view.y) * ratio };
  }

  function panBy(view, dx, dy) {
    return { scale: view.scale, x: view.x + dx, y: view.y + dy };
  }

  // Scale content (cw, ch) to fit the viewport (vw, vh). Center it.
  function fit(cw, ch, vw, vh, margin = 16) {
    if (!(cw > 0 && ch > 0 && vw > 0 && vh > 0)) return initial();
    const scale = clamp(Math.min((vw - 2 * margin) / cw, (vh - 2 * margin) / ch));
    return { scale, x: (vw - cw * scale) / 2, y: (vh - ch * scale) / 2 };
  }

  // Negative deltaY zooms in. Positive deltaY zooms out.
  function wheelFactor(deltaY) {
    return Math.pow(STEP, -Math.sign(deltaY) * Math.min(Math.abs(deltaY) / 100, 3));
  }

  function toCss(view) {
    return `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  }

  return { MIN_SCALE, MAX_SCALE, STEP, clamp, initial, zoomAt, panBy, fit, wheelFactor, toCss };
});
