'use client';
import { useEffect, useState } from 'react';
import { mountTools } from './core.mjs';

// Include in an owned React/Next.js client component. Pass a stable tool array,
// e.g. created with useMemo, whose handlers read from your real application store.
// This is an integration example, not an installed or tested Next.js application.
export default function WebMcpTools({ tools }) {
  const [status, setStatus] = useState('Checking site tools');
  useEffect(() => {
    let active = true;
    const registration = mountTools(tools, {
      onStatus(value) {
        if (!active) return;
        setStatus(value.state === 'registered'
          ? `${value.registered} site tools registered`
          : value.state === 'unavailable' ? 'Site tools unavailable; use the normal interface' : 'Site tool registration failed');
      },
    });
    return () => { active = false; registration.dispose(); };
  }, [tools]);
  return <span role="status">{status}</span>;
}
