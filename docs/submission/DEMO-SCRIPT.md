# Demo Video Script — Atelier

A ready-to-record storyboard for the DevPost demo video. Target length 2.5-3
minutes. Every claim here matches the running system and `docs/SUBMISSION.md`;
do not voice a capability that is not live (see the "Built with Google Cloud"
split in the submission).

Reference frames captured from the live deployment are in
[`assets/`](assets/): `01-bench-observatory.png`, `02-studio-login.png`,
`03-generated-fintech-onboarding.png`.

Live surfaces for the recording:

- Studio (sign-in + generation): the Cloud Run dashboard URL, Google sign-on.
- Bench Observatory (public, no auth): `https://atelier.autonomous-agent.dev`.

---

## Shot list

### 1. The problem (0:00-0:20)

- **Screen:** the Studio sign-in (`02-studio-login.png`), then the empty brief box.
- **Narration:** "AI design tools regenerate instead of edit, drift off the
  brand's tokens, hide their cost, and take an ambiguous prompt literally.
  Atelier answers each one with architecture, not a bigger prompt."

### 2. Brief, plan, sign-off (0:20-0:50)

- **Screen:** type a brief — "Design a calm onboarding flow for a fintech mobile
  app with a clear primary CTA." Show the planner's proposed plan and the
  sign-off prompt; click approve.
- **Narration:** "It researches the domain, proposes a plan, and pauses for
  human sign-off. The pipeline only proceeds on approval — and a non-destructive
  stop preserves a checkpoint."

### 3. Live generation and convergence (0:50-1:40)

- **Screen:** the generation stream — the D-O-R-A-V scorecard animating per
  iteration (Design, Originality, Relevance, Accessibility, Visual clarity), the
  deterministic gates marking candidates pass/fail, and the live token meter
  ticking with the thinking-token split.
- **Narration:** "Every node is a deterministic gate in front of a probabilistic
  agent — never the reverse. A skeleton or off-token candidate is rejected
  before any judge scores it. The surviving candidates are scored on five axes
  by a judge panel, and the loop iterates until it converges above threshold."
- **Note:** a full run takes 20-30 minutes; for the video, record the stream
  starting, then cut to the converged result (or speed-ramp the wait).

### 4. The deliverable (1:40-2:10)

- **Screen:** the converged design (`03-generated-fintech-onboarding.png`) — the
  calm fintech onboarding with a single clear "Get Started" CTA. Open the token
  panel / the HTML to show it is a real, self-contained, accessible page.
- **Narration:** "The output is a design system — DTCG tokens plus self-contained
  portable HTML — not a screenshot. Change one token and it propagates across
  every surface, a property the token-fidelity gate enforces. This run converged
  at 0.92."

### 5. The moat (2:10-2:40)

- **Screen:** the Bench Observatory (`01-bench-observatory.png`,
  `atelier.autonomous-agent.dev`) — calibration pass rate, the per-judge
  calibration, the D-O-R-A-V composite axes, and the DPO promotion events.
- **Narration:** "Quality is measured, not asserted. The public bench tracks
  calibration against a golden set and an adversarial held-out set, and the
  self-improving flywheel mines accepted-versus-rejected pairs into DPO training
  signal in BigQuery."

### 6. Close (2:40-3:00)

- **Screen:** the repository, then `make verify` running the offline suite.
- **Narration:** "Atelier runs on Google ADK, Gemini on Vertex AI, and Cloud Run.
  Every claim is reproducible: a hermetic offline suite, a byte-identical golden
  trajectory, and a recorded production replay. Nothing in the judged path is
  mocked."

---

## Recording checklist

- [ ] Sign in to the Studio with a Google account before recording (the SSO step
      is not scripted here).
- [ ] Pre-run one generation so a converged result is ready to show without the
      full 20-30 minute wait on camera.
- [ ] Open the Bench Observatory in a second tab in advance.
- [ ] Keep the voiceover to the running-system claims only; the advanced Google
      Cloud backends (Agent Engine, Vertex Sessions, Model Armor, Firestore) are
      integrated but off in the demo deployment — do not claim them as live.
