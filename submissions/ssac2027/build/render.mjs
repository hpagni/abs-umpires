import { chromium } from '/Users/hudsonpagni/hudsonpagni-website/node_modules/playwright/index.mjs';
const [,, inp, out] = process.argv;
const b = await chromium.launch();
const p = await b.newPage();
await p.goto('file://' + inp, { waitUntil: 'load' });
await p.pdf({ path: out, format: 'Letter', printBackground: true, margin: { top: '1in', right: '1in', bottom: '1in', left: '1in' }, preferCSSPageSize: true });
await b.close();
