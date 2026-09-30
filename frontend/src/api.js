// Thin JSON + SSE client for the Mot backend (same origin).

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    throw new Error(data?.detail || data?.message || `Request failed (${res.status})`);
  }
  return data;
}

// Read an SSE body as an async iterator of parsed JSON events.
async function* readEvents(res) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split;
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of frame.split('\n')) {
        if (line.startsWith('data:')) {
          try {
            yield JSON.parse(line.slice(5).trim());
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    }
  }
}

// POST /api/chat -> async iterator of parsed SSE events.
export async function* streamChat(payload, signal) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal,
  });

  if (!res.ok || !res.body) {
    let message = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      message = data.detail || data.message || message;
    } catch {
      /* keep default */
    }
    throw new Error(message);
  }

  yield* readEvents(res);
}

// GET /api/actions -> live action updates (install progress after the reply).
// Returns a stop() function; reconnects on its own if the stream drops.
export function watchActions(onEvent) {
  let stopped = false;
  let controller = null;

  (async () => {
    while (!stopped) {
      try {
        controller = new AbortController();
        const res = await fetch('/api/actions', {
          headers: { Accept: 'text/event-stream' },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error('action stream unavailable');
        for await (const event of readEvents(res)) {
          if (stopped) return;
          onEvent(event);
        }
      } catch {
        /* fall through to the retry delay */
      }
      if (!stopped) await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  })();

  return () => {
    stopped = true;
    controller?.abort();
  };
}
