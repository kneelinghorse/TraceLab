import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { TraceLabAPIError } from './api-client.js';

// MCP-6: tracelab_search ask is QA-1's Q&A over POST /search/ask. An agent gets the
// answer the Librarian would give, with every citation opening its chunk, or an
// explicit nothing-found result; a project the caller cannot read is an error, never
// an empty answer.
const project = '00000000-0000-4000-8000-000000000001';
const document = '00000000-0000-4000-8000-000000000002';
const chunk = '00000000-0000-4000-8000-000000000003';
const base = 'https://api.tracelab.aquex.ai';
const web = 'https://tracelab.aquex.ai';
const href = `/documents/${document}?chunk=${chunk}&index=9`;
const fetchMock = vi.fn();
let dispatch: typeof import('./index.js').resolveClusterHandler;

beforeAll(async () => {
  vi.stubEnv('TRACELAB_API_URL', base);
  vi.stubEnv('TRACELAB_API_KEY', 'tl_ask_contract');
  vi.stubEnv('TRACELAB_TOKEN', '');
  vi.stubGlobal('fetch', fetchMock);
  dispatch = (await import('./index.js')).resolveClusterHandler;
});
beforeEach(() => fetchMock.mockReset());
afterAll(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function respond(payload: unknown, status = 200) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } }));
}
async function ask(args: Record<string, unknown>) {
  const response = await dispatch('tracelab_search')!({ action: 'ask', ...args });
  expect(response).not.toHaveProperty('isError', true);
  return JSON.parse(response.content[0].text);
}
function lastRequest() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { url, method: init.method, body: JSON.parse(init.body as string), headers: init.headers as Record<string, string> };
}

const answered = {
  answer: 'The bill is **$48–$63** a month.\n\nManaged hosting costs more.',
  passages: [
    { text: 'The bill is **$48–$63** a month.', citations: [chunk] },
    { text: 'Managed hosting costs more.', citations: [] },
  ],
  citations: [{ chunk_id: chunk, document_id: document, document_name: 'qdrant-on-railway.md', chunk_index: 9, snippet: 'The Hobby plan bill is $48-$63 a month.', href }],
  no_evidence: false,
  model: 'gpt-test',
};

describe('MCP-6 tracelab_search ask', () => {
  it('asks through POST /search/ask and links every citation to its chunk', async () => {
    respond(answered);
    const value = await ask({ project_id: project, question: '  What does self-hosting Qdrant cost?  ', max_tokens: 2000 });
    expect(lastRequest()).toMatchObject({
      url: `${base}/api/v1/search/ask`,
      method: 'POST',
      body: { project_id: project, question: 'What does self-hosting Qdrant cost?', max_tokens: 2000 },
    });
    expect(lastRequest().headers['X-API-Key']).toBe('tl_ask_contract');
    expect(value.answer).toBe(answered.answer);
    expect(value.passages).toEqual(answered.passages);
    expect(value.no_evidence).toBe(false);
    expect(value.citations).toEqual([{ ...answered.citations[0], url: `${web}${href}` }]);
    expect(value.project_url).toBe(`${web}/projects/${project}`);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('leaves the budget to the server when max_tokens is omitted', async () => {
    respond(answered);
    await ask({ project_id: project, question: 'What does it cost?' });
    expect(lastRequest().body).toEqual({ project_id: project, question: 'What does it cost?' });
  });

  it('returns the nothing-found result as it is, asserting nothing', async () => {
    const refusal = 'Nothing in this project answers that question.';
    respond({ answer: refusal, passages: [{ text: refusal, citations: [] }], citations: [], no_evidence: true, model: null });
    const value = await ask({ project_id: project, question: 'How does Kubernetes autoscale pods?' });
    expect(value).toMatchObject({ answer: refusal, no_evidence: true, citations: [] });
  });

  it('surfaces a refused project as the API error, never as an empty answer', async () => {
    respond({ detail: 'You do not have access to this resource.' }, 403);
    const failure = dispatch('tracelab_search')!({ action: 'ask', project_id: project, question: 'What does it cost?' });
    await expect(failure).rejects.toBeInstanceOf(TraceLabAPIError);
    await expect(failure).rejects.toMatchObject({ statusCode: 403 });
  });

  it.each([
    { question: 'What does it cost?' },
    { project_id: 'not-a-uuid', question: 'What does it cost?' },
    { project_id: project },
    { project_id: project, question: '   ' },
    { project_id: project, question: 'x'.repeat(20001) },
    { project_id: project, question: 'Cost?', max_tokens: 63 },
    { project_id: project, question: 'Cost?', max_tokens: 4001 },
    { project_id: project, question: 'Cost?', max_tokens: 600.5 },
  ])('rejects invalid ask input before HTTP: %j', async args => {
    await expect(dispatch('tracelab_search')!({ action: 'ask', ...args })).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
