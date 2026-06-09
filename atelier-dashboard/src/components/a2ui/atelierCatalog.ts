'use client';

/**
 * ADR-0024 / P0.4 (G4) — Atelier Custom Material-3 A2UI Catalog.
 *
 * Replaces the upstream `basicCatalog` as the production TRUSTED ALLOWLIST +
 * design contract + security perimeter for the Governed A2UI design-system
 * surface. The catalog declares EXACTLY the 6 component types the AT-044 surface
 * emits — Card, Column, Row, Text, Divider, List — and nothing else. The schema
 * IS the allowlist: an agent emission whose component is outside this set, or
 * whose props violate the per-component Zod schema, fails closed (the surface
 * renders nothing) and the panel's fail-soft boundary swaps in the hand-built
 * panel. The gate (G2, backend) consumes the byte-identical Python mirror of
 * this allowlist (`ATELIER_CATALOG_COMPONENTS`) as its fail-closed input.
 *
 * WHY a custom catalog (vs `basicCatalog`):
 *   `basicCatalog` renders bare `<div>`/`<span>` and DROPS the resolved
 *   `accessibility` props on the floor (verified `@a2ui/react/v0_9/index.js` —
 *   none of Text/Column/Row/List/Card/Divider read `props.accessibility`). The
 *   Atelier catalog instead emits NATIVE SEMANTIC HTML with accessible names by
 *   construction:
 *     - Text     → <h1..h5> per variant, <small> for caption, <p> for body
 *     - Column   → <section>
 *     - Row      → <div role="group">
 *     - List     → <ul> with each child wrapped in <li>
 *     - Card     → <article>
 *     - Divider  → <hr aria-orientation> (native separator, implicit role)
 *   `accessibility.label` is wired to `aria-label` on every component. This is
 *   the semantic-DOM contract the a11y track (G3) and its axe assertion rely on.
 *
 * Verified API (grounded against the installed packages):
 *   - `createComponentImplementation(api, FC)` from `@a2ui/react/v0_9`
 *     (`v0_9/index.d.ts:37`): returns `ReactComponentImplementation` ({name,
 *     schema, render}). The FC receives `{ props, buildChild, context }` where
 *     `props` is the GenericBinder-resolved snapshot of the schema (nested
 *     `accessibility` is deeply resolved — `generic-binder.d.ts:77`
 *     `ResolveA2uiProps`).
 *   - `useMarkdownRenderer()` from `@a2ui/react/v0_9` (`index.d.ts:378`): the
 *     EXPORTED hook returning the `MarkdownRenderer | undefined` from
 *     `MarkdownContext`. Text uses it to render its (variant-prefixed) markdown
 *     string, mirroring the upstream async render-or-plaintext fallback
 *     (`index.js:201-232`). The panel supplies `@a2ui/markdown-it`'s
 *     `renderMarkdown` via `MarkdownContext.Provider`.
 *   - `new Catalog(id, components[])` from `@a2ui/web_core/v0_9`
 *     (`catalog/types.d.ts:78`): `id` is the catalogId string; `components` is
 *     `ReactComponentImplementation[]`; `.components` exposes a
 *     `ReadonlyMap<string, T>` keyed by component name.
 *   - `CommonSchemas` from `@a2ui/web_core/v0_9` (`common-types.d.ts:433`):
 *     `DynamicString`, `ChildList`, `ComponentId`, `AccessibilityAttributes`.
 *
 * SCHEMA PARITY: each `*Api` schema is re-declared field-for-field from upstream
 * `basic_catalog/components/basic_components.js` (same field names, enum members,
 * defaults, `.strict()`), so the backend component tree (which mirrors the
 * basic_components shapes) validates against the Atelier catalog UNCHANGED. The
 * upstream `*Api` objects are NOT exported by `@a2ui/react`, hence the re-declare.
 *
 * STYLING: 100% driven by the existing `--a2ui-*` CSS custom properties supplied
 * by `a2ui-theme.css` on `.a2ui-host`, so the theme sheet is REUSED UNCHANGED.
 * We deliberately do NOT call `injectBasicCatalogStyles` (a `basic_catalog`
 * subpath we avoid coupling to, consistent with the wrap-don't-fork stance); each component inlines
 * the same `--a2ui-*` `style={{}}` var pattern as upstream — safe because the
 * theme overlay defines every referenced var.
 */

import React from 'react';
import { z } from 'zod';
import {
  createComponentImplementation,
  useMarkdownRenderer,
  type ReactComponentImplementation,
} from '@a2ui/react/v0_9';
import { Catalog, CommonSchemas } from '@a2ui/web_core/v0_9';

/**
 * CROSS-TRACK CONTRACT — the canonical Atelier catalog identifier.
 *
 * Byte-identical to the two Python mirrors (`A2UI_CATALOG_ID` in
 * `atelier-core/.../a2ui/surface.py` — the wire emit — and `ATELIER_CATALOG_ID`
 * in `atelier-core/.../a2ui/catalog.py` — the gate/allowlist source). It is an
 * OPAQUE IDENTIFIER, never fetched: the `MessageProcessor` matches a surface's
 * `createSurface.catalogId` against the registered catalog's `.id`. Uses the
 * canonical Atelier domain (memory `atelier_canonical_domain`).
 */
export const ATELIER_CATALOG_ID =
  'https://atelier.autonomous-agent.dev/a2ui/catalogs/design-system/v1.json';

// ---------------------------------------------------------------------------
// Common props — mirrors `basic_components.js:18-24` (CommonProps) EXACTLY.
// Every component carries `accessibility?` (label/description) + `weight?`.
// ---------------------------------------------------------------------------
const CommonProps = {
  accessibility: CommonSchemas.AccessibilityAttributes.optional(),
  weight: z.number().optional(),
};

// ---------------------------------------------------------------------------
// Per-component Api schemas — re-declared field-for-field from upstream
// `basic_catalog/components/basic_components.js:25-271` (verified). The schema
// IS the design contract + the security perimeter.
// ---------------------------------------------------------------------------

/** Text — `basic_components.js:25-38`. */
const TextApi = {
  name: 'Text',
  schema: z
    .object({
      ...CommonProps,
      text: CommonSchemas.DynamicString,
      variant: z.enum(['h1', 'h2', 'h3', 'h4', 'h5', 'caption', 'body']).default('body').optional(),
    })
    .strict(),
} as const;

/** Row — `basic_components.js:162-181`. */
const RowApi = {
  name: 'Row',
  schema: z
    .object({
      ...CommonProps,
      children: CommonSchemas.ChildList,
      justify: z
        .enum(['center', 'end', 'spaceAround', 'spaceBetween', 'spaceEvenly', 'start', 'stretch'])
        .default('start')
        .optional(),
      align: z.enum(['start', 'center', 'end', 'stretch']).default('stretch').optional(),
    })
    .strict(),
} as const;

/** Column — `basic_components.js:182-201`. */
const ColumnApi = {
  name: 'Column',
  schema: z
    .object({
      ...CommonProps,
      children: CommonSchemas.ChildList,
      justify: z
        .enum(['start', 'center', 'end', 'spaceBetween', 'spaceAround', 'spaceEvenly', 'stretch'])
        .default('start')
        .optional(),
      align: z.enum(['center', 'end', 'start', 'stretch']).default('stretch').optional(),
    })
    .strict(),
} as const;

/** List — `basic_components.js:202-224` (incl. the optional `listStyle` for parity). */
const ListApi = {
  name: 'List',
  schema: z
    .object({
      ...CommonProps,
      children: CommonSchemas.ChildList,
      direction: z.enum(['vertical', 'horizontal']).default('vertical').optional(),
      align: z.enum(['start', 'center', 'end', 'stretch']).default('stretch').optional(),
      listStyle: z.enum(['ordered', 'unordered', 'none']).optional(),
    })
    .strict(),
} as const;

/** Card — `basic_components.js:225-233`. */
const CardApi = {
  name: 'Card',
  schema: z
    .object({
      ...CommonProps,
      child: CommonSchemas.ComponentId,
    })
    .strict(),
} as const;

/** Divider — `basic_components.js:261-271`. */
const DividerApi = {
  name: 'Divider',
  schema: z
    .object({
      ...CommonProps,
      axis: z.enum(['horizontal', 'vertical']).default('horizontal').optional(),
    })
    .strict(),
} as const;

// ---------------------------------------------------------------------------
// Style helpers — re-implemented inline (the upstream helpers `mapJustify`,
// `mapAlign`, `getWeightStyle`, etc. are NOT exported). Values mirror
// `@a2ui/react/v0_9/index.js:152-195` so layout matches the basic catalog.
// ---------------------------------------------------------------------------

type JustifyValue =
  | 'center'
  | 'end'
  | 'spaceAround'
  | 'spaceBetween'
  | 'spaceEvenly'
  | 'start'
  | 'stretch';
type AlignValue = 'start' | 'center' | 'end' | 'stretch';

function mapJustify(j: JustifyValue | undefined): React.CSSProperties['justifyContent'] {
  switch (j) {
    case 'center':
      return 'center';
    case 'end':
      return 'flex-end';
    case 'spaceAround':
      return 'space-around';
    case 'spaceBetween':
      return 'space-between';
    case 'spaceEvenly':
      return 'space-evenly';
    case 'start':
      return 'flex-start';
    case 'stretch':
      return 'stretch';
    default:
      return 'flex-start';
  }
}

function mapAlign(a: AlignValue | undefined): React.CSSProperties['alignItems'] {
  switch (a) {
    case 'start':
      return 'flex-start';
    case 'center':
      return 'center';
    case 'end':
      return 'flex-end';
    case 'stretch':
      return 'stretch';
    default:
      return 'stretch';
  }
}

function weightStyle(weight: number | undefined): React.CSSProperties {
  if (typeof weight !== 'number') return {};
  return { flex: `${weight}`, minWidth: 0, minHeight: 0 };
}

/**
 * Resolve `accessibility.label` into an `aria-label`. The GenericBinder resolves
 * the outer `accessibility` object, but `label` is statically typed as the full
 * `DynamicString` union ((string | {path} | {call})); at runtime, after binding,
 * a bound label is a plain string. We narrow to that string and return
 * `undefined` (not empty string) when absent/non-string so React omits the
 * attribute entirely.
 */
function ariaLabelOf(accessibility: { label?: unknown } | undefined): string | undefined {
  const label = accessibility?.label;
  return typeof label === 'string' && label.length > 0 ? label : undefined;
}

/**
 * Strips a single outer <p> wrapper from the rendered HTML string. Markdown-it
 * wraps even single-line text in <p> when calling `.render()`; we strip it
 * when we are already wrapping the content in a semantic block element (like
 * <h1> or <small>) to prevent invalid nesting like <h1><p>...</h1>.
 */
function stripParagraphWrapper(html: string): string {
  const pOpen = '<p>';
  const pClose = '</p>';
  if (html.startsWith(pOpen) && html.endsWith(pClose)) {
    // Only strip if there's exactly one <p> pair at the start and end.
    // If there are multiple paragraphs, we keep them as-is (degrading to
    // invalid nesting but preserving the content's block structure).
    if (html.indexOf(pOpen, pOpen.length) === -1) {
      return html.slice(pOpen.length, -pClose.length);
    }
  }
  return html;
}

// ---------------------------------------------------------------------------
// Component implementations — semantic HTML + a11y by construction.
// ---------------------------------------------------------------------------

/**
 * Async markdown → HTML, mirroring the upstream `useMarkdown` hook
 * (`index.js:201-232`) but kept local (the upstream hook is not exported).
 * Returns the rendered HTML string, or `null` until/unless a renderer resolves
 * it (the caller then falls back to the raw markdown text as `children`).
 */
function useRenderedMarkdown(markdown: string): string | null {
  const renderer = useMarkdownRenderer();
  // Keyed by the current markdown so a content change re-resolves cleanly and a
  // stale async result for a previous markdown can never paint.
  const [resolved, setResolved] = React.useState<{ key: string; html: string } | null>(null);

  React.useEffect(() => {
    // No renderer in context: nothing to subscribe to — the hook returns null and
    // the FC fails soft to plaintext (acknowledged below, never a silent blank).
    if (!renderer) return;
    let active = true;
    renderer(markdown)
      .then((result) => {
        if (active) setResolved({ key: markdown, html: result });
      })
      .catch((err: unknown) => {
        // Render failure → log + degrade to plaintext (never a silent blank).
        console.error('[atelierCatalog/Text] markdown render failed:', err);
      });
    return () => {
      active = false;
    };
  }, [markdown, renderer]);

  if (!renderer) return null; // fail-soft to plaintext when no renderer is configured
  return resolved && resolved.key === markdown ? resolved.html : null;
}

/**
 * Text → semantic heading / caption / body element by `variant`.
 *   h1..h5 → <h1>..<h5> ; caption → <small> ; body (default) → <p>.
 * Content is markdown-rendered via the context renderer (same as upstream); the
 * caption keeps an emphasis treatment so `a2ui-theme.css`'s `.a2ui-host em`
 * mono-styling for token values continues to apply (we render `<small>` whose
 * values — keep this `<small>`+`<em>` pairing in sync with the theme CSS.
 */
const Text: ReactComponentImplementation = createComponentImplementation(TextApi, ({ props }) => {
  const text = typeof props.text === 'string' ? props.text : String(props.text ?? '');
  const variant = props.variant;
  // G4: unlike upstream, we do NOT prefix headings with '#' or wrap captions in
  // '*' in `variantToMarkdown` because we wrap the output in semantic HTML tags
  // (<h1>, <small>) below. We pass the raw text as markdown.
  const markdown = variant === 'caption' ? `*${text}*` : text;
  const renderedHtml = useRenderedMarkdown(markdown);
  const ariaLabel = ariaLabelOf(props.accessibility);
  const style: React.CSSProperties = {
    boxSizing: 'border-box',
    margin: 0,
    ...weightStyle(props.weight),
  };

  // Either inject the rendered HTML, or fall back to the raw markdown string.
  const contentProps: React.HTMLAttributes<HTMLElement> =
    renderedHtml !== null
      ? { dangerouslySetInnerHTML: { __html: stripParagraphWrapper(renderedHtml) } }
      : { children: markdown };

  const common: React.HTMLAttributes<HTMLElement> = {
    style,
    'aria-label': ariaLabel,
    ...contentProps,
  };

  // Variant → semantic element. `<small>` (caption) keeps the upstream emphasis
  // treatment: its inner `*...*` markdown renders as `<em>`, which
  // `a2ui-theme.css`'s `.a2ui-host em` rule styles as upright monospace for token
  // values — keep this `<small>`+`<em>` pairing in sync with the theme CSS.
  const tag: keyof React.JSX.IntrinsicElements =
    variant === 'h1'
      ? 'h1'
      : variant === 'h2'
        ? 'h2'
        : variant === 'h3'
          ? 'h3'
          : variant === 'h4'
            ? 'h4'
            : variant === 'h5'
              ? 'h5'
              : variant === 'caption'
                ? 'small'
                : 'p';
  return React.createElement(tag, common);
});

/** Column → <section> (a generic grouping landmark when labelled). */
const Column: ReactComponentImplementation = createComponentImplementation(
  ColumnApi,
  ({ props, buildChild }) => {
    const ariaLabel = ariaLabelOf(props.accessibility);
    const style: React.CSSProperties = {
      ...weightStyle(props.weight),
      display: 'flex',
      flexDirection: 'column',
      justifyContent: mapJustify(props.justify as JustifyValue | undefined),
      alignItems: mapAlign(props.align as AlignValue | undefined),
      gap: 'var(--a2ui-column-gap, var(--a2ui-spacing-m))',
      boxSizing: 'border-box',
    };
    return React.createElement(
      'section',
      { 'aria-label': ariaLabel, style },
      renderChildren(props.children, buildChild)
    );
  }
);

/** Row → <div role="group"> (semantic grouping of related controls/content). */
const Row: ReactComponentImplementation = createComponentImplementation(
  RowApi,
  ({ props, buildChild }) => {
    const ariaLabel = ariaLabelOf(props.accessibility);
    const style: React.CSSProperties = {
      ...weightStyle(props.weight),
      display: 'flex',
      flexDirection: 'row',
      justifyContent: mapJustify(props.justify as JustifyValue | undefined),
      alignItems: mapAlign(props.align as AlignValue | undefined),
      gap: 'var(--a2ui-row-gap, var(--a2ui-spacing-m))',
      boxSizing: 'border-box',
    };
    return React.createElement(
      'div',
      { role: 'group', 'aria-label': ariaLabel, style },
      renderChildren(props.children, buildChild)
    );
  }
);

/** List → <ul> with each child wrapped in a semantic <li>. */
const List: ReactComponentImplementation = createComponentImplementation(
  ListApi,
  ({ props, buildChild }) => {
    const ariaLabel = ariaLabelOf(props.accessibility);
    const isHorizontal = props.direction === 'horizontal';
    const style: React.CSSProperties = {
      display: 'flex',
      flexDirection: isHorizontal ? 'row' : 'column',
      alignItems: mapAlign(props.align as AlignValue | undefined),
      overflowX: isHorizontal ? 'auto' : 'hidden',
      overflowY: isHorizontal ? 'hidden' : 'auto',
      gap: 'var(--a2ui-list-gap, var(--a2ui-spacing-s))',
      // <ul> resets: strip the UA list bullet + default indent; the theme owns
      // padding via --a2ui-list-padding (defaults to 0).
      listStyle: 'none',
      margin: 0,
      padding: 'var(--a2ui-list-padding, 0)',
      boxSizing: 'border-box',
    };
    return React.createElement(
      props.listStyle === 'ordered' ? 'ol' : 'ul',
      {
        'aria-label': ariaLabel,
        style,
        // A11y: ordered lists should have their type set if needed, but the
        // theme manages numerals.
      },
      renderChildrenAsListItems(props.children, buildChild)
    );
  }
);

/** Card → <article> (a self-contained, landmark-friendly composition). */
const Card: ReactComponentImplementation = createComponentImplementation(
  CardApi,
  ({ props, buildChild }) => {
    const ariaLabel = ariaLabelOf(props.accessibility);
    const child = typeof props.child === 'string' ? props.child : undefined;
    const style: React.CSSProperties = {
      ...weightStyle(props.weight),
      boxSizing: 'border-box',
      display: 'block',
      border: 'var(--a2ui-card-border, var(--a2ui-border))',
      borderRadius: 'var(--a2ui-card-border-radius, var(--a2ui-border-radius, 8px))',
      padding: 'var(--a2ui-card-padding, var(--a2ui-spacing-m, 16px))',
      background: 'var(--a2ui-card-background, var(--a2ui-color-surface, var(--g-surface)))',
      color: 'var(--a2ui-color-on-surface, var(--g-text))',
      boxShadow: 'var(--a2ui-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1))',
      margin: 'var(--a2ui-card-margin, var(--a2ui-spacing-m))',
    };
    return React.createElement(
      'article',
      { 'aria-label': ariaLabel, style },
      child ? buildChild(child) : null
    );
  }
);

/**
 * Divider → native <hr>. `<hr>` carries an implicit `role="separator"`; we set
 * `aria-orientation` to expose the axis. A bare `<hr>` with default UA borders
 * would clash with the flat theme, so we zero the border and paint a 1px rule
 * via the same `--a2ui-*` tokens the upstream Divider uses.
 */
const Divider: ReactComponentImplementation = createComponentImplementation(
  DividerApi,
  ({ props }) => {
    const ariaLabel = ariaLabelOf(props.accessibility);
    const isVertical = props.axis === 'vertical';
    const style: React.CSSProperties = {
      border: 'none',
      backgroundColor: 'var(--a2ui-color-border, var(--g-outline))',
      boxSizing: 'border-box',
    };
    if (isVertical) {
      style.width = 'var(--a2ui-border-width, 1px)';
      style.height = '100%';
      style.margin = '0 var(--a2ui-divider-spacing, var(--a2ui-spacing-m, 0.5rem))';
    } else {
      style.width = '100%';
      style.height = 'var(--a2ui-border-width, 1px)';
      style.margin = 'var(--a2ui-divider-spacing, var(--a2ui-spacing-m, 0.5rem)) 0';
    }
    return React.createElement('hr', {
      role: 'separator',
      'aria-orientation': isVertical ? 'vertical' : 'horizontal',
      'aria-label': ariaLabel,
      style,
    });
  }
);

// ---------------------------------------------------------------------------
// Child rendering — mirrors the upstream `ChildList` helper
// (`@a2ui/react/v0_9/index.js:388-402`): `children` is either a resolved
// string[] of component ids OR a template-expanded array of `{id, basePath}`.
// ---------------------------------------------------------------------------

type ChildEntry = string | { id: string; basePath?: string };

/** Normalises the binder-resolved `children` (typed `any`) into child entries. */
function toChildEntries(children: unknown): ChildEntry[] {
  if (!Array.isArray(children)) return [];
  return children.filter(
    (item): item is ChildEntry =>
      typeof item === 'string' ||
      (typeof item === 'object' && item !== null && 'id' in (item as Record<string, unknown>))
  );
}

/** Flat children for Row/Column (no <li> wrapping). */
function renderChildren(
  children: unknown,
  buildChild: (id: string, basePath?: string) => React.ReactNode
): React.ReactNode {
  return toChildEntries(children).map((item, i) => {
    const id = typeof item === 'string' ? item : item.id;
    const basePath = typeof item === 'string' ? undefined : item.basePath;
    return React.createElement(React.Fragment, { key: `${id}-${i}` }, buildChild(id, basePath));
  });
}

/** Children wrapped in semantic <li> for List. */
function renderChildrenAsListItems(
  children: unknown,
  buildChild: (id: string, basePath?: string) => React.ReactNode
): React.ReactNode {
  return toChildEntries(children).map((item, i) => {
    const id = typeof item === 'string' ? item : item.id;
    const basePath = typeof item === 'string' ? undefined : item.basePath;
    return React.createElement('li', { key: `${id}-${i}` }, buildChild(id, basePath));
  });
}

// ---------------------------------------------------------------------------
// The catalog — the trusted allowlist + design contract. Exactly 6 components.
// ---------------------------------------------------------------------------

/** The 6 trusted Atelier components, in a stable declaration order. */
const ATELIER_COMPONENTS: ReactComponentImplementation[] = [Text, Column, Row, List, Card, Divider];

/**
 * The Atelier design-system catalog. Registered into the panel's
 * `MessageProcessor`; its `.id` must equal the surface's `createSurface.catalogId`
 * (`ATELIER_CATALOG_ID`) or the surface renders nothing. `.components` is a
 * `ReadonlyMap<string, ReactComponentImplementation>` keyed by component name —
 * the 6 keys ARE the frontend mirror of the Python `ATELIER_CATALOG_COMPONENTS`.
 */
export const atelierCatalog = new Catalog(ATELIER_CATALOG_ID, ATELIER_COMPONENTS);
