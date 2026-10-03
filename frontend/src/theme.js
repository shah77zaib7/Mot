// Light / dark / system theme handling, plus the accent colour (Phase 6).

const HEX = /^#[0-9a-fA-F]{6}$/;
export const DEFAULT_ACCENT = '#14b8a6'; // matches --accent in index.css

let accent = DEFAULT_ACCENT;

function clamp01(value) {
  return Math.min(1, Math.max(0, value));
}

function hexToRgb(hex) {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
}

function rgbToHex(r, g, b) {
  const part = (value) =>
    Math.round(clamp01(value / 255) * 255).toString(16).padStart(2, '0');
  return `#${part(r)}${part(g)}${part(b)}`;
}

function hexToHsl(hex) {
  const [r0, g0, b0] = hexToRgb(hex).map((v) => v / 255);
  const max = Math.max(r0, g0, b0);
  const min = Math.min(r0, g0, b0);
  const light = (max + min) / 2;
  if (max === min) return [0, 0, light];
  const delta = max - min;
  const sat = light > 0.5 ? delta / (2 - max - min) : delta / (max + min);
  let hue;
  if (max === r0) hue = ((g0 - b0) / delta + (g0 < b0 ? 6 : 0)) / 6;
  else if (max === g0) hue = ((b0 - r0) / delta + 2) / 6;
  else hue = ((r0 - g0) / delta + 4) / 6;
  return [hue * 360, sat, light];
}

function hueToRgb(p, q, t) {
  let value = t;
  if (value < 0) value += 1;
  if (value > 1) value -= 1;
  if (value < 1 / 6) return p + (q - p) * 6 * value;
  if (value < 1 / 2) return q;
  if (value < 2 / 3) return p + (q - p) * (2 / 3 - value) * 6;
  return p;
}

function hslToHex(hue, sat, light) {
  if (sat === 0) {
    const grey = light * 255;
    return rgbToHex(grey, grey, grey);
  }
  const h = (((hue % 360) + 360) % 360) / 360;
  const q = light < 0.5 ? light * (1 + sat) : light + sat - light * sat;
  const p = 2 * light - q;
  return rgbToHex(
    hueToRgb(p, q, h + 1 / 3) * 255,
    hueToRgb(p, q, h) * 255,
    hueToRgb(p, q, h - 1 / 3) * 255
  );
}

// A slightly darker / lighter sibling of the chosen colour, so the strong and
// ink variants stay in the same family instead of keeping the old teal.
function shade(hex, delta) {
  const [h, s, l] = hexToHsl(hex);
  return hslToHex(h, s, clamp01(l + delta));
}

function paintAccent() {
  const root = document.documentElement;
  root.style.setProperty('--accent', accent);
  root.style.setProperty('--accent-strong', shade(accent, -0.1));
  const dark = root.classList.contains('dark');
  root.style.setProperty('--accent-ink', shade(accent, dark ? 0.22 : -0.15));
}

export function applyAccent(value) {
  accent = HEX.test(String(value || '').trim()) ? String(value).trim() : DEFAULT_ACCENT;
  paintAccent();
}

export function applyTheme(theme) {
  const root = document.documentElement;
  const dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  root.classList.toggle('dark', dark);
  paintAccent(); // --accent-ink reads the light/dark state
}

export function watchSystemTheme(theme) {
  if (theme !== 'system') return () => {};
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const onChange = () => applyTheme('system');
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}
