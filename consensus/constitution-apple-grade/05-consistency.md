# Consistency

> Source: Apple Human Interface Guidelines — Consistency; Nielsen Norman Group Heuristic #4 (Consistency and Standards)

Consistency means that the interface follows platform conventions, uses familiar patterns, and applies the same visual and interaction rules throughout. Users transfer their existing knowledge; the interface doesn't force them to relearn.

## Do examples

1. **Follow platform navigation conventions.** iOS apps use tab bars at the bottom; Android apps use navigation drawers or bottom navigation. Web apps use a persistent sidebar or top navigation bar. Rationale: violating platform conventions adds cognitive load for every user.

2. **Use the same component style for the same semantic role.** All primary CTAs share the same button style (color, border-radius, padding). All destructive actions share a distinct style (e.g., red outline). Rationale: semantic consistency allows users to predict behavior from appearance.

3. **Maintain consistent terminology across the interface.** If "Projects" is the term in the sidebar, don't call them "Workspaces" in the settings page. Rationale: synonyms create doubt about whether two labels refer to the same concept.

## Don't examples

1. **Don't mix interaction patterns within the same view.** If some list items are tappable and others are not, users will try tapping all of them and feel frustrated when some don't respond. Rationale: inconsistent affordance creates confusion and error-prone exploration.

2. **Don't change the position of persistent navigation elements.** A floating action button that moves between screens breaks spatial memory. Rationale: users build motor habits around element positions; moving targets increase error rates.

3. **Don't use different date formats across the application.** "Jan 15, 2026" in one view and "2026-01-15" in another forces mental translation. Rationale: format inconsistency adds cognitive overhead to every comparison.

## Edge case: Consistency vs. Clarity

When platform convention (consistency) uses an ambiguous icon but a custom icon would be clearer, prefer the platform convention for common actions (e.g., share icon) and the clearer custom icon for domain-specific actions. Resolution: use platform icons for the 20 most common actions; use labeled custom icons for domain-specific functions.
