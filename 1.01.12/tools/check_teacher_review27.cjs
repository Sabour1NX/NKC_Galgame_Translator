// SPDX-License-Identifier: MIT
// Render only local project documentation in a separate headless Edge profile.
const fs = require('fs'), path = require('path');
const {spawn} = require('child_process'), {pathToFileURL} = require('url');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'reports', 'teacher-review27', 'document-screenshots');
const reportPath = path.join(root, 'reports', 'teacher-review27', 'document-browser.json');
const profile = path.join(root, 'build', 'teacher-review-edge-' + Date.now());
fs.mkdirSync(out, {recursive:true}); fs.mkdirSync(profile, {recursive:true});
const sleep = ms => new Promise(r => setTimeout(r, ms));
let socket, seq = 0; const pending = new Map(), errors = [], results = [], shots = [];
const child = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
 ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'],
 {windowsHide:true, stdio:'ignore'});
function call(method, params={}) {
 return new Promise((resolve,reject) => {
  const id=++seq; pending.set(id,{resolve,reject}); socket.send(JSON.stringify({id,method,params}));
  setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('Timeout: '+method))}},20000).unref();
 });
}
async function evaluate(expression) {
 const r = await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
 return r.result.value;
}
async function capture(name, detail) {
 const image = await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 fs.writeFileSync(path.join(out,name),Buffer.from(image.data,'base64'));
 shots.push({file:name,...detail});
}
async function inspect(relative, prefix, mobile=false) {
 const file=path.join(root,relative); if(!fs.existsSync(file))throw Error('Missing '+relative);
 await call('Emulation.setDeviceMetricsOverride',{width:mobile?430:1440,height:1000,deviceScaleFactor:1,mobile});
 await call('Page.navigate',{url:pathToFileURL(file).href});
 await sleep(450);
 await evaluate('Promise.all([document.fonts.ready,...Array.from(document.images).map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r}))]).then(()=>true)');
 const state=await evaluate(`(()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);return {
  title:document.title, width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
  missingImages:[...document.images].filter(i=>!i.complete||!i.naturalWidth).map(i=>i.getAttribute('src').slice(0,150)),
  duplicateIds:ids.filter((v,i)=>ids.indexOf(v)!==i),
  missingAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>a.hash.length>1&&!document.getElementById(decodeURIComponent(a.hash.slice(1)))).map(a=>a.hash),
  remoteResources:[...document.querySelectorAll('script[src],link[rel="stylesheet"],img[src],iframe[src]')].map(e=>e.src||e.href).filter(s=>/^https?:/.test(s)),
  sections:[...document.querySelectorAll('article[id], main>section[id], main>div>section[id], body>section[id]')].map(e=>({id:e.id,title:(e.querySelector('h1,h2,h3')?.innerText||e.id).trim()}))
 }})()`);
 state.file=relative; state.mobile=mobile;
 state.passed=state.scrollWidth<=state.width+1&&!state.missingImages.length&&!state.duplicateIds.length&&!state.missingAnchors.length&&!state.remoteResources.length;
 results.push(state);
 await evaluate('scrollTo({top:0,behavior:"instant"});true');
 await capture(prefix+'-top.png',{document:relative,view:'top',mobile,title:state.title});
 if(!mobile){
  for(const section of state.sections){
   await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(section.id)});e.scrollIntoView({block:'start',behavior:'instant'});return true})()`);
   await sleep(40);
   await capture(prefix+'-'+section.id.replace(/[^a-z0-9_-]/gi,'-')+'.png', {document:relative,view:section.id,title:section.title,mobile:false});
  }
 }
}
(async()=>{try{
 const portfile=path.join(profile,'DevToolsActivePort');
 for(let n=0;n<150&&!fs.existsSync(portfile);n++)await sleep(100);
 const port=fs.readFileSync(portfile,'utf8').split('\n')[0].trim();let tabs;
 for(let n=0;n<50;n++){try{tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();break}catch{await sleep(100)}}
 socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
 await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});
 socket.onmessage=ev=>{const m=JSON.parse(ev.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params)};
 await call('Page.enable'); await call('Runtime.enable');
 const pages=[['docs/teacher-review27/index.html','portal'],['docs/teacher-review27/performance.html','review-performance'],
  ['docs/teacher-review27/gallery.html','gallery'],['docs/teacher-review27/architecture.html','architecture'],['docs/PERFORMANCE_REPORT.html','performance'],
  ['docs/PERFORMANCE_REPORT.en.html','performance-en'],['docs/PROJECT_MANUAL.html','manual'],['docs/PROJECT_MANUAL.en.html','manual-en']];
 for(const [file,prefix] of pages){await inspect(file,prefix);await inspect(file,prefix+'-mobile',true)}
 const report={version:'0.01.27',method:'Isolated headless Microsoft Edge, actual local HTML rendering, section screenshots',
  passed:results.every(x=>x.passed)&&!errors.length,results,screenshots:shots,runtimeErrors:errors};
 fs.writeFileSync(reportPath,JSON.stringify(report,null,2));
 console.log(JSON.stringify({passed:report.passed,pages:results.length,screenshots:shots.length,failed:results.filter(r=>!r.passed),report:reportPath}));
 await call('Browser.close').catch(()=>{});socket.close();if(!report.passed)process.exitCode=1;
 }catch(e){console.error(String(e));process.exitCode=1;if(socket)socket.close();child.kill()}
 finally{setTimeout(()=>process.exit(process.exitCode||0),100).unref()}
})();
