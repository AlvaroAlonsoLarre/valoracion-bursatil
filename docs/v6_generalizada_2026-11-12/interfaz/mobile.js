const {chromium}=require('/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.goto('http://127.0.0.1:8503');await page.getByRole('heading',{name:'Microsoft Corporation',exact:true}).waitFor({timeout:90000});
 const checks=[];
 for(const name of ['Resumen','Histórico','Trimestrales','Comparables','Valoración','Datos y auditoría']){
  await page.getByRole('tab',{name,exact:true}).click();await page.waitForTimeout(500);
  if(await page.getByTestId('stException').count())throw new Error(name);
  checks.push(name);
 }
 await page.getByRole('tab',{name:'Resumen',exact:true}).click();await page.waitForTimeout(500);
 await page.getByTestId('stMain').evaluate(el=>el.scrollTo(0,1100));await page.waitForTimeout(500);
 await page.screenshot({path:'/workspace/work/v6_general/browser/movil_negocio.png'});
 fs.writeFileSync('/workspace/work/v6_general/browser/mobile_tabs.json',JSON.stringify({tabs:checks,all_without_exceptions:true},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
