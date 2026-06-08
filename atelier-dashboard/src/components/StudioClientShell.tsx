'use client';

import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { onIdTokenChanged } from 'firebase/auth';
import { auth } from '@/lib/firebase';
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
  WifiOff,
  Square,
  Settings,
  BookOpen,
  FileText,
  Shield,
  LifeBuoy,
  LogOut,
  Check,
  Copy,
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
  type PlanData,
  type SpecialistTraceData,
  type ResearchQueryData,
  type RouteDecisionData,
  type DreamingArtifactData,
  type StopData,
  type RunVerdict,
} from '@/lib/api';
import ApprovalCard from './ApprovalCard';
import TracePanel from './legibility/TracePanel';
import TopologyGraph from './legibility/TopologyGraph';
import OptimizeArtifactCard from './OptimizeArtifactCard';
import AttributionView from './legibility/AttributionView';
import StopButton from './legibility/StopButton';
import {
  subscribeSignoff,
  submitApproval,
  SIGNOFF_APPROVED,
  SIGNOFF_COMPLETED,
  type SignoffSnapshot,
} from '@/lib/approval-listener';
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
import { prettifyProjectName } from '@/lib/project-utils';

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

  useEffect(() => {
    if (!auth) return;
    const unsubscribe = onIdTokenChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        try {
          const token = await firebaseUser.getIdToken();
          const userStr = localStorage.getItem('user');
          if (userStr) {
            const userObj = JSON.parse(userStr) as UserSession;
            if (userObj.token !== token) {
              userObj.token = token;
              localStorage.setItem('user', JSON.stringify(userObj));
              setUser(userObj);
            }
          }
        } catch (err) {
          console.error('Failed to sync Firebase token:', err);
        }
      }
    });
    return () => unsubscribe();
  }, []);

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
 * AT-094 (R9): the one branded cap-stop string. Byte-identical to the backend
 * constant `atelier-core/src/atelier/orchestrator/governor.py::TOKEN_CAP_MESSAGE`
 * (PRD §13.2). The live API emits it as the `cap_reached` event `detail`; this
 * local copy is the fail-soft fallback when no server detail is present, so the
 * user always sees the exact branded stop — never a paraphrase. If the backend
 * constant changes, change this in lockstep (the two must not drift).
 */
const TOKEN_CAP_MESSAGE =
  "You've reached this account's usage limit. Contact administrator to continue.";

/**
 * AT-094 (R9): live offline detection. Returns `true` whenever the browser
 * reports no network connectivity (`navigator.onLine === false`). Subscribes to
 * the real `online`/`offline` window events so the shell re-renders on transition
 * — not a hard-coded toggle. SSR-safe: assumes online until the client mounts.
 */
function useOnlineStatus(): boolean {
  const [isOffline, setIsOffline] = React.useState(false);
  React.useEffect(() => {
    const sync = () => setIsOffline(!navigator.onLine);
    sync(); // reconcile against the actual state at mount
    window.addEventListener('online', sync);
    window.addEventListener('offline', sync);
    return () => {
      window.removeEventListener('online', sync);
      window.removeEventListener('offline', sync);
    };
  }, []);
  return isOffline;
}

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
        className="px-3 py-2 rounded bg-black/30 border border-[var(--g-info)]/30"
      >
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-[11px] text-[var(--g-info)] font-medium">{control.label}</span>
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
          className="w-full accent-[var(--g-primary-blue)]"
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
      className="px-3 py-2 rounded bg-black/30 border border-[var(--g-info)]/30"
    >
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-[11px] text-[var(--g-info)] font-medium">{control.label}</span>
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
        className="w-full accent-[var(--g-primary-blue)]"
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
        <Palette size={12} className="text-[var(--g-info)]" />
        Design System
        <span
          data-testid="ds-panel-count"
          className="ml-auto px-1.5 py-0.5 rounded text-[9px] bg-[var(--g-info)]/20 text-[var(--g-info)] font-mono border border-[var(--g-info)]/30"
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
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(false);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [isMobileOrTablet, setIsMobileOrTablet] = useState(false);
  const [isXl, setIsXl] = useState(false);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
    if (typeof window === 'undefined') return;
    const mediaLg = window.matchMedia('(max-width: 1023px)');
    const mediaXl = window.matchMedia('(max-width: 1279px)');

    const sync = () => {
      setIsMobileOrTablet(mediaLg.matches);
      setIsXl(mediaXl.matches);
    };

    sync();
    mediaLg.addEventListener('change', sync);
    mediaXl.addEventListener('change', sync);
    return () => {
      mediaLg.removeEventListener('change', sync);
      mediaXl.removeEventListener('change', sync);
    };
  }, []);
  const [temperature, setTemperature] = useState(0.4);
  const [topK, setTopK] = useState(40);
  const [maxTokens, setMaxTokens] = useState(4096);
  const { user, initRef } = useClientAuth();

  const [briefText, setBriefText] = useState('');

  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBriefText(params.get('brief') || '');
    }
  }, []);

  const projectTitle = useMemo(() => {
    return prettifyProjectName(briefText, id);
  }, [briefText, id]);

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getUserInitials = (): string => {
    if (!user?.displayName) return '?';
    return user.displayName
      .split(' ')
      .map((n) => n[0])
      .join('')
      .substring(0, 2)
      .toUpperCase();
  };

  const handleLogout = () => {
    localStorage.removeItem('user');
    router.push('/login');
  };

  const [selectedModel, setSelectedModel] = useState('gemini-2.5-pro');
  const iframeRef = useRef<HTMLIFrameElement>(null);

  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const modelParam = params.get('model');
      if (modelParam) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSelectedModel(modelParam);
      }
    }
  }, []);

  const [status, setStatus] = useState<
    | 'idle'
    | 'generating'
    | 'awaiting-signoff'
    | 'converged'
    | 'degraded'
    | 'error'
    | 'cap-reached'
    | 'stopped'
  >('idle');
  // AT-042: the locked pre-sign-off plan surfaced by the ApprovalCard. Captured
  // from the `plan` SSE event when it carries sign-off-relevant content (cited
  // defaults or the est-tokens/WCAG/specialist scope fields). Null until then.
  const [signoffPlan, setSignoffPlan] = useState<PlanData | null>(null);
  // AT-042: true while the APPROVED write to the run doc is in flight.
  const [signoffSubmitting, setSignoffSubmitting] = useState(false);
  // AT-042: teardown for the active Firestore onSnapshot subscription. The
  // subscription is the push-free resume mechanism — a cold clone observes the
  // APPROVED transition through it, with no FCM. Held in a ref so we can
  // unsubscribe on resume/unmount without re-subscribing on every render.
  const signoffUnsubRef = useRef<(() => void) | null>(null);
  // AT-094 (R9): live network status. Offline is a transient, self-acknowledged
  // degradation: it overrides the idle/empty canvas with a skeleton + banner,
  // but NEVER masks an in-flight run (would lose context) nor the fail-loud
  // cap-reached stop (the user must see the cap, not a transient offline notice).
  const isOffline = useOnlineStatus();
  const [logs, setLogs] = useState<{ id: number; time: string; level: string; msg: string }[]>([]);
  const [convergedHtml, setConvergedHtml] = useState<string>('');

  interface Layer {
    id: string;
    name: string;
  }

  const layers = useMemo<Layer[]>(() => {
    if (typeof window === 'undefined' || !convergedHtml) {
      return [];
    }
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(convergedHtml, 'text/html');
      const elements = doc.querySelectorAll('header, section, footer, [id]');
      const found: Layer[] = [];
      const seenIds = new Set<string>();

      elements.forEach((el, index) => {
        let id = el.getAttribute('id');
        let name = '';

        const tag = el.tagName.toLowerCase();
        if (tag === 'header') {
          name = 'Header Section';
        } else if (tag === 'footer') {
          name = 'Footer Section';
        } else {
          const classes = el.getAttribute('class') || '';
          if (classes.includes('hero')) name = 'Hero Section';
          else if (classes.includes('features')) name = 'Features Section';
          else if (classes.includes('testimonials')) name = 'Testimonials';
          else if (classes.includes('pricing')) name = 'Pricing Section';
          else if (classes.includes('contact')) name = 'Contact Section';
          else if (id) {
            name = id.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
          }
        }

        if (!name) {
          if (tag === 'section') {
            name = `Section ${found.filter((f) => f.name.startsWith('Section')).length + 1}`;
          } else {
            return;
          }
        }

        if (!id) {
          id = `section-layer-${index}`;
        }

        if (!seenIds.has(id)) {
          seenIds.add(id);
          found.push({ id, name });
        }
      });

      return found;
    } catch (e) {
      console.error('Failed to parse layers from HTML:', e);
      return [];
    }
  }, [convergedHtml]);

  const handleLayerClick = (layer: Layer, index: number) => {
    if (!iframeRef.current) return;
    try {
      const iframeDoc =
        iframeRef.current.contentDocument || iframeRef.current.contentWindow?.document;
      if (!iframeDoc) return;

      let targetEl = null;
      if (layer.id && !layer.id.startsWith('section-layer-')) {
        targetEl = iframeDoc.getElementById(layer.id);
      }
      if (!targetEl) {
        const elements = iframeDoc.querySelectorAll('header, section, footer, [id]');
        if (elements[index]) {
          targetEl = elements[index];
        }
      }

      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (e) {
      console.error('Failed to scroll to layer inside iframe:', e);
    }
  };

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
  // Multi-surface: planned surfaces from the plan SSE event, converged HTML per surface.
  const [plannedSurfaces, setPlannedSurfaces] = useState<string[]>([]);
  const [surfaces, setSurfaces] = useState<Record<string, string>>({});
  const [selectedSurface, setSelectedSurface] = useState<string | null>(null);
  // AT-096: live token meter — cumulative per-user counter (NOT reset on new run)
  const [tokenUsage, setTokenUsage] = useState<TokenDeltaData | null>(null);
  // AT-096: soft-warn dismissal — once dismissed, stays dismissed for the session
  const [softWarnDismissed, setSoftWarnDismissed] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  React.useEffect(() => {
    if (user?.uid && !tokenUsage) {
      try {
        const storedUsage = localStorage.getItem(`atelier_last_token_usage_${user.uid}`);
        if (storedUsage) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setTokenUsage(JSON.parse(storedUsage) as TokenDeltaData);
        }
      } catch (e) {
        console.error('Failed to load token usage from localStorage:', e);
      }
    }
  }, [isSettingsOpen, user?.uid, tokenUsage]);

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };
  // AT-026 (legibility): the live agent trace — one entry per DDLC specialist
  // hand-off and one per WRAI research query, accumulated from the SSE stream.
  const [specialistTraces, setSpecialistTraces] = useState<SpecialistTraceData[]>([]);
  const [researchQueries, setResearchQueries] = useState<ResearchQueryData[]>([]);
  // AT-027: read-only optimize assets surfaced from the run's SSE trace.
  const [routeDecision, setRouteDecision] = useState<RouteDecisionData | null>(null);
  const [dreamingArtifact, setDreamingArtifact] = useState<DreamingArtifactData | null>(null);
  // AT-026 (Post / Attribution): the run-oracle verdict from the complete event.
  const [runVerdict, setRunVerdict] = useState<RunVerdict | null>(null);
  // AT-026 (R13 interruption): the session id of THIS run (Stop control target),
  // captured from the plan/screen_start/complete events.
  const [sessionId, setSessionId] = useState<string | null>(null);
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
  const [isBeatDismissed, setIsBeatDismissed] = useState(false);
  // G3 a11y: a single SHELL-OWNED announcer. `a2uiAnnouncement` is written into a
  // persistent role="status" aria-live="polite" region mounted BEFORE the surface
  // (so SC 4.1.3 is satisfied — the region pre-exists the update). `a2uiPanelRef`
  // points at the A2UI panel wrapper so we can move focus to it on (re)mount.
  const [a2uiAnnouncement, setA2uiAnnouncement] = useState('');
  const a2uiPanelRef = useRef<HTMLDivElement>(null);
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
    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const time = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    setLogs((prev) => [...prev, { id: Date.now(), time, level, msg }]);
  };

  // AT-042: tear down any active sign-off subscription. Idempotent — safe to
  // call on resume, on a new run, and on unmount.
  const teardownSignoff = useCallback(() => {
    signoffUnsubRef.current?.();
    signoffUnsubRef.current = null;
  }, []);

  // AT-042: the run resumes the moment the run doc reaches APPROVED (or the
  // terminal COMPLETED). This is the push-free hook: a cold clone subscribed via
  // onSnapshot observes the transition with NO FCM and leaves the ApprovalCard,
  // dropping into the generating state the backend is already advancing.
  const handleSignoffSnapshot = useCallback(
    (snap: SignoffSnapshot | null) => {
      const next = snap?.signoff_status;
      if (next === SIGNOFF_APPROVED || next === SIGNOFF_COMPLETED) {
        teardownSignoff();
        setSignoffSubmitting(false);
        addLog('SUCCESS', `Sign-off ${next} — resuming generation.`);
        setStatus('generating');
        setIsRightSidebarOpen(true);
      }
    },
    [teardownSignoff]
  );

  // AT-042: subscribe to the run's sign-off doc. Always attached when a sign-off
  // plan is surfaced, so a status already-APPROVED on a cold clone resumes
  // immediately (onSnapshot fires with the current doc on attach).
  const watchSignoff = useCallback(
    (tenantId: string, runId: string) => {
      teardownSignoff();
      signoffUnsubRef.current = subscribeSignoff(
        tenantId,
        runId,
        handleSignoffSnapshot,
        (error) => {
          // Fail-soft: the agent acknowledges the degradation; the user can
          // still approve (the write path reports its own failure).
          addLog('WARN', `Sign-off subscription degraded: ${error.message}`);
        }
      );
    },
    [teardownSignoff, handleSignoffSnapshot]
  );

  // AT-042: approve the (possibly user-edited) plan. Writes APPROVED + the plan
  // of record to the run doc; the onSnapshot subscription then resumes the run.
  const handleApproveSignoff = useCallback(
    async (editedPlan: PlanData) => {
      if (!user || signoffSubmitting) return;
      setSignoffSubmitting(true);
      addLog('INFO', 'Submitting sign-off approval…');
      try {
        await submitApproval(user.tenant_id, id, user.uid, editedPlan);
        // The resume itself is driven by the onSnapshot subscription (push-free),
        // not by this write returning — keep submitting until the snapshot lands.
      } catch (error: unknown) {
        // Fail-soft: the approval did not land. Acknowledge it; do not silently
        // swallow, and do not falsely advance to generating.
        const message = error instanceof Error ? error.message : String(error);
        addLog('ERROR', `Sign-off approval failed: ${message}`);
        setSignoffSubmitting(false);
      }
    },
    [user, id, signoffSubmitting]
  );

  // AT-042: back out of sign-off without approving — return to the empty canvas.
  const handleRejectSignoff = useCallback(() => {
    teardownSignoff();
    setSignoffPlan(null);
    setSignoffSubmitting(false);
    addLog('INFO', 'Sign-off dismissed — generation not started.');
    setStatus('idle');
  }, [teardownSignoff]);

  // AT-042: release the subscription when the shell unmounts.
  React.useEffect(() => teardownSignoff, [teardownSignoff]);

  // ADR-0024 / P0.4: fail-soft latch for the A2UI panel. On a renderer failure
  // we acknowledge degradation (log) and flip to the hand-built panel — the
  // agent always acknowledges degradation; never a silent blank.
  const handleA2uiRenderError = (error: Error) => {
    setA2uiRenderFailed(true);
    addLog('WARN', `A2UI panel degraded — using hand-built panel: ${error.message}`);
    // G3 a11y: durable announcement of the fail-soft swap (the in-panel degraded
    // transient unmounts on fallback; the shell live region is the durable voice).
    setA2uiAnnouncement('Design system panel unavailable — showing the standard panel');
  };

  // G3 a11y: the A2UI surface materialized. Announce readiness once and move
  // focus to the Atelier-owned wrapper (NOT the catalog's markdown-rendered,
  // id-less heading). Fired from the panel post-mount, so the wrapper exists.
  const handleA2uiSurfaceReady = useCallback(() => {
    setA2uiAnnouncement('Design system panel ready');
    a2uiPanelRef.current?.focus();
  }, []);

  const handleZoom = (delta: number) => {
    setScale((s) => Math.max(0.2, Math.min(3, s + delta)));
  };

  const startGeneration = (overrideBrief?: string) => {
    if (status === 'generating' || status === 'cap-reached' || !user) return;
    // AT-094 (R9): fail-fast when offline — do not open a request that cannot
    // succeed. Acknowledge the degradation (log) and surface the offline state;
    // the `online` event will clear it back to a generatable canvas.
    if (!navigator.onLine) {
      addLog('WARN', 'Offline — generation deferred until the connection is restored.');
      return;
    }
    setStatus('generating');
    setIsRightSidebarOpen(true);
    setLogs([]);
    // AT-042: reset any prior sign-off state for the new run.
    teardownSignoff();
    setSignoffPlan(null);
    setSignoffSubmitting(false);
    setIterationScores([]); // AT-093: reset per-iteration scorecard on each new run
    setPlannedSurfaces([]);
    setSurfaces({});
    setSelectedSurface(null);
    // AT-026: reset the legibility trace + attribution + stop target for the new run
    setSpecialistTraces([]);
    setResearchQueries([]);
    setRouteDecision(null);
    setDreamingArtifact(null);
    setRunVerdict(null);
    setSessionId(null);
    // AT-044: reset the design-system panel for the new run
    setBaseDesignSystem(null);
    setTokenEdits({});
    setGroupScales({});
    // ADR-0024 / P0.4: reset the A2UI surface + fail-soft latch for the new run
    setA2uiPayload(null);
    setA2uiRenderFailed(false);
    setIsBeatDismissed(false);
    // G3 a11y: clear the live region so the next surface-ready re-announces.
    setA2uiAnnouncement('');
    addLog('INFO', 'Initiating Vertex AI Convergence Loop...');

    let brief = overrideBrief;
    if (!brief) {
      const searchParams = new URLSearchParams(window.location.search);
      brief = searchParams.get('brief') || 'SaaS landing page';
      const deviceParam = searchParams.get('device');
      if (deviceParam === 'app' || deviceParam === 'web') {
        brief = `${brief} [Device Platform: ${deviceParam}]`;
      }
    }

    const callbacks: StreamCallbacks = {
      onPlan: (data) => {
        addLog('INFO', `Plan received: ${data.surfaces?.join(', ') || 'N/A'}`);
        if (data.surfaces && data.surfaces.length > 0) {
          setPlannedSurfaces(data.surfaces);
          setSelectedSurface(data.surfaces[0]);
        }
        // AT-026: capture the run id so the Stop control can address THIS run.
        if (data.session_id) setSessionId(data.session_id);
        // AT-042: a plan that carries sign-off-relevant scope (cited defaults or
        // the est-tokens/WCAG/specialist fields) HALTS for human sign-off before
        // any screen generation. A legacy minimal plan (surfaces only) keeps the
        // old straight-through behaviour, so existing flows are unchanged.
        const isSignoffPlan =
          (data.proposed_defaults != null && data.proposed_defaults.length > 0) ||
          data.est_tokens != null ||
          data.wcag_target != null ||
          data.specialist_count != null;
        if (isSignoffPlan && user) {
          setSignoffPlan(data);
          setStatus('awaiting-signoff');
          // Subscribe to the run doc: if a cold clone finds it already APPROVED,
          // onSnapshot fires on attach and resumes without showing the card.
          watchSignoff(user.tenant_id, id);
          addLog('INFO', 'Plan locked — awaiting human sign-off.');
        }
      },
      onScreenStart: (data) => {
        addLog('INFO', `Generating screen: ${data.screen}`);
        // AT-026: the screen_start event also carries the session id (the Stop
        // target) — capture it in case the plan event was minimal.
        if (data.session_id) setSessionId(data.session_id);
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
        setSurfaces((prev) => ({ ...prev, [data.screen]: data.html }));
        setSelectedSurface((prev) => {
          if (!prev || prev === data.screen) {
            setConvergedHtml(data.html);
            return data.screen;
          }
          return prev;
        });
      },
      onComplete: (data) => {
        if (data.best_html) setConvergedHtml(data.best_html);
        if (data.dorav) setDorav(data.dorav);
        if (data.nielsen) setNielsen(data.nielsen);
        // AT-026 (Post): the run-oracle verdict (criterion -> verdict + evidence).
        if (data.run_verdict !== undefined) setRunVerdict(data.run_verdict ?? null);
        if (data.session_id) setSessionId(data.session_id);
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
        // AT-094 (R9): prefer the server's branded stop, else the SPEC-EXACT
        // constant (PRD §13.2). Never a paraphrase — the cap message is one of
        // the few user-facing strings the spec pins byte-for-byte.
        const detail = data.detail || TOKEN_CAP_MESSAGE;
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
        if (user?.uid) {
          try {
            localStorage.setItem(`atelier_last_token_usage_${user.uid}`, JSON.stringify(data));
          } catch (e) {
            console.error('Failed to save token usage to localStorage:', e);
          }
        }
      },
      // AT-026 (Mid): append each DDLC specialist hand-off to the live trace.
      onSpecialistTrace: (data: SpecialistTraceData) => {
        setSpecialistTraces((prev) => [...prev, data]);
        addLog('INFO', `Specialist ${data.role}: ${data.summary}`);
      },
      // AT-026 (Mid): append each WRAI research query to the live trace.
      onResearchQuery: (data: ResearchQueryData) => {
        setResearchQueries((prev) => [...prev, data]);
        addLog('INFO', `Research: ${data.query}`);
      },
      // AT-027: surface the run's read-only MoE routing decision.
      onRouteDecision: (data: RouteDecisionData) => {
        setRouteDecision(data);
        addLog('INFO', `Route: ${data.expert} (${data.routing_mode})`);
      },
      // AT-027: surface a read-only dreaming/DPO artifact for the run.
      onDreamingArtifact: (data: DreamingArtifactData) => {
        setDreamingArtifact(data);
        addLog('INFO', `DPO pair: margin ${data.margin.toFixed(2)}`);
      },
      // AT-026 (R13): the run halted at the user's request — acknowledge + flip
      // to the stopped state (the agent always acknowledges the interruption).
      onStop: (data: StopData) => {
        if (data.session_id) setSessionId(data.session_id);
        addLog('WARN', `Stopped at iteration ${data.iteration + 1} — checkpoint saved.`);
        setStatus('stopped');
      },
    };

    const executeGeneration = (tokenToUse: string | null) => {
      runGenerationStream(brief, tokenToUse, callbacks, {
        model: selectedModel,
        temperature,
        top_k: topK,
        max_tokens: maxTokens,
      });
    };

    if (auth && auth.currentUser) {
      auth.currentUser
        .getIdToken(true)
        .then((newToken) => {
          const userStr = localStorage.getItem('user');
          if (userStr) {
            const userObj = JSON.parse(userStr) as UserSession;
            userObj.token = newToken;
            localStorage.setItem('user', JSON.stringify(userObj));
            user.token = newToken;
          }
          executeGeneration(newToken);
        })
        .catch((err) => {
          console.error('Failed to force refresh token, using current token:', err);
          executeGeneration(user.token);
        });
    } else {
      executeGeneration(user.token);
    }
  };

  const handleSteerSignoff = useCallback(
    (steeringText: string) => {
      if (!user) return;
      teardownSignoff();
      setSignoffPlan(null);
      setSignoffSubmitting(false);

      const searchParams = new URLSearchParams(window.location.search);
      let baseBrief = searchParams.get('brief') || 'SaaS landing page';
      const deviceParam = searchParams.get('device');
      if (deviceParam === 'app' || deviceParam === 'web') {
        baseBrief = `${baseBrief} [Device Platform: ${deviceParam}]`;
      }

      const augmentedBrief = `${baseBrief}\n\n[Human Steering Context]:\n${steeringText}`;
      addLog('INFO', 'Applying interactive chat steering & restarting Convergence Loop...');
      startGeneration(augmentedBrief);
    },
    [user, teardownSignoff, startGeneration]
  );

  const renderLeftSidebarContent = () => (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-[var(--g-outline)] flex items-center justify-between lg:justify-start gap-2">
        <div className="flex items-center gap-2">
          <Layout size={14} className="text-gray-400" />
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
            Layers
          </span>
        </div>
        <button
          onClick={() => setIsLeftSidebarOpen(false)}
          className="lg:hidden p-1 hover:bg-white/10 rounded text-gray-400 hover:text-white transition-colors"
          aria-label="Close layers panel"
        >
          <X size={14} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {layers.map((layer, i) => (
          <div
            key={i}
            onClick={() => {
              handleLayerClick(layer, i);
              setIsLeftSidebarOpen(false);
            }}
            className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--g-surface-hover)] text-xs text-gray-400 cursor-pointer group transition-colors"
          >
            <Box
              size={14}
              className="text-gray-500 group-hover:text-[var(--g-info)] transition-colors"
            />
            <span className="truncate">{layer.name}</span>
          </div>
        ))}
        {layers.length === 0 && (
          <div className="p-3 text-xs text-gray-500 italic text-center">No layers generated</div>
        )}
      </div>
    </div>
  );

  const renderRightSidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* G3 a11y: persistent, single live region for A2UI state. Mounted
          UNCONDITIONALLY and BEFORE the A2UI surface so per SC 4.1.3 the
          region pre-exists the update (the renderer injects container +
          content together and has no aria-live of its own). Tailwind's
          built-in `sr-only` keeps it visually hidden but screen-reader
          reachable. Do NOT mount a second live region — double-announce. */}
      <div data-testid="a2ui-live-region" role="status" aria-live="polite" className="sr-only">
        {a2uiAnnouncement}
      </div>
      <div className="p-4 border-b border-[var(--g-outline)] flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SlidersHorizontal size={16} className="text-[var(--g-info)]" />
          <span className="text-sm font-semibold text-white">Vertex AI Settings</span>
        </div>
        <button
          onClick={() => setIsRightSidebarOpen(false)}
          className="xl:hidden p-1 hover:bg-white/10 rounded text-gray-400 hover:text-white transition-colors"
          aria-label="Close settings panel"
        >
          <X size={16} />
        </button>
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
              className="w-full accent-[var(--g-primary-blue)]"
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
              className="w-full accent-[var(--g-primary-blue)]"
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
              className="w-full accent-[var(--g-primary-blue)]"
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
              <span className="ml-2 px-1.5 py-0.5 rounded text-[9px] bg-[var(--g-info)]/20 text-[var(--g-info)] font-mono border border-[var(--g-info)]/30 align-middle">
                iter {currentIteration + 1}
              </span>
            )}
          </h4>
          {/* Composite headline */}
          <div className="bg-black/40 p-3 rounded border border-[var(--g-info)]/30 flex justify-between items-center mb-3">
            <span className="text-xs text-gray-300 font-semibold">Composite</span>
            <span
              className={`text-sm font-mono font-bold ${liveDorav?.composite != null ? 'text-[var(--g-info)]' : 'text-gray-600'}`}
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

        {/* AT-026 (Mid legibility): live agent trace — specialist hand-offs +
            research queries + D-O-R-A-V tooltips. Shown while generating and
            whenever any trace has arrived (so it persists after convergence). */}
        {(status === 'generating' || specialistTraces.length > 0 || researchQueries.length > 0) && (
          <>
            <TopologyGraph
              specialistTraces={specialistTraces}
              error={status === 'error' ? 'Pipeline error' : null}
            />
            <TracePanel specialistTraces={specialistTraces} researchQueries={researchQueries} />
          </>
        )}

        {/* AT-027 (Optimize surfacing): read-only MoE routing decision +
            dreaming/DPO artifact for the run. Shown whenever either asset
            has arrived; the card itself returns null if both are empty. */}
        {(routeDecision || dreamingArtifact) && (
          <OptimizeArtifactCard routeDecision={routeDecision} dreamingArtifact={dreamingArtifact} />
        )}

        {/* AT-026 (Post / Attribution): the run-oracle verdict — every
            acceptance criterion -> verdict + evidence. Shown on a terminal
            outcome (converged / degraded / stopped) once a run has produced a
            verdict; "Amend & regenerate" re-enters the loop. */}
        {(status === 'converged' || status === 'degraded' || status === 'stopped') &&
          (runVerdict !== null || convergedHtml) && (
            <AttributionView runVerdict={runVerdict} onAmend={startGeneration} />
          )}

        {/* AT-096: Live Token Meter */}
        <div className="h-px bg-[var(--g-outline)] my-4" />
        {(() => {
          const cumulative = tokenUsage?.cumulative_user_tokens ?? 0;
          const pct = Math.min(100, (cumulative / TOKEN_CAP) * 100);
          const remaining = TOKEN_CAP - cumulative;
          const barColor = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500';
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
                    <span>You&apos;re approaching this account&apos;s usage limit (90%).</span>
                    <button
                      onClick={() => setSoftWarnDismissed(true)}
                      className="shrink-0 p-0.5 rounded hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
                      aria-label="Dismiss token warning"
                    >
                      <X size={12} />
                    </button>
                  </div>
                )}
              <div data-testid="token-meter" data-cumulative={cumulative} data-cap={TOKEN_CAP}>
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

        {/* AT-044 / ADR-0024: design-system panel */}
        {convergedHtml && effectiveDesignSystem && (
          <>
            {useA2uiPanel && a2uiPayload ? (
              <div data-testid="studio-a2ui-section" aria-busy={status === 'generating'}>
                <div className="h-px bg-[var(--g-outline)] my-4" />
                <div className="mb-2 flex justify-end">
                  <span
                    className="rounded border border-[var(--g-info)]/30 bg-[var(--g-info)]/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-[var(--g-info)]"
                    title="Rendered from the agent-emitted A2UI surface (Governed A2UI)"
                  >
                    A2UI
                  </span>
                </div>
                <A2uiDesignSystemPanel
                  ref={a2uiPanelRef}
                  messages={a2uiPayload}
                  onRenderError={handleA2uiRenderError}
                  onSurfaceReady={handleA2uiSurfaceReady}
                  isStreaming={status === 'generating'}
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

        {/* Why Atelier (AT-090 competitor beat) */}
        {status === 'converged' && !isBeatDismissed && (
          <div>
            <div className="h-px bg-[var(--g-outline)] my-4" />
            <div
              data-testid="competitor-contrast-beat"
              className="p-4 rounded-md border border-[var(--g-outline)] bg-[var(--g-surface-hover)] relative"
            >
              <button
                data-testid="competitor-contrast-dismiss"
                onClick={() => setIsBeatDismissed(true)}
                className="absolute top-2 right-2 p-1 rounded hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
                aria-label="Dismiss competitor beat"
              >
                <X size={14} />
              </button>
              <h4 className="text-[11px] uppercase tracking-wider font-semibold text-[var(--g-info)] mb-2">
                Why Atelier
              </h4>
              <p className="text-xs text-gray-300 leading-relaxed pr-4">
                Atelier enforces an absolute deterministic structure gate (reject+halt on skeletons)
                before the LLM judge evaluates the design. While competitors apply brand consistency
                probabilistically, Atelier guarantees it.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  if (!user) return <div ref={initRef} />;

  // AT-094 (R9): the offline acknowledgement owns the canvas ONLY when there is
  // no usable on-screen content to protect — i.e. the idle/empty canvas or a
  // pipeline error. It deliberately does NOT replace already-produced output
  // (`converged`/`degraded`): that iframe is a static, network-independent
  // srcDoc, so a transient network blip must not destroy completed work. It also
  // yields to an in-flight `generating` run and the fail-loud `cap-reached` stop.
  const showOffline = isOffline && (status === 'idle' || status === 'error');

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
            <button
              onClick={() => setIsLeftSidebarOpen(!isLeftSidebarOpen)}
              className="lg:hidden p-1.5 hover:bg-[var(--g-surface-hover)] rounded-md transition-colors text-gray-400 hover:text-white"
              aria-label="Toggle layers panel"
            >
              <Layout size={18} />
            </button>
            <div className="flex items-center gap-2 max-w-[120px] sm:max-w-none">
              <span className="font-semibold text-[13px] text-white tracking-wide truncate">
                {projectTitle}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--g-info)]/20 text-[var(--g-info)] font-mono border border-[var(--g-info)]/30 shrink-0">
                v1.0
              </span>
            </div>
          </div>

          {plannedSurfaces.length > 0 && (
            <div className="flex items-center gap-1 bg-black/40 p-1 rounded-md border border-[var(--g-outline)] max-w-[200px] sm:max-w-none overflow-x-auto">
              {plannedSurfaces.map((surf) => {
                const isAvailable = !!surfaces[surf];
                const isSelected = selectedSurface === surf;
                return (
                  <button
                    key={surf}
                    onClick={() => {
                      if (isAvailable) {
                        setSelectedSurface(surf);
                        setConvergedHtml(surfaces[surf]);
                      }
                    }}
                    disabled={!isAvailable}
                    title={isAvailable ? surf : `${surf} — generating…`}
                    className={`px-3 py-1 rounded text-xs font-medium transition-colors shrink-0 ${
                      isSelected
                        ? 'bg-[var(--g-outline)] text-white shadow-sm'
                        : isAvailable
                          ? 'text-gray-400 hover:text-white cursor-pointer'
                          : 'text-gray-600 cursor-default'
                    }`}
                  >
                    {surf}
                    {!isAvailable && status === 'generating' && (
                      <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-gray-600 animate-pulse align-middle" />
                    )}
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex items-center gap-3">
            <div className="relative flex items-center">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="appearance-none bg-black/20 border border-[var(--g-outline)] rounded-md px-3 py-1.5 pr-8 text-xs text-white font-medium focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)] cursor-pointer"
                aria-label="Select Model"
              >
                <option value="gemini-2.5-pro" className="bg-[#1e1f22] text-white">
                  Gemini 2.5 Pro
                </option>
                <option value="gemini-2.5-flash" className="bg-[#1e1f22] text-white">
                  Gemini 2.5 Flash
                </option>
              </select>
              <ChevronDown
                size={12}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
              />
            </div>
            {/* AT-026 (R13): the user Stop control — only while a run is in flight. */}
            {status === 'generating' && (
              <StopButton
                sessionId={sessionId}
                token={user.token}
                stopped={false}
                onStopRequested={() =>
                  addLog('INFO', 'Stop requested — halting at next iteration…')
                }
                onStopFailed={(msg) => addLog('ERROR', `Stop failed: ${msg}`)}
              />
            )}
            <button
              onClick={() => startGeneration()}
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

            {/* Settings Toggle Button on mobile */}
            <button
              onClick={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
              className="xl:hidden p-1.5 hover:bg-[var(--g-surface-hover)] rounded-md transition-colors text-gray-400 hover:text-white"
              aria-label="Toggle settings panel"
            >
              <SlidersHorizontal size={18} />
            </button>

            {/* Avatar Dropdown */}
            {user && (
              <div className="relative ml-2" ref={menuRef}>
                <button
                  onClick={() => setIsMenuOpen(!isMenuOpen)}
                  className="w-7 h-7 rounded-full bg-[var(--g-primary-blue)] flex items-center justify-center text-[10px] font-bold text-white cursor-pointer hover:bg-[var(--g-primary-blue-hover)] transition-colors shadow-sm focus:outline-none focus:ring-1 focus:ring-[var(--g-primary-blue)]"
                  title={user.email}
                  aria-haspopup="true"
                  aria-expanded={isMenuOpen}
                >
                  {getUserInitials()}
                </button>

                {isMenuOpen && (
                  <div className="absolute right-0 mt-2 w-60 bg-[var(--g-surface)]/95 border border-[var(--g-outline)] rounded-lg shadow-2xl backdrop-blur-md p-2 z-50 animate-in fade-in slide-in-from-top-1 duration-200">
                    <div className="px-3 py-1.5 border-b border-[var(--g-outline)] mb-1">
                      <p className="text-xs font-medium text-white truncate">{user.displayName}</p>
                      <p className="text-[10px] text-[var(--g-text-muted)] truncate">
                        {user.email}
                      </p>
                    </div>

                    <div className="space-y-0.5">
                      <button
                        onClick={() => {
                          setIsSettingsOpen(true);
                          setIsMenuOpen(false);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-gray-200 hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors"
                      >
                        <Settings size={12} className="text-[var(--g-text-muted)]" />
                        Account Settings
                      </button>
                      <a
                        href="https://atelier.autonomous-agent.dev/docs"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-gray-200 hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors"
                      >
                        <BookOpen size={12} className="text-[var(--g-text-muted)]" />
                        Documentation
                      </a>
                      <a
                        href="/terms"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-gray-200 hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors"
                      >
                        <FileText size={12} className="text-[var(--g-text-muted)]" />
                        Terms of Service
                      </a>
                      <a
                        href="/privacy"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-gray-200 hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors"
                      >
                        <Shield size={12} className="text-[var(--g-text-muted)]" />
                        Privacy Policy
                      </a>
                      <a
                        href="mailto:support@atelier.autonomous-agent.dev"
                        className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-gray-200 hover:bg-[var(--g-surface-hover)] hover:text-white transition-colors"
                      >
                        <LifeBuoy size={12} className="text-[var(--g-text-muted)]" />
                        Help &amp; Support
                      </a>
                    </div>

                    <div className="h-px bg-[var(--g-outline)] my-1" />

                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2 px-3 py-1.5 rounded text-left text-xs text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors"
                    >
                      <LogOut size={12} />
                      Logout
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </header>

        <div className="flex-1 flex overflow-hidden relative">
          {/* Desktop Left Block Drawer */}
          {(!mounted || !isMobileOrTablet) && (
            <aside className="hidden lg:flex w-56 border-r border-[var(--g-outline)] bg-[var(--g-surface)]/50 backdrop-blur-md flex-col z-10 shrink-0">
              {renderLeftSidebarContent()}
            </aside>
          )}

          {/* Mobile Left Sidebar Drawer */}
          <AnimatePresence>
            {mounted && isMobileOrTablet && isLeftSidebarOpen && (
              <div className="fixed inset-0 z-40 lg:hidden flex">
                {/* Backdrop */}
                <m.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={() => setIsLeftSidebarOpen(false)}
                  className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
                />
                {/* Sidebar Content */}
                <m.aside
                  initial={{ x: -224 }}
                  animate={{ x: 0 }}
                  exit={{ x: -224 }}
                  transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                  className="relative w-56 bg-[var(--g-bg)] border-r border-[var(--g-outline)] h-full flex flex-col z-50"
                >
                  {renderLeftSidebarContent()}
                </m.aside>
              </div>
            )}
          </AnimatePresence>

          {/* Center Canvas */}
          <main className="flex-1 relative flex items-center justify-center overflow-auto">
            {/* Canvas Toolbar */}
            <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-1 bg-[var(--g-surface)]/80 backdrop-blur-md p-1 rounded-lg border border-[var(--g-outline)] shadow-lg z-20">
              <button
                data-testid="device-390"
                aria-label="Mobile 390px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 390 ? 'bg-[var(--g-info)]/30 text-[var(--g-info)]' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(390)}
              >
                <Smartphone size={16} />
              </button>
              <button
                data-testid="device-768"
                aria-label="Tablet 768px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 768 ? 'bg-[var(--g-info)]/30 text-[var(--g-info)]' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
                onClick={() => setDeviceWidth(768)}
              >
                <Tablet size={16} />
              </button>
              <button
                data-testid="device-1280"
                aria-label="Desktop 1280px"
                className={`p-1.5 rounded transition-colors ${deviceWidth === 1280 ? 'bg-[var(--g-info)]/30 text-[var(--g-info)]' : 'hover:bg-[var(--g-surface-hover)] text-gray-400 hover:text-white'}`}
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
              {/* Offline state (AT-094 / R9) — skeleton + acknowledgement banner. */}
              {showOffline && (
                <div data-testid="state-offline" className="w-full h-full relative bg-gray-50">
                  {/* Skeleton: muted placeholder blocks pulse under the banner so the
                      surface reads as "waiting for connection", not broken/empty. */}
                  <div
                    aria-hidden="true"
                    className="absolute inset-0 flex flex-col gap-4 px-8 pt-24 pb-8 motion-safe:animate-pulse"
                  >
                    <div className="h-7 w-2/5 rounded bg-gray-200" />
                    <div className="h-40 w-full rounded-lg bg-gray-200" />
                    <div className="grid grid-cols-3 gap-3">
                      <div className="h-24 rounded-lg bg-gray-200" />
                      <div className="h-24 rounded-lg bg-gray-200" />
                      <div className="h-24 rounded-lg bg-gray-200" />
                    </div>
                    <div className="h-4 w-3/4 rounded bg-gray-200" />
                    <div className="h-4 w-1/2 rounded bg-gray-200" />
                  </div>
                  {/* Acknowledgement banner — the agent always acknowledges degradation
                      (PRD §21 trichotomy). Offline is transient/self-healing: announced
                      politely, clears automatically when the connection returns. */}
                  <div
                    role="status"
                    aria-live="polite"
                    className="absolute top-0 left-0 right-0 flex items-start gap-3 bg-slate-100 border-b-2 border-slate-400 px-4 py-3"
                  >
                    <WifiOff
                      size={20}
                      className="text-slate-600 mt-0.5 shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <h2 className="text-sm font-semibold text-slate-800">
                        No connection &mdash; waiting to reconnect
                      </h2>
                      <p className="text-xs text-slate-600 mt-0.5">
                        Your connection was lost. Generation is paused; it resumes automatically
                        once you&apos;re back online.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {status === 'idle' && !showOffline && (
                <div
                  data-testid="state-empty"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <MousePointer2 size={40} className="text-[var(--g-info)]" aria-hidden="true" />
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

              {/* ── Awaiting sign-off (AT-042) — ApprovalCard, push-free resume ── */}
              {status === 'awaiting-signoff' && signoffPlan && (
                <ApprovalCard
                  plan={signoffPlan}
                  onApprove={handleApproveSignoff}
                  onReject={handleRejectSignoff}
                  isSubmitting={signoffSubmitting}
                  onSteer={handleSteerSignoff}
                />
              )}

              {/* ──────────────── Loading (generating) state ────────────────────────────── */}
              {status === 'generating' && (
                <div
                  data-testid="state-loading"
                  role="status"
                  aria-live="polite"
                  aria-label="Generating design \u2014 please wait"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4"
                >
                  <Loader2
                    size={40}
                    className="text-[var(--g-info)] animate-spin"
                    aria-hidden="true"
                  />
                  <h2 className="text-lg font-semibold text-gray-700">Generating…</h2>
                  <p className="text-sm text-gray-600">
                    Vertex AI Convergence Loop is running. This may take a moment.
                  </p>
                </div>
              )}

              {/* ── Converged state — render iframe ──────────────────── */}
              {status === 'converged' && convergedHtml && (
                <iframe
                  ref={iframeRef}
                  sandbox="allow-scripts allow-same-origin"
                  srcDoc={effectiveSrcDoc}
                  title="Converged design output"
                  className="w-full h-full border-0"
                />
              )}

              {/* ── Degraded state — show output + degradation banner ── */}
              {status === 'degraded' && (
                <div data-testid="state-degraded" className="w-full h-full relative">
                  {/* Still render the best available output behind the banner */}
                  {convergedHtml && (
                    <iframe
                      ref={iframeRef}
                      sandbox="allow-scripts allow-same-origin"
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
              {status === 'error' && !showOffline && (
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
                    onClick={() => startGeneration()}
                    className="mt-2 flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Retry generation
                  </button>
                </div>
              )}

              {/* \u2500\u2500 Cap-reached state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */}
              {status === 'stopped' && (
                <div
                  data-testid="state-stopped"
                  role="status"
                  aria-live="polite"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <Square size={40} className="text-red-400 fill-current" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-gray-700">Generation stopped</h2>
                  <p className="text-sm text-gray-600 text-center max-w-xs">
                    You stopped this run. Progress was checkpointed before the next model call
                    &mdash; no further tokens were spent. Run again to start a fresh design.
                  </p>
                  <button
                    onClick={() => startGeneration()}
                    className="mt-2 flex items-center gap-2 bg-[var(--g-primary-blue)] hover:bg-[var(--g-primary-blue-hover)] text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Run again
                  </button>
                </div>
              )}

              {status === 'cap-reached' && (
                <div
                  data-testid="state-cap-reached"
                  role="alert"
                  className="w-full h-full flex flex-col items-center justify-center bg-gray-50 gap-4 px-8"
                >
                  <ZapOff size={40} className="text-orange-400" aria-hidden="true" />
                  <h2 className="text-lg font-semibold text-orange-700">Token cap reached</h2>
                  {/* AT-094 (R9): the SPEC-EXACT stop string (PRD §13.2). The live
                      backend sends it as `capReachedDetail`; the constant is the
                      byte-identical fail-soft fallback — never a paraphrase. */}
                  <p className="text-sm text-gray-600 text-center max-w-xs">
                    {capReachedDetail || TOKEN_CAP_MESSAGE}
                  </p>
                </div>
              )}
            </m.div>
          </main>

          {/* Desktop Right Vertex AI Config Panel */}
          {(!mounted || !isXl) && (
            <aside className="hidden xl:flex w-72 border-l border-[var(--g-outline)] bg-[var(--g-surface)]/50 backdrop-blur-md flex-col z-10 shrink-0">
              {renderRightSidebarContent()}
            </aside>
          )}

          {/* Mobile Right Sidebar Drawer */}
          <AnimatePresence>
            {mounted && isXl && isRightSidebarOpen && (
              <div className="fixed inset-0 z-40 xl:hidden flex justify-end">
                {/* Backdrop */}
                <m.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={() => setIsRightSidebarOpen(false)}
                  className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
                />
                {/* Sidebar Content */}
                <m.aside
                  initial={{ x: 288 }}
                  animate={{ x: 0 }}
                  exit={{ x: 288 }}
                  transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                  className="relative w-72 bg-[var(--g-bg)] border-l border-[var(--g-outline)] h-full flex flex-col z-50"
                >
                  {renderRightSidebarContent()}
                </m.aside>
              </div>
            )}
          </AnimatePresence>

          {/* Bottom Drawer: Cloud Log Explorer */}
          <AnimatePresence>
            {isDrawerOpen && (
              <m.div
                initial={{ y: '100%' }}
                animate={{ y: 0 }}
                exit={{ y: '100%' }}
                transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
                className="absolute bottom-0 left-0 lg:left-56 right-0 xl:right-72 h-64 bg-[#1e1f22] border-t border-[var(--g-outline)] shadow-2xl flex flex-col z-30"
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

      {/* Account Settings Modal */}
      <AnimatePresence>
        {isSettingsOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <m.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsSettingsOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-md"
            />

            {/* Modal Content */}
            <m.div
              initial={{ scale: 0.95, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              transition={{ type: 'spring', duration: 0.4 }}
              className="relative w-full max-w-2xl bg-[#131416]/95 border border-[var(--g-outline)] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--g-outline)] bg-black/20 text-left">
                <div className="flex items-center gap-2">
                  <Settings size={16} className="text-[var(--g-primary-blue)]" />
                  <h2 className="text-sm font-semibold text-white">Account Settings</h2>
                </div>
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="text-gray-400 hover:text-white p-1 rounded-md hover:bg-white/5 transition-colors cursor-pointer"
                  aria-label="Close settings"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6 text-left">
                {/* User Profile Info */}
                <div className="bg-black/20 rounded-lg border border-[var(--g-outline)] p-4 space-y-3">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    User Profile
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <label className="text-gray-500 block mb-0.5">Display Name</label>
                      <div className="font-medium text-white">{user?.displayName || '—'}</div>
                    </div>
                    <div>
                      <label className="text-gray-500 block mb-0.5">Email Address</label>
                      <div className="font-medium text-white">{user?.email || '—'}</div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-[var(--g-outline)]/50 space-y-2 text-xs">
                    <div className="flex justify-between items-center">
                      <div>
                        <label className="text-gray-500 block mb-0.5">User ID (UID)</label>
                        <div className="font-mono text-gray-300 select-all truncate max-w-[280px] md:max-w-[400px]">
                          {user?.uid || '—'}
                        </div>
                      </div>
                      {user?.uid && (
                        <button
                          onClick={() => handleCopy(user.uid, 'uid')}
                          className="shrink-0 p-1.5 rounded hover:bg-white/5 text-gray-400 hover:text-white transition-colors cursor-pointer"
                          title="Copy UID"
                        >
                          {copiedField === 'uid' ? (
                            <Check size={14} className="text-emerald-400" />
                          ) : (
                            <Copy size={14} />
                          )}
                        </button>
                      )}
                    </div>

                    <div className="flex justify-between items-center pt-2 border-t border-[var(--g-outline)]/50">
                      <div>
                        <label className="text-gray-500 block mb-0.5">Tenant ID</label>
                        <div className="font-mono text-gray-300 select-all truncate max-w-[280px] md:max-w-[400px]">
                          {user?.tenant_id || '—'}
                        </div>
                      </div>
                      {user?.tenant_id && (
                        <button
                          onClick={() => handleCopy(user.tenant_id, 'tenant')}
                          className="shrink-0 p-1.5 rounded hover:bg-white/5 text-gray-400 hover:text-white transition-colors cursor-pointer"
                          title="Copy Tenant ID"
                        >
                          {copiedField === 'tenant' ? (
                            <Check size={14} className="text-emerald-400" />
                          ) : (
                            <Copy size={14} />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* GCP & Platform Config */}
                <div className="bg-black/20 rounded-lg border border-[var(--g-outline)] p-4 space-y-3">
                  <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                    Workspace &amp; GCP Environment
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="flex items-center justify-between pr-2">
                      <div>
                        <label className="text-gray-500 block mb-0.5">GCP Project</label>
                        <span className="font-mono text-gray-200">atelier-build-2026</span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Connected
                      </span>
                    </div>
                    <div>
                      <label className="text-gray-500 block mb-0.5">Active Billing Tier</label>
                      <div className="font-medium text-white flex items-center gap-1.5">
                        <span>Enterprise AI Developer (Self-Serve)</span>
                      </div>
                    </div>
                    <div>
                      <label className="text-gray-500 block mb-0.5">Base API URL</label>
                      <span className="font-mono text-gray-300 truncate block max-w-[280px]">
                        https://atelier-dashboard-537337457799.us-central1.run.app/
                      </span>
                    </div>
                    <div>
                      <label className="text-gray-500 block mb-0.5">Platform Status</label>
                      <span className="text-emerald-400 font-medium">All Services Operational</span>
                    </div>
                  </div>
                </div>

                {/* Token Allocation & Usage */}
                <div className="bg-black/20 rounded-lg border border-[var(--g-outline)] p-4 space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                      Token Allocation &amp; Usage
                    </h3>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-[var(--g-primary-blue)]/20 text-[var(--g-primary-blue)] border border-[var(--g-primary-blue)]/30 font-mono">
                      Limit: 5,000,000
                    </span>
                  </div>

                  {(() => {
                    const TOKEN_CAP = 5_000_000;
                    const cumulative = tokenUsage?.cumulative_user_tokens ?? 0;
                    const pct = Math.min(100, (cumulative / TOKEN_CAP) * 100);
                    const remaining = TOKEN_CAP - cumulative;
                    const barColor =
                      pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500';

                    return (
                      <div className="space-y-4">
                        <div>
                          <div className="flex justify-between items-baseline mb-1.5 text-xs">
                            <span className="text-gray-400">Cumulative Usage</span>
                            <span className="font-mono text-white">
                              {cumulative.toLocaleString()} / {TOKEN_CAP.toLocaleString()} (
                              {pct.toFixed(1)}%)
                            </span>
                          </div>

                          {/* Progress bar */}
                          <div className="w-full h-2 rounded-full bg-white/10 overflow-hidden mb-2">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>

                          <div className="flex justify-between items-baseline text-xs">
                            <span className="text-gray-500">Available Headroom</span>
                            <span
                              className={`font-mono font-bold ${pct >= 90 ? 'text-red-400' : pct >= 70 ? 'text-amber-400' : 'text-emerald-400'}`}
                            >
                              {remaining.toLocaleString()} tokens
                            </span>
                          </div>
                        </div>

                        {/* Breakdown */}
                        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-[var(--g-outline)]/50">
                          {[
                            { label: 'Input Tokens', val: tokenUsage?.input },
                            { label: 'Output Tokens', val: tokenUsage?.output },
                            { label: 'Thinking Tokens', val: tokenUsage?.thinking },
                          ].map(({ label, val }) => (
                            <div
                              key={label}
                              className="bg-black/30 border border-[var(--g-outline)] rounded p-2 text-center"
                            >
                              <div className="text-[10px] text-gray-500 block mb-0.5">{label}</div>
                              <div className="text-xs font-mono font-semibold text-gray-200">
                                {val != null ? val.toLocaleString() : '0'}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-[var(--g-outline)] bg-black/20 flex justify-end gap-3">
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="px-4 py-1.5 rounded-md border border-[var(--g-outline)] text-xs font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </m.div>
          </div>
        )}
      </AnimatePresence>
    </LazyMotion>
  );
}
