const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const assert=require('node:assert/strict');
(async()=>{
 const server=spawn('python3',['tests/source_review_browser_server.py']);
 const lines=readline.createInterface({input:server.stdout});let browser;
 try{
  const port=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Server startup timed out')),15000);server.on('exit',()=>reject(Error('Server exited')));lines.once('line',line=>{clearTimeout(timer);resolve(Number(line));});});
  browser=await chromium.launch({headless:true,...(process.env.VM_BROWSER_EXECUTABLE?{executablePath:process.env.VM_BROWSER_EXECUTABLE}:{})});
  const page=await browser.newPage({viewport:{width:390,height:844},extraHTTPHeaders:{Authorization:'Bearer '+'s'.repeat(48)}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));const root='http://127.0.0.1:'+port;
  await page.goto(root+'/workflow-log');await page.locator('#state').filter({hasText:'Connected'}).waitFor();
  const checked=page.locator('article').filter({hasText:'Video SYNTHETIC05'});
  await checked.filter({hasText:'Technical processing ended; review pending'}).waitFor();
  assert.match(await checked.innerText(),/Worker is generating test speech/);
  assert.match(await checked.innerText(),/not complete/);
  const waiting=page.locator('article').filter({hasText:'Video SYNTHETIC04'});
  assert.match(await waiting.innerText(),/Waiting for a worker/);
  assert.doesNotMatch(await waiting.innerText(),/Worker is generating|Worker processing/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  const response=await page.request.post(root+'/queue',{data:{videos:[{url:'https://youtu.be/SYNTHETIC04',name:'<script>private-name</script>'}]}});assert.equal(response.status(),200);
  await page.locator('#refresh').click();
  await waiting.filter({hasText:'Laptop received this link again'}).waitFor({timeout:6000});
  assert.doesNotMatch(await page.locator('#videos').innerText(),/private-name/);
  await waiting.locator('a').click();await page.locator('#state').filter({hasText:'Connected'}).waitFor();
  assert.equal(await page.locator('article').count(),1);assert.match(page.url(),/video=SYNTHETIC04/);
  await page.screenshot({path:process.env.VM_WORKFLOW_SCREENSHOT||'/tmp/voicematrix-workflow-mobile.png',fullPage:true});
  await page.route('**/workflow?video=*',route=>route.fulfill({status:503,body:'unavailable'}));
  await page.locator('#refresh').click();await page.locator('#state').filter({hasText:'Displayed history is stale'}).waitFor();
  assert.equal(await page.locator('article').count(),1);assert.deepEqual(errors,[]);
  console.log('Workflow browser passed: real receipt, waiting, checked processing, duplicate receipt, per-video navigation, mobile layout, privacy and stale connection.');
 }finally{if(browser)await browser.close();lines.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
