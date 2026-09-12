// Read-only authenticated route, theme, responsive-layout and axe smoke.
// Credentials stay in memory; only the configured TraceLab API receives them.
// Run against a production build, then again with UI_BASE=https://tracelab.aquex.ai.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(new URL("../package.json", import.meta.url));
const {chromium}=require('playwright');
let browser;
async function run() {
const base=process.env.UI_BASE || 'http://localhost:3100';
const out=process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-ui-shell');
await fs.mkdir(out,{recursive:true});
const creds=JSON.parse(await fs.readFile(path.join(os.homedir(),'.config/tracelab-mcp/credentials.json'),'utf8'));
const api='https://api.tracelab.aquex.ai';
if(creds.apiBaseUrl.replace(/\/$/,'')!==api)throw Error('Unexpected credential scope');
async function get(route){const r=await fetch(api+'/api/v1'+route,{headers:{'X-API-Key':creds.key}}); if(!r.ok)throw Error('API preflight '+route+' '+r.status);return r.json()}
const [me,projects,documents,missions,reports,collections]=await Promise.all(['/auth/me','/projects?page_size=100','/documents?page_size=1','/missions?page_size=100','/reports?page_size=1','/collections'].map(get));
const project=projects.data.find(p=>/UX|TraceLab/i.test(p.name))||projects.data[0];
const mission=missions.data.find(m=>m.mission_id==='TL-UX-R001')||missions.data[0];
const ids={project:project.id,document:documents.data[0].id,mission:mission.id,report:reports.items[0].id,collection:collections.data[0]?.id};
await fs.writeFile(out+'/inventory.json',JSON.stringify({ids,projectName:project.name,missionName:mission.mission_id,role:me.role},null,2));
const routes=['/','/projects',`/projects/${ids.project}`,'/documents',`/documents/${ids.document}`,'/documents/upload','/collections',`/collections/${ids.collection}`,'/reports',`/reports/${ids.report}`,'/missions',`/missions/${ids.mission}`,'/missions/new','/missions/queue','/search','/search/results','/saved-searches','/settings','/invites','/device','/admin/users','/admin/spaces','/console','/console/missions',`/console/missions/${ids.mission}`,'/console/corrections','/404','/evidence'];
const selected=process.env.UI_ROUTE?[process.env.UI_ROUTE]:process.env.UI_PROBE?['/missions','/search','/settings','/admin/users','/evidence']:routes;
browser=await chromium.launch({headless:true});
const results=[];
for (const theme of (process.env.UI_THEME?[process.env.UI_THEME]:['light','dark'])) {
 for (const width of (process.env.UI_WIDTH?[Number(process.env.UI_WIDTH)]:[1440,390])) {
  let transportErrors=[];
  const context=await browser.newContext({viewport:{width,height:1000},colorScheme:theme});
  await context.route(api+'/**', async route => {
    try {
    const headers = {...route.request().headers()};
    delete headers.authorization;
    headers['X-API-Key'] = creds.key;
    if (base.startsWith('http://localhost')) {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({status: 204, headers: {'access-control-allow-origin': base, 'access-control-allow-headers':'authorization,content-type,x-api-key', 'access-control-allow-methods':'GET,POST,PUT,PATCH,DELETE,OPTIONS'}});
      } else {
        try {
          const response = await route.fetch({headers, timeout:45000});
          await route.fulfill({response, headers:{...response.headers(), 'access-control-allow-origin':base, 'access-control-allow-credentials':'true'}});
        } catch {
          transportErrors.push({path:new URL(route.request().url()).pathname, error:'API proxy request failed'});
          await route.abort().catch(() => {});
        }
      }
    } else await route.continue({headers});
    } catch { transportErrors.push({path:new URL(route.request().url()).pathname,error:"API route failed"}); await route.abort().catch(() => {}); }
  });
  await context.addInitScript(({user,theme})=>{
   localStorage.setItem('tracelab.auth.v2',JSON.stringify({token:'ui-smoke-placeholder',user_id:user.user_id,email:user.email,display_name:'UX validation'}));
   localStorage.setItem('tracelab.theme.v1:'+user.user_id,theme);
  },{user:me,theme});
  const page=await context.newPage();
  let errors=[];page.on('pageerror',e=>errors.push(e.message.slice(0,300)));
  for(const route of selected) {
   errors=[]; transportErrors=[];
   const slug=route.replace(/\//g,'_')||'home';
   const response=await page.goto(base+route,{waitUntil:'networkidle',timeout:60000});
   await page.waitForTimeout(400);
   if(route==='/evidence') {await page.getByLabel('Find a project').fill(project.name);await page.getByRole('combobox',{name:'Project',exact:true}).selectOption(ids.project);await page.waitForTimeout(1200);}
   await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
   const measured=await page.evaluate(async()=>{
    const axe=await window.axe.run(document,{resultTypes:['violations']});
    const rules=['html-has-lang','region','landmark-one-main','landmark-no-duplicate-banner'];
    const root=document.documentElement;
    return {width:innerWidth,scrollWidth:root.scrollWidth,theme:root.dataset.theme,mainCount:document.querySelectorAll('main').length,background:getComputedStyle(document.body).backgroundColor,
     overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+1||r.left < -1)&&getComputedStyle(e).visibility!=='hidden'&&e.getClientRects().length}).slice(0,15).map(e=>({tag:e.tagName,class:e.className,text:e.textContent?.slice(0,45)})),
     violations:axe.violations.filter(v=>rules.includes(v.id)||['critical','serious'].includes(v.impact)).map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,html:n.html.slice(0,400),summary:n.failureSummary}))}))};
   });
   const shot=`${theme}-${width}-${slug}.png`;
   await page.screenshot({path:path.join(out,shot),fullPage:true, mask:page.url().includes('/settings')?[page.locator('code')]:[]});
   const result={route,themeRequested:theme,theme,width,status:response.status(),finalUrl:page.url(),...measured,errors,transportErrors:[...transportErrors],screenshot:shot};
   results.push(result);
   await fs.writeFile(out+'/results.json',JSON.stringify(results,null,2));
   console.log(JSON.stringify({route,theme,width,status:response.status(),overflow:measured.scrollWidth>width+1,violations:measured.violations.map(v=>v.id+':'+v.nodes.length),errors:errors.length}));
  }
  await context.close();
 }
}
await browser.close();
browser=undefined;
const failures=results.filter(r => r.scrollWidth > r.width+1 || r.violations.length || r.errors.length || r.transportErrors.length || r.mainCount !== 1 || r.theme !== r.themeRequested || r.status !== (r.route === '/404' ? 404 : 200));
await fs.writeFile(out+'/summary.json', JSON.stringify({base, checkedAt:new Date().toISOString(), checks:results.length, routes:[...new Set(results.map(r=>r.route))].length, failures:failures.map(r=>({route:r.route,theme:r.theme,width:r.width})), localApiProxy:base.startsWith('http://localhost')},null,2));
if(failures.length)process.exitCode=1;

}
try { await run(); } catch { console.error("UI smoke could not finish. Browser/API error details suppressed to protect request credentials."); process.exitCode=1; } finally { await browser?.close(); }
