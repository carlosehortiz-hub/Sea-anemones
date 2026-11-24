// Print paper/build/manuscript.html to PDF with headless Chromium (Playwright).
// Usage: node paper/print.cjs <input.html> <output.pdf> "<running head>"
const { chromium } = require('playwright');

(async () => {
  const [, , input, output, head] = process.argv;
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage();
  await page.goto('file://' + input, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const style = 'font-family: Liberation Sans, Arial, sans-serif; font-size: 7.5px; color: #555;' +
    ' width: 100%; padding: 0 16mm; display: flex; justify-content: space-between;';
  await page.pdf({
    path: output,
    width: '210mm', height: '279mm',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: `<div style="${style}"><span>${head}</span>` +
      '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
    footerTemplate: `<div style="${style} justify-content: center;">` +
      '<span>Manuscript prepared in the format of <i>Marine Biodiversity Records</i>. ' +
      'Not peer reviewed.</span></div>',
    margin: { top: '17mm', bottom: '16mm', left: '16mm', right: '16mm' },
    preferCSSPageSize: false,
  });
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
