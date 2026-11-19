// E2E + tilgængelighed (axe-core, WCAG 2.2 AA-regler) mod den kørende stak.
// Kør: se README ("Tilgængelighedstest"). Kræver en gyldig respondentkode i E2E_CODE.
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const BASE = process.env.E2E_BASE || 'https://localhost:8443';
const CODE = process.env.E2E_CODE;
const OUT = process.env.E2E_OUT || '/out';
let failures = 0;

async function axe(page, label) {
  // axe injiceres via CDP-isoleret verden, så sidens CSP/Trusted Types ikke svækkes
  if (!(await page.evaluate(() => Boolean(window.axe)))) await page.evaluate(axeSource);
  const res = await page.evaluate(async () => await window.axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }));
  const v = res.violations;
  console.log(`axe ${label}: ${v.length} overtrædelser`);
  for (const x of v) { failures++; console.log(`  - ${x.id} (${x.impact}): ${x.help} -> ${x.nodes.map((n) => n.target.join(' ')).slice(0, 3).join(' | ')}`); }
}

const browser = await chromium.launch();
for (const [name, viewport] of [['desktop', { width: 1280, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport, bypassCSP: false });
  const page = await ctx.newPage();
  const csp = [];
  page.on('console', (m) => { if (/Content Security Policy|Trusted Type/i.test(m.text())) csp.push(m.text()); });
  page.on('pageerror', (e) => { csp.push(`pageerror: ${e.message}`); });
  await page.goto(BASE + '/');
  await page.waitForSelector('#code');
  await axe(page, `${name} kode`);
  await page.screenshot({ path: `${OUT}/${name}-1-kode.png`, fullPage: true });
  // tom indsendelse -> fejl annonceres
  await page.click('button[type=submit]');
  if (!(await page.textContent('#code-error'))) { failures++; console.log('  - mangler fejlbesked ved tom kode'); }
  await page.fill('#code', CODE.toLowerCase());
  await page.keyboard.press('Enter');
  await page.waitForSelector('#consent');
  await axe(page, `${name} information`);
  await page.screenshot({ path: `${OUT}/${name}-2-info.png`, fullPage: true });
  await page.check('#consent');
  await page.click('button[type=submit]');
  await page.waitForSelector('.resume-key');
  await page.screenshot({ path: `${OUT}/${name}-3-genoptag.png` });
  await page.click('text=Fortsæt til spørgsmålene');
  await page.waitForSelector('fieldset.item');
  await axe(page, `${name} spørgsmål`);
  await page.screenshot({ path: `${OUT}/${name}-4-spm.png`, fullPage: true });
  const perPage = await page.locator('fieldset.item').count();
  console.log(`${name}: ${perPage} item(s) pr. side`);
  if ((name === 'mobile' && perPage !== 1) || perPage > 3) { failures++; console.log('  - forkert antal items pr. side'); }
  // tastatur: Tab til første radio, piletast vælger
  const firstLegend = await page.locator('fieldset.item legend').first().textContent();
  await page.locator('fieldset.item input[type=radio]').first().focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  const checked = await page.locator('fieldset.item').first().locator('input:checked').getAttribute('value');
  console.log(`${name}: tastaturvalg gav værdi ${checked}`);
  if (checked !== '3') { failures++; console.log('  - tastaturnavigation i radiogruppe virker ikke som forventet'); }
  await page.waitForTimeout(800);
  const status = await page.textContent('#save-status');
  console.log(`${name}: autosave-status "${status}"`);
  const firstOrder = await page.locator('fieldset.item legend').allTextContents();
  await page.click('button[type=submit]');
  await page.waitForTimeout(500);
  // genindlæs -> samme session, fortsætter efter besvarede
  await page.reload();
  await page.waitForSelector('fieldset.item');
  // genoptagelse lander på siden med første ubesvarede item
  if (name === 'mobile') await page.click('text=Tilbage');
  const again = await page.locator('fieldset.item').first().locator('input:checked').getAttribute('value');
  if (again !== '3') { failures++; console.log('  - svar ikke bevaret efter genindlæsning'); }
  console.log(`${name}: efter reload og tilbage er svaret ${again}; første item "${firstLegend.slice(0, 50)}…"`);
  void firstOrder;
  await ctx.close();
  // Admin login
  const actx = await browser.newContext({ ignoreHTTPSErrors: true, viewport });
  const ap = await actx.newPage();
  ap.on('console', (m) => { if (/Content Security Policy|Trusted Type/i.test(m.text())) csp.push(m.text()); });
  await ap.goto(BASE + '/admin/');
  await ap.waitForSelector('input[name=username]');
  await axe(ap, `${name} admin-login`);
  await ap.screenshot({ path: `${OUT}/${name}-5-admin.png` });
  await actx.close();
  if (csp.length) { failures += csp.length; console.log('CSP/Trusted Types-fejl:', csp); }
}
await browser.close();
console.log(failures ? `FEJL: ${failures}` : 'OK: ingen axe-overtrædelser, ingen CSP-fejl');
process.exit(failures ? 1 : 0);
