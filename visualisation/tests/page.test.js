const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const pages = ['swarmform', 'swarmharm'];

for (const name of pages) {
  const dir = path.join(root, name);
  const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');

  test(`${name}/index.html loads local scripts that exist, in dependency order`, () => {
    const scripts = [...html.matchAll(/<script src="([^"]+)"/g)].map((m) => m[1]);
    assert.deepEqual(scripts, ['../vendor/mermaid.min.js', '../zoom.js', 'diagrams.js', '../app.js']);
    for (const s of scripts) assert.ok(fs.existsSync(path.join(dir, s)), s);
  });

  test(`${name}/index.html loads no remote resources and points at the repository root`, () => {
    assert.doesNotMatch(html, /(src|href)="https?:/);
    assert.match(html, /data-repo="\.\.\/\.\.\/"/);
    assert.ok(fs.existsSync(path.join(dir, '../../AGENTS.md')));
  });
}

test('the stylesheet and reproduction prompt exist', () => {
  assert.ok(fs.existsSync(path.join(root, 'styles.css')));
  assert.ok(fs.statSync(path.join(root, 'PROMPT.md')).size > 200);
});

test('the viewer wires zoom controls to the zoom module', () => {
  const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
  for (const name of ['zoomAt', 'panBy', 'fit', 'wheelFactor']) assert.match(app, new RegExp('Zoom\\.' + name), name);
  assert.match(app, /Draws on:/);
});
