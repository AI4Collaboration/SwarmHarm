const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const FORM = require('../swarmform/diagrams.js');
const HARM = require('../swarmharm/diagrams.js');
// Both folders share one data shape. The tests below check the two folders together.
const D = { kinds: FORM.kinds, environments: [...FORM.environments, ...HARM.environments] };

const repo = path.resolve(__dirname, '..', '..');
const HEADER = { ontology: /^classDiagram\b/, sequence: /^sequenceDiagram\b/, object: /^flowchart\b/, conceptual: /^flowchart\b/ };

test('only the four allowed diagram kinds exist', () => {
  assert.deepEqual(D.kinds, ['ontology', 'sequence', 'object', 'conceptual']);
  for (const env of D.environments) for (const d of env.diagrams) assert.ok(D.kinds.includes(d.kind), `${env.id}: ${d.kind}`);
});

test('each environment has exactly one diagram of each kind', () => {
  for (const env of D.environments) assert.deepEqual(env.diagrams.map((d) => d.kind), D.kinds, env.id);
});

test('environment ids are unique across both folders', () => {
  const ids = D.environments.map((e) => e.id);
  assert.equal(new Set(ids).size, ids.length);
});

test('the SwarmForm folder holds the five deployments and the v57 pilot, and nothing else', () => {
  assert.deepEqual(FORM.environments.map((e) => e.id),
    ['shared_files', 'shared_ipc', 'worker_endpoint', 'artifact_namespace', 'job_namespace', 'work_cache']);
});

test('the SwarmHarm folder holds only the reporting baseline', () => {
  assert.deepEqual(HARM.environments.map((e) => e.id), ['reporting_baseline']);
});

test('each diagram starts with the Mermaid header for its kind', () => {
  for (const env of D.environments) for (const d of env.diagrams) {
    assert.match(d.mermaid.trim(), HEADER[d.kind], `${env.id}/${d.kind}`);
  }
});

test('object diagrams use instance notation, name : Type', () => {
  for (const env of D.environments) {
    const d = env.diagrams.find((x) => x.kind === 'object');
    assert.match(d.mermaid, /\["[^"]+ : [A-Z][A-Za-z]+/, env.id);
  }
});

test('every diagram lists at least one source and each file exists', () => {
  for (const env of D.environments) for (const d of env.diagrams) {
    assert.ok(d.sources.length > 0, `${env.id}/${d.kind} has no sources`);
    for (const s of d.sources) assert.ok(fs.statSync(path.join(repo, s)).isFile(), `missing ${s}`);
  }
});

test('subgraph and end keywords balance in flowcharts', () => {
  for (const env of D.environments) for (const d of env.diagrams.filter((x) => x.mermaid.startsWith('flowchart'))) {
    const open = (d.mermaid.match(/^\s*subgraph\b/gm) || []).length;
    const close = (d.mermaid.match(/^\s*end\s*$/gm) || []).length;
    assert.equal(open, close, `${env.id}/${d.kind}`);
  }
});

test('sequence diagrams use only declared participants', () => {
  for (const env of D.environments) {
    const d = env.diagrams.find((x) => x.kind === 'sequence');
    const declared = new Set([...d.mermaid.matchAll(/^\s*participant (\w+)/gm)].map((m) => m[1]));
    const used = new Set();
    for (const m of d.mermaid.matchAll(/^\s*(\w+)\s*-{1,2}>>[+-]?(\w+):/gm)) { used.add(m[1]); used.add(m[2]); }
    for (const name of used) assert.ok(declared.has(name), `${env.id}: ${name} is not declared`);
  }
});

test('each summary has a headline and, for SwarmForm environments, two or three short points', () => {
  for (const env of D.environments) {
    assert.match(env.summary.headline, /\.$/, env.id);
    assert.ok(env.summary.points.length >= 2 && env.summary.points.length <= 3, env.id);
  }
});
