const { chromium } = require('playwright');
const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const { pathToFileURL } = require('url');
(async () => {
 const root=path.resolve('docs/diagrams/current-architecture');
 const html=path.join(root,'overview.html');
 const browser=await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:900},offline:true});
 const page=await context.newPage();const errors=[];page.on('pageerror', e=>errors.push(String(e)));
 await page.goto(pathToFileURL(html).href);
 const results=[];
 async function select(name) {
  await page.locator('#tab-'+name).click();
  const handle=await page.locator('#view-'+name).elementHandle();
  const frame=await handle.contentFrame();
  await frame.waitForSelector('svg');
  await frame.evaluate(async()=>{await document.fonts.ready;await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
  return frame;
 }
 for (const size of [{width:1440,height:900},{width:1600,height:1000},{width:1920,height:1080},{width:2048,height:1320}]) {
  await page.setViewportSize(size);
  for(const name of ['architecture','workflow']) {
   const frame=await select(name);
   const measure=()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,svgCount:document.querySelectorAll('svg').length});
   const outer=await page.evaluate(measure),inner=await frame.evaluate(measure);
   const ok=outer.scrollWidth<=outer.width && outer.scrollHeight<=outer.height && inner.scrollWidth<=inner.width && inner.scrollHeight<=inner.height && inner.svgCount>=1;
   results.push({name,viewport:size,outer,inner,ok});
   if(size.width===1440 || size.width===2048)await page.screenshot({path:path.join(root,`overview.${name}.${size.width}x${size.height}.png`)});
  }
 }
 const frame=await select('architecture');
 console.log('CONTROLS',JSON.stringify(await frame.locator('button').evaluateAll(nodes=>nodes.slice(0,18).map(n=>({text:n.textContent.trim().slice(0,40),title:n.title,aria:n.getAttribute('aria-label')})))));
 await page.locator('#tab-architecture').focus();await page.keyboard.press('ArrowRight');
 const keyboard=await page.locator('#tab-workflow').getAttribute('aria-selected')==='true';
 const embedded=await page.locator('#embedded-diagrams').textContent();
 const same=Object.entries(JSON.parse(embedded)).every(([name,value])=>Buffer.from(value,'base64').equals(fs.readFileSync(path.join(root,name+'.html'))));
 const bytes=fs.readFileSync(html);
 const receipt={status:results.every(r=>r.ok)&&keyboard&&same&&!errors.length?'pass':'fail',artifact:{path:html,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length},evidenceKind:'supplementary-combined-viewer-browser',offline:true,embedded_originals_unchanged:same,keyboard_tabs:keyboard,errors,viewports:results,visualReview:'pending',note:'Original Archify deliver receipts apply to the byte-identical embedded viewers. This combined wrapper is separately browser-checked; it is not a single-diagram Archify delivery.'};
 fs.writeFileSync(path.join(root,'overview.browser-check.json'),JSON.stringify(receipt,null,2)+'\n');
 console.log(JSON.stringify(receipt));await browser.close();if(receipt.status!=='pass')process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
