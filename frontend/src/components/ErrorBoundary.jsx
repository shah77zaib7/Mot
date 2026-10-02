import { Component } from 'react';
import { reportError } from '../report.js';

// The last line of defence: a render crash must never leave a blank window.
// The traceback goes to logs/mot.log (POST /api/log) and the person in front
// of Mot gets one short sentence and a way out.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
    this.reload = this.reload.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    reportError(
      error?.message || String(error),
      (info?.componentStack || '').split('\n').slice(0, 6).join(' | '),
      'render',
    );
  }

  reload() {
    window.location.reload();
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-screen bg-canvas text-ink flex items-center justify-center p-8">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-semibold">Mot hit a problem</h1>
          <p className="text-sm text-inksoft leading-relaxed">
            Something in the interface stopped working. Mot saved what
            happened to its log, so nothing is lost.
          </p>
          <button
            type="button"
            onClick={this.reload}
            className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentstrong"
          >
            Reload Mot
          </button>
        </div>
      </div>
    );
  }
}
