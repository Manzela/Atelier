# Apple-Grade Design Constitution (CSC-D N6)

> **Visual Register**: Editorial / Corporate / Dense-Data
> **When applied**: Default constitution when `BriefSpec.visual_register` is NOT `brutalist`

## Design Principles

### 1. Clarity Above All

Every element serves a purpose. Remove anything that doesn't contribute to
the user's task. Empty space is a design tool, not wasted space.

### 2. Consistency is Trust

- Use the design system's tokens — never deviate for "creative reasons"
- Typography scale: strict adherence to the type ramp
- Color usage: semantic colors only (error=red, success=green, info=blue)
- Spacing: multiples of the base unit (4px or 8px)

### 3. Hierarchy Through Typography

- One hero element per viewport
- Clear reading order: title → subtitle → body → action
- Contrast ratios: ≥ 4.5:1 for text, ≥ 3:1 for large text

### 4. Motion with Purpose

- Transitions: 200-300ms ease-out (never bounce or overshoot)
- Animate state changes, not decorations
- Respect `prefers-reduced-motion`

### 5. Accessibility is Non-Negotiable

- Keyboard navigable: all interactive elements focusable + visible focus ring
- Screen reader compatible: semantic HTML + ARIA where needed
- Touch targets: ≥ 44×44px

### 6. Performance is UX

- First Contentful Paint: < 1.5s
- Largest Contentful Paint: < 2.5s
- Cumulative Layout Shift: < 0.1

## Anti-Patterns (REJECTED)

- ❌ Decorative gradients that don't convey information
- ❌ Carousel/slider as primary navigation
- ❌ Auto-playing media without user consent
- ❌ Modal dialogs for non-critical information
- ❌ Custom scrollbars that break native behavior
- ❌ Text over images without sufficient overlay contrast
