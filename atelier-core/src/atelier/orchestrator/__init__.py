"""Atelier orchestrator package — pipeline coordination layer.

The orchestrator wires together the 8-node DAG: Generator (N3a),
deterministic gates (N3c), ConsensusAgent (N3d), Fixer (N3e), and
coherence check. Phase 1 ships the gate-runner orchestration only;
full DAG orchestration arrives in Phase 2.
"""
