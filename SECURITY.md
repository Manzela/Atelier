# Security Policy

## Supported versions

Atelier follows semantic versioning. Security fixes are backported to:

| Version                             | Supported                                                        |
| ----------------------------------- | ---------------------------------------------------------------- |
| `v1.x.y` (current stable)           | ✅                                                               |
| `v0.x.y` (alpha/beta during sprint) | ⚠️ Best-effort during 2026-05-15 → 2026-06-04 sprint window only |
| `< v0.1.0`                          | ❌                                                               |

## Reporting a vulnerability

**Do not file public GitHub issues for security vulnerabilities.**

Use one of the following private channels:

1. **GitHub Security Advisory** (preferred) — [Open a private security advisory](https://github.com/Manzela/atelier/security/advisories/new). This routes directly to the maintainers with full encryption.
2. **Email** — `security@atelier.dev` (PGP key fingerprint published below)
3. **Encrypted form** — [atelier.dev/security/report](https://atelier.dev/security/report)

Include in your report:

- Description of the vulnerability
- Steps to reproduce
- Impact assessment (what an attacker could do)
- Affected versions
- Suggested mitigation if you have one
- Your name and contact details (for credit, if desired)

We aim to acknowledge reports within **48 hours**, provide an initial triage within **5 business days**, and release a fix within **30 days** for High/Critical severity issues.

## Disclosure policy

We follow **coordinated disclosure**:

- We will work with you on a fix and disclosure timeline.
- We will request a 90-day embargo for High/Critical severity issues to allow downstream consumers to update.
- We will credit you in the security advisory and the release notes (with your permission).
- We do not currently offer monetary bounties but will publicly acknowledge significant contributions in our [Hall of Fame](https://atelier.dev/security/hall-of-fame).

## Severity definitions

| Severity     | Examples                                                                                                                                       | Response time                       |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **Critical** | Remote code execution, authentication bypass, secret exposure across tenants, data exfiltration                                                | 48 hours acknowledgment, 7 days fix |
| **High**     | Privilege escalation within a tenant, persistent XSS in dashboard, judge reward hacking enabling drift, prompt injection bypassing Model Armor | 5 days acknowledgment, 30 days fix  |
| **Medium**   | Information disclosure (non-secret), DoS without amplification, CSRF on non-critical endpoints                                                 | 14 days acknowledgment, 60 days fix |
| **Low**      | Best-practice deviations, non-exploitable misconfigurations                                                                                    | 30 days acknowledgment, 90 days fix |

## Out of scope

- Social engineering of Atelier maintainers
- DoS via resource exhaustion that requires authenticated user privileges (use rate limits)
- Self-XSS requiring victim to paste content into their own console
- Vulnerabilities in third-party dependencies — please report those upstream first; we will track and patch when fixes land
- Vulnerabilities affecting outdated browsers (we support evergreen Chrome/Firefox/Safari/Edge)

## Security architecture

For background on Atelier's defense-in-depth approach, see:

- [PRD §7.5 — Trust + safety + network egress allowlist](docs/superpowers/specs/2026-05-14-atelier-prd.md#75-trust--safety--network-egress-allowlist)
- [ADR 0003 — Tiered sandboxing strategy](docs/decisions/0003-tiered-sandboxing-strategy.md)
- [ADR 0006 — Google-native stack](docs/decisions/0006-google-native-stack-no-langfuse.md) (multi-tenant isolation via IAM Conditions)
- [Runbook: incident response](docs/runbooks/incident-response.md)

## What you can verify yourself

These are reasonable to test against the public production environment with your own tenant — please do not test against other tenants:

- ✅ Sign-up + sign-in flow (Identity Platform)
- ✅ API rate limits per your tenant
- ✅ Output scrubber on your own session output
- ✅ Multi-tenant isolation via your tenant's data only
- ✅ Cost cap enforcement at your tenant's budget

These require explicit written permission (request via the channels above):

- ❌ Penetration testing against shared infrastructure
- ❌ Load testing beyond your tenant's rate limit
- ❌ Testing IAM Conditions cross-tenant boundaries
- ❌ Testing Model Armor bypass attempts (we have automated detection; spurious attempts may trigger account suspension)

## PGP key

Email reports may be encrypted with the following key:

```
Fingerprint: [TO-BE-PUBLISHED-AT-LAUNCH]
Key URL:     https://atelier.dev/security/pgp.asc
```

The PGP key will be published before the v1.0.0 release on 2026-06-03.

## Past security advisories

| Date         | ID  | Severity | Component | Resolution |
| ------------ | --- | -------- | --------- | ---------- |
| _(none yet)_ |     |          |           |            |

## Compliance posture

See [PRD §7.6](docs/superpowers/specs/2026-05-14-atelier-prd.md#76-compliance-roadmap) for the compliance roadmap. At public launch (2026-06-05) we are GDPR-compliant + EU AI Act limited-risk-transparency compliant. SOC 2 Type 2 evidence collection begins day-0 via Vanta; certification target 2026-12.
