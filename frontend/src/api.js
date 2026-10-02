// Thin JSON + SSE client for the Mot backend (same origin).

// fetch() only ever rejects when the network itself failed — never with a
// readable reason — so the sentence has to come from here.
export const OFFLINE =
  "Mot can't reach its own server. It may still be starting up \u2014 try again in a moment.";

function networkError() {
  const error = new Error(OFFLINE);
  error.offline = true;
  return error;
}

async function get(path, init) {
  try {
    return await fetch(path, init);
  } catch {
    throw networkError();
  }
}

function messageFrom(data, status) {
  const detail = data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (typeof data?.message === 'string' && data.message.trim()) return data.message;
  return `Mot could not finish that request (error ${status}).`;
}

export async function api(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw networkError();
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    throw new Error(messageFrom(data, res.status));
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
  const res = await get('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal,
  });

  if (!res.ok || !res.body) {
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* keep default */
    }
    throw new Error(messageFrom(data, res.status));
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
