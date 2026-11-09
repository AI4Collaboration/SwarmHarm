# Environment diagrams

There are two viz pages:

| Page | Shows |
| --- | --- |
| `swarmform/index.html` | The five SwarmForm deployments and the v57 work-cache pilot |
| `swarmharm/index.html` | The SwarmHarm reporting baseline |

Shared code in `app.js`, `zoom.js`, `styles.css` and `vendor/`.

## View

Open `index.html` in a browser or IDE preview.

## Edit

- Edit diagrams in `swarmform/diagrams.js` or `swarmharm/diagrams.js`. Each file is the one source of data for its page.
- Each diagram has a `kind`: ontology, sequence, object or conceptual.
- Add the repository files that you use to the `sources` list of the diagram.

## Test

- Run `npm test` in this directory.
- Use Node 20 or later. No install step is needed.
- The GitHub workflow `checks.yml` runs the same command.

## Re-rendering

- Use [PROMPT.md](PROMPT.md) to update the visualisation.

## Licences

- `vendor/` holds Mermaid 11.4.1 (MIT licence).
