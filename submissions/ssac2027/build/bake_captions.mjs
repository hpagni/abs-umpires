// Renders each chosen exhibit with its caption as one PNG (2x), so the PDF carries the
// caption as image pixels rather than text. Usage: node bake_captions.mjs <repo root>
import { chromium } from '/Users/hudsonpagni/hudsonpagni-website/node_modules/playwright/index.mjs';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const root = process.argv[2];
const chosen = readFileSync(join(root, 'abstract/exhibits/chosen.txt'), 'utf8').split('\n')
  .filter(l => l.trim() && !l.startsWith('#')).map(l => l.split(/\s+/)[1]);
const b = await chromium.launch();
for (const name of chosen) {
  const dir = join(root, 'abstract/exhibits', name);
  const png = readFileSync(join(dir, name + '.png')).toString('base64');
  const caption = readFileSync(join(dir, 'caption.md'), 'utf8').split(/\s+/).join(' ').trim();
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body { margin: 0; background: #fff; } .wrap { width: 624px; padding: 0; }
    img { width: 624px; display: block; }
    p { font-family: Georgia, 'Times New Roman', serif; font-size: 9.5pt; line-height: 1.3; color: #222; margin: 4pt 0 0 0; }
  </style></head><body><div class="wrap"><img src="data:image/png;base64,${png}"><p>${esc(caption)}</p></div></body></html>`;
  const p = await b.newPage({ viewport: { width: 624, height: 800 }, deviceScaleFactor: 3 });
  await p.setContent(html, { waitUntil: 'load' });
  const el = await p.$('.wrap');
  const out = join(here, name + '-with-caption.png');
  await el.screenshot({ path: out, omitBackground: false });
  console.log('wrote', out);
  await p.close();
}
await b.close();
