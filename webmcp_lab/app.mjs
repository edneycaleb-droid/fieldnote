import { mountTools } from './core.mjs';
import { createWorkbench } from './workflows.mjs';
const $ = id => document.getElementById(id);
const node = (tag, content, className) => { const element = document.createElement(tag); if (content !== undefined) element.textContent = content; if (className) element.className = className; return element; };
let photoUrl;
let pendingApproval;
function approve(request) {
  return new Promise(resolve => {
    if (request.signal?.aborted) { resolve(false); return; }
    const dialog = $('approval');
    $('approval-description').textContent = request.description;
    $('approval-args').textContent = JSON.stringify({ tool: request.tool, arguments: request.arguments, revision: request.revision }, null, 2);
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      request.signal?.removeEventListener('abort', cancel);
      dialog.removeEventListener('cancel', cancel);
      dialog.removeEventListener('close', cancel);
      $('approve-yes').onclick = null;
      $('approve-no').onclick = null;
      pendingApproval = null;
      if (dialog.open) dialog.close();
      resolve(value);
    };
    const cancel = event => { event?.preventDefault?.(); finish(false); };
    $('approve-yes').onclick = () => finish(true);
    $('approve-no').onclick = () => finish(false);
    dialog.addEventListener('cancel', cancel);
    dialog.addEventListener('close', cancel);
    request.signal?.addEventListener('abort', cancel, { once: true });
    pendingApproval = cancel;
    dialog.showModal();
  });
}
const audit = [];
const lab = createWorkbench({ approve, onChange: render, onAudit: event => {
  audit.unshift(`${event.tool} — ${event.outcome} — revision ${event.revision}`);
  audit.splice(60);
  $('audit').replaceChildren(...audit.map(line => node('li', line)));
} });
function render() {
  const state = lab.getState();
  $('groceries').replaceChildren(...(state.groceries.length ? state.groceries.map(item => node('li', item.item)) : [node('li', 'Your local list is empty.', 'muted')]));
  $('board').replaceChildren(...['ideas', 'building', 'done'].map(column => {
    const element = node('div', undefined, 'column');
    element.append(node('h3', column[0].toUpperCase() + column.slice(1)));
    for (const card of state.board.filter(card => card.column === column)) element.append(node('div', `${card.title}\n${card.priority} · ${card.id}`, 'card'));
    return element;
  }));
  $('metrics').replaceChildren(...lab.getMetrics().map(row => {
    const element = node('div', `${row.channel} · ${row.period} · $${row.revenue.toLocaleString('en-US')}`, 'metric');
    const bar = node('meter'); bar.min = 0; bar.max = 15000; bar.value = row.revenue; bar.setAttribute('aria-label', `${row.channel} ${row.period} synthetic revenue`); element.append(bar); return element;
  }));
  const selected = state.inbox.find(row => row.id === state.selectedRefund);
  $('inbox').textContent = selected ? `${selected.subject} · $${selected.amount}\n${selected.id} · ${selected.status} · ${selected.priority}\n\nDraft: ${selected.draft || '(none)'}` : 'No conversation selected. Three synthetic requests are available.';
  $('photo-image').style.filter = `brightness(${2 ** state.photo.exposure}) contrast(${state.photo.contrast}%) saturate(${state.photo.saturation}%)`;
  $('photo-values').textContent = `Exposure ${state.photo.exposure}; contrast ${state.photo.contrast}%; saturation ${state.photo.saturation}%`;
  renderScene(state.scene);
}
function renderScene(scene) {
  const svg = $('scene');
  const angle = scene.angle * Math.PI / 180;
  const rotate = (x, y) => [x * Math.cos(angle) - y * Math.sin(angle), x * Math.sin(angle) + y * Math.cos(angle)];
  const project = (x, y, z) => { const [a, b] = rotate(x, y); return [(a - b) * 20, (a + b) * 10 - z * 24]; };
  const faces = [];
  for (const block of [...scene.blocks].sort((a, b) => a.z - b.z || a.y - b.y)) {
    const { x, y, z, size: s } = block;
    const shape = [
      { points: [[x,y,z],[x+s,y,z],[x+s,y,z+s],[x,y,z+s]], fill: '#376cc0' },
      { points: [[x+s,y,z],[x+s,y+s,z],[x+s,y+s,z+s],[x+s,y,z+s]], fill: '#244d8a' },
      { points: [[x,y,z+s],[x+s,y,z+s],[x+s,y+s,z+s],[x,y+s,z+s]], fill: '#83a9e0' },
    ];
    for (const face of shape) {
      const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      polygon.setAttribute('points', face.points.map(point => project(...point).join(',')).join(' '));
      polygon.setAttribute('fill', face.fill); polygon.setAttribute('stroke', 'white'); polygon.setAttribute('stroke-width', '.7'); faces.push(polygon);
    }
  }
  svg.replaceChildren(...faces);
  svg.setAttribute('aria-label', `Local isometric scene with ${scene.blocks.length} blocks; view angle ${scene.angle} degrees`);
}
async function invoke(name, args = {}) {
  const tool = lab.tools.find(tool => tool.name === name);
  if (!tool?.annotations.readOnlyHint && !Object.hasOwn(args, 'request_id')) args = { ...args, request_id: crypto.randomUUID() };
  $('notice').textContent = `Running ${name}…`;
  const result = await lab.call(name, args);
  $('result').textContent = JSON.stringify(result, null, 2);
  $('notice').textContent = result.ok ? `${name} completed in this tab.` : `${name}: ${result.error.message}`;
  return result;
}
$('grocery-form').addEventListener('submit', async event => {
  event.preventDefault(); const result = await invoke('add_grocery_items', { items: [$('grocery-input').value] }); if (result.ok) $('grocery-input').value = '';
});
$('move-card').onclick = () => invoke('move_idea', { id: 'idea-1', column: 'building' });
$('filter-chart').onclick = () => invoke('show_revenue_chart', { period: 'current', channel: 'all' });
$('open-refund').onclick = async () => { const found = await lab.call('find_refund_requests', { status: 'unresolved' }); if (found.ok && found.data[0]) await invoke('open_refund_request', { id: found.data[0].id }); };
$('brighten').onclick = () => { const photo = lab.getState().photo; return invoke('set_photo_adjustments', { exposure: Math.min(3, photo.exposure + 0.8), contrast: photo.contrast, saturation: photo.saturation }); };
$('add-blocks').onclick = () => invoke('add_blocks', { blocks: [1, 2, 3].map(z => ({ x: 0, y: 0, z, size: 1 })) });
$('photo-file').onchange = async event => {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) { $('notice').textContent = 'Choose a PNG, JPEG or WebP no larger than 10 MB.'; return; }
  const nextUrl = URL.createObjectURL(file);
  const probe = new Image(); probe.src = nextUrl;
  try {
    await probe.decode();
    if (probe.naturalWidth * probe.naturalHeight > 40000000) throw new Error('Image dimensions are too large');
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = nextUrl; $('photo-image').src = photoUrl; $('photo-image').hidden = false; $('photo-empty').hidden = true;
    await lab.markPhotoLoaded(); $('notice').textContent = 'Local image loaded; no upload occurred.';
  } catch { URL.revokeObjectURL(nextUrl); $('notice').textContent = 'This image could not be decoded or exceeds 40 megapixels.'; }
};
const samples = {
  add_grocery_items: { items: ['Sourdough bread', 'Oatmeal'] }, remove_grocery_item: { id: 'grocery-10' },
  add_idea: { title: 'Keyboard shortcuts' }, move_idea: { id: 'idea-1', column: 'building' }, set_idea_priority: { id: 'idea-1', priority: 'high' },
  query_metrics: { period: 'all', channel: 'all' }, show_revenue_chart: { period: 'current', channel: 'all' },
  find_refund_requests: { status: 'unresolved' }, open_refund_request: { id: 'refund-2' }, set_refund_priority: { id: 'refund-2', priority: 'high' },
  draft_refund_reply: { id: 'refund-2', body: 'Thank you for reporting the damaged shipment. Please keep the packaging while the support team reviews your request. This draft does not promise or issue a refund.' },
  set_photo_adjustments: { exposure: 0.8, contrast: 100, saturation: 100 },
  add_blocks: { blocks: [{ x: 0, y: 0, z: 2, size: 1 }] }, remove_block: { id: 'block-1' }, set_scene_view: { angle: 60 },
};
$('tool-select').replaceChildren(...lab.tools.map(tool => { const option = node('option', `${tool.name} · ${tool.annotations.readOnlyHint ? 'read' : 'change'}`); option.value = tool.name; return option; }));
function selectTool() { const tool = lab.tools.find(tool => tool.name === $('tool-select').value); $('tool-description').textContent = tool.description; $('tool-args').value = JSON.stringify(samples[tool.name] ?? {}, null, 2); $('schema').textContent = JSON.stringify(tool.inputSchema, null, 2); }
$('tool-select').onchange = selectTool;
$('invoke-tool').onclick = async () => { try { const args = JSON.parse($('tool-args').value); await invoke($('tool-select').value, args); } catch { $('notice').textContent = 'Enter a valid JSON object.'; } };
let mounted;
function register() {
  mounted?.dispose();
  mounted = mountTools(lab.tools, { onStatus: status => {
    $('support').textContent = status.state === 'registered' ? `Native WebMCP: ${status.registered} tools registered. Actual agent discovery must be verified in the host browser.` : status.state === 'unavailable' ? 'Native WebMCP is unavailable here. Manual controls and the local test console still work.' : `Native registration failed (${status.error}); no lab tools remain registered.`;
  } });
}
$('retry-tools').onclick = register;
window.addEventListener('pagehide', event => { mounted?.dispose(); pendingApproval?.(); if (!event.persisted && photoUrl) URL.revokeObjectURL(photoUrl); });
window.addEventListener('pageshow', event => { if (event.persisted) register(); });
$('tools-count').textContent = `${lab.tools.length} tool definitions · 6 workflow domains`;
selectTool(); render(); register();
