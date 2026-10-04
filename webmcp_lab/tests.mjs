import test from 'node:test';
import assert from 'node:assert/strict';
import { setImmediate as tick } from 'node:timers/promises';
import { mountTools, object, text, validate } from './core.mjs';
import { createWorkbench } from './workflows.mjs';
const permitted = options => createWorkbench({ approve: async () => true, ...options });
async function call(lab, name, args = {}) { const result = await lab.call(name, args); assert.equal(result.ok, true, JSON.stringify(result)); return result.data; }
function registry() {
  const tools = new Map();
  return { tools, root: { modelContext: { registerTool(tool, { signal }) {
    if (tools.has(tool.name)) throw new Error('Duplicate name');
    if (signal.aborted) throw new Error('Cancelled');
    tools.set(tool.name, tool);
    signal.addEventListener('abort', () => { if (tools.get(tool.name) === tool) tools.delete(tool.name); }, { once: true });
  } } } };
}
test('19 explicit tools with six reads, closed schemas and untrusted outputs', () => {
  const lab = permitted();
  assert.equal(lab.tools.length, 19);
  assert.equal(lab.tools.filter(tool => tool.annotations.readOnlyHint).length, 6);
  assert.equal(new Set(lab.tools.map(tool => tool.name)).size, 19);
  for (const tool of lab.tools) { assert.equal(tool.inputSchema.additionalProperties, false); assert.equal(tool.annotations.untrustedContentHint, true); assert.ok(tool.description.length > 20); }
  assert.ok(!lab.tools.some(tool => /send|execute_code|fetch_url/.test(tool.name)));
});
test('all writes fail closed when no approval provider is supplied', async () => {
  const lab = createWorkbench();
  const result = await lab.call('add_grocery_items', { items: ['Bread'] });
  assert.equal(result.error.code, 'approval_required'); assert.equal(lab.getState().groceries.length, 0); assert.equal(lab.getState().revision, 0);
});
test('blank, malformed, unknown and oversized inputs are rejected without changes', async () => {
  const lab = permitted();
  for (const args of [null, [], {}, { items: [' '] }, { items: [1] }, { items: ['x'.repeat(161)] }, { items: [] }, { items: Array(21).fill('x') }, { items: ['x'], approved: true }]) {
    const result = await lab.call('add_grocery_items', args); assert.equal(result.error.code, 'invalid_input');
  }
  assert.equal(lab.getState().revision, 0);
});
test('schema validator rejects unknown schema types and non-plain inputs', () => {
  assert.throws(() => validate({ type: 'not-supported' }, 1), /Unsupported/);
  assert.throws(() => validate(object({ item: text() }), new Date()), /plain object/);
});
test('grocery batch addition and removal share current state', async () => {
  const lab = permitted();
  const rows = await call(lab, 'add_grocery_items', { items: [' Bread ', 'Oatmeal'] });
  assert.equal(rows[0].item, 'Bread'); assert.equal((await call(lab, 'get_groceries')).length, 2);
  await call(lab, 'remove_grocery_item', { id: rows[0].id }); assert.equal((await call(lab, 'get_groceries'))[0].item, 'Oatmeal');
});
test('results and state snapshots cannot mutate the underlying store', async () => {
  const lab = permitted(); const board = await call(lab, 'get_board'); board[0].title = 'Changed';
  const snapshot = lab.getState(); snapshot.board[0].title = 'Changed again';
  assert.equal((await call(lab, 'get_board'))[0].title, 'Agent-friendly checkout');
});
test('Kanban composes read, move, priority and creation tools', async () => {
  const lab = permitted(); await call(lab, 'move_idea', { id: 'idea-1', column: 'building' });
  await call(lab, 'set_idea_priority', { id: 'idea-1', priority: 'high' }); await call(lab, 'add_idea', { title: 'Keyboard shortcuts' });
  const board = await call(lab, 'get_board'); assert.equal(board.length, 2); assert.equal(board[0].column, 'building'); assert.equal(board[0].priority, 'high');
});
test('invalid IDs and enum values do not ask for approval', async () => {
  let approvals = 0; const lab = permitted({ approve: async () => { approvals++; return true; } });
  assert.equal((await lab.call('move_idea', { id: 'missing', column: 'building' })).error.code, 'not_found');
  assert.equal((await lab.call('move_idea', { id: 'idea-1', column: 'production' })).error.code, 'invalid_input'); assert.equal(approvals, 0);
});
test('analytics filters and totals match the synthetic dataset', async () => {
  const lab = permitted();
  assert.equal((await call(lab, 'query_metrics', { period: 'all', channel: 'all' })).total, 45000);
  assert.equal((await call(lab, 'query_metrics', { period: 'current', channel: 'organic' })).total, 15000);
  await call(lab, 'show_revenue_chart', { period: 'current', channel: 'all' }); assert.equal(lab.getMetrics().length, 2);
});
test('inbox chooses highest unresolved request and drafts without sending', async () => {
  const lab = permitted(); const requests = await call(lab, 'find_refund_requests', { status: 'unresolved' });
  assert.equal(requests[0].id, 'refund-2'); assert.equal(requests.length, 2);
  await call(lab, 'open_refund_request', { id: requests[0].id });
  await call(lab, 'set_refund_priority', { id: requests[0].id, priority: 'high' });
  const draft = await call(lab, 'draft_refund_reply', { id: requests[0].id, body: 'We are reviewing your request.' });
  assert.equal(draft.sent, false); assert.equal(lab.getState().selectedRefund, 'refund-2'); assert.equal(lab.getState().inbox[1].priority, 'high');
});
test('photo adjustments require an actual local image-loading UI event', async () => {
  const lab = permitted(); const args = { exposure: 0.8, contrast: 110, saturation: 100 };
  assert.equal((await lab.call('set_photo_adjustments', args)).error.code, 'image_required');
  await lab.markPhotoLoaded(); await call(lab, 'set_photo_adjustments', args);
  assert.equal((await call(lab, 'get_photo_adjustments')).exposure, 0.8);
});
test('photo and block numeric bounds reject nonfinite and out-of-range values', async () => {
  const lab = permitted(); await lab.markPhotoLoaded();
  for (const exposure of [Infinity, NaN, 3.1, '1']) assert.equal((await lab.call('set_photo_adjustments', { exposure, contrast: 100, saturation: 100 })).error.code, 'invalid_input');
  assert.equal((await lab.call('add_blocks', { blocks: [{ x: 0, y: 0, z: 1, size: 0 }] })).error.code, 'invalid_input');
});
test('block modeling supports add, read, rotate and remove', async () => {
  const lab = permitted(); const added = await call(lab, 'add_blocks', { blocks: [1,2,3].map(z => ({ x: 0, y: 0, z, size: 1 })) });
  assert.equal((await call(lab, 'get_scene')).blocks.length, 4);
  await call(lab, 'set_scene_view', { angle: 90 }); await call(lab, 'remove_block', { id: added[0].id });
  assert.equal(lab.getState().scene.angle, 90); assert.equal(lab.getState().scene.blocks.length, 3);
});
test('batch validation is atomic', async () => {
  const lab = permitted(); const result = await lab.call('add_blocks', { blocks: [{ x: 0, y: 0, z: 1, size: 1 }, { x: 0, y: 0, z: 99, size: 1 }] });
  assert.equal(result.ok, false); assert.equal(lab.getState().scene.blocks.length, 1); assert.equal(lab.getState().revision, 0);
});
test('capacity limits reject an entire batch', async () => {
  const lab = permitted(); for (let i = 0; i < 5; i++) await call(lab, 'add_grocery_items', { items: Array(20).fill('x') });
  assert.equal((await lab.call('add_grocery_items', { items: ['overflow'] })).error.code, 'capacity'); assert.equal(lab.getState().groceries.length, 100);
});
test('same request_id and arguments replay exactly once', async () => {
  let approvals = 0; const lab = permitted({ approve: async () => { approvals++; return true; } });
  const args = { items: ['Bread'], request_id: 'receipt-1' };
  const first = await lab.call('add_grocery_items', args); const second = await lab.call('add_grocery_items', args);
  assert.deepEqual(first, second); assert.equal(approvals, 1); assert.equal(lab.getState().groceries.length, 1);
});
test('request_id conflicts include differences in nested object properties', async () => {
  const lab = permitted(); const block = { x: 0, y: 0, z: 1, size: 1 };
  await call(lab, 'add_blocks', { blocks: [block], request_id: 'nested' });
  const result = await lab.call('add_blocks', { blocks: [{ ...block, x: 1 }], request_id: 'nested' });
  assert.equal(result.ok, false); assert.equal(result.error.code, 'idempotency_conflict'); assert.equal(lab.getState().scene.blocks.length, 2);
});
test('concurrent writes are serialized with no lost updates', async () => {
  const lab = permitted(); await Promise.all(Array.from({ length: 15 }, (_, i) => call(lab, 'add_grocery_items', { items: [`Item ${i}`] })));
  assert.equal(lab.getState().groceries.length, 15); assert.equal(lab.getState().revision, 15); assert.equal(new Set(lab.getState().groceries.map(x => x.id)).size, 15);
});
test('cancellation before execution cannot mutate state', async () => {
  const lab = permitted(); const controller = new AbortController(); controller.abort();
  const result = await lab.call('add_grocery_items', { items: ['Bread'] }, { signal: controller.signal });
  assert.equal(result.error.code, 'cancelled'); assert.equal(lab.getState().revision, 0);
});
test('cancellation during approval cannot mutate state', async () => {
  const controller = new AbortController(); const lab = permitted({ approve: async () => { controller.abort(); return true; } });
  const result = await lab.call('add_grocery_items', { items: ['Bread'] }, { signal: controller.signal });
  assert.equal(result.error.code, 'cancelled'); assert.equal(lab.getState().revision, 0);
});
test('approval is invalidated by an intervening local UI state change', async () => {
  let release; const lab = permitted({ approve: () => new Promise(resolve => { release = resolve; }) });
  const pending = lab.call('add_grocery_items', { items: ['Bread'] }); await tick(); await lab.markPhotoLoaded(); release(true);
  assert.equal((await pending).error.code, 'stale_state'); assert.equal(lab.getState().groceries.length, 0);
});
test('render completion precedes success; render errors disclose committed state', async () => {
  let rendered = false; const lab = permitted({ onChange: async () => { await tick(); rendered = true; } });
  await call(lab, 'add_idea', { title: 'A' }); assert.equal(rendered, true);
  const broken = permitted({ onChange: () => { throw new Error('Renderer failure'); } });
  const result = await broken.call('add_idea', { title: 'B' }); assert.equal(result.ok, true); assert.ok(result.ui_warning); assert.equal(broken.getState().board.length, 2);
});
test('unknown tools and failing audit observers are handled safely', async () => {
  const lab = permitted({ onAudit: () => { throw new Error('Observer failure'); } });
  assert.equal((await lab.call('send_email')).error.code, 'unknown_tool'); await call(lab, 'get_board');
});
test('unsupported browsers do not receive a fabricated native API', async () => {
  const root = {}; const result = await mountTools(permitted().tools, { root }).ready;
  assert.equal(result.supported, false); assert.equal(result.registered, 0); assert.equal(root.modelContext, undefined);
});
test('registration contract and AbortSignal cleanup cover all tools', async () => {
  const mock = registry(); const lab = permitted(); const registration = mountTools(lab.tools, { root: mock.root });
  assert.equal((await registration.ready).registered, 19); const saved = mock.tools.get('get_board');
  assert.equal((await saved.execute({})).ok, true); registration.dispose(); assert.equal(mock.tools.size, 0);
  await assert.rejects(saved.execute({}), error => error.code === 'cancelled');
});
test('partial registration failure rolls back only this mount', async () => {
  const mock = registry(); const outside = { name: 'get_board' }; mock.tools.set('get_board', outside);
  const result = await mountTools(permitted().tools, { root: mock.root }).ready;
  assert.equal(result.state, 'registration_failed'); assert.equal(mock.tools.size, 1); assert.equal(mock.tools.get('get_board'), outside);
});
test('unmount while registration is pending cannot leave a registered tool', async () => {
  let release; let active = false;
  const gate = new Promise(resolve => { release = resolve; });
  const root = { modelContext: { async registerTool(_tool, { signal }) { await gate; if (signal.aborted) throw new Error('Cancelled'); active = true; signal.addEventListener('abort', () => { active = false; }, { once: true }); } } };
  const registration = mountTools(permitted().tools, { root }); registration.dispose(); release();
  assert.equal((await registration.ready).registered, 0); assert.equal(active, false);
});
