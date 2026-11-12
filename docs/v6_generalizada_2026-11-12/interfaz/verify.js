const { chromium }=require('/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1200}});const errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('http://127.0.0.1:8503',{waitUntil:'domcontentloaded'});
 await page.getByRole('heading',{name:'Microsoft Corporation',exact:true}).waitFor({timeout:90000});
 await page.getByTestId('stMetricValue').filter({hasText:/[0-9]/}).first().waitFor();
 await page.getByRole('tab',{name:'Resumen',exact:true}).click();
 await page.locator('canvas').first().waitFor({state:'visible',timeout:30000});
 await page.screenshot({path:'/workspace/work/v6_general/browser/escritorio.png',fullPage:true});
 const tabs=['Resumen','Histórico','Trimestrales','Comparables','Valoración','Datos y auditoría'];
 for(const tab of tabs){await page.getByRole('tab',{name:tab,exact:true}).click();await page.waitForTimeout(350);if(await page.getByTestId('stException').count())throw new Error('Streamlit exception '+tab);}
 await page.getByRole('tab',{name:'Valoración',exact:true}).click();
 await page.getByRole('heading',{name:'Supuestos editables',exact:true}).waitFor();
 await page.screenshot({path:'/workspace/work/v6_general/browser/valoracion.png',fullPage:true});
 // Verificar edición de un criterio sin consultas financieras ni cambio de targets.
 await page.getByRole('tab',{name:'Resumen',exact:true}).click();
 await page.getByText('Criterios de atractivo y posición (opcional)',{exact:true}).click();
 const ret=page.getByLabel('Retorno exigido',{exact:true});await ret.fill('20');
 const button=page.getByRole('button',{name:/Aplicar criterios/});
 if(await button.count())await button.click();else throw new Error('No se encuentra envío de criterios');
 await page.waitForTimeout(1500);
 await page.getByRole('tab',{name:'Datos y auditoría',exact:true}).click();
 for(const [label,file] of [['Descargar Excel','export.xlsx'],['Descargar resultados JSON','resultados.json'],['Descargar captura reproducible','inputs.json']]){
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:label,exact:true}).click()]);
  await download.saveAs('/workspace/work/v6_general/browser/'+file);
 }
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('tab',{name:'Resumen',exact:true}).click();await page.waitForTimeout(1000);
 await page.screenshot({path:'/workspace/work/v6_general/browser/movil.png',fullPage:true});
 const overflow=await page.evaluate(()=>({body:document.body.scrollWidth,viewport:innerWidth}));
 if(overflow.body>overflow.viewport+2)throw new Error('Desbordamiento horizontal '+JSON.stringify(overflow));
 fs.writeFileSync('/workspace/work/v6_general/browser/verificacion.json',JSON.stringify({tabs,errors,overflow,exports:['export.xlsx','resultados.json','inputs.json'],viewport_desktop:[1440,1200],viewport_mobile:[390,844]},null,2));
 if(errors.length)throw new Error(errors.join('\n'));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
