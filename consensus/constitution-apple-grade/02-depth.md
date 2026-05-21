# Depth

> Source: Apple Human Interface Guidelines — Depth; Material Design — Elevation System

Depth provides visual layers and realistic motion that convey hierarchy and facilitate understanding. Distinct layers create a sense of place: content in the foreground, supporting elements behind. Transitions use physics-based motion to communicate spatial relationships.

## Do examples

1. **Use elevation to distinguish interactive layers.** Modals, sheets, and popovers cast shadows proportional to their z-distance from the base layer. Rationale: shadow depth communicates which element is "on top" and will receive input, reducing accidental taps.

2. **Animate transitions between layers with physics-based easing.** When a sheet slides up from the bottom, it decelerates naturally (ease-out). Rationale: physics-based motion feels predictable; linear motion feels mechanical and disorienting.

3. **Use parallax scrolling sparingly to reinforce spatial hierarchy.** Background elements move slower than foreground content during scroll. Rationale: parallax creates a 2.5D effect that helps users understand content is layered, but overdone parallax causes motion sickness.

## Don't examples

1. **Don't flatten all elements to the same visual plane.** Without depth cues, users cannot distinguish a floating action button from a static label. Rationale: flat designs require compensating cues (borders, color contrast); depth provides this naturally.

2. **Don't use inconsistent shadow directions.** If one card casts a shadow to the bottom-right and another to the top-left, the spatial model breaks. Rationale: a single consistent light source is fundamental to believable depth.

3. **Don't animate depth changes without a user-initiated trigger.** Elements that spontaneously elevate or sink create visual noise. Rationale: depth changes should map to user actions (tap, long-press) or system state changes (loading complete).

## Edge case: Depth vs. Clarity

When depth effects (blur, shadow, parallax) reduce text legibility, clarity wins. Resolution: blur effects behind text must preserve contrast ratios. Use a semi-opaque overlay between blurred content and text if needed.
