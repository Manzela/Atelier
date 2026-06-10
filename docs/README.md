# Atelier Documentation Index

This directory contains the design documentation, architecture specifications, and runbooks for Atelier.

## Reading Order for Technical Auditors

To understand the system design, implementation details, and operational model, review the documents in the following sequence:

1. **Architecture Overview** ([architecture/README.md](architecture/README.md)) — Summarizes the system pillars, architectural goals, and directory mappings.
2. **System Pillars**
   - **Govern Pillar** ([architecture/govern-pillar.md](architecture/govern-pillar.md)) — Details the six layers of safety controls, Firebase Auth, Identity-Aware Proxy (IAP), token caps, and OpenTelemetry PII scrubbing.
   - **Optimize Pillar** ([architecture/optimize-pillar.md](architecture/optimize-pillar.md)) — Details the DPO preference-pair learning model, BigQuery trajectory storage, and Vertex AI fine-tuning pipeline.
3. **Architecture Decision Records (ADRs)** ([decisions/](decisions/)) — Contains point-in-time design trade-offs and decisions, including:
   - [ADR-0024: Governed A2UI](decisions/0024-governed-a2ui.md)
   - [ADR-0025: Generation Latency](decisions/0025-generation-latency.md)
   - [ADR-0026: OpenAPI Production Gating](decisions/0026-openapi-prod-gated.md)
4. **Operations & Runbooks** ([runbooks/README.md](runbooks/README.md)) — Details how to manage production deployments, updates, and recovery procedures:
   - [Go-Live Operations Runbook](runbooks/go-live.md)
   - [Rollback Operations Runbook](runbooks/rollback.md)
5. **Technical Style Guide** ([STYLE.md](STYLE.md)) — Specifies guidelines for writing documentation, comments, and code formatting to maintain repo hygiene.
6. **Submission Reference** ([SUBMISSION.md](SUBMISSION.md)) — The operator checklists and details for the Google AI Agents Challenge 2026.

## Subpackage Map

Atelier is organized as a monorepo containing the following components:

- **[atelier-core](../atelier-core/)**: Core Python engine containing the 8-node DAG orchestrator, specialist pipeline nodes, D-O-R-A-V judge panel, and API routing.
- **[atelier-eval](../atelier-eval/)**: Evaluation suite for testing convergence across the golden set, measuring calibrator agreement, and generating adapter evaluations.
- **[atelier-deploy](../atelier-deploy/)**: Infrastructure-as-code configuration containing Terraform manifests, Dockerfiles, and deployment scripts for Cloud Run, IAP, KMS, and BigQuery.
- **[atelier-dashboard](../atelier-dashboard/)**: Next.js user dashboard providing design workspace orchestration, visual iframe rendering, and time-machine reviews.
- **[atelier-figma-plugin](../atelier-figma-plugin/)**: Figma integration plugin enabling export of briefs and token overrides directly into the workspace.
- **[atelier-chrome-extension](../atelier-chrome-extension/)**: Browser extension facilitating live design extraction, client-side overrides, and quick-access telemetry.
- **[atelier-action](../atelier-action/)**: GitHub Action allowing teams to run intake, design verification, and convergence tests during continuous integration.
