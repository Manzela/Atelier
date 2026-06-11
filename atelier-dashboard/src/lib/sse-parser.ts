/**
 * Dependency-free incremental Server-Sent-Events parser (L07 / JAM-BUG-1).
 *
 * The previous parser was inlined in `runGenerationStream` and declared the
 * `event:` name (`currentEvent`) INSIDE the per-chunk `while (reader.read())`
 * loop, resetting it on every chunk. When a frame's `event:` line arrived in one
 * TCP/proxy chunk and its (often large) `data:` line completed in the next — which
 * is exactly what happens for `screen_converged` (full HTML) and an untruncated
 * `specialist_trace` — the name was lost and the completed frame dispatched under
 * an empty event type. That hit the `default` branch (`"Unhandled SSE event: "`)
 * and silently dropped the frame, so wireframes never rendered and the terminal
 * `complete` could be missed.
 *
 * The fix is structural: hold both the line `buffer` and the `currentEvent` as
 * INSTANCE state so they persist across `push()` calls (chunk boundaries). The
 * event name is reset only after a `data:` line is emitted (correct intra-frame),
 * never merely because a new network chunk arrived.
 */
export interface SSEFrame {
  /** The SSE `event:` type for this frame ('' only for a genuinely nameless frame). */
  event: string;
  /** The raw `data:` payload string (JSON, not yet parsed). */
  data: string;
}

export class SSEStreamParser {
  private buffer = '';
  private currentEvent = '';

  /**
   * Feed one decoded text chunk; return any complete `data:` frames it produced.
   * A trailing partial line (and the pending event name) is retained for the next
   * chunk, so frames that straddle a chunk boundary are reassembled intact.
   */
  push(chunk: string): SSEFrame[] {
    const frames: SSEFrame[] = [];
    this.buffer += chunk;
    const lines = this.buffer.split('\n');
    // The last element is a possibly-incomplete line — keep it for the next chunk.
    this.buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('event:')) {
        this.currentEvent = trimmed.slice(6).trim();
      } else if (trimmed.startsWith('data:')) {
        frames.push({ event: this.currentEvent, data: trimmed.slice(5).trim() });
        // Reset only after emitting the frame (intra-frame), not per network chunk.
        this.currentEvent = '';
      }
    }
    return frames;
  }
}
