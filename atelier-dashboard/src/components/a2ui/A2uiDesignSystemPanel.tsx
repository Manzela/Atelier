'use client';

/**
 * ADR-0024 / P0.4 — Governed A2UI design-system panel (FRONTEND SLICE 2).
 *
 * Renders the agent-emitted A2UI surface (the AT-044 design-system token panel)
 * via `@a2ui/react`, themed to the Material-3 dark "Stitch" system so it is
 * visually indistinguishable in quality from the hand-built panel. This is
 * Studio CHROME only (ADR-0024) — it never touches the design deliverable
 * (`best_html`). It mounts behind the `NEXT_PUBLIC_A2UI_RENDER` flag, with the
 * hand-built `DesignSystemPanel` as the default and the fail-soft fallback.
 *
 * Verified API (grounded against the installed packages — `<no_unverified_apis>`):
 *   - `@a2ui/react@0.10.0`  → `A2uiSurface`, `MarkdownContext` from `.../v0_9`
 *     (`node_modules/@a2ui/react/v0_9/index.d.ts`):
 *       · `A2uiSurface: FC<{ surface: SurfaceModel<ReactComponentImplementation> }>`
 *   - `atelierCatalog` (G4, this repo) — the Atelier custom Material-3 catalog
 *     that REPLACES the upstream `basicCatalog`. It declares exactly the 6
 *     trusted component types (Card/Column/Row/Text/Divider/List) and renders
 *     NATIVE SEMANTIC HTML with `aria-label` by construction (see
 *     `./atelierCatalog`). Its `.id` is `ATELIER_CATALOG_ID`; the surface's
 *     `createSurface.catalogId` must equal it or nothing renders.
 *   - `@a2ui/web_core`      → `MessageProcessor` from `.../v0_9`
 *     (`message-processor.d.ts` / `surface-group-model.d.ts`):
 *       · `new MessageProcessor(catalogs)` ; `.processMessages(A2uiMessage[])`
 *       · `.model.surfacesMap: ReadonlyMap<string, SurfaceModel>`
 *       · `.onSurfaceCreated(fn) / .onSurfaceDeleted(fn) → { unsubscribe() }`
 *
 * Styling is driven entirely by the `--a2ui-*` CSS custom properties supplied by
 * the Material-3 dark "Stitch" overlay (`a2ui-theme.css`, maps `--g-*` Studio
 * tokens → `--a2ui-*`); the Atelier catalog inlines those vars per component, so
 * no external catalog sheet is needed. The `Text` component renders MARKDOWN, so
 * we also provide `@a2ui/markdown-it`'s `renderMarkdown` via `MarkdownContext`
 * (else headings/values leak raw markdown).
 *
 * Accessibility (G3): the Atelier-owned root wrapper carries a stable identity
 * (`role="group"`, `aria-label`, `tabIndex={-1}`, `aria-busy`, ref forwarding)
 * so the shell can move focus to it on (re)mount and scope its axe assertion to
 * it — independent of the catalog's (markdown-rendered, id-less) heading.
 */

import React, {
  Component,
  forwardRef,
  useEffect,
  useState,
  type ErrorInfo,
  type ReactNode,
} from 'react';
import { A2uiSurface, MarkdownContext } from '@a2ui/react/v0_9';
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import { renderMarkdown } from '@a2ui/markdown-it';
import type { A2uiMessage } from '@/lib/api';
import { atelierCatalog } from './atelierCatalog';
// Material-3 dark "Stitch" overlay — maps `--g-*` Studio tokens onto `--a2ui-*`.
// The Atelier catalog drives every component's visuals through these vars, so we
// do NOT import any catalog component sheet — the overlay is the single source.
import './a2ui-theme.css';

/**
 * web_core version-bridge (documented, single boundary).
 *
 * `@a2ui/react@0.10.0` is paired with `@a2ui/web_core@0.10.0` (its nested copy),
 * but the workspace currently hoists `@a2ui/web_core@0.9.2` at the root (pulled
 * up to satisfy `@a2ui/markdown-it`'s `^0.9.2`), so a bare
 * `import … from '@a2ui/web_core/v0_9'` resolves to 0.9.2. The 0.9.2 and 0.10.0
 * `SurfaceModel` / `Catalog` / `DataModel` declarations are byte-identical
 * (verified: the `data-model.d.ts` files diff clean) and there are NO `instanceof`
 * checks in the renderer — they differ only nominally because each class declares
 * a `private` field, which TypeScript treats as a distinct identity. The two
 * boundary casts below bridge that nominal gap; they are runtime no-ops. The
 * Atelier catalog is built on the react package's `createComponentImplementation`
 * (web_core 0.10.0) and registered into the root 0.9.2 `MessageProcessor` — the
 * SAME nominal-private-field gap, bridged by the SAME documented cast (we do not
 * introduce a new cast style).
 *
 * A root `overrides` forcing a single `@a2ui/web_core@0.10.0` was evaluated and
 * REJECTED: npm retains both copies regardless (`@a2ui/markdown-it` pins 0.9.2),
 * and the clean reinstall it requires destabilized the workspace. These
 * documented, runtime-safe casts are the ACCEPTED bridge for this inherent
 * upstream skew — not a temporary workaround. Revisit only if upstream aligns
 * `@a2ui/markdown-it` onto web_core 0.10.0. See `audit/P0.4-slice1-gaps.md`.
 */
type RendererSurface = Parameters<typeof A2uiSurface>[0]['surface'];

/**
 * Inner error boundary. A renderer failure (bad message, runtime throw inside
 * `A2uiSurface`) must be FAIL-SOFT: signal the parent to swap in the hand-built
 * panel via `onRenderError`, and meanwhile acknowledge degradation rather than
 * blanking. Per the failure trichotomy: tool/render error → fail-soft + log.
 */
class A2uiRenderErrorBoundary extends Component<
  { children: ReactNode; onRenderError: (error: Error) => void },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Structured log (never a silent swallow — <no_silent_error_suppression>).
    console.error(
      '[A2uiDesignSystemPanel] render failed; falling back to the hand-built panel:',
      error,
      info
    );
    this.props.onRenderError(error);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // Transient acknowledgement until the parent swaps to the fallback panel.
      return (
        <div
          data-testid="studio-a2ui-design-system-degraded"
          role="status"
          className="text-[11px] text-[var(--g-text-muted)] px-2 py-1.5"
        >
          A2UI panel unavailable — showing the standard design-system panel.
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * The actual surface renderer. Pattern is verbatim from the `@a2ui/react`
 * renderer README, adapted to the verified 0.10.0 / web_core types: build a
 * `MessageProcessor` once, seed it with the message list, then keep the surface
 * list in sync with create/delete events.
 */
function A2uiSurfaceRenderer({
  messages,
  onSurfaceReady,
}: {
  messages: A2uiMessage[];
  onSurfaceReady?: () => void;
}) {
  // `processMessages` accepts the strict `A2uiMessage[]` union; our loose
  // `api.ts` type is assignable to it. The single `unknown`→processor cast is
  // localized here so the rest of the app stays free of the renderer's
  // internal package types.
  const [processor] = useState(() => {
    // `atelierCatalog` (built on react-pkg 0.10.0) → `MessageProcessor` (0.9.2)
    // catalog param: bridged (see the version-bridge note above; runtime-
    // identical, nominal-only gap). REUSE the documented cast — no new style.
    const p = new MessageProcessor([
      atelierCatalog as unknown as ConstructorParameters<typeof MessageProcessor>[0][number],
    ]);
    p.processMessages(messages as Parameters<typeof p.processMessages>[0]);
    return p;
  });

  const [surfaces, setSurfaces] = useState(() => Array.from(processor.model.surfacesMap.values()));

  useEffect(() => {
    const sync = () => setSurfaces(Array.from(processor.model.surfacesMap.values()));
    const created = processor.onSurfaceCreated(sync);
    const deleted = processor.onSurfaceDeleted(sync);
    return () => {
      created.unsubscribe();
      deleted.unsubscribe();
    };
  }, [processor]);

  // A11y (G3): once a surface has materialized, signal the shell so it can
  // announce readiness in the persistent live region and move focus to the
  // Atelier-owned wrapper. Fires post-paint (effect) so AT does not miss it; the
  // catalog heading is markdown-rendered with no stable id, so the shell focuses
  // the wrapper, NOT the heading.
  const ready = surfaces.length > 0;
  useEffect(() => {
    if (ready) onSurfaceReady?.();
  }, [ready, onSurfaceReady]);

  if (surfaces.length === 0) {
    // No surface materialized — treat as a soft gap so the parent can fall back.
    throw new Error('A2UI payload produced no surfaces');
  }

  return (
    // The Atelier catalog's `Text` component renders its content as MARKDOWN;
    // without a renderer in context it falls back to a raw-passthrough that leaks
    // the markdown source (e.g. `### Design System`, `**`). We provide
    // `@a2ui/markdown-it`'s `renderMarkdown` (the package's own renderer;
    // signature matches the `MarkdownRenderer` type) so headings/values render
    // cleanly INSIDE the semantic <h1..5>/<small>/<p> elements the catalog emits.
    <MarkdownContext.Provider value={renderMarkdown}>
      {surfaces.map((surface) => (
        // 0.9.2 SurfaceModel → renderer's 0.10.0 SurfaceModel: bridged
        // (runtime-identical; see the version-bridge note above).
        <A2uiSurface key={surface.id} surface={surface as unknown as RendererSurface} />
      ))}
    </MarkdownContext.Provider>
  );
}

export interface A2uiDesignSystemPanelProps {
  /** The raw ordered A2UI message list from the SSE `complete` event. */
  messages: A2uiMessage[];
  /**
   * Fail-soft signal: invoked when the A2UI render cannot proceed (empty/invalid
   * payload or a runtime throw). The parent uses this to swap in the hand-built
   * AT-044 panel. The agent always acknowledges degradation — never silent.
   */
  onRenderError: (error: Error) => void;
  /**
   * A11y (G3): fired once a surface has materialized (post-mount). The shell uses
   * it to announce readiness in the persistent live region and move focus to this
   * wrapper (the focus-on-remount target — NOT the catalog's id-less heading).
   */
  onSurfaceReady?: () => void;
  /**
   * A11y (G3): drives `aria-busy` on the wrapper. The shell sets this true while
   * the surface is streaming/generating so AT knows the region is updating.
   * Defaults to false; forward-compatible with future streaming (G2).
   */
  isStreaming?: boolean;
}

/**
 * Governed A2UI design-system panel. Themed to match the hand-built panel; on
 * any render failure it acknowledges degradation and signals the parent to fall
 * back.
 *
 * A11y (G3): the root wrapper (`data-testid="studio-a2ui-design-system"`) is the
 * Atelier-owned focus + axe anchor. It carries a stable identity that survives
 * the React/MessageProcessor subtree swap because it lives OUTSIDE the renderer's
 * reconciliation: `role="group"`, `aria-label="Generated design system"`,
 * `tabIndex={-1}` (programmatically focusable on remount), `aria-busy`
 * (streaming hint), and a forwarded `ref` so the shell can call `.focus()`.
 */
const A2uiDesignSystemPanel = forwardRef<HTMLDivElement, A2uiDesignSystemPanelProps>(
  function A2uiDesignSystemPanel({ messages, onRenderError, onSurfaceReady, isStreaming }, ref) {
    return (
      <div
        ref={ref}
        data-testid="studio-a2ui-design-system"
        className="a2ui-host"
        role="group"
        aria-label="Generated design system"
        tabIndex={-1}
        aria-busy={isStreaming ?? false}
      >
        <A2uiRenderErrorBoundary onRenderError={onRenderError}>
          <A2uiSurfaceRenderer messages={messages} onSurfaceReady={onSurfaceReady} />
        </A2uiRenderErrorBoundary>
      </div>
    );
  }
);

export default A2uiDesignSystemPanel;
