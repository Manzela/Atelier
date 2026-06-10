# Atelier — Business Case

Atelier is a governed autonomous design agent: from a natural-language brief it
researches the domain, plans, pauses for human sign-off, then generates, judges,
and iterates a production-grade design system — and refuses to ship work that
fails its gates.

## The problem

Design systems are where brand, accessibility, and engineering velocity meet, and
they are expensive to build and even harder to keep consistent at scale. The
current generation of AI design tools does not solve this for an organization that
has standards to enforce. They share four structural failures:

- they regenerate instead of edit, so iteration discards prior work;
- they drift off the brand's tokens, because nothing enforces them;
- they hide their cost, which is untenable on a metered model API;
- and they take an ambiguous brief literally, with no plan and no sign-off.

For a team that owns a design system, the result is output that still needs a
designer and a reviewer to make it safe to ship. The autonomy is cosmetic.

## Who it is for

The primary customer is the **enterprise design-system / design-operations team** —
the group accountable for brand-token fidelity, accessibility compliance, and
consistency across many product surfaces. Their pain is not "draw me a screen";
it is "produce surfaces that already conform to our system, prove they conform,
and let me sign off before anything ships." Atelier's architecture maps to that
pain directly: token fidelity is enforced, accessibility is gated by axe-core, and
the pipeline halts for human approval by design.

## The category: governed autonomous design

Atelier does not compete with ungoverned generators (Stitch, v0, Lovable,
Figma AI) on raw output. It defines a different category — **governed autonomous
design** — distinguished by three properties those tools structurally lack:

1. **Deterministic-gate-first.** Every node is a deterministic gate in front of a
   probabilistic agent, never the reverse. An empty, skeleton, or off-token
   candidate is rejected before any judge scores it; the gate battery (semantic
   HTML, contrast, accessibility, token fidelity, performance, visual diff) runs
   on every candidate. The system fails closed.
2. **Measured, not asserted, quality.** Candidates are scored on five axes
   (Design, Originality, Relevance, Accessibility, Visual clarity) by a judge
   panel, gated by the deterministic floor, and tracked on a public bench against
   a golden and an adversarial held-out set.
3. **Governed autonomy.** A per-user token cap is enforced server-side before any
   model call; a live meter shows used-versus-remaining; a Model Armor callback
   guards every model call; and the agent acknowledges degradation rather than
   failing silently. These are the controls that let a regulated enterprise
   actually deploy an autonomous agent.

## The wedge: a first-class citizen of the Google agent stack

Atelier's sharpest differentiator is that it is **ADK-native and Agent-Garden
deployable end to end**, not a wrapper around a single model call. The pipeline is
a Google ADK agent graph; every agent and sub-agent — the planner, the brief
parser, the six DDLC specialists, the fixer, the five judges, and the four
critics — carries its own A2A 0.3.0 agent card and a Discovery Engine registration
payload, so each is independently discoverable and deployable to the Gemini
Enterprise Agent Gallery. It runs on Gemini on Vertex AI, Cloud Run, Firebase,
and BigQuery, with Vertex Agent Engine, Sessions and Memory Bank, and Model Armor
integrated as configuration-selectable backends.

For an enterprise already standardizing on Google's agent platform, that means
Atelier is not a silo: its agents register alongside the rest of the organization's
fleet, speak A2A, and are governed by the same platform controls. The moat is
interoperability plus governance, not a prompt.

## Market

The directly comparable category — generative AI applied to design — is a **~$1.0B
market in 2025 growing to ~$16.9B by 2035 (~32.8% CAGR)** ([Precedence Research, Jan
2026](https://www.precedenceresearch.com/generative-ai-in-design-market)), riding the
broader enterprise shift to agent platforms that Gartner projects will reach **~30% of
enterprise application-software revenue by 2035**, up from ~2% in 2025 (Gartner, Aug
2025, via [Process Excellence Network](https://www.processexcellencenetwork.com/ai/news/gartner-40-percent-of-enterprise-apps-will-feature-task-specific-ai-agents-by-2026)).

Atelier's serviceable wedge is bottom-up. Of the **~24,400 US firms with 1,000+
employees** ([NAICS, 2024](https://www.naics.com/business-lists/counts-by-company-size/)),
roughly **57% run a dedicated design-system team** ([Forrester for Adobe, 2021](https://blog.adobe.com/en/publish/2021/05/26/best-practices-to-scale-design-with-design-systems);
directional, vendor-sponsored) — on the order of **~13,900 enterprise buyer accounts in
the US alone**, a serviceable market of roughly a billion dollars per year at enterprise
ACVs before any global expansion. The binding constraint is category maturity and
willingness-to-pay, not the size of the addressable base. (The per-account ACV and the
global extension are our estimates, not sourced figures.)

## Business model

Pricing is **usage-based** — per converged design (or per metered token-operation
for high-volume API use). Two properties make this the right model:

- It aligns price to delivered value. A converged design is a reviewed,
  gate-passing, on-brand surface plus its design tokens — a unit of work that
  otherwise consumes designer and reviewer hours.
- The unit economics are metered, not guessed. Every run is metered end to end by the
  same server-side counter that enforces the token cap and powers the live meter, so
  cost of goods per converged design is computed from measured token consumption at the
  published Vertex serving rate — and it is bounded, because every run terminates at a
  deterministic stop (converged, max-iterations, or per-user cap). Quality is reported
  on the public bench; the per-design cost ledger is computed from that same metering.

A platform tier (self-host / VPC plus the embedding API) serves the largest
enterprise accounts where the registration-and-governance story is the buying
reason; consumption is the metering underneath it.

## Why now, and the moat

Two shifts make this the moment: enterprises are standardizing on a managed agent
platform (ADK / Vertex Agent Engine / the Agent Gallery), and they will not deploy
autonomous agents they cannot govern. Atelier is built for exactly that
intersection.

The defensibility compounds. Every accepted-versus-rejected pair the system
produces is mined into DPO preference signal in BigQuery — a self-improving
flywheel that makes the judges and the generator better the more the product is
used, on data no competitor has. Governance plus interoperability is the wedge;
the flywheel is the moat that widens with adoption.

---

_Production-readiness and the Google Cloud architecture are detailed in
[`SUBMISSION.md`](../SUBMISSION.md); the demo walkthrough is in
[`DEMO-SCRIPT.md`](DEMO-SCRIPT.md)._
