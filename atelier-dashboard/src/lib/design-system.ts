/**
 * AT-044 — Design-system panel substrate.
 *
 * Pure, framework-agnostic helpers for the Studio design-system panel:
 *   - flatten a DTCG design system into one editable row per leaf token;
 *   - mirror the Style Dictionary CSS-variable naming (AT-050) so a live edit
 *     re-flows any rendered surface that consumes `var(--<token>)`;
 *   - synthesize the design-specific controls that matter for *this* system
 *     (a primary-hue knob, a per-scale slider) rather than a fixed control set
 *     (the "custom sliders" pattern, PRD section 25 / E4).
 *
 * The Studio iframe is sandboxed `allow-scripts` (opaque origin), so the parent
 * cannot patch its CSSOM; propagation works by recomposing `srcDoc` with a live
 * `:root` block appended last in the document (it wins the cascade over any
 * baked `:root`). See `composeSrcDoc`.
 */

export type TokenValue = string | number | Array<string | number>;

export interface TokenLeafMeta {
  $value: TokenValue;
  $type?: string;
  $description?: string;
}

export interface DtcgGroup {
  $type?: string;
  $description?: string;
  [childKey: string]: DtcgNode | string | undefined;
}

export type DtcgNode = TokenLeafMeta | DtcgGroup;

/** A DTCG design system: the same shape as `design-tokens/tokens.json`. */
export type DesignSystem = DtcgGroup;

export interface FlatToken {
  /** Dot path, e.g. `color.primary`, `font.size.2xl`. */
  path: string;
  value: TokenValue;
  /** Resolved DTCG `$type` (inherited from the nearest ancestor group). */
  type?: string;
  description?: string;
}

/** A control Atelier synthesizes for a specific design system. */
export type GeneratedControl =
  | { id: string; kind: 'hue'; label: string; tokenPath: string }
  | { id: string; kind: 'scale'; label: string; tokenPath: string; group: string };

function isLeaf(node: DtcgNode): node is TokenLeafMeta {
  return typeof node === 'object' && node !== null && '$value' in node;
}

/**
 * Flatten a DTCG design system to its leaf tokens (one per panel row).
 * A node is a leaf when it carries `$value`; `$type` is inherited from the
 * nearest ancestor group (DTCG type inheritance).
 */
export function flattenDesignSystem(ds: DesignSystem): FlatToken[] {
  const out: FlatToken[] = [];
  const walk = (node: DtcgGroup, prefix: string[], inheritedType?: string): void => {
    const groupType = typeof node.$type === 'string' ? node.$type : inheritedType;
    for (const key of Object.keys(node)) {
      if (key.startsWith('$')) continue;
      const child = node[key];
      if (child == null || typeof child === 'string') continue;
      const path = [...prefix, key];
      if (isLeaf(child)) {
        out.push({
          path: path.join('.'),
          value: child.$value,
          type: typeof child.$type === 'string' ? child.$type : groupType,
          description: child.$description,
        });
      } else {
        walk(child, path, groupType);
      }
    }
  };
  walk(ds, []);
  return out;
}

/**
 * CSS custom-property name for a token path, mirroring the Style Dictionary
 * `css` transform group (`name/kebab`): the dot path joined by hyphens.
 * `color.primary` -> `--color-primary`; `font.size.2xl` -> `--font-size-2xl`.
 */
export function cssVarName(path: string): string {
  return `--${path.split('.').join('-')}`;
}

/** Serialize a token value for CSS (arrays become a comma list, as SD emits). */
export function formatTokenValue(value: TokenValue): string {
  return Array.isArray(value) ? value.join(', ') : String(value);
}

/**
 * Strip characters and constructs that could break out of, or abuse, the
 * injected `<style>` / `:root` block. Token values become user-editable, so a
 * value can be arbitrary text:
 *   - `< > { } ;` are removed so a stray `}` or `</style>` cannot escape the
 *     declaration into surrounding markup of the sandboxed srcDoc;
 *   - `url(`, `@import`, `expression(` are removed as defense-in-depth against
 *     a value that smuggles a network beacon or legacy CSS eval (a no-op today
 *     under the sandbox, but hardened ahead of cross-tenant tokens in AT-053).
 *
 * Note: the load-bearing controls are the parent CSP (inherited by the
 * `about:srcdoc` frame) and the opaque-origin sandbox (`allow-scripts`, no
 * `allow-same-origin`); this strip is the inner layer, not the only one.
 */
function sanitizeCssValue(value: string): string {
  return value
    .replace(/[<>{};]/g, '')
    .replace(/url\(/gi, '')
    .replace(/@import/gi, '')
    .replace(/expression\(/gi, '')
    .trim();
}

/** Render the live `:root { --token: value; ... }` block for a design system. */
export function renderRootVars(ds: DesignSystem): string {
  const decls = flattenDesignSystem(ds)
    .map((t) => `${cssVarName(t.path)}: ${sanitizeCssValue(formatTokenValue(t.value))};`)
    .join(' ');
  return `:root { ${decls} }`;
}

/**
 * Compose the iframe `srcDoc` from converged HTML + the live design system.
 *
 * The `<style id="atelier-live-tokens">` block is injected last in document
 * order (before `</body>`, else before `</head>`, else appended) so its
 * `:root` custom properties win the cascade over any values baked into the
 * generated HTML. Surfaces that reference `var(--<token>)` therefore re-flow
 * the instant a token is edited in the panel.
 */
export function composeSrcDoc(html: string, ds: DesignSystem | null): string {
  if (!html) return html;
  if (!ds) return html;
  const style = `<style id="atelier-live-tokens">${renderRootVars(ds)}</style>`;
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, `${style}</body>`);
  if (/<\/head>/i.test(html)) return html.replace(/<\/head>/i, `${style}</head>`);
  return html + style;
}

function cloneDesignSystem(ds: DesignSystem): DesignSystem {
  return JSON.parse(JSON.stringify(ds)) as DesignSystem;
}

/** Set a leaf `$value` by dot path on a design system, in place. */
function setLeafValue(ds: DesignSystem, path: string, value: TokenValue): void {
  const segs = path.split('.');
  let node: DtcgGroup = ds;
  for (let i = 0; i < segs.length - 1; i++) {
    const next = node[segs[i]];
    if (next == null || typeof next === 'string' || isLeaf(next)) return;
    node = next;
  }
  const leaf = node[segs[segs.length - 1]];
  if (leaf != null && typeof leaf !== 'string' && isLeaf(leaf)) {
    leaf.$value = value;
  }
}

/** A simple `<n>px` dimension that is safe to multiply (excludes sentinels). */
function isScalablePx(value: TokenValue): boolean {
  if (typeof value !== 'string') return false;
  const m = /^(\d+(?:\.\d+)?)px$/.exec(value);
  return m !== null && parseFloat(m[1]) < 1000;
}

/**
 * Effective design system = base, with per-group scale multipliers applied,
 * then explicit per-token edits layered on top (an explicit edit always wins).
 * Scaling is always relative to `base`, so a slider never compounds.
 */
export function computeEffectiveSystem(
  base: DesignSystem,
  edits: Record<string, TokenValue>,
  scales: Record<string, number>
): DesignSystem {
  const ds = cloneDesignSystem(base);
  const baseFlat = flattenDesignSystem(base);
  for (const [group, factor] of Object.entries(scales)) {
    if (factor === 1) continue;
    for (const t of baseFlat) {
      if (t.path.startsWith(`${group}.`) && isScalablePx(t.value)) {
        const scaled = `${Math.round(parseFloat(t.value as string) * factor)}px`;
        setLeafValue(ds, t.path, scaled);
      }
    }
  }
  for (const [path, value] of Object.entries(edits)) {
    setLeafValue(ds, path, value);
  }
  return ds;
}

const SCALE_LABELS: Record<string, string> = {
  space: 'Spacing',
  radius: 'Corner radius',
  size: 'Type',
};

function controlLabel(group: string): string {
  return SCALE_LABELS[group] ?? group.charAt(0).toUpperCase() + group.slice(1);
}

/**
 * Synthesize the design-specific controls for a system. The set is *derived*
 * from the system's composition, not hardcoded: a color group exposing a
 * `primary` token yields a hue knob; each top-level dimension group with at
 * least three scalable values yields a scale slider. A system without those
 * groups gets neither control — the controls track the design.
 */
export function deriveControls(ds: DesignSystem): GeneratedControl[] {
  const controls: GeneratedControl[] = [];
  const flat = flattenDesignSystem(ds);

  const primary = flat.find((t) => t.type === 'color' && /(^|\.)primary$/.test(t.path));
  if (primary) {
    controls.push({
      id: 'color-primary-hue',
      kind: 'hue',
      label: 'Primary hue',
      tokenPath: primary.path,
    });
  }

  for (const key of Object.keys(ds)) {
    if (key.startsWith('$')) continue;
    const node = ds[key];
    if (node == null || typeof node === 'string' || isLeaf(node)) continue;
    if (node.$type !== 'dimension') continue;
    const scalable = flat.filter((t) => t.path.startsWith(`${key}.`) && isScalablePx(t.value));
    if (scalable.length >= 3) {
      controls.push({
        id: `${key}-scale`,
        kind: 'scale',
        label: `${controlLabel(key)} scale`,
        tokenPath: scalable[0].path,
        group: key,
      });
    }
  }

  return controls;
}

// --- color helpers (hue knob) ----------------------------------------------

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/** Parse `#rrggbb` (or `#rgb`) to HSL. Returns null for non-hex values. */
export function hexToHsl(hex: string): { h: number; s: number; l: number } | null {
  let h = hex.trim().replace(/^#/, '');
  if (h.length === 3) {
    h = h
      .split('')
      .map((c) => c + c)
      .join('');
  }
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let s = 0;
  let hue = 0;
  const d = max - min;
  if (d !== 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) hue = ((g - b) / d) % 6;
    else if (max === g) hue = (b - r) / d + 2;
    else hue = (r - g) / d + 4;
    hue *= 60;
    if (hue < 0) hue += 360;
  }
  return { h: Math.round(hue), s, l };
}

/** HSL (h in degrees, s/l in 0..1) to `#rrggbb` (lowercase). */
export function hslToHex(h: number, s: number, l: number): string {
  const hue = ((h % 360) + 360) % 360;
  const sat = clamp(s, 0, 1);
  const lum = clamp(l, 0, 1);
  const c = (1 - Math.abs(2 * lum - 1)) * sat;
  const x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
  const m = lum - c / 2;
  let rp = 0;
  let gp = 0;
  let bp = 0;
  if (hue < 60) [rp, gp, bp] = [c, x, 0];
  else if (hue < 120) [rp, gp, bp] = [x, c, 0];
  else if (hue < 180) [rp, gp, bp] = [0, c, x];
  else if (hue < 240) [rp, gp, bp] = [0, x, c];
  else if (hue < 300) [rp, gp, bp] = [x, 0, c];
  else [rp, gp, bp] = [c, 0, x];
  const to2 = (v: number): string =>
    Math.round((v + m) * 255)
      .toString(16)
      .padStart(2, '0');
  return `#${to2(rp)}${to2(gp)}${to2(bp)}`;
}

/**
 * The Atelier default design system — a vendored mirror of the canonical
 * `design-tokens/tokens.json` (single source of truth for the Style Dictionary
 * fan-out, AT-050). The Studio panel falls back to this when a converged design
 * does not carry its own `tokens` payload. The AT-044 e2e reads the canonical
 * file and asserts the panel renders exactly its leaves, guarding this copy
 * against drift.
 */
export const DEFAULT_DESIGN_SYSTEM: DesignSystem = {
  $description: 'Atelier default design system (vendored mirror of design-tokens/tokens.json).',
  color: {
    $type: 'color',
    primary: { $value: '#2563eb', $description: 'Primary brand / action color' },
    'primary-hover': { $value: '#1d4ed8' },
    'on-primary': { $value: '#ffffff' },
    surface: { $value: '#ffffff' },
    'surface-muted': { $value: '#f8fafc' },
    border: { $value: '#e2e8f0' },
    text: { $value: '#0f172a', $description: 'Default body text' },
    'text-muted': { $value: '#475569' },
    success: { $value: '#16a34a' },
    warning: { $value: '#d97706' },
    danger: { $value: '#dc2626' },
  },
  font: {
    family: {
      $type: 'fontFamily',
      sans: { $value: ['Inter', 'system-ui', 'sans-serif'] },
      mono: { $value: ['JetBrains Mono', 'ui-monospace', 'monospace'] },
    },
    size: {
      $type: 'dimension',
      xs: { $value: '12px' },
      sm: { $value: '14px' },
      base: { $value: '16px' },
      lg: { $value: '20px' },
      xl: { $value: '24px' },
      '2xl': { $value: '32px' },
    },
    weight: {
      $type: 'fontWeight',
      regular: { $value: 400 },
      medium: { $value: 500 },
      bold: { $value: 700 },
    },
  },
  space: {
    $type: 'dimension',
    xs: { $value: '4px' },
    sm: { $value: '8px' },
    md: { $value: '16px' },
    lg: { $value: '24px' },
    xl: { $value: '40px' },
  },
  radius: {
    $type: 'dimension',
    sm: { $value: '4px' },
    md: { $value: '8px' },
    lg: { $value: '16px' },
    full: { $value: '9999px' },
  },
};
