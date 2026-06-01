export interface PlanData {
  surfaces: string[];
}

export interface ScreenStartData {
  screen: string;
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

export interface NielsenHeuristic {
  heuristic: string;
  present: boolean;
  votes: number;
}

export interface CompleteData {
  status: string;
  best_html?: string;
  converged?: boolean;
  composite_score?: number;
  dorav?: DoravScores;
  nielsen?: NielsenHeuristic[];
  /** Set to true when the pipeline converged but quality fell below threshold */
  degraded?: boolean;
  /** Human-readable reason for degradation — forwarded to the DegradedState component */
  degradation_reason?: string;
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
}

export const getApiUrl = () => {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

export async function runGenerationStream(
  brief: string,
  token: string | null,
  callbacks: StreamCallbacks
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
      body: JSON.stringify({ brief }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        let detail = '';
        try {
          const body = await response.json();
          detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body);
        } catch {
          detail = await response.text();
        }
        callbacks.onCapReached?.({ detail: detail || 'Token cap reached.' });
        return;
      }
      let errorDetail = '';
      try {
        const errorJson = await response.json();
        errorDetail = errorJson.detail || JSON.stringify(errorJson);
      } catch {
        errorDetail = await response.text();
      }
      callbacks.onError?.(`HTTP ${response.status}: ${errorDetail}`);
      return;
    }

    if (!response.body) {
      callbacks.onError?.('Response body is empty or not readable.');
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent = '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('event:')) {
          currentEvent = trimmed.slice(6).trim();
        } else if (trimmed.startsWith('data:')) {
          const dataStr = trimmed.slice(5).trim();
          try {
            const parsedData = JSON.parse(dataStr);
            triggerCallback(currentEvent, parsedData, callbacks);
          } catch (e) {
            console.error('Failed to parse SSE data JSON:', e, dataStr);
          }
          currentEvent = '';
        }
      }
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
    default:
      console.log(`Unhandled SSE event: ${event}`, data);
  }
}
