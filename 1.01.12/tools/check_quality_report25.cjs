// SPDX-License-Identifier: MIT
// Check only our local report in an isolated headless Edge profile.
const fs=require('fs'),path=require('path'),{spawn}=require('child_process'),{pathToFileURL}=require('url');
const root=path.resolve(__dirname,'..'),reports=path.join(root,'reports');
const profile=path.join(reports,'edge-quality25-'+Date.now());
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
fs.mkdirSync(profile,{recursive:true});
const child=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
 ['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
 {windowsHide:true,stdio:'ignore'});
let socket,seq=0;const pending=new Map(),exceptions=[];
function call(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('CDP timeout: '+method))}},15000).unref()})}
async function evaluate(expression){const v=await call('Runtime.evaluate',{expression,returnByValue:true});if(v.exceptionDetails)throw Error(JSON.stringify(v.exceptionDetails));return v.result.value}
async function screenshot(name){const s=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const dest=path.join(reports,name);fs.writeFileSync(dest,Buffer.from(s.data,'base64'));return dest}
const test=`(()=>{const checks=[],c=(v,n)=>{if(!v)throw Error(n);checks.push(n)};c(data.latency.baseline==='0.01.15'&&data.latency.current==='0.01.25','named baseline/current');c(data.axis_ms===3000,'data-derived 3 second reference');c(data.latency.samples.length===6,'all six timing samples');for(let i=0;i<3;i++){document.querySelector('[data-scene="'+i+'"]').click();for(const side of ['before','after'])c(document.querySelectorAll('#'+side+'-frame .box').length===data.scenes[i][side].lines.length,'actual boxes '+i+' '+side)}document.querySelector('[data-scene="0"]').click();c(document.getElementById('after-text').textContent.includes('souvenirs'),'selected text is retained');document.getElementById('boxes').click();c(document.getElementById('before-frame').classList.contains('hide'),'box toggle hides');document.getElementById('boxes').click();c(!document.getElementById('after-frame').classList.contains('hide'),'box toggle shows');for(const name of ['complete_ms','first_native_paint_ms']){document.querySelector('[data-metric="'+name+'"]').click();const expected=(data.axis_ms-data.latency.summary['0.01.25'][name].median)/data.axis_ms*100;c(Math.abs(parseFloat(document.getElementById('bar-after').style.width)-expected)<.001,'inverse elapsed bar '+name)}c(document.body.innerText.includes('1.863 → 1.994'),'slower first pair retained');c(document.body.innerText.includes('10.172 s')&&document.body.innerText.includes('10.822 s'),'live assisted timing separate');c(document.documentElement.scrollWidth<=innerWidth,'no horizontal page overflow');c([...document.images].every(img=>img.complete&&img.naturalWidth>0),'all embedded images loaded');c([...document.images].every(img=>img.src.startsWith('data:')),'all images offline');c(document.querySelector('title').textContent.includes('0.01.25'),'current page title');if(!data.english)c(document.querySelector('h1').textContent==='\\u54c1\\u8d28\\u7684\\u4f53\\u9a8c\\uff0c\\u66f4\\u5c11\\u7684\\u7b49\\u5f85','approved customer headline');const ids=[...document.querySelectorAll('[id]')].map(x=>x.id);c(new Set(ids).size===ids.length,'no duplicate element ids');c([...document.querySelectorAll('a[href^="#"]')].every(a=>document.getElementById(a.hash.slice(1))),'internal section links');return {passed:true,width:innerWidth,language:document.documentElement.lang,checks}})()`;
(async()=>{try{
 const portfile=path.join(profile,'DevToolsActivePort');for(let i=0;i<150&&!fs.existsSync(portfile);i++)await sleep(100);
 const port=fs.readFileSync(portfile,'utf8').split('\n')[0].trim();let tabs,lastConnectError;
 for(let i=0;i<50;i++){try{tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();break}catch(e){lastConnectError=e;await sleep(100)}}
 if(!tabs)throw Error('Local Edge CDP connection failed: '+String(lastConnectError?.cause||lastConnectError));
 socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
 socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}};
 await call('Page.enable');await call('Runtime.enable');const results=[],shots=[];
 for(const english of [false,true]){
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1150,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:pathToFileURL(path.join(root,'docs','PERFORMANCE_REPORT'+(english?'.en':'')+'.html')).href});
  for(let i=0;i<150;i++){if(await evaluate('!!document.querySelector("#after-frame .box") && [...document.images].every(x=>x.complete&&x.naturalWidth)'))break;await sleep(100)}
  await sleep(150);results.push(await evaluate(test));
  const zoom=await evaluate(`(()=>{document.querySelector('[data-zoom]').click();if(!document.getElementById('image-viewer').open)throw Error('image zoom did not open');if(!document.querySelector('#viewer-content img').src.startsWith('data:'))throw Error('zoom should remain offline');document.getElementById('close-viewer').click();if(document.getElementById('image-viewer').open)throw Error('image zoom did not close');return 'offline image zoom opens/closes'})()`);results.at(-1).checks.push(zoom);
  shots.push(await screenshot('quality-report25-'+(english?'english':'desktop')+'.png'));
  if(!english){
   for(const [id,name] of [['timing','timing'],['evidence','ocr'],['typography','font'],['harness','harness']]){await evaluate('document.getElementById('+JSON.stringify(id)+').scrollIntoView({behavior:"instant"});true');await sleep(100);shots.push(await screenshot('quality-report25-'+name+'.png'))}
   await evaluate('document.querySelector(".panel.live").scrollIntoView({behavior:"instant"});true');await sleep(100);shots.push(await screenshot('quality-report25-live.png'));
  }
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:1000,deviceScaleFactor:1,mobile:true});await evaluate('window.scrollTo({top:0,behavior:"instant"});true');await sleep(100);results.push(await evaluate(test));shots.push(await screenshot('quality-report25-'+(english?'english-mobile':'mobile')+'.png'));
 }
 if(exceptions.length)throw Error('Browser runtime exception: '+JSON.stringify(exceptions));
 const result={version:'0.01.25',method:'Isolated headless Edge; actual DOM interactions and PNG screenshots',passed:true,results,screenshots:shots,runtime_exceptions:exceptions};
 fs.writeFileSync(path.join(reports,'quality-report-browser25.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 await call('Browser.close').catch(()=>{});socket.close();
 }catch(e){console.error(String(e));process.exitCode=1;if(socket)socket.close();child.kill()}
 finally{setTimeout(()=>process.exit(process.exitCode||0),100).unref()}
})();
