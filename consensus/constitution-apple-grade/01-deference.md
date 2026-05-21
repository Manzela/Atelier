# Deference

> Source: Apple Human Interface Guidelines — Deference; Material Design — Surface and Containment

Deference means the interface helps people understand and interact with the content but never competes with it. The UI defers to the content by using translucency, blurs, and minimal chrome — the interface becomes a stage, not the performer.

## Do examples

1. **Use translucent materials for overlays and toolbars.** Frosted-glass effects let background content show through, maintaining spatial context. Rationale: users retain orientation when they can see what's behind a sheet or popover.

2. **Minimize chrome in content-heavy views.** Photo galleries, reading views, and media players should maximize the content area. Navigation and controls recede until needed. Rationale: every pixel of chrome competes with the user's actual content.

3. **Use neutral system backgrounds for container elements.** Cards and sheets use subtle fills (not bold colors) so the content within them is the focal point. Rationale: Apple HIG explicitly warns against "decorating containers" that distract from their payload.

## Don't examples

1. **Don't use heavily branded backgrounds behind user content.** A bright gradient behind a product photo makes the photo harder to evaluate. Rationale: the user's content must be the visual priority, not the app's personality.

2. **Don't make toolbars visually heavier than the content area.** A solid black toolbar with large icons atop a light content area draws the eye upward, away from the task. Rationale: toolbar dominance is a common deference violation in early prototypes.

3. **Don't use animated borders or pulsing elements on passive containers.** Animation signals interactivity. A pulsing card border implies "tap me now" even when no action is required. Rationale: gratuitous animation violates both deference and feedback principles.

## Edge case: Deference vs. Feedback

When deference suggests hiding chrome but feedback requires visible state changes (e.g., a progress bar during upload), feedback wins. Resolution: show feedback elements temporarily, then fade them after the state change completes. The UI defers again once the action is done.
