import type { DesignSystem } from './design-system';
import { SSEStreamParser } from './sse-parser';

/**
 * AT-030 / AT-025: a domain Tier-1 standard the planner proposes applying by
 * default, each attributable to a cited, trust-scored source (PRD §3.5). Wire
 * shape mirrors `atelier-core` `ProposedDefault` EXACTLY (the `plan` SSE event
 * serializes the Pydantic model field-for-field):
 *   standard_id, name, rule, citation_url, trust_score, domain.
 * `citation_url` is never empty — every default Atelier applies on the user's
 * behalf carries its provenance, which the ApprovalCard (AT-042) renders as a
 * clickable citation so the user can verify and edit before approving.
 */
export interface ProposedDefault {
  standard_id: string;
  name: string;
  rule: string;
  citation_url: string;
  trust_score: number;
  domain: string;
}

/**
 * AT-042: the pre-sign-off plan the ApprovalCard surfaces for human review.
 * Extends the original (surfaces-only) shape — every field beyond `surfaces` is
 * optional so the existing `plan` SSE consumers and narrow-brief plans (which
 * carry only `surfaces`) keep working unchanged. Mirrors the subset of
 * `atelier-core` `PlanStep` the dashboard consumes.
 */
export interface PlanData {
  surfaces: string[];
  /**
   * AT-026: the run/session id this plan belongs to. Surfaced on the `plan` SSE
   * event so the legibility UI (and the Stop control) can address THIS run — the
   * Stop endpoint is keyed on session_id and the loop honors it per-session.
   */
  session_id?: string;
  /** Estimated total token budget for the run (rendered on the ApprovalCard). */
  est_tokens?: number;
  /** WCAG conformance target the run will gate against (e.g. "AA"). */
  wcag_target?: string;
  /** Number of specialist agents the run will dispatch (the D-O-R-A-V panel). */
  specialist_count?: number;
  /** D-O-R-A-V axis weight distribution (sums to ~1.0). */
  axis_weights?: Record<string, number>;
  /** Brand constitution to apply, or null/absent for the default. */
  constitution?: string | null;
  /** One-sentence justification for the plan (planner reasoning). */
  reasoning?: string;
  /** AT-025/AT-030 cited defaults — the editable, citation-backed plan rows. */
  proposed_defaults?: ProposedDefault[];
  /** Under-specified aspects of the brief surfaced for the user to clarify. */
  open_questions?: string[];
  /** Known coverage gaps (e.g. research unavailable) acknowledged on the plan. */
  gaps?: string[];
}

export interface ScreenStartData {
  screen: string;
  /** AT-026: the session id, so the Stop control can address this run. */
  session_id?: string;
}

/**
 * AT-026 (Mid legibility): one trace event per DDLC specialist as it hands off.
 * `role` is the specialist's ADK agent author (ux_research, ia_flows, wireframe,
 * ui_design, interaction_spec, tokens); `summary` is a length-capped digest of
 * its contribution so the user sees WHAT each specialist produced, in real time.
 */
export interface SpecialistTraceData {
  screen: string;
  iteration: number;
  role: string;
  summary: string;
}

/**
 * AT-026 (Mid legibility): one trace event per WRAI research query, with the top
 * citation for that query — the grounded provenance of what Atelier looked up.
 */
export interface ResearchQueryData {
  query: string;
  result_count: number;
  top_citation: string;
  top_title: string;
  trust_score: number;
}

/**
 * AT-027 (Optimize surfacing): one read-only MoE routing decision, surfaced for
 * trace legibility. Mirrors `atelier-core` `RouteDecision` (router/protocol.py):
 * the phase-aware expert the bandit router selected, its score/rationale, and
 * the fallback chain. Read-only — the product shows the router's reasoning, it
 * does not let the user change it.
 */
export interface RouteDecisionData {
  expert: string;
  phase: string;
  score: number;
  rationale: string;
  fallback_chain: string[];
  routing_mode: string;
}

/**
 * AT-027 (Optimize surfacing): one read-only dreaming/DPO preference pair,
 * surfaced for trace legibility. Mirrors `atelier-core` `ExtractedPair`
 * (optimize/dreaming_module.py): the chosen vs rejected candidate scores and
 * the margin. `chosen_score` already reflects the §3.6 anti-sycophancy reward.
 */
export interface DreamingArtifactData {
  surface_id: string;
  node_name: string;
  chosen_score: number;
  rejected_score: number;
  margin: number;
}

/**
 * AT-026 (R13 interruption): emitted when a user Stop is honored. The run halted
 * within one iteration BEFORE its next model call and a durable checkpoint was
 * persisted (resume continues from it).
 */
export interface StopData {
  screen: string;
  iteration: number;
  session_id: string;
  checkpointed: boolean;
}

/**
 * AT-026 (Post / Attribution): one acceptance criterion's verdict. Mirrors
 * `atelier-core` `CriterionVerdict` (the `verify_run` oracle output): every
 * ACCEPTANCE.json criterion -> verdict + evidence + provenance source.
 */
export interface CriterionVerdict {
  criterion_id: string;
  kind: string;
  target: string;
  /** "user" | "standard:<standard_id>" — the provenance of the criterion. */
  source: string;
  verdict: boolean;
  evidence_ref: string;
}

/**
 * AT-026 (Post / Attribution): the aggregate run-oracle verdict. `complete` is
 * true iff every criterion verdict holds. Mirrors `atelier-core` `RunVerdict`.
 */
export interface RunVerdict {
  complete: boolean;
  criteria: CriterionVerdict[];
  composite_by_surface: Record<string, number>;
}

export interface IterationStartData {
  screen: string;
  iteration: number;
}

export interface CandidatesData {
  screen: string;
  html: string;
}

export interface GatesEvaluationData {
  screen: string;
  axe_score: number;
  visual_score: number;
  passed: boolean;
}

export interface ConsensusEvaluationData {
  screen: string;
  design_consistency: number;
  layout_structure: number;
  responsive: number;
  aesthetics: number;
  contrast: number;
  votes: string[];
  passed: boolean;
}

export interface FixerDirectiveData {
  screen: string;
  directive: string;
}

export interface ScreenConvergedData {
  screen: string;
  html: string;
}

export interface DoravScores {
  brand?: number;
  originality?: number;
  relevance?: number;
  accessibility?: number;
  'visual-clarity'?: number;
  composite?: number;
}

/**
 * ADR-0024 / P0.4: a single A2UI v0.9-wire server-to-client message. The backend
 * (``atelier-core/src/atelier/a2ui/surface.py``) emits the raw ordered list of
 * the three kinds below on the SSE ``complete`` event (``a2ui_payload``):
 *
 *   1. ``createSurface``    — opens the surface against the basic catalog.
 *   2. ``updateComponents`` — the declarative component tree (one ``id == "root"``).
 *   3. ``updateDataModel``  — the token rows the tree binds against.
 *
 * Loose by design: this mirrors (and is assignable to) the renderer's strict
 * ``A2uiMessage`` union from ``@a2ui/web_core/v0_9`` without forcing this shared
 * lib to take a direct dependency on the renderer's internal package (that
 * boundary lives only in ``components/a2ui/A2uiDesignSystemPanel.tsx``). Every
 * message carries ``version: "v0.9"`` (see ``A2UI_WIRE_VERSION`` server-side).
 */
export type A2uiMessage =
  | {
      version: 'v0.9';
      createSurface: { surfaceId: string; catalogId: string; [k: string]: unknown };
    }
  | {
      version: 'v0.9';
      updateComponents: {
        surfaceId: string;
        components: Array<{ component: string; id?: string; [k: string]: unknown }>;
      };
    }
  | {
      version: 'v0.9';
      updateDataModel: { surfaceId: string; path?: string; value?: unknown };
    }
  | {
      version: 'v0.9';
      deleteSurface: { surfaceId: string };
    };

export interface NielsenHeuristic {
  heuristic: string;
  present: boolean;
  votes: number;
}

export interface CompleteData {
  status: string;
  best_html?: string;
  /**
   * A1: flat {surface: html} map over EVERY converged surface, so the Studio
   * renders the whole multi-surface product, not just surfaces[0]. Belt-and-
   * suspenders with the streaming ``screen_converged`` events.
   */
  screens_html?: Record<string, string>;
  converged?: boolean;
  composite_score?: number;
  dorav?: DoravScores;
  nielsen?: NielsenHeuristic[];
  /** AT-026: the run/session id, for replay + the Stop control. */
  session_id?: string;
  /**
   * AT-026 (Post / Attribution): the AT-007 run-oracle verdict — every acceptance
   * criterion mapped to a verdict + evidence. Null on legacy/degraded paths where
   * the oracle could not run (the Attribution view renders an honest "unavailable").
   */
  run_verdict?: RunVerdict | null;
  /** Set to true when the pipeline converged but quality fell below threshold */
  degraded?: boolean;
  /** Human-readable reason for degradation — forwarded to the DegradedState component */
  degradation_reason?: string;
  /**
   * AT-044: the converged design's DTCG design system (one entry per token).
   * Drives the Studio design-system panel; when absent the panel falls back to
   * the default system (DEFAULT_DESIGN_SYSTEM). Wired end-to-end by AT-053
   * (per-tenant memory) — forward-compatible here.
   */
  tokens?: DesignSystem;
  /**
   * ADR-0024 / P0.4: the Governed A2UI design-system surface — the raw ordered
   * server-to-client message list emitted by the backend alongside ``best_html``.
   * Drives the agent-emitted A2UI rendering of the Studio design-system panel
   * (``A2uiDesignSystemPanel``) behind the ``NEXT_PUBLIC_A2UI_RENDER`` flag. The
   * design deliverable stays ``best_html`` — A2UI is chrome only, never the output.
   * Absent on legacy/degraded paths; the hand-built panel is the fail-soft fallback.
   */
  a2ui_payload?: A2uiMessage[];
  /**
   * ADR-0024 / P0.4 (G2): governance events from the fail-closed A2UI gate. When
   * the gate REJECTS the surface, the backend sets ``a2ui_payload`` to ``[]``
   * (frontend fail-soft → hand-built panel) and attaches the rejection event(s)
   * here. Shape mirrors the gate's ``governance_messages``: an A2UI custom event
   * (``name: "atelier/governance.rejected"``) carrying the surface id and the
   * per-error validation detail. Consumed for provenance/telemetry; the panel
   * still falls back via the empty payload. Absent when the surface passed.
   */
  a2ui_governance?: {
    version: 'v0.9';
    custom: {
      surfaceId: string;
      name: string;
      payload: Record<string, unknown>;
    };
  }[];
}

export interface CapReachedData {
  /** Optional detail from the server (e.g. remaining tokens) */
  detail?: string;
}

/**
 * AT-096: Per-generation token usage delta emitted by the backend (AT-095).
 * ``cumulative_user_tokens`` is the authoritative per-user running total
 * (spans runs — the backend seeds it from the persisted store).
 */
export interface TokenDeltaData {
  input: number;
  output: number;
  thinking: number;
  cumulative_user_tokens: number;
}

/**
 * Per-iteration D-O-R-A-V scores emitted by the backend convergence loop (AT-093).
 * Shape mirrors the ``dorav`` key in CompleteData plus ``failing_axis``.
 */
export interface IterationScoreData {
  screen: string;
  iteration: number;
  /** Per-axis scores keyed by axis name (brand, originality, relevance, accessibility, visual-clarity). */
  dorav: DoravScores;
  /** Overall composite score for this iteration (0–1). */
  composite: number;
  /** Axis name with the lowest score — highlighted amber in the scorecard. */
  failing_axis: string | null;
}

export interface StreamCallbacks {
  onPlan?: (data: PlanData) => void;
  onScreenStart?: (data: ScreenStartData) => void;
  onIterationStart?: (data: IterationStartData) => void;
  onCandidates?: (data: CandidatesData) => void;
  onGatesEvaluation?: (data: GatesEvaluationData) => void;
  onConsensusEvaluation?: (data: ConsensusEvaluationData) => void;
  onFixerDirective?: (data: FixerDirectiveData) => void;
  onScreenConverged?: (data: ScreenConvergedData) => void;
  onComplete?: (data: CompleteData) => void;
  onError?: (error: string) => void;
  /** Fired when a `cap_reached` SSE event is received or the stream returns HTTP 429 */
  onCapReached?: (data: CapReachedData) => void;
  /** AT-093: fired once per convergence iteration with that iteration's D-O-R-A-V scores */
  onIterationScore?: (data: IterationScoreData) => void;
  /** AT-096: fired on each token_delta SSE event with cumulative per-user token counts */
  onTokenDelta?: (data: TokenDeltaData) => void;
  /** AT-026: fired once per DDLC specialist as it hands off (Mid legibility trace) */
  onSpecialistTrace?: (data: SpecialistTraceData) => void;
  /** AT-026: fired once per WRAI research query with its top citation (Mid legibility) */
  onResearchQuery?: (data: ResearchQueryData) => void;
  /** AT-027: fired with the read-only MoE routing decision for the run (Optimize surfacing) */
  onRouteDecision?: (data: RouteDecisionData) => void;
  /** AT-027: fired with a read-only dreaming/DPO artifact for the run (Optimize surfacing) */
  onDreamingArtifact?: (data: DreamingArtifactData) => void;
  /** AT-026: fired when a user Stop is honored (R13 interruption) */
  onStop?: (data: StopData) => void;
}

export const getApiUrl = () => {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

/**
 * Read an error response body EXACTLY ONCE (L16). A `Response` body is a
 * single-use stream: the prior pattern called `response.json()` and then
 * `response.text()` in the catch, which throws "body stream already read" and
 * masks the real HTTP status with that TypeError. We read the text once, then try
 * to parse it as JSON, falling back to the raw text — so a non-JSON 4xx/5xx still
 * surfaces its true status and detail.
 */
async function readErrorDetail(response: Response): Promise<string> {
  let text = '';
  try {
    text = await response.text();
  } catch {
    return '';
  }
  try {
    const body = JSON.parse(text) as Record<string, unknown>;
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body);
  } catch {
    return text;
  }
}

export async function runGenerationStream(
  brief: string,
  token: string | null,
  callbacks: StreamCallbacks,
  settings?: {
    model?: string | null;
    temperature?: number | null;
    top_k?: number | null;
    max_tokens?: number | null;
  }
): Promise<void> {
  const url = `${getApiUrl()}/v1/generate/stream`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        brief,
        ...(settings || {}),
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        // AT-094 (R9): pass the server's branded stop through verbatim; when the
        // body carries none, leave detail empty so the UI renders the SPEC-EXACT
        // TOKEN_CAP_MESSAGE fallback (PRD §13.2) rather than a paraphrase.
        const detail = await readErrorDetail(response);
        callbacks.onCapReached?.({ detail });
        return;
      }
      // readErrorDetail stringifies a non-string FastAPI `detail` (object/array for
      // request-validation / some auth failures) so the user sees real text rather
      // than "HTTP 401: [object Object]".
      const errorDetail = await readErrorDetail(response);
      callbacks.onError?.(`HTTP ${response.status}: ${errorDetail}`);
      return;
    }

    if (!response.body) {
      callbacks.onError?.('Response body is empty or not readable.');
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    // L07: a single stateful parser owns the line buffer AND the pending event
    // name across chunk boundaries, so a frame whose event:/data: lines straddle a
    // network chunk is reassembled with its name intact (see sse-parser.ts).
    const parser = new SSEStreamParser();

    // A run ends with exactly one terminal event (complete / error / cap_reached
    // / stop). If the stream closes WITHOUT one AFTER generation has started
    // producing surfaces — a proxy/Cloud Run wall-clock cut, a half-closed
    // socket, or a run that outlives the request budget — the reader below just
    // `break`s on `done` and, without this guard, the Studio would sit on the
    // "generating" spinner forever (no onComplete/onError ever fires).
    //
    // The guard is scoped to "generation actually progressed": a stream that
    // closes after ONLY a `plan` event is a legitimate transient (the loading
    // spinner before the first surface, or a run parked awaiting sign-off) —
    // not a hung run to error out. We therefore require a generation-progress
    // event before treating a terminal-less close as a failure, so the honest
    // error fires for a mid-generation death but never for a pre-generation
    // pause.
    const TERMINAL_EVENTS = new Set(['complete', 'error', 'cap_reached', 'stop']);
    const PROGRESS_EVENTS = new Set([
      'screen_start',
      'iteration_start',
      'candidates',
      'gates_evaluation',
      'consensus_evaluation',
      'fixer_directive',
      'screen_converged',
      'iteration_score',
    ]);
    let sawTerminalEvent = false;
    let sawGenerationProgress = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
        // L18: parse and dispatch are separate try-blocks. A throw from a render
        // callback must not be mislabeled as (and silently swallowed by) the JSON
        // parse-error path — it surfaces a distinct, honest onError instead.
        let parsedData: Record<string, unknown>;
        try {
          parsedData = JSON.parse(frame.data);
        } catch (e) {
          console.error('Failed to parse SSE data JSON:', e, frame.data);
          continue;
        }
        try {
          triggerCallback(frame.event, parsedData, callbacks);
        } catch (e) {
          // Constant format string (event name passed as a separate arg) so the
          // log cannot be format-string-forged — avoids semgrep unsafe-formatstring.
          console.error('Failed to handle SSE event:', frame.event, e);
          callbacks.onError?.(`Failed to handle ${frame.event} event`);
        }
        if (TERMINAL_EVENTS.has(frame.event)) sawTerminalEvent = true;
        if (PROGRESS_EVENTS.has(frame.event)) sawGenerationProgress = true;
      }
    }

    // The server closed the stream cleanly mid-generation but never sent a
    // terminal event: surface an honest, retryable failure instead of an
    // eternal spinner.
    if (!sawTerminalEvent && sawGenerationProgress) {
      callbacks.onError?.(
        'The run was interrupted before it finished (the connection closed early). Please retry.'
      );
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    callbacks.onError?.(message);
  }
}

function triggerCallback(event: string, data: Record<string, unknown>, callbacks: StreamCallbacks) {
  switch (event) {
    case 'plan':
      callbacks.onPlan?.(data as unknown as PlanData);
      break;
    case 'screen_start':
      callbacks.onScreenStart?.(data as unknown as ScreenStartData);
      break;
    case 'iteration_start':
      callbacks.onIterationStart?.(data as unknown as IterationStartData);
      break;
    case 'candidates':
      callbacks.onCandidates?.(data as unknown as CandidatesData);
      break;
    case 'gates_evaluation':
      callbacks.onGatesEvaluation?.(data as unknown as GatesEvaluationData);
      break;
    case 'consensus_evaluation':
      callbacks.onConsensusEvaluation?.(data as unknown as ConsensusEvaluationData);
      break;
    case 'fixer_directive':
      callbacks.onFixerDirective?.(data as unknown as FixerDirectiveData);
      break;
    case 'screen_converged':
      callbacks.onScreenConverged?.(data as unknown as ScreenConvergedData);
      break;
    case 'complete':
      callbacks.onComplete?.(data as unknown as CompleteData);
      break;
    case 'error': {
      const errorData = data as Record<string, unknown>;
      callbacks.onError?.(
        typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(data)
      );
      break;
    }
    case 'cap_reached':
      callbacks.onCapReached?.(data as unknown as CapReachedData);
      break;
    case 'iteration_score':
      callbacks.onIterationScore?.(data as unknown as IterationScoreData);
      break;
    case 'token_delta':
      callbacks.onTokenDelta?.(data as unknown as TokenDeltaData);
      break;
    case 'specialist_trace':
      callbacks.onSpecialistTrace?.(data as unknown as SpecialistTraceData);
      break;
    case 'research_query':
      callbacks.onResearchQuery?.(data as unknown as ResearchQueryData);
      break;
    case 'route_decision':
      callbacks.onRouteDecision?.(data as unknown as RouteDecisionData);
      break;
    case 'dreaming_artifact':
      callbacks.onDreamingArtifact?.(data as unknown as DreamingArtifactData);
      break;
    case 'stop':
      callbacks.onStop?.(data as unknown as StopData);
      break;
    case 'degraded':
      // The backend emits a `degraded` event (cap / unavailable / blocked) and
      // ALWAYS follows it with a `complete` event carrying `degraded: true` +
      // `degradation_reason`. The Studio acknowledges the degradation off that
      // complete payload (see onComplete), so this event needs no separate
      // handler — swallow it explicitly rather than logging a misleading
      // "Unhandled SSE event" warning during an otherwise-honest degraded run.
      break;
    default: {
      // L07 defense-in-depth: if a frame ever reaches here with a recoverable
      // shape (e.g. a future straddle the parser can't name, or a renamed event),
      // route it by payload shape so user-visible HTML is never silently lost,
      // rather than dropping it with only a warning.
      const d = data as Record<string, unknown>;
      if (typeof d.screen === 'string' && d.iteration !== undefined && typeof d.html === 'string') {
        callbacks.onScreenConverged?.(data as unknown as ScreenConvergedData);
        break;
      }
      if (
        typeof d.screen === 'string' &&
        d.iteration !== undefined &&
        typeof d.role === 'string' &&
        d.summary !== undefined
      ) {
        callbacks.onSpecialistTrace?.(data as unknown as SpecialistTraceData);
        break;
      }
      // nosemgrep: javascript.lang.security.audit.unsafe-formatstring.unsafe-formatstring -- template literal, not a printf-style format string; no format-specifier injection is possible.
      console.warn(`Unhandled SSE event: ${event}`, data);
    }
  }
}

/**
 * AT-026 (R13): request a cooperative Stop of an in-flight run. The backend arms
 * the per-session stop flag; the convergence loop halts within one iteration
 * BEFORE its next model call (no model call after Stop), persists a checkpoint,
 * and emits a `stop` SSE event. Returns true on a 2xx, false otherwise — the
 * caller acknowledges a failed Stop rather than silently assuming it landed.
 */
export async function requestStopRun(sessionId: string, token: string | null): Promise<boolean> {
  const url = `${getApiUrl()}/v1/stop/${encodeURIComponent(sessionId)}`;
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  try {
    const response = await fetch(url, { method: 'POST', headers });
    return response.ok;
  } catch {
    return false;
  }
}

// =============================================================================
// Platform API — /v1/platform/*
//
// Typed client for the GCP-native operator dashboard (Build / Scale / Govern /
// Optimize pillars). All endpoints are authenticated GET requests. Interfaces
// mirror the Pydantic response models field-for-field following the PlanData /
// CompleteData convention established above.
// =============================================================================

// ---------------------------------------------------------------------------
// Shared transport
// ---------------------------------------------------------------------------

/**
 * Authenticated GET helper for all /v1/platform/* endpoints.
 *
 * Passes the Firebase ID token as a Bearer credential. On non-2xx responses,
 * throws an Error with the status code and server detail string so callers can
 * surface a typed failure without parsing the HTTP layer themselves.
 *
 * The platform surface is fail-soft: an unavailable source returns HTTP 200 with
 * `{ available: false, reason }` (NOT a non-2xx), so this helper does NOT throw
 * in that case — callers MUST check the `available` flag(s) before rendering.
 *
 * An optional `AbortSignal` is forwarded to `fetch` so the caller (e.g.
 * `usePlatformData`) can cancel an in-flight request on unmount or refetch.
 *
 * Type parameter T is the expected JSON response shape — the caller supplies
 * the matching interface so the return is narrowed at the call site.
 */
export async function authedGet<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const url = `${getApiUrl()}${path}`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
    signal,
  });
  if (!response.ok) {
    const detail = await readErrorDetail(response); // L16: read body once
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// AgentDescriptor — mirrors GET /v1/platform/agents/{id}
// ---------------------------------------------------------------------------

/**
 * Full descriptor for a single agent in the specialist DAG.
 *
 * Mirrors the backend `AgentDescriptor` Pydantic model field-for-field.
 * `available` is false when the id is not recognised — callers should treat
 * the remaining fields as absent in that case.
 */
export interface AgentDescriptor {
  /** Agent identifier (stable slug, e.g. "ux_research"). */
  id: string;
  /** Display name rendered in the Agent Registry card. */
  name: string;
  /**
   * Broad agent kind. Known values: "specialist", "orchestrator",
   * "evaluator", "router". Extensible — treat unknown values as "specialist".
   */
  kind: string;
  /**
   * Google ADK agent type. Known values: "LlmAgent", "SequentialAgent",
   * "ParallelAgent", "LoopAgent". Extensible.
   */
  adk_type: string;
  /** One-sentence description of the agent's responsibility. */
  description: string;
  /** Served model identifier (e.g. "gemini-2.5-pro"). */
  model_id: string;
  /**
   * Canonical task type label (e.g. "UX Research", "Wireframing"), or null when
   * the agent carries no TaskType (the backend serializes `task_type` as null).
   */
  task_type: string | null;
  /** MCP / function tools available to this agent. */
  tools: string[];
  /**
   * System-prompt excerpt (truncated server-side for display).
   * Absent when the backend withholds it for security reasons.
   */
  prompt?: string;
  /**
   * Human-readable provenance of the system prompt
   * (e.g. "atelier-core/prompts/ux_research.md").
   */
  prompt_source?: string;
  /**
   * State-bag keys this agent reads from upstream nodes.
   * Empty for the first node in a chain.
   */
  upstream_keys: string[];
  /** State-bag key this agent writes its output under. */
  output_key: string;
  /**
   * Parent agent id when this agent is nested inside an orchestrator.
   * Null for top-level agents.
   */
  subagent_of: string | null;
}

/**
 * Compact roster row returned in the `agents` array of GET /v1/platform/agents.
 *
 * Mirrors the backend `_descriptor_summary` projection field-for-field: it is
 * the full `AgentDescriptor` MINUS the prompt body, `upstream_keys`, and
 * `output_key` (those are only on the per-agent `_descriptor_full` view).
 */
export interface AgentSummary {
  id: string;
  name: string;
  kind: string;
  adk_type: string;
  description: string;
  model_id: string;
  /** Null when the agent carries no TaskType (serialized as null by the API). */
  task_type: string | null;
  tools: string[];
  prompt_source: string;
  /** Parent agent id when nested in an orchestrator; null for top-level. */
  subagent_of: string | null;
}

/**
 * Response envelope for GET /v1/platform/agents.
 *
 * The endpoint returns an OBJECT — not a bare array. `available` is always true
 * for this fixed-roster endpoint; callers guard on it for shape uniformity with
 * the other fail-soft platform surfaces. `counts_by_kind` maps each agent
 * `kind` to its count; `agents` is the roster of summary rows.
 */
export interface AgentsResponse {
  available: boolean;
  count: number;
  counts_by_kind: Record<string, number>;
  agents: AgentSummary[];
}

/**
 * Response envelope for GET /v1/platform/agents/{id}.
 *
 * `available` is false (with `reason: "agent_not_found"`) when the id is not in
 * the fixed roster; otherwise `agent` carries the full descriptor. Callers MUST
 * guard on `available` before reading `agent`.
 */
export interface AgentDetailResponse {
  available: boolean;
  reason?: string;
  agent?: AgentDescriptor;
}

// ---------------------------------------------------------------------------
// Topology — mirrors GET /v1/platform/topology
// ---------------------------------------------------------------------------

/** A single node in the static specialist DAG. */
export interface TopologyNode {
  /** Stable node id (matches AgentDescriptor.id). */
  id: string;
  /** Human-readable display label. */
  label: string;
  /**
   * Node kind — aligns with AgentDescriptor.kind.
   * Drives icon / colour selection in the renderer.
   */
  kind: string;
  /** Served model id (task-type value), null for non-LLM nodes. */
  model?: string | null;
}

/** A directed edge between two nodes in the static specialist DAG. */
export interface TopologyEdge {
  from: string;
  to: string;
}

/**
 * System topology graph spec returned by GET /v1/platform/topology.
 *
 * This is the STATIC specialist DAG — the wiring of agents in the pipeline
 * at design time. It is NOT a per-run span tree (use ReplaySpan for that).
 * Mirrors the backend `/topology` response body field-for-field.
 */
export interface TopologyGraphSpec {
  available: boolean;
  /** Discriminator — "static_pipeline_dag". */
  kind?: string;
  /** Honesty note: this is the static hand-off DAG, not a per-run span tree. */
  note?: string;
  /**
   * Firestore board project-path segment the server writes task docs under
   * (`tenants/{tenant}/projects/{project_id}/tasks` — the AT-020b emitter,
   * with `project_id = GOOGLE_CLOUD_PROJECT` server-side). The canonical
   * client-side source for the live board / agent-activity subscriptions —
   * never substitute a hardcoded default. Optional only because older API
   * deploys predate the field.
   */
  project_id?: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

// ---------------------------------------------------------------------------
// Replay — mirrors GET /v1/replay/{session_id}
// ---------------------------------------------------------------------------

/**
 * A single execution span in a session replay.
 *
 * The backend notes that `parent_span_id` and `duration_ms` are not
 * pre-populated from the BQ trajectory schema — callers must compute
 * durations client-side from `started_at` / `ended_at` and treat the
 * tree as flat (ordered by `started_at`).
 *
 * Mirrors `atelier-core` `SpanNode` (replay.py).
 */
export interface ReplaySpan {
  span_id: string;
  parent_span_id: string | null;
  node_name: string;
  /** ISO-8601 timestamp string. */
  started_at: string;
  /** ISO-8601 timestamp string. */
  ended_at: string;
  /**
   * Pre-computed duration in milliseconds. Set to 0.0 by the backend when
   * not available — compute client-side from started_at / ended_at.
   */
  duration_ms: number;
  model_id: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  /** "ok" | "error" | other extensible status strings. */
  status: string;
}

/** Memory recall event in a session replay (semantic or procedural tier). */
export interface MemoryRecall {
  tier: string;
  query_text: string;
  passage: string;
  similarity: number;
  source_event_ids: string[];
}

/** Single gate / judge score in the AND-Gate scorecard for a replay. */
export interface GateScore {
  axis: string;
  score: number;
  confidence_low: number;
  confidence_high: number;
  judge_model: string;
  reasoning: string;
}

/**
 * Full replay payload for a session.
 *
 * Mirrors `atelier-core` `SessionReplayPayload` (replay.py) field-for-field.
 * Includes the AT-027 read-only optimize surfaces (`route_decisions`,
 * `dreaming_artifacts`) threaded through the trace.
 */
export interface SessionReplayPayload {
  session_id: string;
  tenant_id: string;
  project_id: string;
  started_at: string;
  ended_at: string;
  /** "completed" | "stopped" | "degraded" | other extensible outcome strings. */
  outcome: string;
  composite_score: number;
  degradation_reason: string | null;
  user_message: string | null;
  spans: ReplaySpan[];
  memory_recalls: MemoryRecall[];
  gate_scores: GateScore[];
  /** Read-only MoE routing decisions threaded through the trace (AT-027). */
  route_decisions: RouteDecisionData[];
  /** Read-only dreaming / DPO artifacts threaded through the trace (AT-027). */
  dreaming_artifacts: DreamingArtifactData[];
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  candidate_count: number;
  iteration: number;
}

// ---------------------------------------------------------------------------
// Platform pillars — Build / Scale / Govern / Optimize
// ---------------------------------------------------------------------------

/**
 * Agent-card skill entry in the Build pillar.
 *
 * One declared capability read from the repo-root `agent_card.json` and surfaced
 * read-only. Mirrors the backend projection in `/build`: `{ id, name,
 * description, tags }`. The backend reads these straight from the card, so any
 * field may be absent/null when the card omits it.
 */
export interface AgentCardSkill {
  id: string | null;
  name: string | null;
  description: string | null;
  /** Free-form capability tags declared on the skill (e.g. "design"). */
  tags: string[];
}

/**
 * MCP toolset entry in the Build pillar.
 *
 * Derived from the registry's tool labels: one row per distinct tool label,
 * carrying the sorted ids of the agents that hold it. Mirrors the backend
 * `/build` `mcp_toolsets` shape: `{ toolset, agents }`.
 */
export interface McpToolset {
  /** The tool/toolset label (e.g. "stitch_mcp"). */
  toolset: string;
  /** Sorted ids of the agents wired to this toolset. */
  agents: string[];
}

/** Agent-card metadata block on the Build pillar (`agent_card` key). */
export interface AgentCardMeta {
  /** False when the repo-root agent_card.json is absent/unparseable. */
  available: boolean;
  name?: string | null;
  version?: string | null;
  protocolVersion?: string | null;
  protocols?: Record<string, unknown>;
}

/** Aggregate counts block on the Build pillar (`counts` key). */
export interface BuildCounts {
  agents_total: number;
  /** Agent count grouped by kind. */
  by_kind: Record<string, number>;
  skills: number;
  mcp_toolsets: number;
}

/**
 * Build pillar response — GET /v1/platform/build.
 *
 * Agent-card metadata, A2A skills, MCP toolset inventory, and aggregate counts.
 * Mirrors the backend `/build` response body field-for-field.
 */
export interface PlatformBuild {
  available: boolean;
  agent_card: AgentCardMeta;
  skills: AgentCardSkill[];
  mcp_toolsets: McpToolset[];
  counts: BuildCounts;
}

/** Served model catalog entry (Scale pillar). Mirrors `ModelCatalogEntry`. */
export interface ModelCatalogEntry {
  model_id: string;
  /** Human-readable label for the model. */
  display_name: string;
  /** Tier string — "pro" | "flash" | "flash_lite". */
  tier: string;
  /** Per-user lifetime token cap for this tier. */
  token_cap: number;
  /** TaskType value strings this model id is statically routed to. */
  task_types: string[];
}

/**
 * Model catalog block on the Scale pillar (`model_catalog` key).
 *
 * Fail-soft: when the catalog cannot be built, `available` is false and
 * `models` is absent — callers MUST guard before reading `models`.
 */
export interface ModelCatalogBlock {
  available: boolean;
  reason?: string;
  models?: ModelCatalogEntry[];
}

/**
 * Agent Engine deploy configuration block on the Scale pillar
 * (`deploy_config` key). Fail-soft: `available` is false when the config lookup
 * raises; the remaining fields are absent in that case.
 */
export interface DeployConfigBlock {
  available: boolean;
  reason?: string;
  project?: string;
  location?: string;
  display_name?: string;
  description?: string;
  staging_bucket?: string;
}

/** Serving-stack health block on the Scale pillar (`health` key). */
export interface ScaleHealth {
  available: boolean;
  /** "healthy" | other extensible status strings. */
  status: string;
  service: string;
}

/**
 * Scale pillar response — GET /v1/platform/scale.
 *
 * Model routing catalog, the session/usage backend modes (plain strings), the
 * Agent Engine deploy config, and a health rollup. Each sub-block is
 * independently fail-soft. Mirrors the backend `/scale` response body.
 */
export interface PlatformScale {
  available: boolean;
  model_catalog: ModelCatalogBlock;
  /** Session/memory backend mode — e.g. "vertex" | "memory". */
  session_backend: string;
  /** Usage-counter backend — e.g. "firestore" | "memory" | "unknown". */
  usage_backend: string;
  deploy_config: DeployConfigBlock;
  health: ScaleHealth;
}

/** Caller identity block on the Govern pillar (`identity` key). */
export interface GovernIdentity {
  /** Firebase UID of the authenticated caller. */
  uid: string;
  /** Tenant id of the authenticated caller. */
  tenant_id: string;
  email_verified: boolean;
}

/** Per-tier token counters within the Govern usage block. */
export interface TierUsage {
  used: number;
  cap: number;
  remaining: number;
}

/**
 * Per-tier usage block on the Govern pillar (`usage` key).
 *
 * `tiers` is a MAP keyed by tier name (NOT an array). Fail-soft: when the usage
 * store read fails, `available` is false and `tiers`/`total_tokens` are absent.
 */
export interface GovernUsage {
  available: boolean;
  reason?: string;
  /** Map of tier name -> its used/cap/remaining counters. */
  tiers?: Record<string, TierUsage>;
  total_tokens?: number;
}

/** Deterministic injection-guard summary within the Model Armor block. */
export interface InjectionGuard {
  always_on: boolean;
  marker_count: number;
}

/**
 * Model Armor safety block on the Govern pillar (`model_armor` key).
 *
 * Fail-soft: `available` is false when the marker set cannot be loaded.
 */
export interface ModelArmorBlock {
  available: boolean;
  reason?: string;
  deterministic_injection_guard?: InjectionGuard;
  vertex_model_armor_template?: { enabled: boolean };
}

/** Rate-limit thresholds within the Govern thresholds block. */
export interface RateLimitThresholds {
  max_requests: number;
  window_seconds: number;
}

/** Circuit-breaker thresholds within the Govern thresholds block. */
export interface CircuitBreakerThresholds {
  global_token_budget_per_window: number;
  window_seconds: number;
  cooldown_seconds: number;
  enabled: boolean;
}

/**
 * Rate-limit + circuit-breaker thresholds block on the Govern pillar
 * (`thresholds` key). Fail-soft: `available` is false when the live store
 * cannot be read; the nested blocks are absent in that case.
 */
export interface ThresholdConfig {
  available: boolean;
  reason?: string;
  rate_limit?: RateLimitThresholds;
  circuit_breaker?: CircuitBreakerThresholds;
}

/**
 * Govern pillar response — GET /v1/platform/govern.
 *
 * Caller identity, per-tier usage (a MAP), Model Armor safety summary, and the
 * in-force rate-limit + circuit-breaker thresholds. Every sub-block is
 * fail-soft. Mirrors the backend `/govern` response body field-for-field.
 */
export interface PlatformGovern {
  available: boolean;
  identity: GovernIdentity;
  usage: GovernUsage;
  /** Usage-counter backend mode — e.g. "firestore" | "memory" | "unknown". */
  usage_backend: string;
  model_armor: ModelArmorBlock;
  thresholds: ThresholdConfig;
}

/**
 * One recent-run telemetry row (Optimize pillar). Mirrors the backend
 * `RecentRun` Pydantic model field-for-field — the latest trajectory record per
 * session, deep-linking to the full replay. There is NO `started_at` and NO
 * `surface_count`; the run header carries only `ended_at` and the cost/token
 * totals below.
 */
export interface RecentRun {
  session_id: string;
  ended_at: string;
  /** "completed" | "stopped" | "degraded" | other extensible outcome strings. */
  outcome: string;
  composite_score: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  iteration: number;
  /** Absolute path to the full replay: /v1/replay/{session_id} */
  replay_url: string;
}

/**
 * Optimize pillar response — GET /v1/platform/optimize.
 *
 * Recent run telemetry. Fail-soft: when BigQuery is unavailable, `available` is
 * false (with `reason`) and `runs` is absent — callers MUST guard before
 * reading `runs`. `spend_caps_enforced` is always false (RR-05 honesty): the
 * cost figures are observed telemetry, NOT an enforced spend cap.
 */
export interface PlatformOptimize {
  available: boolean;
  reason?: string;
  spend_caps_enforced: boolean;
  note?: string;
  count?: number;
  runs?: RecentRun[];
}

// ---------------------------------------------------------------------------
// Fetcher functions
// ---------------------------------------------------------------------------

/** Fetch the Build pillar data (agent card, skills, MCP toolsets, counts). */
export function getPlatformBuild(token: string): Promise<PlatformBuild> {
  return authedGet<PlatformBuild>('/v1/platform/build', token);
}

/** Fetch the Scale pillar data (model catalog, backends, deploy config). */
export function getPlatformScale(token: string): Promise<PlatformScale> {
  return authedGet<PlatformScale>('/v1/platform/scale', token);
}

/** Fetch the Govern pillar data (usage, identity, Model Armor, thresholds). */
export function getPlatformGovern(token: string): Promise<PlatformGovern> {
  return authedGet<PlatformGovern>('/v1/platform/govern', token);
}

/** Fetch the Optimize pillar data (recent runs with replay deep-links). */
export function getPlatformOptimize(token: string): Promise<PlatformOptimize> {
  return authedGet<PlatformOptimize>('/v1/platform/optimize', token);
}

/**
 * Fetch the static system topology graph (specialist DAG wiring).
 *
 * Returns the data-driven node/edge spec. Pass this to a generalised
 * topology renderer; the existing legibility TopologyGraph feeds on the
 * specialist subgraph from SpecialistTraceData and is a separate surface.
 */
export function getPlatformTopology(token: string): Promise<TopologyGraphSpec> {
  return authedGet<TopologyGraphSpec>('/v1/platform/topology', token);
}

/**
 * Fetch the agent roster (GET /v1/platform/agents).
 *
 * Returns the `{ available, count, counts_by_kind, agents }` ENVELOPE — not a
 * bare array. Callers read `.agents` for the roster rows.
 */
export function getAgents(token: string): Promise<AgentsResponse> {
  return authedGet<AgentsResponse>('/v1/platform/agents', token);
}

/**
 * Fetch a single agent's full descriptor (GET /v1/platform/agents/{id}).
 *
 * Returns the `{ available, agent?, reason? }` envelope. `available` is false
 * (with `reason: "agent_not_found"`) when the id is not in the roster — the
 * caller MUST guard on `available` before reading `agent`.
 */
export function getAgent(id: string, token: string): Promise<AgentDetailResponse> {
  return authedGet<AgentDetailResponse>(`/v1/platform/agents/${encodeURIComponent(id)}`, token);
}

/**
 * Fetch the full session replay payload.
 *
 * The backend may return 404 when BigQuery is unavailable (fail-soft). This
 * function throws an Error in that case (HTTP 404: ...) — callers should catch
 * and render a "replay unavailable" fallback rather than crashing.
 */
export function getReplay(sessionId: string, token: string): Promise<SessionReplayPayload> {
  return authedGet<SessionReplayPayload>(`/v1/replay/${encodeURIComponent(sessionId)}`, token);
}
