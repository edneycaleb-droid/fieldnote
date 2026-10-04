// Dependency-free imperative WebMCP adapter. No polyfill or remote execution.
export class ToolError extends Error {
  constructor(code, message) { super(message); this.name = 'ToolError'; this.code = code; }
}
export const fail = (code, message) => { throw new ToolError(code, message); };
export const clone = value => structuredClone(value);
export const text = (maxLength = 160) => ({ type: 'string', minLength: 1, maxLength });
export const choice = values => ({ type: 'string', enum: values });
export const number = (minimum, maximum) => ({ type: 'number', minimum, maximum });
export const object = (properties = {}, required = Object.keys(properties)) => ({ type: 'object', properties, required, additionalProperties: false });
export const array = (items, maxItems = 20) => ({ type: 'array', items, minItems: 1, maxItems });

// This deliberately supports only the schema subset used by this lab, not all JSON Schema.
export function validate(schema, value, path = 'input') {
  const bad = message => fail('invalid_input', `${path}: ${message}`);
  if (schema.enum && !schema.enum.includes(value)) bad('value is not in the allowed choices');
  switch (schema.type) {
    case 'object': {
      if (!value || typeof value !== 'object' || Array.isArray(value)) bad('expected an object');
      const proto = Object.getPrototypeOf(value);
      if (proto !== Object.prototype && proto !== null) bad('expected a plain object');
      for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) bad(`missing ${key}`);
      for (const key of Object.keys(value)) {
        if (!Object.hasOwn(schema.properties, key)) bad(`unknown property ${key}`);
        validate(schema.properties[key], value[key], `${path}.${key}`);
      }
      break;
    }
    case 'string':
      if (typeof value !== 'string') bad('expected a string');
      if (schema.minLength && value.trim().length < schema.minLength) bad('must not be blank');
      if (schema.maxLength && value.length > schema.maxLength) bad('string is too long');
      break;
    case 'number':
    case 'integer':
      if (typeof value !== 'number' || !Number.isFinite(value)) bad('expected a finite number');
      if (schema.type === 'integer' && !Number.isInteger(value)) bad('expected an integer');
      if (value < schema.minimum || value > schema.maximum) bad('number is outside the allowed range');
      break;
    case 'array':
      if (!Array.isArray(value)) bad('expected an array');
      if (value.length < schema.minItems || value.length > schema.maxItems) bad('invalid array length');
      value.forEach((item, index) => validate(schema.items, item, `${path}[${index}]`));
      break;
    default: fail('invalid_schema', `Unsupported schema type: ${schema.type}`);
  }
  return value;
}
export function checkSignal(signal) {
  if (signal?.aborted) fail('cancelled', 'The operation was cancelled before completion');
}
function linkedSignal(signals) {
  const controller = new AbortController();
  const active = signals.filter(Boolean);
  const abort = () => controller.abort();
  for (const signal of active) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener('abort', abort, { once: true });
  }
  return { signal: controller.signal, dispose: () => active.forEach(s => s.removeEventListener('abort', abort)) };
}

// Return cleanup immediately so React can unmount even while registration is pending.
export function mountTools(tools, { root = globalThis.document, onStatus = () => {} } = {}) {
  const lifecycle = new AbortController();
  const context = root?.modelContext;
  const ready = (async () => {
    if (typeof context?.registerTool !== 'function') {
      const status = { supported: false, registered: 0, state: 'unavailable' };
      onStatus(status); return status;
    }
    let registered = 0;
    try {
      const names = new Set();
      for (const tool of tools) {
        checkSignal(lifecycle.signal);
        if (!/^[A-Za-z0-9_.-]{1,128}$/.test(tool.name) || names.has(tool.name)) fail('invalid_tool', 'Invalid or duplicate tool name');
        names.add(tool.name);
        const exposed = { ...tool, execute: async (input, options = {}) => {
          const execution = linkedSignal([lifecycle.signal, options.signal]);
          try { checkSignal(execution.signal); return await tool.execute(input, { signal: execution.signal }); }
          finally { execution.dispose(); }
        } };
        await context.registerTool(exposed, { signal: lifecycle.signal });
        checkSignal(lifecycle.signal);
        registered += 1;
      }
      const status = { supported: true, registered, state: 'registered' };
      onStatus(status); return status;
    } catch (error) {
      lifecycle.abort();
      const status = { supported: true, registered: 0, state: 'registration_failed', error: error.code ?? 'registration_error' };
      onStatus(status); return status;
    }
  })();
  return { ready, dispose: () => lifecycle.abort() };
}
