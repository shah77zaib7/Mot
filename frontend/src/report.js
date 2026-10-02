// One place where browser-side errors end up: logs/mot.log, next to the
// backend's own tracebacks. Fire and forget — reporting must never throw.
export function reportError(message, stack = '', source = 'js') {
  try {
    fetch('/api/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, stack, source }),
    }).catch(() => {});
  } catch {
    /* the server really is not there; nothing left to do */
  }
}

// Anything the app forgets to catch still gets a line in the log.
export function watchForErrors() {
  window.addEventListener('error', (event) => {
    reportError(event.message || 'Unknown error',
      event.error?.stack || '', 'window');
  });
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    reportError(reason?.message || String(reason),
      reason?.stack || '', 'unhandledrejection');
  });
}
