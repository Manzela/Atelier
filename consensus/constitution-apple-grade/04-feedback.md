# Feedback

> Source: Apple Human Interface Guidelines — Feedback; Nielsen Norman Group Heuristic #1 (Visibility of System Status)

Feedback acknowledges every user action and keeps people informed about what is happening. Interactive elements respond visually to touch. Progress indicators communicate how long an operation will take. Animations provide meaningful context about the result of actions.

## Do examples

1. **Provide immediate visual response on touch/click.** Buttons show a pressed state (scale down, color shift, or ripple) within 100ms of interaction. Rationale: response latency above 100ms feels unresponsive; users may double-tap, causing duplicate actions.

2. **Show determinate progress for operations with known duration.** File uploads, sync operations, and batch processing should display a progress bar with percentage. Rationale: determinate progress reduces perceived wait time by up to 40% compared to spinners.

3. **Confirm successful completion explicitly.** After a form submission, show a success message or transition — don't silently return to the previous state. Rationale: silent success is indistinguishable from a bug; users will resubmit.

## Don't examples

1. **Don't use infinite spinners for operations under 2 seconds.** A brief operation that shows a spinner creates unnecessary anxiety. Use skeleton screens or subtle transitions instead. Rationale: spinners imply "this might take a while" which sets wrong expectations for fast operations.

2. **Don't provide feedback only through color changes.** A field turning red on error is invisible to colorblind users (8% of males). Rationale: feedback must be perceivable through multiple channels — color, text, icon, and position.

3. **Don't delay error feedback until form submission.** Validate fields as they lose focus (onBlur) rather than only on submit. Rationale: batch error display after submit forces the user to scan the entire form to find problems.

## Edge case: Feedback vs. Deference

When feedback demands a prominent notification but deference suggests minimal chrome, use transient feedback (toast, haptic, inline message) that self-dismisses after 3-5 seconds. Persistent feedback banners are reserved for states that require user action (e.g., "Your session will expire in 5 minutes").
