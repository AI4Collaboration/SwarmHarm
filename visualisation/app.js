// Render each diagram with Mermaid. Add wheel, drag and button zoom.
(function () {
  const root = document.getElementById('grid');
  const tabs = document.getElementById('tabs');
  const summary = document.getElementById('summary');
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  mermaid.initialize({ startOnLoad: false, theme: dark ? 'dark' : 'default', securityLevel: 'strict' });

  const REPO = document.body.dataset.repo || '../';
  let counter = 0;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => (k === 'text' ? (node.textContent = v) : node.setAttribute(k, v)));
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  function attachZoom(viewport, stage) {
    let view = Zoom.initial();
    const apply = () => { stage.style.transform = Zoom.toCss(view); };
    const size = () => {
      const svg = stage.querySelector('svg');
      const box = svg ? svg.getBoundingClientRect() : { width: 0, height: 0 };
      return { w: box.width / view.scale, h: box.height / view.scale };
    };
    const fit = () => {
      const s = size();
      view = Zoom.fit(s.w, s.h, viewport.clientWidth, viewport.clientHeight);
      apply();
    };
    const zoom = (factor, cx, cy) => {
      view = Zoom.zoomAt(view, factor, cx === undefined ? viewport.clientWidth / 2 : cx, cy === undefined ? viewport.clientHeight / 2 : cy);
      apply();
    };
    viewport.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = viewport.getBoundingClientRect();
      zoom(Zoom.wheelFactor(e.deltaY), e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    let drag = null;
    viewport.addEventListener('pointerdown', (e) => {
      drag = { x: e.clientX, y: e.clientY };
      viewport.setPointerCapture(e.pointerId);
      viewport.classList.add('dragging');
    });
    viewport.addEventListener('pointermove', (e) => {
      if (!drag) return;
      view = Zoom.panBy(view, e.clientX - drag.x, e.clientY - drag.y);
      drag = { x: e.clientX, y: e.clientY };
      apply();
    });
    const end = () => { drag = null; viewport.classList.remove('dragging'); };
    viewport.addEventListener('pointerup', end);
    viewport.addEventListener('pointercancel', end);
    viewport.addEventListener('dblclick', fit);
    return { fit, zoomIn: () => zoom(Zoom.STEP), zoomOut: () => zoom(1 / Zoom.STEP), reset: () => { view = Zoom.initial(); apply(); } };
  }

  function sourceList(paths) {
    const items = paths.map((p) => el('li', {}, [el('a', { href: REPO + p, text: p })]));
    return el('div', { class: 'sources' }, [el('strong', { text: 'Draws on:' }), el('ul', {}, items)]);
  }

  async function panel(diagram) {
    const stage = el('div', { class: 'stage' });
    const viewport = el('div', { class: 'viewport', 'data-kind': diagram.kind }, [stage]);
    const controls = {};
    const button = (label, title, key) => {
      const b = el('button', { type: 'button', title, 'aria-label': title, text: label });
      b.addEventListener('click', () => controls.api && controls.api[key]());
      return b;
    };
    const tools = el('div', { class: 'tools' }, [
      button('+', 'Zoom in', 'zoomIn'), button('−', 'Zoom out', 'zoomOut'),
      button('Fit', 'Fit to view', 'fit'), button('1:1', 'Reset zoom', 'reset'),
    ]);
    const box = el('section', { class: 'panel' }, [
      el('h2', {}, [el('span', { text: diagram.title }), el('span', { class: 'kind', text: diagram.kind }), tools]),
      viewport,
      sourceList(diagram.sources),
    ]);
    try {
      const { svg } = await mermaid.render('mmd' + counter++, diagram.mermaid);
      stage.innerHTML = svg;
      // Mermaid sizes the SVG to its container. Use the natural size so 1:1 is exact.
      const node = stage.querySelector('svg');
      const natural = node.viewBox.baseVal;
      node.removeAttribute('style');
      node.setAttribute('width', natural.width);
      node.setAttribute('height', natural.height);
      controls.api = attachZoom(viewport, stage);
      box.fitToView = controls.api.fit;
    } catch (error) {
      stage.replaceWith(el('div', { class: 'error', text: 'Mermaid could not render this diagram:\n' + (error && error.message || error) }));
    }
    return box;
  }

  async function show(env) {
    summary.replaceChildren(el('strong', { text: env.summary.headline }),
      ...(env.summary.points.length ? [el('ul', {}, env.summary.points.map((p) => el('li', { text: p })))] : []));
    root.replaceChildren();
    for (const diagram of env.diagrams) {
      const box = await panel(diagram);
      root.appendChild(box);
      // The box needs a size in the page before it can fit.
      if (box.fitToView) box.fitToView();
    }
    [...tabs.children].forEach((b) => b.setAttribute('aria-selected', String(b.dataset.id === env.id)));
    try { history.replaceState(null, '', '#' + env.id); } catch (e) { /* Some browsers reject history changes on file: URLs. */ }
  }

  if (DIAGRAMS.environments.length === 1) tabs.hidden = true;
  DIAGRAMS.environments.forEach((env) => {
    const b = el('button', { type: 'button', 'data-id': env.id, text: env.title });
    b.addEventListener('click', () => show(env));
    tabs.appendChild(b);
  });
  const wanted = DIAGRAMS.environments.find((e) => '#' + e.id === location.hash) || DIAGRAMS.environments[0];
  show(wanted);
})();
