import { chromium } from '/Users/hudsonpagni/hudsonpagni-website/node_modules/playwright/index.mjs';
const [,, inp, out] = process.argv;
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 816, height: 1056 } });
await p.goto('file://' + inp, { waitUntil: 'load' });
await p.emulateMedia({ media: 'print' });
await p.screenshot({ path: out, fullPage: true });
await b.close();
