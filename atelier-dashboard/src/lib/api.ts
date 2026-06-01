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

export interface CompleteData {
  status: string;
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
}

export const getApiUrl = () => {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

export async function runGenerationStream(
  brief: string,
  budgetUsd: number,
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
      body: JSON.stringify({ brief, budget_usd: budgetUsd }),
    });

    if (!response.ok) {
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
    default:
      console.log(`Unhandled SSE event: ${event}`, data);
  }
}
