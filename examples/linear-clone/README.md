# Atelier live generation — Linear clone (reference example / debug case)

First-shot live run against production (`atelier-api-staging`, rev 00030-hut, all 9 V1 features). 2714s (~45 min) wall.

## Verdict: did NOT converge — but NOT a design failure. The run hit the per-user 5M token cap mid-judging

| field                               | value                                                                           |
| ----------------------------------- | ------------------------------------------------------------------------------- |
| session_id                          | `a1f329dd-06de-4787-ba46-04a41e4be9a0`                                          |
| converged                           | **False**                                                                       |
| composite_score                     | 0.0 (no candidate scored)                                                       |
| candidates generated / passed gates | 6 / 0                                                                           |
| candidate composite_scores          | all `None` — **never scored** (judging was cut off)                             |
| tokens_used                         | **5,911,768** (> the 5,000,000 per-user cap, AT-095)                            |
| user_message                        | "You've reached this account's usage limit. Contact administrator to continue." |
| degraded (Stitch)                   | False                                                                           |

### Root cause

The convergence loop generated all **6 design candidates** (the HTML in `output.html` is one of them, used as the N4 best-fallback), but the **per-user 5M-token governance cap (AT-095) fired during the N3d judging phase**, before any candidate could be scored against the D-O-R-A-V gates. So `composite_score` is `None` for every candidate → 0 passed → `converged=False`. The cap is a fail-loud security/governance control and it fired correctly; this is a _budget_ outcome, not a _quality_ outcome.

### Two findings to debug

1. **Token economics:** a maximally-ambitious brief (1:1 Linear, multi-screen) drives ~5.9M tokens through 6 candidates × the 6-role DDLC specialist pipeline + judging — over the 5M cap. Such briefs cannot converge first-shot under default governance. Levers: raise the cap for a power/agency tier; cut candidate count or judging cost; or have the clarify gate (AT-030) flag over-scoped briefs.
2. **Scope/completeness:** the converged candidate renders ONE screen (the Issues list view) faithfully — it does not render the Board, issue-detail panel, ⌘K palette, or Cycle view that the brief also requested. Multi-screen output is a product gap.

### Design quality (the generated candidate — see screenshot.png)

Strong and faithful: dark Linear aesthetic, sidebar (Acme Corp workspace switcher, indigo "New Issue ⌘C", Views / Projects / Engineering sections), status-grouped issues (In Progress / Todo) with priority icons, issue IDs (PRO-123, DES-42), assignee avatars, and timestamps. Nits: only ~3 issues populated; Backlog/Done/Canceled groups empty; avatar `<img>`s reference external URLs that 404.

## Files

- `brief.md` — exact brief submitted (292 words)
- `output.html` — the best candidate (open in a browser; serve over http, not file://)
- `screenshot.png` — rendered at 1440px
- `response.json` — full `/v1/generate` response (incl. all 6 candidate summaries)
- `trajectory.json` — NOT saved: `/v1/replay/{sid}` 404s right after generation (BigQuery trajectory write lags a few seconds); re-fetch later if needed

## To get a converged result

Raise the per-user token cap above ~6M for the eval user (governance config on the API) and re-run the same brief (~45 min), OR scope the brief to a single screen.
