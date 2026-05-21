# Direct Manipulation

> Source: Apple Human Interface Guidelines — Direct Manipulation; Nielsen Norman Group Heuristic #7 (User Control and Freedom)

Direct manipulation means people feel they are directly controlling something on screen, not issuing commands to a proxy. Gestures, drag-and-drop, and inline editing create an immediate, tactile connection between intent and result.

## Do examples

1. **Support drag-and-drop for reordering.** Lists, galleries, and kanban boards should allow items to be grabbed and repositioned with immediate visual feedback (the item follows the cursor/finger). Rationale: dragging is cognitively simpler than "move up/move down" buttons.

2. **Enable inline editing where possible.** Clicking a text field makes it editable in-place rather than opening a separate edit modal. Rationale: context switches disrupt flow; inline editing keeps the user in their spatial context.

3. **Provide an undo path for every destructive action.** After deletion or reordering, a toast with "Undo" appears for 5 seconds. Rationale: direct manipulation can lead to accidental changes; undo restores user confidence.

## Don't examples

1. **Don't require form submission for simple toggles.** A dark-mode switch should take effect immediately, not require "Save preferences." Rationale: forcing a save step after a direct manipulation breaks the illusion of directness.

2. **Don't use modals for actions that can be performed inline.** Editing a username should not open a full-screen dialog when a text field expansion suffices. Rationale: modals are appropriate for complex, multi-field edits — not single-value changes.

3. **Don't disable standard platform gestures.** Overriding the back swipe (iOS) or two-finger zoom (web) breaks user expectations. Rationale: platform gestures are muscle memory; hijacking them creates frustration and accessibility barriers.

## Edge case: Direct Manipulation vs. Error Prevention

When direct manipulation allows a destructive action (e.g., dragging a file to trash), error prevention should provide a confirmation step — but only for irreversible actions. For reversible actions, prefer immediate execution with undo. Resolution: classify actions as reversible or irreversible at design time; apply confirmation only to irreversible ones.
