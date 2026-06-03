'use client';

/**
 * AT-041 — KanbanColumn.
 *
 * One lane of the fixed, ordered 6-column set. It is a labelled region (an
 * `aria-label` naming the canonical column — the test asserts the exact ordered
 * set via these labels) and the native HTML5 drop target for a mouse drag. The
 * cards inside are already sorted by LexoRank by the parent board.
 */
import React from 'react';
import type { BoardColumnId, BoardTask } from '@/lib/firestore-board';

export interface KanbanColumnProps {
  column: BoardColumnId;
  tasks: BoardTask[];
  /** True while a card is being dragged over this column (mouse). */
  isDropTarget: boolean;
  /** Native HTML5 drop onto this column. */
  onDropTask: (column: BoardColumnId) => void;
  onDragOverColumn: (column: BoardColumnId) => void;
  onDragLeaveColumn: () => void;
  children: React.ReactNode;
}

function KanbanColumnImpl({
  column,
  tasks,
  isDropTarget,
  onDropTask,
  onDragOverColumn,
  onDragLeaveColumn,
  children,
}: KanbanColumnProps) {
  // testid uses the canonical column name with spaces hyphenated, so
  // "Awaiting Sign-off" -> "kanban-column-Awaiting-Sign-off".
  const testId = `kanban-column-${column.replace(/\s/g, '-')}`;
  const headingId = `${testId}-heading`;

  return (
    <section
      data-testid={testId}
      aria-label={`${column} column`}
      aria-describedby={headingId}
      onDragOver={(e) => {
        // Allow drop: preventDefault is required for onDrop to fire.
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        onDragOverColumn(column);
      }}
      onDragLeave={onDragLeaveColumn}
      onDrop={(e) => {
        e.preventDefault();
        onDropTask(column);
      }}
      className={[
        'flex h-full min-w-[240px] flex-1 flex-col rounded-lg border bg-[var(--g-surface)]/50 transition-colors',
        isDropTarget
          ? 'border-[var(--g-primary-blue)] bg-[var(--g-primary-blue)]/5'
          : 'border-[var(--g-outline)]',
      ].join(' ')}
    >
      <header className="flex items-center justify-between gap-2 border-b border-[var(--g-outline)] px-3 py-2.5">
        <h2
          id={headingId}
          className="text-[12px] font-semibold uppercase tracking-wider text-[var(--g-text)]"
        >
          {column}
        </h2>
        <span
          aria-label={`${tasks.length} ${tasks.length === 1 ? 'card' : 'cards'}`}
          className="inline-flex min-w-[20px] items-center justify-center rounded-full border border-[var(--g-outline)] px-1.5 py-0.5 text-[10px] font-mono tabular-nums text-[var(--g-text-muted)]"
        >
          {tasks.length}
        </span>
      </header>
      <ul className="flex flex-1 flex-col gap-2 overflow-y-auto p-2.5">
        {tasks.length === 0 ? (
          <li className="select-none rounded-md border border-dashed border-[var(--g-outline)] px-3 py-6 text-center text-[11px] text-[var(--g-text-muted)]">
            No cards
          </li>
        ) : (
          children
        )}
      </ul>
    </section>
  );
}

const KanbanColumn = React.memo(KanbanColumnImpl);
KanbanColumn.displayName = 'KanbanColumn';
export default KanbanColumn;
