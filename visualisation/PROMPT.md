# Prompt to reproduce this visualisation

Paste the text below into a coding agent opened at the repository root.

---

Create a folder `visualisation/` that holds two simple local web pages of Mermaid diagrams for this repository's experimental environments: `visualisation/swarmform/` and `visualisation/swarmharm/`.

**Environments.** Draw one set per environment:
the five SwarmForm deployments (`shared_files`, `shared_ipc`, `worker_endpoint`, `artifact_namespace`, `job_namespace`),
the retained v57 work-cache pilot, and the SwarmHarm reporting baseline.
Read `docs/formation-study-design.md`, `docs/swarmform-coverage.md`, `docs/environment-contract.md`,
`docs/architecture/shared-core-and-phases.md` and `experiments/swarmharm-v1/swarmform/*_deployment.py` first.
Draw only what those files state. Do not invent components.

**Diagram kinds.** Each environment gets exactly four diagrams and no other kind:
1. ontology (Mermaid `classDiagram`),
2. UML sequence diagram (`sequenceDiagram`),
3. object diagram (a `flowchart` whose nodes read `name : Type`, with concrete instances),
4. conceptual diagram (a `flowchart` of the idea, not the code).

**Files.**
- `swarmform/diagrams.js` and `swarmharm/diagrams.js`: the only sources of diagram data. Each is a UMD module exporting `{ kinds, environments }`. Each diagram has `kind`, `title`, `mermaid` and `sources` (repo-relative paths). Each environment has `summary: { headline, points }`: a one-sentence headline and 2-3 plain-language points. The SwarmForm file holds the five deployments and the v57 pilot. The SwarmHarm file holds the reporting baseline only.
- `swarmform/index.html` and `swarmharm/index.html`: two pages, one per project, each showing only its own diagrams. Each sets `data-repo="../../"` on `<body>`. They share `styles.css` and `app.js` in the parent folder. Tabs choose the environment. A single-column list shows the four diagrams. Each diagram starts fitted to its box. Under each diagram, list the files it draws on as links (`../<path>`) with the heading "Draws on:".
- `zoom.js`: pure zoom and pan arithmetic (UMD, no DOM). Mouse wheel zooms at the cursor. Drag pans. Buttons: +, −, Fit, 1:1. Double-click fits.
- `vendor/mermaid.min.js` (Mermaid 11.4.1, MIT licence file beside it). The page must work offline from `file://` with no remote resources.
- `tests/*.test.js` and `package.json`: a minimal suite using `node:test`, no dependencies. Run with `npm test` inside `visualisation/`.
- `README.md`: how to open, test and edit.

**Tests must check.**
- zoom: clamp, zoom keeps the cursor point fixed, pan, fit, wheel direction;
- data: exactly the four kinds, one of each per environment, correct Mermaid header per kind,
  instance notation in object diagrams, balanced `subgraph`/`end`, declared sequence participants,
  and every listed source file exists;
- page: local scripts exist and load in order, no remote URLs, zoom module is wired in.

**CI.** Add a step to `.github/workflows/checks.yml` that runs `npm test` in `visualisation/` after Node is set up.

**Verify.** Render every environment in headless Chromium and confirm four SVGs and no Mermaid error.

Style: simple, light and dark themes, no framework.
