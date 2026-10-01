// The shared smoke route handler is exercised in both production and proxy modes.
export async function handleSmokeApiRequest(route, {api, base, directProduction, apiKey, transportErrors, suppressedWrites, fetchResponse = fetch}) {
    const incoming = new URL(route.request().url());
    const method = route.request().method();
    const readOnly = method === 'GET' || (method === 'POST' && incoming.pathname === '/api/v1/pedr/search');
    const localWrite = method === 'PUT' && ['/api/v1/activity/viewed', '/api/v1/activity/viewed/evidence'].includes(incoming.pathname);
    try {
      if (directProduction) {
        if (incoming.origin !== api) throw Error('Production UI requested a non-production API');
        if (method === 'OPTIONS') { await route.continue(); return; }
        if (localWrite) { suppressedWrites.push({method, path:incoming.pathname}); await route.fulfill({status:200, json:{viewed:0,new_total:0}, headers:{'access-control-allow-origin':base,'access-control-allow-credentials':'true'}}); return; }
        if (!readOnly) throw Error('Smoke forbids API writes');
        const headers = {...route.request().headers(), 'x-api-key':apiKey};
        delete headers.authorization;
        await route.continue({headers}); return;
      }
      if (method === 'OPTIONS') {
        await route.fulfill({status:204, headers:{'access-control-allow-origin':base,'access-control-allow-headers':'authorization,content-type,x-api-key','access-control-allow-methods':'GET,POST,PUT,OPTIONS'}}); return;
      }
      if (localWrite) { suppressedWrites.push({method, path:incoming.pathname}); await route.fulfill({status:200, json:{viewed:0,new_total:0}, headers:{'access-control-allow-origin':base}}); return; }
      if (!readOnly) throw Error('Smoke forbids API writes');
      const response = await fetchResponse(api + incoming.pathname + incoming.search, {method, headers:{'X-API-Key':apiKey,'Content-Type':'application/json'}, ...(method === 'POST' ? {body:route.request().postData()} : {})});
      if (!response.ok) transportErrors.push({path:incoming.pathname,status:response.status});
      await route.fulfill({status:response.status,body:await response.text(),headers:{'content-type':'application/json','access-control-allow-origin':base}});
    } catch { transportErrors.push({path:incoming.pathname,error:'API smoke request failed'}); await route.abort().catch(() => {}); }
}
