"""Competitive browser UI/UX audit module.

Automates Playwright-based audits comparing Atelier against Tier 1
production-proven agentic AI design products (Stitch, Lovable, v0, Claude).

Usage:
    python -m atelier_eval.competitive_audit --products all --output audit/
    python -m atelier_eval.competitive_audit --products atelier,stitch --lighthouse-only
"""

from atelier_eval.competitive_audit.config import PRODUCTS, AuditConfig, Product

__all__ = ["PRODUCTS", "AuditConfig", "Product"]
