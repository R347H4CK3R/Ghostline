const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const assert=require('node:assert/strict');
(async()=>{
 const server=spawn('python',['tests/source_review_browser_server.py']);
 const lines=readline.createInterface({input:server.stdout});
 let browser;
 try{
  const port=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Server startup timed out')),10000);server.on('exit',()=>reject(Error('Server exited')));lines.once('line',line=>{clearTimeout(timer);resolve(Number(line));});});
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844},extraHTTPHeaders:{Authorization:'Bearer '+'s'.repeat(48)}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+port+'/review?video=SYNTHETIC04');await page.locator('#video option').waitFor();
  await page.locator('#reviewer').fill('Fixture creator');await page.locator('#record').fill('Original synthetic fixture');
  for(const [key,value] of Object.entries({id:'original-fixture',name:'Original fixture',start:'0',end:'0.7',referenceText:'A reference sentence.'}))await page.locator('[data-key='+key+']').fill(value);
  await page.locator('[data-key=labelStatus]').selectOption('original-speaker-reviewed');await page.locator('#approved').check();
  await page.locator('#submit').click();await page.locator('#status').filter({hasText:'Reviewed segments saved'}).waitFor();
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'source-review-mobile.png',fullPage:true});
  await page.locator('#submit').click();await page.locator('#status').filter({hasText:'existing review'}).waitFor();
  console.log('Real browser mobile form, source-use review, HTTP save and replacement refusal passed');
 }finally{if(browser)await browser.close();lines.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
