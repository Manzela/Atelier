'use client';

/**
 * AT-026 — StopButton (R13 interruption).
 *
 * A real, enforced Stop control. Pressing it calls `POST /v1/stop/{session_id}`,
 * which arms the backend's cooperative stop flag; the convergence loop honors it at
 * the top of its next iteration BEFORE any model call (no model call after Stop),
 * persists a durable checkpoint, and emits a `stop` SSE event. This is the
 * trust-critical halt — a user who hits Stop is owed an immediate, honest stop, not
 * a run that keeps burning tokens. Once the `stop` event lands the shell flips to
 * the stopped state and this button reflects "Stopped".
 *
 * Pure presentational + one fetch. Disabled until a session id exists (the run must
 * have started) and while a Stop is already in flight. Accessible: a real <button>
 * with an explicit aria-label and a disabled state.
 */
import React, { useState, useCallback } from 'react';
import { Square, Loader2 } from 'lucide-react';
import { requestStopRun } from '@/lib/api';

export interface StopButtonProps {
  /** The run/session id to stop (from the `plan`/`screen_start` event). */
  sessionId: string | null;
  /** Auth token for the Stop request. */
  token: string | null;
  /** True once the run is no longer in flight (converged/stopped/errored). */
  stopped?: boolean;
  /** Optional: called after a Stop request was acknowledged by the server. */
  onStopRequested?: () => void;
  /** Optional: called when the Stop request failed (so the shell can acknowledge). */
  onStopFailed?: (message: string) => void;
}

export default function StopButton({
  sessionId,
  token,
  stopped = false,
  onStopRequested,
  onStopFailed,
}: StopButtonProps) {
  const [pending, setPending] = useState(false);

  const handleStop = useCallback(async () => {
    if (!sessionId || pending) return;
    setPending(true);
    try {
      const ok = await requestStopRun(sessionId, token);
      if (ok) {
        onStopRequested?.();
      } else {
        onStopFailed?.('Stop request was not accepted by the server.');
      }
    } finally {
      setPending(false);
    }
  }, [sessionId, token, pending, onStopRequested, onStopFailed]);

  const disabled = !sessionId || pending || stopped;

  return (
    <button
      type="button"
      data-testid="stop-button"
      onClick={handleStop}
      disabled={disabled}
      aria-label={stopped ? 'Run stopped' : 'Stop generation'}
      className="inline-flex items-center gap-1.5 rounded-md border border-[var(--g-error)]/50 bg-red-950/30 px-3 py-1.5 text-xs font-medium text-red-300 transition-colors hover:bg-red-900/40 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {pending ? (
        <Loader2 size={13} className="animate-spin" aria-hidden="true" />
      ) : (
        <Square size={13} className="fill-current" aria-hidden="true" />
      )}
      {stopped ? 'Stopped' : pending ? 'Stopping…' : 'Stop'}
    </button>
  );
}
