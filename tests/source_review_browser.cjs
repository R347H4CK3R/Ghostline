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
  browser=await chromium.launch({headless:true,...(process.env.VM_BROWSER_EXECUTABLE?{executablePath:process.env.VM_BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:390,height:844},extraHTTPHeaders:{Authorization:'Bearer '+'s'.repeat(48)}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+port+'/review?video=SYNTHETIC04');await page.locator('#video option').first().waitFor({state:'attached'});assert.equal(await page.locator('#video').inputValue(),'SYNTHETIC04');
  await page.locator('#reviewer').fill('Fixture creator');await page.locator('#record').fill('Original synthetic fixture');
  for(const [key,value] of Object.entries({id:'original-fixture',name:'Original fixture',start:'0',end:'0.7',referenceText:'A reference sentence.'}))await page.locator('[data-key='+key+']').fill(value);
  await page.locator('[data-key=labelStatus]').selectOption('original-speaker-reviewed');await page.locator('#approved').check();
  await page.locator('#submit').click();await page.locator('#status').filter({hasText:'Reviewed segments saved'}).waitFor();
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'source-review-mobile.png',fullPage:true});
  await page.locator('#submit').click();await page.locator('#status').filter({hasText:'existing review'}).waitFor();
  await page.goto('http://127.0.0.1:'+port+'/review?video=SYNTHETIC03');await page.locator('#video option').first().waitFor({state:'attached'});assert.equal(await page.locator('#video').inputValue(),'SYNTHETIC03');
  await page.locator('#reviewer').fill('Fixture creator');await page.locator('#record').fill('Original synthetic fixture');
  await page.locator('#inspect').click();await page.locator('#inspection-status').filter({hasText:'explicitly approve inspection'}).waitFor();
  await page.locator('#inspect-approved').check();await page.locator('#inspect').click();await page.locator('#use-proposals').waitFor({state:'visible',timeout:20000});
  assert.ok(await page.locator('audio').count()>=2);
  const audio=page.locator('audio').first();const response=await page.request.get(new URL(await audio.getAttribute('src'),page.url()).href);assert.equal(response.status(),200);assert.equal(response.headers()['content-type'],'audio/wav');
  await audio.evaluate(async a=>{await a.play();a.pause();});
  await page.locator('#use-proposals').click();assert.equal(await page.locator('#approved').isChecked(),false);
  for(const f of await page.locator('#segments fieldset').all()){assert.equal(await f.locator('[data-key=name]').inputValue(),'');assert.equal(await f.locator('[data-key=labelStatus]').inputValue(),'');}
  let n=0;for(const f of await page.locator('#segments fieldset').all()){await f.locator('[data-key=name]').fill('Original synthetic region '+(++n));await f.locator('[data-key=labelStatus]').selectOption('original-speaker-reviewed');}
  await page.locator('#approved').check();const saved=page.waitForResponse(r=>r.url().endsWith('/review')&&r.request().method()==='POST');await page.locator('#submit').click();const sent=await saved;assert.equal(sent.status(),200);assert.match(sent.request().postDataJSON().inspectedSourceSHA256,/^[a-f0-9]{64}$/);
  await page.locator('#status').filter({hasText:'Reviewed segments saved'}).waitFor();
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:'source-inspection-mobile.png',fullPage:true});
  await page.goto('http://127.0.0.1:'+port+'/listening');await page.locator('#candidates section').waitFor();
  assert.equal(await page.locator('select[name=decision]').inputValue(),'');
  for(const audio of await page.locator('audio').all())await audio.evaluate(async a=>{await a.play();a.pause();});
  await page.locator('input[name=reviewer]').fill('Original fixture reviewer');await page.locator('select[name=decision]').selectOption('Unsure');await page.locator('form button').click();await page.locator('.status').filter({hasText:'Decision saved'}).waitFor();
  await page.locator('#refresh').click();await page.locator('#candidates section').filter({hasText:'Original fixture reviewer: Unsure'}).waitFor();
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:'listening-review-mobile.png',fullPage:true});
  console.log('Private reference/preview browser playback, explicit Unsure decision and durable refresh passed');
  console.log('Real mobile browser inspection request, owned-worker AV activity previews, audio playback, explicit label review and source-bound HTTP save passed');
 }finally{if(browser)await browser.close();lines.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
