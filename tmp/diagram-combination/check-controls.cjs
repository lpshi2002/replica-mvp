const {chromium}=require('playwright');const fs=require('fs');const path=require('path');const {pathToFileURL}=require('url');
(async()=>{
 const root=path.resolve('docs/diagrams/current-architecture');
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:900},offline:true});
 page.setDefaultTimeout(10000);
 await page.goto(pathToFileURL(path.join(root,'overview.html')).href);const checks=[];
 for(const name of ['architecture','workflow']){
  await page.locator('#tab-'+name).click();const frame=await(await page.locator('#view-'+name).elementHandle()).contentFrame();
  await frame.waitForSelector('svg');await frame.evaluate(()=>document.fonts.ready);
  const theme=await frame.locator('html').getAttribute('data-theme');
  await frame.getByRole('button',{name:'Toggle color theme',exact:true}).click();
  const newTheme=await frame.locator('html').getAttribute('data-theme');
  await page.waitForFunction(({name,newTheme})=>document.documentElement.dataset.theme===newTheme,{name,newTheme});
  const scale=()=>[...document.querySelectorAll('span,button,output')].map(n=>n.textContent.trim()).filter(t=>/^\d+%$/.test(t));
  const before=await frame.evaluate(scale);await frame.getByRole('button',{name:'Zoom in',exact:true}).click();const after=await frame.evaluate(scale);
  await frame.getByRole('button',{name:'Find a node',exact:true}).click();
  const input=frame.locator('input[aria-label="Search diagram nodes"]');await input.fill('평가');const searched=await input.inputValue()==='평가';
  await frame.getByRole('button',{name:'Close node finder',exact:true}).click();
  await frame.getByRole('button',{name:'Zoom out',exact:true}).click();
  if(newTheme!=='dark') await frame.getByRole('button',{name:'Toggle color theme',exact:true}).click();
  await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await page.screenshot({path:path.join(root,`overview.${name}.dark.png`)});
  await frame.getByRole('button',{name:'Export diagram',exact:true}).click();
  const downloaded=page.waitForEvent('download');
  await frame.locator('button').filter({hasText:/^SVG\s*Editable vector$/}).click();
  const download=await downloaded;const saved=await download.path();const svg=fs.readFileSync(saved,'utf8');
  checks.push({name,themeToggled:theme!==newTheme,outerThemeSynchronized:true,zoomChanged:JSON.stringify(before)!==JSON.stringify(after),search:searched,svgDownload:svg.includes('<svg'),filename:download.suggestedFilename()});
 }
 const p=path.join(root,'overview.browser-check.json');const receipt=JSON.parse(fs.readFileSync(p));receipt.controls=checks;
 if(!checks.every(c=>c.themeToggled&&c.zoomChanged&&c.search&&c.svgDownload))receipt.status='fail';
 fs.writeFileSync(p,JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(checks));await browser.close();if(receipt.status!=='pass')process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
