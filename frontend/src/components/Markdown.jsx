import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Flatten React children to plain text (for the copy button).
function textOf(node) {
  if (node == null || node === false || node === true) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node.props) return textOf(node.props.children);
  return '';
}

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  const raw = textOf(children);
  const className = children?.props?.className || '';
  const lang = className.replace('language-', '').trim();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="group/code relative my-3 overflow-hidden rounded-xl border border-line bg-surface2">
      <div className="flex items-center justify-between px-4 pt-2">
        <span className="text-[10.5px] font-medium uppercase tracking-wider text-inksoft">
          {lang || 'code'}
        </span>
        <button
          onClick={copy}
          className="rounded-md px-2 py-1 text-[11px] text-inksoft opacity-0 transition-opacity hover:bg-surface hover:text-ink group-hover/code:opacity-100"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="mx-0 mb-0 overflow-x-auto px-4 pb-3.5 pt-1.5">{children}</pre>
    </div>
  );
}

const COMPONENTS = {
  pre: CodeBlock,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
};

export default function Markdown({ children }) {
  return (
    <div className="md text-ink">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
