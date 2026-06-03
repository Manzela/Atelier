'use client';

/**
 * AT-041 — KanbanBoard.
 *
 * The board orchestrator. It:
 *   1. Subscribes to the project's §7A.5 task docs via Firestore `onSnapshot`
 *      (firestore-board.ts). The lane is live — as the AT-020b autonomous run
 *      drives the lead card through the exact ordered 6-column set, the board
 *      re-renders with no polling and no push.
 *   2. Groups cards by `columnId` and sorts each column by LexoRank.
 *   3. Persists a MANUAL move (mouse drag OR keyboard pick-up + arrows): it
 *      computes a fresh LexoRank BETWEEN the destination column's neighbours and
 *      writes it back via `updateTaskColumn`. The move is optimistic (the card
 *      jumps immediately); the `onSnapshot` echo reconciles it.
 *
 * Failure trichotomy: the board is an observability surface. A subscription
 * error or a failed move write FAILS SOFT — it is surfaced as an acknowledged
 * banner (never a silent swallow, never a crash). The agent always acknowledges
 * degradation (R9).
 *
 * Accessibility: every card is a focusable `<button>` (keyboard-operable move —
 * pick up with Enter/Space, move with arrows, drop with Enter/Space, cancel with
 * Escape). Live move announcements go to an `aria-live` region. The axe bar is
 * 0 critical/serious.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  subscribeTasks,
  updateTaskColumn,
  BOARD_COLUMNS,
  type BoardColumnId,
  type BoardTask,
} from '@/lib/firestore-board';
import { generateRank, compareRanks } from '@/lib/lexorank';
import KanbanColumn from './KanbanColumn';
import KanbanCard from './KanbanCard';

export interface KanbanBoardProps {
  tenantId: string;
  projectId: string;
}

/** Per-column, rank-sorted view of the live task collection. */
function groupByColumn(tasks: BoardTask[]): Record<BoardColumnId, BoardTask[]> {
  const grouped = Object.fromEntries(BOARD_COLUMNS.map((c) => [c, [] as BoardTask[]])) as Record<
    BoardColumnId,
    BoardTask[]
  >;
  for (const task of tasks) {
    grouped[task.columnId]?.push(task);
  }
  for (const col of BOARD_COLUMNS) {
    grouped[col].sort((a, b) => compareRanks(a.rank, b.rank));
  }
  return grouped;
}

export default function KanbanBoard({ tenantId, projectId }: KanbanBoardProps) {
  const [tasks, setTasks] = useState<BoardTask[]>([]);
  const [ready, setReady] = useState(false);
  const [degraded, setDegraded] = useState<string | null>(null);
  // Keyboard move source: the picked-up card id, or null when nothing is held.
  const [pickedUp, setPickedUp] = useState<string | null>(null);
  // Mouse drag source (native HTML5 DnD).
  const draggingId = useRef<string | null>(null);
  const [dropTarget, setDropTarget] = useState<BoardColumnId | null>(null);
  // aria-live announcement for the keyboard move.
  const [announcement, setAnnouncement] = useState('');

  // 1) Live subscription. Cleanup on unmount (no leaked listener).
  useEffect(() => {
    const unsubscribe = subscribeTasks(
      tenantId,
      projectId,
      (next) => {
        setTasks(next);
        setReady(true);
      },
      (error) => {
        // Fail-soft: acknowledge the degradation; do not crash the board.
        console.error('[KanbanBoard] task subscription error:', error);
        setDegraded('Live updates are degraded — the board may be stale.');
        setReady(true);
      }
    );
    return unsubscribe;
  }, [tenantId, projectId]);

  const grouped = useMemo(() => groupByColumn(tasks), [tasks]);

  /**
   * Persist a card move to a destination column. Computes a LexoRank that sorts
   * AFTER the current last card in the destination column (append to its tail),
   * which is always strictly between the existing neighbours and the conceptual
   * end — the §7A.5 "between-neighbours" insert. Optimistic + fail-soft.
   */
  const persistMove = useCallback(
    async (taskId: string, destination: BoardColumnId) => {
      const source = tasks.find((t) => t.task_id === taskId);
      if (!source || source.columnId === destination) return;

      const destCards = grouped[destination];
      const tail = destCards.length > 0 ? destCards[destCards.length - 1].rank : null;
      // Insert at the column tail: between the last card and the end (no `after`).
      const newRank = generateRank(tail, null);

      // Optimistic local update so the card moves immediately (no flicker waiting
      // on the round-trip); the onSnapshot echo reconciles.
      setTasks((prev) =>
        prev.map((t) => (t.task_id === taskId ? { ...t, columnId: destination, rank: newRank } : t))
      );
      setAnnouncement(`Moved ${taskId} to ${destination}.`);

      try {
        await updateTaskColumn(tenantId, projectId, taskId, {
          columnId: destination,
          rank: newRank,
        });
      } catch (error) {
        // Fail-soft: the move did not land. Acknowledge it (R9) — never swallow.
        console.error('[KanbanBoard] move persistence failed:', error);
        setDegraded(`Could not save the move of ${taskId} — it may revert.`);
      }
    },
    [tasks, grouped, tenantId, projectId]
  );

  // --- Keyboard move (a11y path) -----------------------------------------------
  const togglePickUp = useCallback(
    (taskId: string) => {
      setPickedUp((cur) => {
        if (cur === taskId) {
          setAnnouncement(`Dropped ${taskId}.`);
          return null; // drop in place
        }
        const task = tasks.find((t) => t.task_id === taskId);
        setAnnouncement(
          task
            ? `Picked up ${taskId} from ${task.columnId}. Use left and right arrows to choose a column, Enter to drop.`
            : `Picked up ${taskId}.`
        );
        return taskId;
      });
    },
    [tasks]
  );

  const cancelMove = useCallback(() => {
    setPickedUp((cur) => {
      if (cur) setAnnouncement(`Cancelled moving ${cur}.`);
      return null;
    });
  }, []);

  const movePickedUp = useCallback(
    (direction: -1 | 1) => {
      if (!pickedUp) return;
      const task = tasks.find((t) => t.task_id === pickedUp);
      if (!task) return;
      const curIdx = BOARD_COLUMNS.indexOf(task.columnId);
      const nextIdx = curIdx + direction;
      if (nextIdx < 0 || nextIdx >= BOARD_COLUMNS.length) return; // clamp at edges
      void persistMove(pickedUp, BOARD_COLUMNS[nextIdx]);
    },
    [pickedUp, tasks, persistMove]
  );

  // --- Mouse drag (native HTML5 DnD) -------------------------------------------
  const handleDragStart = useCallback((taskId: string) => {
    draggingId.current = taskId;
  }, []);

  const handleDropTask = useCallback(
    (column: BoardColumnId) => {
      const taskId = draggingId.current;
      draggingId.current = null;
      setDropTarget(null);
      if (taskId) void persistMove(taskId, column);
    },
    [persistMove]
  );

  return (
    <div data-testid="kanban-board" className="stitch-grid-bg flex h-full w-full flex-col">
      {/* aria-live announcer for the keyboard move (visually hidden). */}
      <div aria-live="polite" className="sr-only" data-testid="kanban-announcer">
        {announcement}
      </div>

      <div className="flex items-center justify-between gap-4 border-b border-[var(--g-outline)] px-5 py-3">
        <div>
          <h1 className="text-[15px] font-semibold text-[var(--g-text)]">Board</h1>
          <p className="text-[12px] text-[var(--g-text-muted)]">
            Live task pipeline — each card moves through the six stages as the run advances.
          </p>
        </div>
        {!ready && (
          <span
            data-testid="kanban-loading"
            className="text-[12px] text-[var(--g-text-muted)]"
            role="status"
          >
            Connecting…
          </span>
        )}
      </div>

      {/* Acknowledged degradation banner (R9) — never a silent failure. */}
      {degraded && (
        <div
          role="status"
          data-testid="kanban-degraded"
          className="flex items-start gap-2 border-b border-[var(--g-warning)]/40 bg-[var(--g-warning)]/10 px-5 py-2.5"
        >
          <AlertTriangle
            size={14}
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-[var(--g-warning)]"
          />
          <p className="text-[11px] text-[var(--g-text-muted)]">{degraded}</p>
        </div>
      )}

      <div className="flex flex-1 gap-3 overflow-x-auto p-4">
        {BOARD_COLUMNS.map((column) => (
          <KanbanColumn
            key={column}
            column={column}
            tasks={grouped[column]}
            isDropTarget={dropTarget === column}
            onDropTask={handleDropTask}
            onDragOverColumn={setDropTarget}
            onDragLeaveColumn={() => setDropTarget(null)}
          >
            {grouped[column].map((task) => (
              <li key={task.task_id}>
                <KanbanCard
                  task={task}
                  isPickedUp={pickedUp === task.task_id}
                  onTogglePickUp={togglePickUp}
                  onCancelMove={cancelMove}
                  onMove={movePickedUp}
                  onDragStart={handleDragStart}
                />
              </li>
            ))}
          </KanbanColumn>
        ))}
      </div>
    </div>
  );
}
