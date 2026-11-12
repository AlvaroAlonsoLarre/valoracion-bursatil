const {chromium}=require('/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1200}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('http://127.0.0.1:8504');await page.getByRole('heading',{name:'NVIDIA Corporation',exact:true}).waitFor({timeout:90000});
 await page.getByTestId('stMetricValue').filter({hasText:/[0-9]/}).first().waitFor();
 await page.getByRole('tab',{name:'Resumen',exact:true}).click();await page.locator('canvas').first().waitFor({state:'visible',timeout:30000});
 await page.getByText(/Base · crecimiento/).waitFor();
 await page.screenshot({path:'/workspace/work/economia_v6/browser/resumen.png',fullPage:true});
 await page.getByRole('tab',{name:'Valoración',exact:true}).click();
 await page.getByText('Sensibilidad y comparación con la cotización',{exact:true}).click();
 await page.getByText('PER implícito',{exact:true}).first().waitFor({timeout:10000}).catch(()=>{});
 await page.getByText('Contraste de retorno de precio cero',{exact:true}).waitFor();await page.waitForTimeout(700);
 await page.screenshot({path:'/workspace/work/economia_v6/browser/sensibilidad.png',fullPage:true});
 await page.getByTestId('stExpander').filter({has:page.getByText('Sensibilidad y comparación con la cotización',{exact:true})}).getByTestId('stDataFrame').nth(1).scrollIntoViewIfNeeded();
 await page.screenshot({path:'/workspace/work/economia_v6/browser/contraste.png'});
 await page.getByText('Resultados recurrentes y calidad del PER histórico',{exact:true}).click();await page.waitForTimeout(300);
 if(await page.getByTestId('stException').count())throw new Error('Streamlit exception');
 await page.getByRole('tab',{name:'Datos y auditoría',exact:true}).click();
 for(const [label,name] of [['Descargar Excel','export.xlsx'],['Descargar resultados JSON','resultados.json'],['Descargar captura reproducible','inputs.json']]){
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:label,exact:true}).click()]);await download.saveAs('/workspace/work/economia_v6/browser/'+name);
 }
 await page.setViewportSize({width:390,height:844});
 const tabs=['Resumen','Histórico','Trimestrales','Comparables','Valoración','Datos y auditoría'];
 for(const name of tabs){await page.getByRole('tab',{name,exact:true}).click();await page.waitForTimeout(250);if(await page.getByTestId('stException').count())throw new Error(name);}
 await page.getByRole('tab',{name:'Resumen',exact:true}).click();await page.waitForTimeout(500);
 await page.screenshot({path:'/workspace/work/economia_v6/browser/movil.png'});
 const overflow=await page.evaluate(()=>({body:document.body.scrollWidth,viewport:innerWidth}));if(overflow.body>overflow.viewport+2)throw new Error('overflow');
 fs.writeFileSync('/workspace/work/economia_v6/browser/resultado.json',JSON.stringify({tabs,errors,overflow,exports:3,summary_assumptions_visible:true,sensitivity_expander:true},null,2));
 if(errors.length)throw new Error(errors.join('\n'));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
