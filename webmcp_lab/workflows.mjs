import { ToolError, fail, clone, text, choice, number, object, array, validate, checkSignal } from './core.mjs';
const columns = ['ideas', 'building', 'done'];
const priorities = ['normal', 'high'];
const metricRows = [
  { period: 'previous', channel: 'organic', revenue: 12000 },
  { period: 'previous', channel: 'email', revenue: 8000 },
  { period: 'current', channel: 'organic', revenue: 15000 },
  { period: 'current', channel: 'email', revenue: 10000 },
];
const seed = () => ({ revision: 0, nextId: 10, groceries: [],
  board: [{ id: 'idea-1', title: 'Agent-friendly checkout', column: 'ideas', priority: 'normal' }],
  chart: { period: 'all', channel: 'all' },
  inbox: [
    { id: 'refund-1', subject: 'Duplicate order', amount: 125, status: 'unresolved', priority: 'normal', draft: '' },
    { id: 'refund-2', subject: 'Damaged shipment', amount: 450, status: 'unresolved', priority: 'normal', draft: '' },
    { id: 'refund-3', subject: 'Previously resolved', amount: 900, status: 'resolved', priority: 'normal', draft: '' },
  ], selectedRefund: null,
  photo: { loaded: false, exposure: 0, contrast: 100, saturation: 100 },
  scene: { angle: 35, blocks: [{ id: 'block-1', x: 0, y: 0, z: 0, size: 1 }] },
});
const canonical = value => JSON.stringify(value, Object.keys(value).sort());
const lookup = (rows, id) => rows.find(row => row.id === id) ?? fail('not_found', 'No item has that ID');
const metrics = filter => metricRows.filter(row => (filter.period === 'all' || filter.period === row.period) && (filter.channel === 'all' || filter.channel === row.channel));
const filterSchema = { period: choice(['all', 'previous', 'current']), channel: choice(['all', 'organic', 'email']) };

// All data is synthetic, in-memory, and tab-local. No network or storage adapters.
export function createWorkbench({ approve = async () => false, onChange = () => {}, onAudit = () => {} } = {}) {
  let state = seed();
  let queue = Promise.resolve();
  const receipts = new Map();
  const tools = [];
  const audit = (name, outcome) => { try { onAudit({ tool: name, outcome, revision: state.revision }); } catch {} };
  function add(name, description, properties, handler, write = false, required = Object.keys(properties)) {
    const inputSchema = object(write ? { ...properties, request_id: text(80) } : properties, required);
    async function run(raw, options = {}) {
      try {
        validate(inputSchema, raw);
        const args = clone(raw);
        checkSignal(options.signal);
        const fingerprint = canonical(args);
        if (write && args.request_id && receipts.has(args.request_id)) {
          const receipt = receipts.get(args.request_id);
          if (receipt.name !== name || receipt.fingerprint !== fingerprint) fail('idempotency_conflict', 'request_id was already used for different arguments');
          return clone(receipt.result);
        }
        const before = state.revision;
        const draft = clone(state);
        const value = handler(draft, args); // Validate the entire operation on a private copy.
        const result = { ok: true, tool: name, data: clone(value), revision: before + Number(write), synthetic: true };
        if (write) {
          const accepted = await approve({ tool: name, description, arguments: clone(args), revision: before, signal: options.signal });
          if (accepted !== true) fail('approval_required', 'The user did not approve this local change');
          checkSignal(options.signal);
          if (state.revision !== before) fail('stale_state', 'State changed while approval was pending; review again');
          draft.revision = before + 1;
          state = draft;
          if (args.request_id) {
            receipts.set(args.request_id, { name, fingerprint, result: clone(result) });
            if (receipts.size > 200) receipts.delete(receipts.keys().next().value);
          }
          try { await onChange(clone(state)); }
          catch { result.ui_warning = 'Change committed, but the UI renderer reported an error'; }
        }
        audit(name, 'success');
        return result;
      } catch (error) {
        audit(name, error.code ?? 'internal_error');
        return { ok: false, tool: name, error: { code: error instanceof ToolError ? error.code : 'internal_error', message: error instanceof ToolError ? error.message : 'The local operation failed' }, revision: state.revision };
      }
    }
    tools.push({ name, title: name.replaceAll('_', ' '), description,
      inputSchema, annotations: { readOnlyHint: !write, untrustedContentHint: true },
      execute: (input, options) => {
        if (!write) return run(input, options);
        // Serialize writes, including approvals, to avoid lost updates.
        const pending = queue.then(() => run(input, options));
        queue = pending.then(() => {}, () => {});
        return pending;
      },
    });
  }
  add('get_groceries', 'Read the current local demo grocery list.', {}, s => s.groceries);
  add('add_grocery_items', 'Add up to 20 grocery items to the local list after visible approval. Does not buy anything.', { items: array(text()) }, (s, a) => {
    if (s.groceries.length + a.items.length > 100) fail('capacity', 'The demo allows at most 100 grocery items');
    const added = a.items.map(item => ({ id: `grocery-${s.nextId++}`, item: item.trim() }));
    s.groceries.push(...added); return added;
  }, true);
  add('remove_grocery_item', 'Remove one item from the local grocery list after approval. Does not affect any external service.', { id: text(80) }, (s, a) => {
    const row = lookup(s.groceries, a.id); s.groceries = s.groceries.filter(item => item.id !== a.id); return row;
  }, true);
  add('get_board', 'Read all local Kanban cards with their IDs, columns and priorities.', {}, s => s.board);
  add('add_idea', 'Create one idea card in the local Kanban board after approval.', { title: text() }, (s, a) => {
    if (s.board.length >= 100) fail('capacity', 'The demo allows at most 100 cards');
    const row = { id: `idea-${s.nextId++}`, title: a.title.trim(), column: 'ideas', priority: 'normal' }; s.board.push(row); return row;
  }, true);
  add('move_idea', 'Move one existing local Kanban card to a named column after approval.', { id: text(80), column: choice(columns) }, (s, a) => { const row = lookup(s.board, a.id); row.column = a.column; return row; }, true);
  add('set_idea_priority', 'Set the priority of one existing local Kanban card after approval.', { id: text(80), priority: choice(priorities) }, (s, a) => { const row = lookup(s.board, a.id); row.priority = a.priority; return row; }, true);
  add('query_metrics', 'Read synthetic revenue rows and total for a period/channel filter. These are not personal or business financial records.', filterSchema, (_s, a) => { const rows = metrics(a); return { rows, total: rows.reduce((sum, row) => sum + row.revenue, 0) }; });
  add('show_revenue_chart', 'Update the visible local chart filters after approval; no underlying revenue data changes.', filterSchema, (s, a) => { s.chart = { period: a.period, channel: a.channel }; return metrics(a); }, true);
  add('find_refund_requests', 'Read synthetic refund requests by status, highest requested amount first. Does not access email or issue refunds.', { status: choice(['all', 'unresolved', 'resolved']) }, (s, a) => s.inbox.filter(row => a.status === 'all' || row.status === a.status).sort((a, b) => b.amount - a.amount));
  add('open_refund_request', 'Select a synthetic refund conversation in the visible demo after approval.', { id: text(80) }, (s, a) => { const row = lookup(s.inbox, a.id); s.selectedRefund = row.id; return row; }, true);
  add('set_refund_priority', 'Set the priority of one synthetic refund conversation after approval.', { id: text(80), priority: choice(priorities) }, (s, a) => { const row = lookup(s.inbox, a.id); row.priority = a.priority; return row; }, true);
  add('draft_refund_reply', 'Save a reply draft only in this tab after approval. Never sends email or processes a refund.', { id: text(80), body: text(2000) }, (s, a) => { const row = lookup(s.inbox, a.id); row.draft = a.body.trim(); s.selectedRefund = row.id; return { id: row.id, draft: row.draft, sent: false }; }, true);
  add('get_photo_adjustments', 'Read whether a local image is loaded and its preview adjustments. Does not expose the image or its filename.', {}, s => s.photo);
  add('set_photo_adjustments', 'Change the preview of the image the user loaded locally, after approval. The original file is not modified or uploaded.', { exposure: number(-3, 3), contrast: number(0, 200), saturation: number(0, 200) }, (s, a) => {
    if (!s.photo.loaded) fail('image_required', 'Load a local image in the Photo panel first');
    Object.assign(s.photo, { exposure: a.exposure, contrast: a.contrast, saturation: a.saturation }); return s.photo;
  }, true);
  const block = object({ x: number(-5, 5), y: number(-5, 5), z: number(0, 8), size: number(0.25, 3) });
  add('get_scene', 'Read the local isometric block scene. This is a small modeling reference, not a full CAD application.', {}, s => s.scene);
  add('add_blocks', 'Add a bounded batch of up to 20 blocks to the local scene after approval.', { blocks: array(block) }, (s, a) => {
    if (s.scene.blocks.length + a.blocks.length > 60) fail('capacity', 'The demo allows at most 60 blocks');
    const added = a.blocks.map(block => ({ ...block, id: `block-${s.nextId++}` })); s.scene.blocks.push(...added); return added;
  }, true);
  add('remove_block', 'Remove one local scene block after approval.', { id: text(80) }, (s, a) => { const row = lookup(s.scene.blocks, a.id); s.scene.blocks = s.scene.blocks.filter(block => block.id !== a.id); return row; }, true);
  add('set_scene_view', 'Rotate the local scene view in degrees after approval. Does not change the block geometry.', { angle: number(-180, 180) }, (s, a) => { s.scene.angle = a.angle; return s.scene; }, true);
  return {
    tools,
    getState: () => clone(state),
    getMetrics: () => clone(metrics(state.chart)),
    call: (name, input = {}, options = {}) => {
      const tool = tools.find(tool => tool.name === name);
      return tool ? tool.execute(input, options) : Promise.resolve({ ok: false, error: { code: 'unknown_tool', message: 'No such tool' } });
    },
    // Only the trusted file-input UI uses this. It is intentionally not exposed as an agent tool.
    markPhotoLoaded: async () => { state.photo.loaded = true; state.revision += 1; await onChange(clone(state)); },
  };
}
