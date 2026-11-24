// Export each figure SVG as a separate submission file: vector PDF and 600 dpi PNG.
// Usage: node paper/export_figures.cjs <in.svg> <out-stem> [<in.svg> <out-stem> ...]
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const args = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] });
  for (let i = 0; i < args.length; i += 2) {
    const [svgPath, stem] = [args[i], args[i + 1]];
    const svg = fs.readFileSync(svgPath, 'utf8').replace(/^<\?xml[^>]*>\s*/, '');
    const html = '<!doctype html><html><head><style>html,body{margin:0;background:#fff}' +
      'svg{display:block}</style></head><body>' + svg + '</body></html>';
    const page = await browser.newPage({ deviceScaleFactor: 600 / 96 });
    await page.setContent(html, { waitUntil: 'load' });
    const box = await page.evaluate(() => {
      const r = document.querySelector('svg').getBoundingClientRect();
      return { w: Math.ceil(r.width), h: Math.ceil(r.height) };
    });
    await page.setViewportSize({ width: box.w, height: box.h });
    await page.screenshot({ path: stem + '.png', clip: { x: 0, y: 0, width: box.w, height: box.h } });
    await page.pdf({
      path: stem + '.pdf', width: box.w + 'px', height: (box.h + 1) + 'px',
      printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 }, pageRanges: '1',
    });
    await page.close();
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
