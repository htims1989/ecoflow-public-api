// Preview the EcoFlow power-flow card overlay on top of house.png.
//
//   node preview.mjs         -> /tmp/ef_house.png (plain preview)
//   node preview.mjs grid    -> also draws a 100px coordinate grid to read
//                               off pixel positions for tweaking _svgMarkup()
//
// After editing ecoflow-power-flow-card.js, just re-run this and reopen the PNG.

import fs from 'fs';
import { execSync } from 'child_process';

const dir = new URL('.', import.meta.url).pathname;
const showGrid = process.argv.includes('grid');

let src = fs.readFileSync(`${dir}/ecoflow-power-flow-card.js`, 'utf8');

// Stub the browser globals the class touches, then import just the class.
global.HTMLElement = class {};
global.customElements = { define() {} };
global.window = { customCards: [] };
global.document = { createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }) };

const cut = src.indexOf('customElements.define(');
fs.writeFileSync('/tmp/_card.mjs', src.slice(0, cut) + '\nexport { EcoflowPowerFlowCard };');
const { EcoflowPowerFlowCard } = await import('/tmp/_card.mjs?' + Date.now());

const card = Object.create(EcoflowPowerFlowCard.prototype);
card._config = { watt_threshold: 20 };
let markup = card._svgMarkup();

// Inject sample live values so every flow + label is visible.
const set = (id, txt) => { markup = markup.replace(new RegExp(`(id="${id}">)[^<]*`), `$1${txt}`); };
set('ef-val-solar', '2.14 kW');
set('ef-val-grid', '640 W');  set('ef-lbl-grid', 'EXPORT');
set('ef-val-batt', '480 W');  set('ef-lbl-batt', 'CHARGE');
set('ef-val-soc', '86%');
set('ef-val-home', '1.02 kW');
markup = markup.replace(/class="flow idle"/g, 'class="flow"');

const inner = markup.replace(/^\s*<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');

// Optional coordinate grid (light lines every 100px, labels every 200px).
let grid = '';
if (showGrid) {
  const parts = ['<g stroke="#00e5ff" stroke-width="1" opacity="0.35">'];
  for (let x = 0; x <= 1448; x += 100) parts.push(`<line x1="${x}" y1="0" x2="${x}" y2="1086"/>`);
  for (let y = 0; y <= 1086; y += 100) parts.push(`<line x1="0" y1="${y}" x2="1448" y2="${y}"/>`);
  parts.push('</g><g fill="#00e5ff" font="12px sans-serif" opacity="0.9">');
  for (let x = 0; x <= 1448; x += 200) parts.push(`<text x="${x + 2}" y="16">${x}</text>`);
  for (let y = 100; y <= 1086; y += 200) parts.push(`<text x="2" y="${y - 3}">${y}</text>`);
  parts.push('</g>');
  grid = parts.join('');
}

const css = `
  .wire{fill:none;stroke:#ffffff;stroke-linecap:round;stroke-width:4;opacity:.55;filter:drop-shadow(0 0 5px currentColor)}
  .comet{fill:none;stroke:currentColor;stroke-linecap:round}
  .head{stroke-width:7;stroke-dasharray:12 148;opacity:1;filter:drop-shadow(0 0 6px currentColor)}
  .t2{stroke-width:9;stroke-dasharray:34 126;opacity:.40;filter:drop-shadow(0 0 7px currentColor)}
  .t3{stroke-width:11;stroke-dasharray:66 94;opacity:.16;filter:drop-shadow(0 0 9px currentColor)}
  .tick{stroke:#aeb6c2;stroke-width:2;opacity:.5}
  text{paint-order:stroke;stroke:rgba(8,10,14,.85);stroke-width:5px;stroke-linejoin:round}
  .lbl{font:700 22px sans-serif;letter-spacing:1.5px;fill:#aab3c0}
  .val{font:800 40px sans-serif;fill:#fff}
  .soc{font:700 24px sans-serif;fill:#bfe8d6}
`;

const img = fs.readFileSync(`${dir}/house.png`).toString('base64');
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1448 1086" width="1448" height="1086">
<style>${css}</style>
<image href="data:image/png;base64,${img}" x="0" y="0" width="1448" height="1086"/>
${grid}
${inner}
</svg>`;

fs.writeFileSync('/tmp/ef_house.svg', svg);
execSync('rsvg-convert -w 1000 /tmp/ef_house.svg -o /tmp/ef_house.png');
console.log('Rendered /tmp/ef_house.png' + (showGrid ? ' (with grid)' : ''));
