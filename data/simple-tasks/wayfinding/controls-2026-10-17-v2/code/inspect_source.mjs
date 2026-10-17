// Read-only helper. Run from an operator directory linked to bundled node_modules.
import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const [source, output] = process.argv.slice(2);
if (!source || !output) throw new Error('Usage: inspect_source.mjs source.xlsx new-view.json');
const bytes = await fs.readFile(source);
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
await wb.inspect({kind: 'workbook,sheet,table', maxChars: 7000, tableMaxRows: 3, tableMaxCols: 5});
const checklist = wb.worksheets.getItem('Wayfinding Checklist').getRange('A1:L54').values;
const services = wb.worksheets.getItem('Move Matrix').getRange('A1:B13').values;
if (!bytes.equals(await fs.readFile(source))) throw new Error('Source changed');
await fs.writeFile(output, JSON.stringify({checklist, services}, null, 2), {flag: 'wx'});
console.log(JSON.stringify({checklistRows: checklist.length, serviceRows: services.length, sourceUnchanged: true}));
