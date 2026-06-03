'use client';

/**
 * AT-041 — KanbanCard.
 *
 * One board card = one §7A.5 task doc. It shows the active `agentRole` and the
 * `statusLine` (which, on the Generating column, carries the active role per U6).
 *
 * The card is the move handle. It is a real, focusable `<button>`, so it is
 * keyboard-operable out of the box (the axe bar requires this): focus it, press
 * Enter/Space to PICK IT UP, ArrowLeft/ArrowRight to choose a destination column,
 * Enter/Space to DROP, Escape to cancel. Mouse users get native HTML5 drag in
 * parallel (draggable=true). The keyboard contract is owned by the parent board
 * (it tracks the picked-up card + listens for arrows); the card only reports its
 * own pick-up / drag-start so the board knows which card is in flight.
 */
import React from 'react';
import { GripVertical, UserCog } from 'lucide-react';
import type { BoardTask } from '@/lib/firestore-board';

export interface KanbanCardProps {
  task: BoardTask;
  /** True while THIS card is the picked-up (keyboard) move source. */
  isPickedUp: boolean;
  /** Request to pick up / drop this card (keyboard Enter/Space toggle). */
  onTogglePickUp: (taskId: string) => void;
  /** Cancel an in-flight keyboard move (Escape). */
  onCancelMove: () => void;
  /** Move the picked-up card one column left/right (keyboard arrows). */
  onMove: (direction: -1 | 1) => void;
  /** Native HTML5 drag start (mouse) — report which card is dragging. */
  onDragStart: (taskId: string) => void;
}

function KanbanCardImpl({
  task,
  isPickedUp,
  onTogglePickUp,
  onCancelMove,
  onMove,
  onDragStart,
}: KanbanCardProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    switch (e.key) {
      case 'Enter':
      case ' ':
        e.preventDefault();
        onTogglePickUp(task.task_id);
        break;
      case 'Escape':
        if (isPickedUp) {
          e.preventDefault();
          onCancelMove();
        }
        break;
      case 'ArrowRight':
        if (isPickedUp) {
          e.preventDefault();
          onMove(1);
        }
        break;
      case 'ArrowLeft':
        if (isPickedUp) {
          e.preventDefault();
          onMove(-1);
        }
        break;
      default:
        break;
    }
  };

  return (
    <button
      type="button"
      data-testid={`kanban-card-${task.task_id}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', task.task_id);
        onDragStart(task.task_id);
      }}
      onKeyDown={handleKeyDown}
      onClick={() => onTogglePickUp(task.task_id)}
      aria-pressed={isPickedUp}
      aria-label={
        isPickedUp
          ? `${task.agentRole} card picked up. Use left and right arrows to choose a column, Enter to drop, Escape to cancel.`
          : `${task.agentRole} card. Press Enter to pick up and move with the arrow keys.`
      }
      className={[
        'group w-full cursor-grab rounded-md border bg-[var(--g-bg)]/60 p-3 text-left',
        'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--g-primary-blue)]',
        isPickedUp
          ? 'border-[var(--g-primary-blue)] ring-2 ring-[var(--g-primary-blue)] cursor-grabbing'
          : 'border-[var(--g-outline)] hover:border-[var(--g-text-muted)] hover:bg-[var(--g-surface-hover)]',
      ].join(' ')}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--g-info)]">
          <UserCog size={12} aria-hidden="true" className="shrink-0" />
          <span className="font-mono">{task.agentRole}</span>
        </span>
        <GripVertical
          size={14}
          aria-hidden="true"
          className="shrink-0 text-[var(--g-text-muted)] opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
        />
      </div>
      <p
        data-testid={`kanban-card-${task.task_id}-status`}
        className="text-[12px] leading-snug text-[var(--g-text)]"
      >
        {task.statusLine}
      </p>
      <p className="mt-1.5 font-mono text-[10px] text-[var(--g-text-muted)]">{task.task_id}</p>
    </button>
  );
}

const KanbanCard = React.memo(KanbanCardImpl);
KanbanCard.displayName = 'KanbanCard';
export default KanbanCard;
