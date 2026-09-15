// Read-only authenticated route, theme, responsive-layout and axe smoke.
// Credentials stay in memory; only the configured TraceLab API receives them.
// Run against a production build, then again with UI_BASE=https://tracelab.aquex.ai.
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {inspectInternalLinks} from './route-migration-links.mjs';
const require=createRequire(new URL("../package.json", import.meta.url));
const {chromium}=require('playwright');
let browser;
async function run() {
const base=process.env.UI_BASE || 'http://localhost:3100';
const directProduction = new URL(base).origin === 'https://tracelab.aquex.ai';
const timezoneId=process.env.UI_TIMEZONE || 'America/Chicago';
const out=process.env.UI_OUT || path.join(os.tmpdir(), 'tracelab-ui-shell');
await fs.mkdir(out,{recursive:true});
const creds=JSON.parse(await fs.readFile(path.join(os.homedir(),'.config/tracelab-mcp/credentials.json'),'utf8'));
const api='https://api.tracelab.aquex.ai';
if(creds.apiBaseUrl.replace(/\/$/,'')!==api)throw Error('Unexpected credential scope');
async function get(route){const r=await fetch(api+'/api/v1'+route,{headers:{'X-API-Key':creds.key}}); if(!r.ok)throw Error('API preflight '+route+' '+r.status);return r.json()}
const [me,projects,documents,missions,reports,collections]=await Promise.all(['/auth/me','/projects?page_size=100','/documents?page_size=1','/missions?page_size=100','/reports?page_size=1','/collections'].map(get));
const project=projects.data.find(p=>p.id==='0afcc588-e722-45bd-8320-f486601b877c')||projects.data[0];
const mission=missions.data.find(m=>m.mission_id==='TL-UX-R001')||missions.data[0];
const ids={project:project.id,document:documents.data[0].id,mission:mission.id,report:reports.items[0].id,collection:collections.data[0]?.id};
await fs.writeFile(out+'/inventory.json',JSON.stringify({ids,projectName:project.name,missionName:mission.mission_id,role:me.role},null,2));
const evidence = await get('/evidence?project_id='+project.id);
const routes=['/','/inbox','/graph',`/graph?root=project:${ids.project}`,'/projects',`/projects/${ids.project}`,'/documents',`/documents/${ids.document}`,'/documents/upload','/collections',`/collections/${ids.collection}`,'/reports',`/reports/${ids.report}`,'/missions',`/missions/${ids.mission}`,'/missions/new','/missions/queue','/missions?view=attention&reason=unreviewed','/search','/search/results','/saved-searches','/settings','/invites','/device','/admin/users','/admin/spaces','/console','/console/missions',`/console/missions/${ids.mission}`,'/console/corrections','/404','/evidence','/admin/observability','/admin/corrections',...(evidence.entries[0]?['/evidence/'+evidence.entries[0].id]:[])];
const selected=process.env.UI_ROUTE?[process.env.UI_ROUTE]:process.env.UI_PROBE?['/missions','/search','/settings','/admin/users','/evidence']:routes;
browser=await chromium.launch({headless:true});
const results=[];
for (const theme of (process.env.UI_THEME?[process.env.UI_THEME]:['light','dark'])) {
 for (const width of (process.env.UI_WIDTH?[Number(process.env.UI_WIDTH)]:[1440,390])) {
  let transportErrors=[]; let navigationCancellations=[];
  const context=await browser.newContext({timezoneId,viewport:{width,height:1000},colorScheme:theme === 'dark' ? 'dark' : 'light'});
  await context.route(/https?:\/\/(api\.tracelab\.aquex\.ai|localhost:8000|127\.0\.0\.1:8103)\/.*/, async route => {
    const incoming = new URL(route.request().url());
    const method = route.request().method();
    // Facet metadata is an authenticated read even though its API uses POST.
    const readOnly = method === 'GET' || (method === 'POST' && incoming.pathname === '/api/v1/facets');
    try {
      if (directProduction) {
        if (incoming.origin !== api) throw Error('Production UI requested a non-production API');
        if (route.request().method() === 'OPTIONS') { await route.continue(); return; }
        if (!readOnly) throw Error('Smoke forbids API writes');
        const headers = {...route.request().headers(), 'x-api-key':creds.key};
        delete headers.authorization;
        await route.continue({headers}); return;
      }
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({status:204, headers:{'access-control-allow-origin':base,'access-control-allow-headers':'authorization,content-type,x-api-key','access-control-allow-methods':'GET,POST,OPTIONS'}}); return;
      }
      if (!readOnly) throw Error('Smoke forbids API writes');
      const response = await fetch(api + incoming.pathname + incoming.search, {method, headers:{'X-API-Key':creds.key,'Content-Type':'application/json'}, ...(method === 'POST' ? {body:route.request().postData()} : {})});
      if (!response.ok) transportErrors.push({path:incoming.pathname,status:response.status});
      await route.fulfill({status:response.status,body:await response.text(),headers:{'content-type':'application/json','access-control-allow-origin':base}});
    } catch { transportErrors.push({path:incoming.pathname,error:'API smoke request failed'}); await route.abort().catch(() => {}); }
  });
  await context.addInitScript(({user,theme})=>{
   localStorage.setItem('tracelab.auth.v2',JSON.stringify({token:'ui-smoke-placeholder',user_id:user.user_id,email:user.email,display_name:'UX validation'}));
   localStorage.setItem('tracelab.theme.v1:'+user.user_id,theme);
  },{user:me,theme});
  const page=await context.newPage();
  let errors=[];page.on('pageerror',()=>errors.push('Client-side exception (detail suppressed)'));
  page.on('response', response => { if(directProduction && new URL(response.url()).origin === api && response.status() >= 400) transportErrors.push({path:new URL(response.url()).pathname,status:response.status()}); });
  page.on('requestfailed', request => { if(new URL(request.url()).origin === api) { const failure = request.failure()?.errorText; const item={path:new URL(request.url()).pathname,error:failure || 'Browser API request failed'}; if(failure === 'net::ERR_ABORTED') navigationCancellations.push(item); else transportErrors.push(item); } });
  for(const route of selected) {
   errors=[]; transportErrors=[]; navigationCancellations=[];
   const slug=route.replace(/\//g,'_')||'home';
   const response=await page.goto(base+route,{waitUntil:'networkidle',timeout:60000});
   await page.waitForTimeout(400);
   if(route==='/evidence') {await page.getByLabel('Find a project').fill(project.name);await page.getByRole('combobox',{name:'Project',exact:true}).selectOption(ids.project);await page.getByText(`${evidence.entry_total} evidence entries`,{exact:true}).waitFor();await page.waitForLoadState('networkidle');}
   await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});
   const measured=await page.evaluate(async()=>{
    const axe=await window.axe.run(document,{resultTypes:['violations']});
    const rules=['html-has-lang','region','landmark-one-main','landmark-no-duplicate-banner'];
    const root=document.documentElement;
    return {width:innerWidth,scrollWidth:root.scrollWidth,theme:root.dataset.theme,mainCount:document.querySelectorAll('main').length,shellPresent:!!document.querySelector('.app-workspace'),background:getComputedStyle(document.body).backgroundColor,
     overflow:[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+1||r.left < -1)&&getComputedStyle(e).visibility!=='hidden'&&e.getClientRects().length}).slice(0,15).map(e=>({tag:e.tagName,class:e.className,text:e.textContent?.slice(0,45)})),
     violations:axe.violations.filter(v=>rules.includes(v.id)||['critical','serious'].includes(v.impact)).map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,html:n.html.slice(0,400),summary:n.failureSummary}))}))};
   });
   // Settings contains live invite codes and key prefixes. Preserve selectors
   // and contrast measurements, but never retain its literal HTML or text.
   if (page.url().includes('/settings')) {
     for (const violation of measured.violations) for (const node of violation.nodes) node.html = '[settings content omitted]';
     for (const node of measured.overflow) node.text = '[settings content omitted]';
   }
   const shot=`${theme}-${width}-${slug}.png`;
   const links=inspectInternalLinks(await page.locator('a[href]').evaluateAll(nodes=>nodes.map(node=>node.href)),page.url());
   await page.screenshot({path:path.join(out,shot),fullPage:true, mask:page.url().includes('/settings')?[page.locator('code')]:[]});
   const result={route,themeRequested:theme,theme,width,status:response.status(),finalUrl:page.url(),...measured,...links,errors,transportErrors:[...transportErrors],navigationCancellations:[...navigationCancellations],screenshot:shot};
   results.push(result);
   await fs.writeFile(out+'/results.json',JSON.stringify(results,null,2));
   console.log(JSON.stringify({route,theme,width,status:response.status(),overflow:measured.scrollWidth>width+1,violations:measured.violations.map(v=>v.id+':'+v.nodes.length),errors:errors.length}));
  }
  await context.close();
 }
}
await browser.close();
browser=undefined;
const failures=results.filter(r => r.scrollWidth > r.width+1 || r.violations.length || r.errors.length || r.transportErrors.length || r.legacyInternalLinks.length || r.mainCount !== 1 || !r.shellPresent || r.theme !== r.themeRequested || r.status !== (r.route === '/404' ? 404 : 200));
await fs.writeFile(out+'/summary.json', JSON.stringify({base, timezoneId, checkedAt:new Date().toISOString(), checks:results.length, routes:[...new Set(results.map(r=>r.route))].length, failures:failures.map(r=>({route:r.route,theme:r.theme,width:r.width})), internalLinkPaths:[...new Set(results.flatMap(r=>r.internalLinks))].sort(), legacyInternalLinks:results.flatMap(r=>r.legacyInternalLinks), readOnly:true, directProductionApi:directProduction, readOnlyApiProxy:!directProduction},null,2));
if(failures.length)process.exitCode=1;

}
try { await run(); } catch { console.error("UI smoke could not finish. Browser/API error details suppressed to protect request credentials."); process.exitCode=1; } finally { await browser?.close(); }
