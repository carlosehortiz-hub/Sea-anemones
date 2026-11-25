// Print an HTML page to PDF with headless Chromium (Playwright).
// Usage: node paper/print.cjs <input.html> <output.pdf> <header> <footer>
// Header and footer are inline HTML; {page} and {pages} become page numbers, '|' splits
// left and right, and an empty string leaves that band blank.
const { chromium } = require('playwright');

const style = 'font-family: Liberation Sans, Arial, sans-serif; font-size: 7.5px; color: #555;' +
  ' width: 100%; padding: 0 16mm; display: flex; justify-content: space-between;';

function band(text) {
  if (!text) return '<div></div>';
  const fill = (s) => s.replace('{page}', '<span class="pageNumber"></span>')
    .replace('{pages}', '<span class="totalPages"></span>');
  const parts = text.split('|').map((s) => `<span>${fill(s.trim())}</span>`);
  const justify = parts.length === 1 ? ' justify-content: center;' : '';
  return `<div style="${style}${justify}">${parts.join('')}</div>`;
}

(async () => {
  const [, , input, output, head = '', foot = ''] = process.argv;
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage();
  await page.goto('file://' + input, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: output,
    format: undefined,
    width: '210mm', height: process.env.PAGE_HEIGHT || '279mm',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: band(head),
    footerTemplate: band(foot),
    margin: {
      top: process.env.MARGIN_TOP || '17mm', bottom: '16mm',
      left: process.env.MARGIN_SIDE || '16mm', right: process.env.MARGIN_SIDE || '16mm',
    },
  });
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
