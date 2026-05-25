# ADR 0014: Model Deviation Rationale

**Status:** Accepted
**Date:** 2026-05-25

## Context

The Atelier PRD specifies `gemini-3-flash` for the N1 BriefParserAgent. However, `gemini-2.5-flash-preview-05-20` is currently used in the codebase.

## Decision

We will use `gemini-2.5-flash-preview-05-20` instead of `gemini-3-flash`.

## Rationale

`gemini-3-flash` is not yet available in the Vertex AI Model Garden for our current GCP region (`us-central1`). We fall back to the most advanced available flash model (`gemini-2.5-flash-preview-05-20`) to ensure unblocked development and to meet the Sprint D14 deployment deadline. We will upgrade to `gemini-3-flash` once it enters GA.
