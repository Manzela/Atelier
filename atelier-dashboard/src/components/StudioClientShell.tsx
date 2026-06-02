'use client';

import React, { useState, useRef, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import {
  LazyMotion,
  domAnimation,
  m,
  AnimatePresence,
  useMotionValue,
  useSpring,
  useTransform,
} from 'framer-motion';
import {
  ArrowLeft,
  Play,
  Layout,
  Box,
  Terminal,
  ChevronUp,
  ChevronDown,
  SlidersHorizontal,
  MousePointer2,
  ZoomIn,
  ZoomOut,
  Maximize,
  Smartphone,
  Tablet,
  Monitor,
  Loader2,
  AlertTriangle,
  XCircle,
  ZapOff,
  RotateCcw,
  X,
  Palette,
} from 'lucide-react';
import {
  runGenerationStream,
  type StreamCallbacks,
  type DoravScores,
  type NielsenHeuristic,
  type CapReachedData,
  type IterationScoreData,
  type TokenDeltaData,
  type A2uiMessage,
} from '@/lib/api';
import {
  DEFAULT_DESIGN_SYSTEM,
  flattenDesignSystem,
  computeEffectiveSystem,
  composeSrcDoc,
  deriveControls,
  hexToHsl,
  hslToHex,
  formatTokenValue,
  type DesignSystem,
  type TokenValue,
  type FlatToken,
  type GeneratedControl,
} from '@/lib/design-system';

// ADR-0024 / P0.4: the Governed A2UI design-system panel. Client-only (the
// renderer auto-injects styles via document.adoptedStyleSheets), so it is
// dynamically imported with `ssr: false` to keep it out of the server bundle.
const A2uiDesignSystemPanel = dynamic(() => import('./a2ui/A2uiDesignSystemPanel'), { ssr: false });

/**
 * ADR-0024 / P0.4: feature flag for rendering the agent-emitted A2UI surface in
 * place of the hand-built design-system panel. Default OFF — the hand-built
 * panel stays the default AND the fail-soft fallback. Read at module scope
 * because `NEXT_PUBLIC_*` env vars are statically inlined at build time.
 */
const A2UI_RENDER_ENABLED = process.env.NEXT_PUBLIC_A2UI_RENDER === '1';

interface UserSession {
  uid: string;
  email: string;
  displayName: string;
  token: string;
  tenant_id: string;
}

function useClientAuth() {
  const router = useRouter();
  const initialized = useRef(false);
  const [user, setUser] = useState<UserSession | null>(null);

  const initRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (initialized.current || !node) return;
      initialized.current = true;
      const userStr = localStorage.getItem('user');
      if (!userStr) {
        router.push('/login');
        return;
      }
      try {
        setUser(JSON.parse(userStr) as UserSession);
      } catch {
        localStorage.removeItem('user');
        router.push('/login');
      }
    },
    [router]
  );

  return { user, initRef };
}

type DeviceWidth = 390 | 768 | 1280;

// AT-093: D-O-R-A-V axis definitions (order matches PRD §12 E9)
const DORAV_AXES = [
  { key: 'brand' as const, label: 'Brand' },
  { key: 'originality' as const, label: 'Originality' },
  { key: 'relevance' as const, label: 'Relevance' },
  { key: 'accessibility' as const, label: 'Accessibility' },
  { key: 'visual-clarity' as const, label: 'Visual Clarity' },
] as const;

type DoravAxisKey = (typeof DORAV_AXES)[number]['key'];

/** AT-096: Per-user lifetime token cap (5 million tokens). */
const TOKEN_CAP = 5_000_000;

/**
 * AT-093: Animated per-axis score bar using framer-motion spring.
 * Avoids per-event React re-render storms by driving the display value via
 * useMotionValue + useSpring + useTransform; the React state update only sets
 * the motion value, not the displayed integer, so no extra render occurs.
 */
function AnimatedScoreValue({ value }: { value: number | undefined }) {
  const mv = useMotionValue(value ?? 0);
  const spring = useSpring(mv, { stiffness: 120, damping: 20 });
  const display = useTransform(spring, (v) => (value != null ? String(Math.round(v * 100)) : '—'));

  // Drive the motion value whenever the prop changes
  React.useEffect(() => {
    if (value != null) mv.set(value);
  }, [value, mv]);

  return <m.span>{display}</m.span>;
}

// AT-090: Competitor-contrast beat — rendered on convergence, dismissible.
// Product COPY only; no runtime Claude integration. ADR-0020/§13.5 guardrail honored.
function CompetitorContrastBeat({ onDismiss }: { onDismiss: () => void }) {
  return (
    <m.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
      data-testid="competitor-contrast-beat"
      className="rounded border border-indigo-500/30 bg-black/40 p-4 text-[11px] leading-relaxed"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <h4 className="text-[11px] uppercase tracking-wider font-semibold text-indigo-300">
          Why Atelier?
        </h4>
        <button
          data-testid="competitor-contrast-dismiss"
          onClick={onDismiss}
          className="shrink-0 p-0.5 rounded hover:bg-white/10 text-gray-500 hover:text-white transition-colors"
          aria-label="Dismiss competitor contrast"
        >
          <X size={12} />
        </button>
      </div>

      {/* vs Stitch / v0 / Lovable */}
      <div className="mb-3">
        <p className="text-gray-400 font-semibold mb-1">vs Stitch / v0 / Lovable</p>
        <ul className="space-y-1 text-gray-400">
          <li>
            <span className="text-white font-medium">reject+halt on skeleton</span> — deterministic
            structure gate rejects empty/skeleton output before any LLM token burns
          </li>
          <li>
            <span className="text-white font-medium">anchored tokens</span> — zero-tolerance token
            gate; a design-system value edit propagates to every token-bound surface, not suggested
            and drifted
          </li>
          <li>
            <span className="text-white font-medium">edit-not-regenerate</span> — one-edit -&gt;
            N-surface token propagation (AT-052); byte-stable replay
          </li>
          <li>
            <span className="text-white font-medium">legible token meter</span> — token-based
            governance with fail-closed gates; live per-user cap in deploy wave; invisible burn is
            the top usage complaint
          </li>
          <li>
            <span className="text-white font-medium">proactive standards + scope-lock</span> —
            checks applied before generation, not after
          </li>
        </ul>
      </div>

      {/* vs Claude Design */}
      <div className="mb-3">
        <p className="text-gray-400 font-semibold mb-1">
          vs Claude Design (Anthropic Labs, research preview)
        </p>
        <p className="text-gray-500 mb-1.5 italic text-[10px]">
          Claude Design out-polishes Atelier on raw visual fidelity, interactive-refinement feel,
          output breadth, and real adoption. It is a flagship WYSIWYG editor. Atelier does a
          different job.
        </p>
        <ul className="space-y-1 text-gray-400">
          <li>
            <span className="text-white font-medium">autonomous and long-running</span> — unattended
            convergence vs synchronous human-collaborative editing
          </li>
          <li>
            <span className="text-white font-medium">multi-specialist DAG + critique panel</span> —
            6-role DDLC specialist pipeline, Fixer loop, 5-axis D-O-R-A-V judge vs single-model pass
          </li>
          <li>
            <span className="text-white font-medium">
              ENFORCES brand (zero-tolerance token gate)
            </span>{' '}
            — applied and verified vs built and suggested
          </li>
          <li>
            <span className="text-white font-medium">governed</span> — fail-closed gates,
            converge-or-halt discipline (live); Model Armor + IAP auth (deploy wave)
          </li>
          <li>
            <span className="text-white font-medium">observable</span> — per-iteration scorecard
            (oracle-score deltas, AT-093), byte-equal replay (live); Kanban board (deploy wave)
          </li>
          <li>
            <span className="text-white font-medium">Google-native</span> — Vertex AI + Gemini +
            BigQuery + Cloud Run + Firebase
          </li>
        </ul>
      </div>

      {/* Proof-points */}
      <div className="pt-2 border-t border-[var(--g-outline)] text-[10px] text-gray-500">
        B1 proof-points: skeleton reject+halt / one-edit -&gt; N-surface (AT-052) / converging
        oracle-score deltas (AT-093) / byte-stable replay
      </div>
    </m.div>
  );
}

// AT-044: Design-system panel — one editable row per design-system token, plus
// the design-specific controls Atelier synthesizes for *this* system (PRD §12
// E4 / §25). Editing a token re-flows every surface that consumes it: the panel
// recomposes the iframe srcDoc with a live :root block (see composeSrcDoc).
function tokenSlug(path: string): string {
  return path.split('.').join('-');
}

function DesignSystemTokenRow({
  token,
  onEdit,
}: {
  token: FlatToken;
  onEdit: (path: string, value: TokenValue) => void;
}) {
  const slug = tokenSlug(token.path);
  const isColor = token.type === 'color' && typeof token.value === 'string';
  const display = formatTokenValue(token.value);
  return (
    <div
      data-testid={`ds-token-row-${slug}`}
      className="flex items-center gap-2 px-2 py-1.5 rounded bg-black/20 border border-[var(--g-outline)]"
    >
      {isColor && (
        <span
          data-testid={`ds-token-swatch-${slug}`}
          className="shrink-0 w-4 h-4 rounded border border-white/20"
          style={{ backgroundColor: String(token.value) }}
          aria-hidden="true"
        />
      )}
      <span className="text-[10px] font-mono text-gray-400 flex-1 truncate" title={token.path}>
        {token.path}
      </span>
      {isColor ? (
        <input
          data-testid={`ds-token-input-${slug}`}
          type="color"
          value={String(token.value)}
          onChange={(e) => onEdit(token.path, e.target.value)}
          className="shrink-0 w-7 h-6 rounded cursor-pointer bg-transparent border border-[var(--g-outline)] p-0"
          aria-label={`Edit ${token.path}`}
        />
      ) : (
        <input
          data-testid={`ds-token-input-${slug}`}
          type="text"
          value={display}
          onChange={(e) => onEdit(token.path, e.target.value)}
          className="shrink-0 w-24 text-[10px] font-mono text-gray-200 bg-black/30 border border-[var(--g-outline)] rounded px-1.5 py-0.5"
          aria-label={`Edit ${token.path}`}
        />
      )}
    </div>
  );
}

function GeneratedControlRow({
  control,
  rows,
  scale,
  onEditToken,
  onScale,
}: {
  control: GeneratedControl;
  rows: FlatToken[];
  scale: number;
  onEditToken: (path: string, value: TokenValue) => void;
  onScale: (group: string, factor: number) => void;
}) {
  if (control.kind === 'hue') {
    const current = rows.find((t) => t.path === control.tokenPath);
    const hex = typeof current?.value === 'string' ? current.value : '#000000';
    const hsl = hexToHsl(hex);
    const hue = hsl?.h ?? 0;
    return (
      <div
        data-testid={`ds-generated-control-${control.id}`}
        data-token={control.tokenPath}
        className="px-3 py-2 rounded bg-black/30 border border-indigo-500/30"
      >
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-[11px] text-indigo-200 font-medium">{control.label}</span>
          <span className="text-[10px] font-mono text-gray-400">{Math.round(hue)}&deg;</span>
        </div>
        <input
          data-testid={`ds-generated-input-${control.id}`}
          type="range"
          min="0"
          max="360"
          step="1"
          value={hue}
          onChange={(e) => {
            const base = hsl ?? { s: 0.7, l: 0.5 };
            onEditToken(control.tokenPath, hslToHex(parseInt(e.target.value, 10), base.s, base.l));
          }}
          className="w-full accent-indigo-500"
          aria-label={`${control.label} — bound to ${control.tokenPath}`}
        />
      </div>
    );
  }
  // kind === 'scale'
  return (
    <div
      data-testid={`ds-generated-control-${control.id}`}
      data-token={control.tokenPath}
      className="px-3 py-2 rounded bg-black/30 border border-indigo-500/30"
    >
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-[11px] text-indigo-200 font-medium">{control.label}</span>
        <span className="text-[10px] font-mono text-gray-400">{scale.toFixed(2)}&times;</span>
      </div>
      <input
        data-testid={`ds-generated-input-${control.id}`}
        type="range"
        min="0.5"
        max="2"
        step="0.05"
        value={scale}
        onChange={(e) => onScale(control.group, parseFloat(e.target.value))}
        className="w-full accent-indigo-500"
        aria-label={`${control.label} — bound to ${control.tokenPath}`}
      />
    </div>
  );
}

function DesignSystemPanel({
  rows,
  controls,
  scales,
  onEditToken,
  onScale,
}: {
  rows: FlatToken[];
  controls: GeneratedControl[];
  scales: Record<string, number>;
  onEditToken: (path: string, value: TokenValue) => void;
  onScale: (group: string, factor: number) => void;
}) {
  return (
    <div data-testid="ds-panel">
      <div className="h-px bg-[var(--g-outline)] my-4" />
      <h4 className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3">
        <Palette size={12} className="text-indigo-400" />
        Design System
        <span
          data-testid="ds-panel-count"
          className="ml-auto px-1.5 py-0.5 rounded text-[9px] bg-indigo-500/20 text-indigo-300 font-mono border border-indigo-500/30"
        >
          {rows.length} tokens
        </span>
      </h4>

      {/* Agent-generated, design-specific controls (the "custom sliders" pattern) */}
      {controls.length > 0 && (
        <div data-testid="ds-generated-controls" className="space-y-2 mb-3">
          {controls.map((c) => (
            <GeneratedControlRow
              key={c.id}
              control={c}
              rows={rows}
              scale={c.kind === 'scale' ? (scales[c.group] ?? 1) : 1}
              onEditToken={onEditToken}
              onScale={onScale}
            />
          ))}
        </div>
      )}

      {/* One row per token — editing a value propagates to every surface that consumes it */}
      <div className="space-y-1 max-h-72 overflow-y-auto pr-1">
        {rows.map((token) => (
          <DesignSystemTokenRow key={token.path} token={token} onEdit={onEditToken} />
        ))}
      </div>
    </div>
  );
}

export default function StudioClientShell({ id }: { id: string }) {
  const router = useRouter();
  const [scale, setScale] = useState(1);
  const [deviceWidth, setDeviceWidth] = useState<DeviceWidth>(1280);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [temperature, setTemperature] = useState(0.4);
  const [topK, setTopK] = useState(40);
  const [maxTokens, setMaxTokens] = useState(4096);
  const { user, initRef } = useClientAuth();

  const [status, setStatus] = useState<
    'idle' | 'generating' | 'converged' | 'degraded' | 'error' | 'cap-reached'
  >('idle');
  const [logs, setLogs] = useState<{ id: number; time: string; level: string; msg: string }[]>([]);
  const [convergedHtml, setConvergedHtml] = useState<string>('');
  const [dorav, setDorav] = useState<DoravScores | null>(null);
  const [nielsen, setNielsen] = useState<NielsenHeuristic[]>([]);
  // AT-093: per-iteration scorecard state — updated on each iteration_score SSE event
  const [iterationScores, setIterationScores] = useState<IterationScoreData[]>([]);
  const latestIterScore = iterationScores[iterationScores.length - 1] ?? null;
  // Live D-O-R-A-V: prefer the latest iteration scores while generating; fall back to final
  const liveDorav: DoravScores | null = useMemo(() => {
    if (latestIterScore) return { ...latestIterScore.dorav, composite: latestIterScore.composite };
    return dorav;
  }, [latestIterScore, dorav]);
  const currentIteration = latestIterScore?.iteration ?? null;
  const failingAxis: string | null = latestIterScore?.failing_axis ?? null;
  const [degradationReason, setDegradationReason] = useState<string>('');
  const [capReachedDetail, setCapReachedDetail] = useState<string>('');
  // AT-090: competitor-contrast beat — shown on convergence, dismissible
  const [competitorBeatVisible, setCompetitorBeatVisible] = useState(true);
  // AT-096: live token meter — cumulative per-user counter (NOT reset on new run)
  const [tokenUsage, setTokenUsage] = useState<TokenDeltaData | null>(null);
  // AT-096: soft-warn dismissal — once dismissed, stays dismissed for the session
  const [softWarnDismissed, setSoftWarnDismissed] = useState(false);
  // AT-044: the active design system (from the converged design, else the default),
  // plus the panel's live edits. The effective system layers edits + per-group
  // scales over the base, and feeds both the panel rows and the iframe srcDoc.
  const [baseDesignSystem, setBaseDesignSystem] = useState<DesignSystem | null>(null);
  const [tokenEdits, setTokenEdits] = useState<Record<string, TokenValue>>({});
  const [groupScales, setGroupScales] = useState<Record<string, number>>({});
  // ADR-0024 / P0.4: the agent-emitted A2UI design-system surface (raw message
  // list from the SSE `complete` event), plus a fail-soft latch. When the flag
  // is ON and a payload is present we render the A2UI panel; if its renderer
  // throws, `a2uiRenderFailed` latches and we fall back to the hand-built panel.
  const [a2uiPayload, setA2uiPayload] = useState<A2uiMessage[] | null>(null);
  const [a2uiRenderFailed, setA2uiRenderFailed] = useState(false);
  // Render the A2UI panel only when: flag ON, a payload arrived, and it has not
  // already failed. Otherwise the hand-built panel is the default + fallback.
  const useA2uiPanel = A2UI_RENDER_ENABLED && a2uiPayload !== null && !a2uiRenderFailed;
  const effectiveDesignSystem = useMemo(
    () =>
      baseDesignSystem ? computeEffectiveSystem(baseDesignSystem, tokenEdits, groupScales) : null,
    [baseDesignSystem, tokenEdits, groupScales]
  );
  const designSystemRows = useMemo(
    () => (effectiveDesignSystem ? flattenDesignSystem(effectiveDesignSystem) : []),
    [effectiveDesignSystem]
  );
  // Controls are derived from the system's *structure* (stable across edits).
  const generatedControls = useMemo(
    () => (baseDesignSystem ? deriveControls(baseDesignSystem) : []),
    [baseDesignSystem]
  );
  // Whether the user has overridden the converged design system via the panel.
  const hasDesignSystemOverrides =
    Object.keys(tokenEdits).length > 0 || Object.values(groupScales).some((f) => f !== 1);
  // The converged output renders byte-exact by default (AT-040 invariant); once
  // a token is edited, the iframe surface consumes the live tokens as :root vars
  // (appended last so they win the cascade), so the edit re-flows the surface.
  const effectiveSrcDoc = useMemo(
    () =>
      hasDesignSystemOverrides
        ? composeSrcDoc(convergedHtml, effectiveDesignSystem)
        : convergedHtml,
    [hasDesignSystemOverrides, convergedHtml, effectiveDesignSystem]
  );
  const handleEditToken = useCallback((path: string, value: TokenValue) => {
    setTokenEdits((prev) => ({ ...prev, [path]: value }));
  }, []);
  const handleScaleGroup = useCallback((group: string, factor: number) => {
    setGroupScales((prev) => ({ ...prev, [group]: factor }));
  }, []);

  const addLog = (level: string, msg: string) => {
    const time = new Date().toISOString().split('T')[1].slice(0, 8);
    setLogs((prev) => [...prev, { id: Date.now(), time, level, msg }]);
  };

  // ADR-0024 / P0.4: fail-soft latch for the A2UI panel. On a renderer failure
  // we acknowledge degradation (log) and flip to the hand-built panel — the
  // agent always acknowledges degradation; never a silent blank.
  const handleA2uiRenderError = (error: Error) => {
    setA2uiRenderFailed(true);
    addLog('WARN', `A2UI panel degraded — using hand-built panel: ${error.message}`);
  };

  const handleZoom = (delta: number) => {
    setScale((s) => Math.max(0.2, Math.min(3, s + delta)));
  };

  const startGeneration = () => {
    if (status === 'generating' || status === 'cap-reached' || !user) return;
    setStatus('generating');
    setLogs([]);
    setIterationScores([]); // AT-093: reset per-iteration scorecard on each new run
    setCompetitorBeatVisible(true); // AT-090: show beat again on each new run
    // AT-044: reset the design-system panel for the new run
    setBaseDesignSystem(null);
    setTokenEdits({});
    setGroupScales({});
    // ADR-0024 / P0.4: reset the A2UI surface + fail-soft latch for the new run
    setA2uiPayload(null);
    setA2uiRenderFailed(false);
    addLog('INFO', 'Initiating Vertex AI Convergence Loop...');

    const brief = new URLSearchParams(window.location.search).get('brief') || 'SaaS landing page';

    const callbacks: StreamCallbacks = {
      onPlan: (data) => {
        addLog('INFO', `Plan received: ${data.surfaces?.join(', ') || 'N/A'}`);
      },
      onScreenStart: (data) => {
        addLog('INFO', `Generating screen: ${data.screen}`);
      },
      onIterationStart: (data) => {
        addLog('INFO', `Iteration #${data.iteration} started`);
      },
      onCandidates: () => {
        addLog('INFO', 'Candidate HTML received');
      },
      onGatesEvaluation: (data) => {
        const level = data.passed ? 'SUCCESS' : 'WARN';
        addLog(level, `Gates: axe=${data.axe_score}, visual=${data.visual_score}`);
      },
      onConsensusEvaluation: (data) => {
        const level = data.passed ? 'SUCCESS' : 'WARN';
        addLog(level, `Consensus: [${data.votes?.join(', ')}]`);
      },
      onFixerDirective: (data) => {
        addLog('WARN', `Fixer: ${data.directive}`);
      },
      onScreenConverged: (data) => {
        addLog('SUCCESS', `Screen converged: ${data.screen}`);
      },
      onComplete: (data) => {
        if (data.best_html) setConvergedHtml(data.best_html);
        if (data.dorav) setDorav(data.dorav);
        if (data.nielsen) setNielsen(data.nielsen);
        // AT-044: the design's own system if it carries one, else the default.
        setBaseDesignSystem(data.tokens ?? DEFAULT_DESIGN_SYSTEM);
        // ADR-0024 / P0.4: capture the Governed A2UI surface if the backend
        // emitted one. Only consumed when NEXT_PUBLIC_A2UI_RENDER === '1';
        // otherwise it is inert and the hand-built panel renders.
        setA2uiPayload(
          Array.isArray(data.a2ui_payload) && data.a2ui_payload.length > 0
            ? data.a2ui_payload
            : null
        );
        if (data.degraded) {
          const reason =
            data.degradation_reason || 'Output quality fell below the convergence threshold.';
          setDegradationReason(reason);
          addLog('WARN', `Generation degraded: ${reason}`);
          setStatus('degraded');
        } else {
          addLog('SUCCESS', 'Generation complete. All screens converged.');
          setStatus('converged');
        }
      },
      onError: (err) => {
        addLog('ERROR', `Pipeline error: ${err}`);
        setStatus('error');
      },
      onCapReached: (data: CapReachedData) => {
        const detail = data.detail || 'Token cap reached. Please wait before running again.';
        setCapReachedDetail(detail);
        addLog('ERROR', `Token cap reached: ${detail}`);
        setStatus('cap-reached');
      },
      // AT-093: accumulate per-iteration scores so the scorecard animates each climb
      onIterationScore: (data: IterationScoreData) => {
        setIterationScores((prev) => [...prev, data]);
        const comp = Math.round((data.composite ?? 0) * 100);
        addLog(
          'INFO',
          `Iter ${data.iteration} D-O-R-A-V composite=${comp} failing=${data.failing_axis ?? 'none'}`
        );
      },
      // AT-096: update cumulative token usage; do NOT reset between runs (acceptance 1)
      onTokenDelta: (data: TokenDeltaData) => {
        setTokenUsage(data);
        const delta = data.input + data.output + data.thinking;
        addLog('INFO', `Tokens: +${delta} (Σ ${data.cumulative_user_tokens}/${TOKEN_CAP})`);
      },
    };

    runGenerationStream(brief, user.token, callbacks);
  };

  if (!user) return <div ref={initRef} />;

  return (
    <LazyMotion features={domAnimation}>
      <div className="h-screen w-screen bg-[var(--g-bg)] text-[var(--g-text)] overflow-hidden flex flex-col font-sans stitch-grid-bg">
        {/* Top Navbar */}
        <header className="h-14 flex items-center justify-between px-4 border-b border-[var(--g-outline)] bg-[var(--g-surface)]/80 backdrop-blur-md z-40">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push('/')}
              className="p-1.5 hover:bg-[var(--g-surface-hover)] rounded-md transition-colors"
              aria-label="Back to dashboard"
            >
              <ArrowLeft size={18} className="text-[var(--g-text-muted)]" />
            </button>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-[13px] text-white tracking-wide">{id}</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/20 text-indigo-300 font-mono border border-indigo-500/30">
                v1.0
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1 bg-black/40 p-1 rounded-md border border-[var(--g-outline)]">
            <button className="px-3 py-1 rounded text-xs font-medium bg-[var(--g-outline)] text-white shadow-sm">
              Home
            </button>
            <button className="px-3 py-1 rounded text-xs font-medium text-gray-400 hover:text-white transition-colors">
              Auth
            </button>
            <button className="px-3 py-1 rounded text-xs font-medium text-gray-400 hover:text-white transition-colors">
              Dashboard
            </button>
          </div>

          <div className="flex items-center gap-3">
            <div className="px-3 py-1.5 text-xs text-gray-400 border border-[var(--g-outline)] rounded-md bg-black/20 flex items-center gap-2">
              Model: <span className="text-white font-medium">Gemini 2.5 Pro</span>
            </div>
            <button
              onClick={startGeneration}
              disabled={status === 'generating' || status === 'cap-reached'}
              className="flex items-center gap-1.5 bg-[var(--g-primary-blue)] hover:bg-[var(--g-primary-blue-hover)] disabled:opacity-50 text-white px-4 py-1.5 rounded-md text-xs font-medium transition-colors shadow-sm"
            >
              {status === 'generating' ? (
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Play size={14} className="ml-0.5 fill-current" />
              )}
              {status === 'generating' ? 'Generating...' : 'Run'}
            </button>
          </div>
        </header>

        <div className="flex-1 flex overflow-hidden relative">
          {/* Left Block Drawer */}
          <aside className="w-56 border-r border-[var(--g-outline)] bg-[var(--g-surface)]/50 backdrop-blur-md flex flex-col z-10">
            <div className="p-3 border-b border-[var(--g-outline)] flex items-center gap-2">
              <Layout size={14} className="text-gray-400" />
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                Layers
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {['Hero Section', 'Feature Grid', 'Testimonials', 'Pricing Table', 'Footer'].map(
                (layer, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--g-surface-hover)] text-xs text-gray-400 cursor-pointer group transition-colors"
                  >
                    <Box
                      size={14}
                      className="text-gray-500 group-hover:text-indigo-400 transition-colors"
                    />
                    <span className="truncate">{layer}</span>
                  </div>
                )
              )}
            </div>
          </aside>

          {/* Center Canvas */}
          <main className="flex-1 relative flex items-center justify-center overflow-auto">
            {/* Canvas Toolbar */}
            <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-[var(--g-surface)]/80 backdrop-blur-md p-1 rounded-lg border border-[var(--g-outline)] shadow-lg z-20">
              <button
                data-testid="device-390"
                aria-label="Mobile 390px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 390 ? 'bg-indigo-500/30 text-indigo-300' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(390)}
              >
                <Smartphone size={16} />
              </button>
              <button
                data-testid="device-768"
                aria-label="Tablet 768px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 768 ? 'bg-indigo-500/30 text-indigo-300' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(768)}
              >
                <Tablet size={16} />
              </button>
              <button
                data-testid="device-1280"
                aria-label="Desktop 1280px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 1280 ? 'bg-indigo-500/30 text-indigo-300' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(1280)}
              >
                <Monitor size={16} />
              </button>
              <div className="w-px h-4 bg-[var(--g-outline)] mx-1" />
              <button
                className="p-1.5 rounded hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white transition-colors"
                onClick={() => handleZoom(-0.1)}
                aria-label="Zoom out"
              >
                <ZoomOut size={16} />
              </button>
              <span className="text-xs font-mono w-12 text-center text-gray-300">
                {Math.round(scale * 100)}%
              </span>
              <button
                className="p-1.5 rounded hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white transition-colors"
                onClick={() => handleZoom(0.1)}
                aria-label="Zoom in"
              >
                <ZoomIn size={16} />
              </button>
              <div className="w-px h-4 bg-[var(--g-outline)] mx-1" />
              <button
                className="p-1.5 rounded hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white transition-colors"
                onClick={() => setScale(1)}
                aria-label="Reset zoom"
              >
                <Maximize size={16} />
              </button>
            </div>

            {/* Draggable/Zoomable Canvas Area */}
            <m.div
              data-testid="studio-canvas"
              drag
              dragMomentum={false}
              animate={{ scale }}
              transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
              style={{ width: deviceWidth }}
              className="shrink-0 h-[768px] bg-white rounded-lg shadow-2xl overflow-hidden border border-gray-200 cursor-grab active:cursor-grabbing origin-center"
            >
              {/* \u2500\u2500 Empty (idle) state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'idle' && (
                <div
                  data-testid="state-empty"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <MousePointer2 size={40} className="text-indigo-300" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-gray-700 text-center">
                    Ready to generate
                  </h2>
                  <p className="text-sm text-gray-600 text-center max-w-xs">
                    Configure your brief in the URL and click{' '}
                    <strong className="text-gray-800">Run</strong> to start the Vertex AI
                    Convergence Loop.
                  </p>
                </div>
              )}

              {/* \u2500\u2500 Loading (generating) state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'generating' && (
                <div
                  data-testid="state-loading"
                  role="status"
                  aria-live="polite"
                  aria-label="Generating design \u2014 please wait"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4"
                >
                  <Loader2 size={40} className="text-indigo-500 animate-spin" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-gray-700">Generating\u2026</h2>
                  <p className="text-sm text-gray-600">
                    Vertex AI Convergence Loop is running. This may take a moment.
                  </p>
                </div>
              )}

              {/* \u2500\u2500 Converged state \u2014 render iframe \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'converged' && convergedHtml && (
                <iframe
                  sandbox="allow-scripts"
                  srcDoc={effectiveSrcDoc}
                  title="Converged design output"
                  className="w-full h-full border-0"
                />
              )}

              {/* \u2500\u2500 Degraded state \u2014 show output + degradation banner \u2500\u2500\u2500 */}
              {status === 'degraded' && (
                <div data-testid="state-degraded" className="w-full h-full relative">
                  {/* Still render the best available output behind the banner */}
                  {convergedHtml && (
                    <iframe
                      sandbox="allow-scripts"
                      srcDoc={effectiveSrcDoc}
                      title="Degraded design output"
                      className="w-full h-full border-0"
                    />
                  )}
                  {/* Degradation acknowledgment overlay (PRD: agent always acknowledges degradation) */}
                  <div
                    role="status"
                    aria-live="polite"
                    className="absolute top-0 left-0 right-0 flex items-start gap-3 bg-amber-50 border-b-2 border-amber-400 px-4 py-3"
                  >
                    <AlertTriangle
                      size={20}
                      className="text-amber-600 mt-0.5 shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <h2 className="text-sm font-semibold text-amber-800">
                        Result is degraded \u2014 showing the best available output
                      </h2>
                      {degradationReason && (
                        <p className="text-xs text-amber-700 mt-0.5">{degradationReason}</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* \u2500\u2500 Error state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'error' && (
                <div
                  data-testid="state-error"
                  role="alert"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <XCircle size={40} className="text-red-400" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-red-700">Pipeline error</h2>
                  <p className="text-sm text-gray-500 text-center max-w-xs">
                    The generation pipeline encountered an error. Check the log below for details,
                    then try again.
                  </p>
                  <button
                    onClick={startGeneration}
                    className="mt-2 flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Retry generation
                  </button>
                </div>
              )}

              {/* \u2500\u2500 Cap-reached state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'cap-reached' && (
                <div
                  data-testid="state-cap-reached"
                  role="alert"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <ZapOff size={40} className="text-orange-400" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-orange-700">Token cap reached</h2>
                  <p className="text-sm text-gray-600 text-center max-w-xs">
                    {capReachedDetail ||
                      "You've reached your token cap for this session. Please wait before running another generation."}
                  </p>
                  <p className="text-xs text-gray-600 text-center max-w-xs">
                    Token limits reset periodically. Contact your administrator if you need a higher
                    limit.
                  </p>
                </div>
              )}
            </m.div>
          </main>

          {/* Right Vertex AI Config Panel */}
          <aside className="w-72 border-l border-[var(--g-outline)] bg-[var(--g-surface)]/50 backdrop-blur-md flex flex-col z-10">
            <div className="p-4 border-b border-[var(--g-outline)] flex items-center gap-2">
              <SlidersHorizontal size={16} className="text-indigo-400" />
              <span className="text-sm font-semibold text-white">Vertex AI Settings</span>
            </div>

            <div className="p-5 space-y-6 flex-1 overflow-y-auto">
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-400">Temperature</span>
                    <span className="text-white font-mono">{temperature.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="w-full accent-indigo-500"
                    aria-label="Temperature"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-400">Top-K</span>
                    <span className="text-white font-mono">{topK}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="40"
                    value={topK}
                    onChange={(e) => setTopK(parseInt(e.target.value))}
                    className="w-full accent-indigo-500"
                    aria-label="Top-K"
                  />
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-400">Max Tokens</span>
                    <span className="text-white font-mono">{maxTokens}</span>
                  </div>
                  <input
                    type="range"
                    min="1024"
                    max="8192"
                    step="512"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                    className="w-full accent-indigo-500"
                    aria-label="Max Tokens"
                  />
                </div>
              </div>

              <div className="h-px bg-[var(--g-outline)] my-6"></div>

              {/* AT-093: D-O-R-A-V Scorecard — animates per-iteration during generation */}
              <div data-testid="dorav-scorecard" data-iteration={currentIteration ?? ''}>
                <h4 className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3">
                  D-O-R-A-V Scorecard
                  {currentIteration != null && (
                    <span className="ml-2 px-1.5 py-0.5 rounded text-[9px] bg-indigo-500/20 text-indigo-300 font-mono border border-indigo-500/30 align-middle">
                      iter {currentIteration + 1}
                    </span>
                  )}
                </h4>
                {/* Composite headline */}
                <div className="bg-black/40 p-3 rounded border border-indigo-500/30 flex justify-between items-center mb-3">
                  <span className="text-xs text-gray-300 font-semibold">Composite</span>
                  <span
                    className={`text-sm font-mono font-bold ${liveDorav?.composite != null ? 'text-indigo-300' : 'text-gray-600'}`}
                  >
                    {liveDorav?.composite != null ? (
                      <AnimatedScoreValue value={liveDorav.composite} />
                    ) : (
                      '--'
                    )}
                  </span>
                </div>
                <div className="space-y-2">
                  {DORAV_AXES.map(({ key, label }) => {
                    const val = liveDorav?.[key as DoravAxisKey];
                    const isFailing = failingAxis === key;
                    return (
                      <div
                        key={key}
                        data-testid={`dorav-axis-${key}`}
                        data-score={val != null ? String(Math.round(val * 100)) : ''}
                        className={`px-3 py-2 rounded border flex justify-between items-center transition-colors ${
                          isFailing
                            ? 'failing-axis bg-amber-950/40 border-amber-500/60'
                            : 'bg-black/30 border-[var(--g-outline)]'
                        }`}
                      >
                        <span
                          className={`text-xs ${isFailing ? 'text-amber-300 font-semibold' : 'text-gray-400'}`}
                        >
                          {label}
                          {isFailing && (
                            <span className="ml-1 text-[9px] text-amber-400 font-mono">↓ low</span>
                          )}
                        </span>
                        <span
                          className={`text-xs font-mono font-bold ${
                            isFailing
                              ? 'text-amber-400'
                              : val != null
                                ? 'text-emerald-400'
                                : 'text-gray-600'
                          }`}
                        >
                          {val != null ? <AnimatedScoreValue value={val} /> : '—'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* AT-096: Live Token Meter */}
              <div className="h-px bg-[var(--g-outline)] my-4" />
              {(() => {
                const cumulative = tokenUsage?.cumulative_user_tokens ?? 0;
                const pct = Math.min(100, (cumulative / TOKEN_CAP) * 100);
                const remaining = TOKEN_CAP - cumulative;
                const barColor =
                  pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500';
                return (
                  <>
                    {/* Soft warning banner — dismissible, non-blocking, shown once */}
                    {tokenUsage &&
                      tokenUsage.cumulative_user_tokens >= 0.9 * TOKEN_CAP &&
                      !softWarnDismissed && (
                        <div
                          data-testid="token-soft-warning"
                          className="flex items-center justify-between gap-2 mb-3 px-3 py-2 rounded border border-amber-500/60 bg-amber-950/40 text-[11px] text-amber-300"
                          role="status"
                          aria-live="polite"
                        >
                          <span>
                            You&apos;re approaching this account&apos;s usage limit (90%).
                          </span>
                          <button
                            onClick={() => setSoftWarnDismissed(true)}
                            className="shrink-0 p-0.5 rounded hover:bg-white/10 text-amber-400 hover:text-white transition-colors"
                            aria-label="Dismiss token warning"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      )}
                    <div
                      data-testid="token-meter"
                      data-cumulative={cumulative}
                      data-cap={TOKEN_CAP}
                    >
                      <h4 className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-2">
                        Token Usage
                      </h4>
                      {/* Hero: remaining headroom */}
                      <div className="bg-black/40 p-3 rounded border border-[var(--g-outline)] mb-2">
                        <div className="flex justify-between items-baseline mb-1.5">
                          <span className="text-[10px] text-gray-400">Used</span>
                          <span className="text-xs font-mono text-white">
                            {cumulative.toLocaleString()} / {TOKEN_CAP.toLocaleString()}
                          </span>
                        </div>
                        {/* Progress bar */}
                        <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden mb-1.5">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <div className="flex justify-between items-baseline">
                          <span className="text-[10px] text-gray-500">Remaining</span>
                          <span
                            className={`text-xs font-mono font-bold ${pct >= 90 ? 'text-red-400' : pct >= 70 ? 'text-amber-400' : 'text-emerald-400'}`}
                          >
                            {remaining.toLocaleString()}
                          </span>
                        </div>
                      </div>
                      {/* Per-type breakdown */}
                      <div className="space-y-1">
                        {[
                          { testid: 'token-meter-input', label: 'Input', val: tokenUsage?.input },
                          {
                            testid: 'token-meter-output',
                            label: 'Output',
                            val: tokenUsage?.output,
                          },
                          {
                            testid: 'token-meter-thinking',
                            label: 'Thinking',
                            val: tokenUsage?.thinking,
                          },
                        ].map(({ testid, label, val }) => (
                          <div
                            key={testid}
                            data-testid={testid}
                            className="flex justify-between items-center px-2 py-1 rounded bg-black/20 border border-[var(--g-outline)]"
                          >
                            <span className="text-[10px] text-gray-500">{label}</span>
                            <span className="text-[10px] font-mono text-gray-300">
                              {val != null ? val.toLocaleString() : '—'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                );
              })()}

              {/* Nielsen Heuristics */}
              {(status === 'converged' || nielsen.length > 0) && (
                <div>
                  <div className="h-px bg-[var(--g-outline)] my-4" />
                  <h4 className="text-[11px] uppercase tracking-wider font-semibold text-gray-500 mb-3">
                    Nielsen Heuristics
                  </h4>
                  {nielsen.length === 0 ? (
                    <p className="text-xs text-gray-600 italic">No heuristic data</p>
                  ) : (
                    <div className="space-y-1.5">
                      {nielsen.map((item) => (
                        <div
                          key={item.heuristic}
                          className="flex items-center gap-2 px-2 py-1.5 rounded bg-black/20 border border-[var(--g-outline)]"
                        >
                          <span
                            className={`shrink-0 w-2 h-2 rounded-full ${item.present ? 'bg-emerald-400' : 'bg-gray-600'}`}
                            aria-label={item.present ? 'present' : 'absent'}
                          />
                          <span className="text-[10px] text-gray-400 flex-1 truncate capitalize">
                            {item.heuristic.replace(/_/g, ' ')}
                          </span>
                          <span className="text-[10px] font-mono text-gray-500 shrink-0">
                            {item.votes}/3
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* AT-044 / ADR-0024: design-system panel. When the A2UI flag is ON
                  and the agent emitted a surface, render it via @a2ui/react;
                  otherwise (and on any A2UI render failure) the hand-built panel
                  is the default + fail-soft fallback. */}
              {convergedHtml && effectiveDesignSystem && (
                <>
                  {useA2uiPanel && a2uiPayload ? (
                    <div data-testid="studio-a2ui-section">
                      <div className="h-px bg-[var(--g-outline)] my-4" />
                      {/* Provenance only — the A2UI surface is self-describing
                          (it renders its own "Design System" title + token rows),
                          so the chrome adds just the Governed-A2UI badge. Design-
                          system colored (--g-info); indigo is off-system per
                          DESIGN_SYSTEM.md and must not be (re)introduced here. */}
                      <div className="mb-2 flex justify-end">
                        <span
                          className="rounded border border-[var(--g-info)]/30 bg-[var(--g-info)]/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-[var(--g-info)]"
                          title="Rendered from the agent-emitted A2UI surface (Governed A2UI)"
                        >
                          A2UI
                        </span>
                      </div>
                      <A2uiDesignSystemPanel
                        messages={a2uiPayload}
                        onRenderError={handleA2uiRenderError}
                      />
                    </div>
                  ) : (
                    <DesignSystemPanel
                      rows={designSystemRows}
                      controls={generatedControls}
                      scales={groupScales}
                      onEditToken={handleEditToken}
                      onScale={handleScaleGroup}
                    />
                  )}
                </>
              )}

              {/* AT-090: Competitor-contrast beat */}
              <AnimatePresence>
                {status === 'converged' && competitorBeatVisible && (
                  <div>
                    <div className="h-px bg-[var(--g-outline)] my-4" />
                    <CompetitorContrastBeat onDismiss={() => setCompetitorBeatVisible(false)} />
                  </div>
                )}
              </AnimatePresence>
            </div>
          </aside>

          {/* Bottom Drawer: Cloud Log Explorer */}
          <AnimatePresence>
            {isDrawerOpen && (
              <m.div
                initial={{ y: '100%' }}
                animate={{ y: 0 }}
                exit={{ y: '100%' }}
                transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
                className="absolute bottom-0 left-56 right-72 h-64 bg-[#1e1f22] border-t border-[var(--g-outline)] shadow-2xl flex flex-col z-30"
              >
                <div className="h-10 bg-[#2d2f31] flex items-center justify-between px-4 border-b border-[var(--g-outline)]">
                  <div className="flex items-center gap-2 text-xs text-gray-300 font-medium">
                    <Terminal size={14} className="text-blue-400" />
                    Cloud Log Explorer
                  </div>
                  <button
                    onClick={() => setIsDrawerOpen(false)}
                    className="p-1 hover:bg-black/20 rounded text-gray-400 hover:text-white transition-colors"
                    aria-label="Close log drawer"
                  >
                    <ChevronDown size={16} />
                  </button>
                </div>
                <div className="flex-1 p-4 overflow-y-auto font-mono text-[11px] space-y-1.5 bg-[#0f1013]">
                  {logs.length === 0 ? (
                    <p className="text-gray-600 italic">
                      No logs available. Start a generation run.
                    </p>
                  ) : (
                    logs.map((log) => (
                      <div key={log.id} className="flex gap-3">
                        <span className="text-gray-500 shrink-0">{log.time}</span>
                        <span
                          className={`shrink-0 w-12 ${log.level === 'SUCCESS' ? 'text-emerald-400' : log.level === 'ERROR' ? 'text-red-400' : log.level === 'WARN' ? 'text-amber-400' : 'text-blue-400'}`}
                        >
                          {log.level}
                        </span>
                        <span className="text-gray-300">{log.msg}</span>
                      </div>
                    ))
                  )}
                </div>
              </m.div>
            )}
          </AnimatePresence>

          {/* Drawer Toggle Handle */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20">
            {!isDrawerOpen && (
              <button
                onClick={() => setIsDrawerOpen(true)}
                className="bg-[var(--g-surface)] border border-[var(--g-outline)] shadow-lg rounded-full px-4 py-1.5 flex items-center gap-2 text-xs font-medium text-gray-400 hover:text-white transition-colors"
              >
                <Terminal size={14} /> View Logs <ChevronUp size={14} className="ml-1" />
              </button>
            )}
          </div>
        </div>
      </div>
    </LazyMotion>
  );
}
