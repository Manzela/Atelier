# Claude Opus 4.6 (Thinking) — Best Practices Playbook

> **Sources**:
>
> 1. [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
> 2. [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
> 3. [Harness Design for Long-Running Apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
> 4. [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
> 5. [Writing Tools for Agents (ACI)](https://www.anthropic.com/engineering/writing-tools-for-agents)
> 6. [Claude 4 Prompting Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
> 7. [PipelineCodeReview.md](file:///Users/danielmanzela/Developer/PRODUCT/Base%20Prompts/PipelineCodeReview.md) — Production review prompt

---

## 1. Core Architectural Patterns (Workflows vs. Agents)

> **Guiding Principle:** Favor simplicity. Start with basic workflows before escalating to full agentic autonomy. Avoid heavy, opaque frameworks; prefer explicit orchestration with raw code.

### 1.1 The Six Composable Patterns

1. **Augmented Generation:** Fetching context via tools (RAG) before generation.
2. **Prompt Chaining:** Breaking linear tasks into sequential LLM calls, passing the output of one as context to the next.
3. **Routing:** Classifying input upfront to direct it to a specialized downstream prompt or agent.
4. **Parallelization:** Sectioning tasks simultaneously (e.g., scoring multiple chunks concurrently) to reduce latency and aggregate results.
5. **Orchestrator-Workers:** A central "brain" LLM maps out sub-tasks, delegates them to scoped worker LLMs in parallel, and synthesizes their outputs.
6. **Evaluator-Optimizer Loop:** A generator LLM drafts an output, an independent evaluator LLM critiques it against criteria, and the cycle repeats until thresholds are met.

### 1.2 When to Use What

- Use **Workflows** (Patterns 1-4) for predictable, well-defined tasks.
- Use **Agents** (Patterns 5-6 + Long-Running loops) when tasks require flexibility, exploration, and dynamic decision-making at scale.

---

## 2. Agent-Computer Interface (ACI) & Tool Design

Tools are the bridges between the LLM and your environment. Treat the LLM like a sharp but literal-minded junior developer.

### 2.1 Poka-yoke (Mistake-Proofing)

- **Simplify parameters:** Avoid deep JSON nesting unless completely unavoidable. Enforce specific `enums` or data shapes.
- **Fail gracefully with instructions:** If a tool fails (e.g., file not found, API timeout), do not just return a stack trace. Return a string analyzing _why_ it failed and explicitly stating _what the agent should try next_.

### 2.2 Naming and Documentation

- **Descriptive Naming:** Tool names should be unambiguous (e.g., `git_commit` vs `update`).
- **Namespacing:** Group related tools structurally to reduce context load.
- **Examples in Docstrings:** The best way to align an LLM with tool usage is showing it 1-2 examples within the tool's description itself.

---

## 3. Context Engineering (The Finite Resource)

> **Guiding Principle:** Find the _smallest possible set of high-signal tokens_ that maximize the likelihood of the desired outcome. LLMs have an "attention budget" — every new token depletes it.

### 3.1 Context Rot vs. Hybrid Loading

As token count grows, recall accuracy degrades (n² pairwise attention).

- **Pre-load** critical structural context (`CLAUDE.md`, core schemas) upfront for speed.
- **Dynamically load (JIT)** granular data (logs, raw file lines) into context at runtime using explicit lookup tools.

### 3.2 System Prompting Best Practices

- Use **clear, direct language** at the right altitude.
- Use XML tags (`<instructions>`, `<background>`, `<success_criteria>`) to delineate context.
- Start minimal. Add constraints or few-shot examples only based on observed failure modes.

---

## 4. Prompting Claude Opus 4.6

### 4.1 Configuration: Adaptive Thinking

Claude 4.6 models deprecate `budget_tokens` in favor of adaptive planning.

```python
thinking: {type: "adaptive"}
output_config: {effort: "high"} # Options: low, medium, high
```

_Use `high` effort for forensic audits, structural codebase changes, and long-horizon tasks._

### 4.2 Anti-Hallucination Constraints

To prevent confident guessing about unseen logic:

```xml
<investigate_before_answering>
Never speculate about code you have not opened. If a file is referenced, you MUST read the file before answering. Give grounded, hallucination-free answers.
</investigate_before_answering>
```

### 4.3 Generalization (Avoiding Test-Driven Slop)

Add forceful constraints against hacky shortcuts:
_“Write a general-purpose solution. Do not create helper scripts or workaround test cases. Do not hard-code values. Tests are there to verify correctness, not to define the solution.”_

### 4.4 Defeating "AI Slop" Aesthetics (Frontend Design)

Claude 4.6 can produce stunning UIs if specifically instructed to avoid generic paths:

```xml
<frontend_aesthetics>
Avoid generic "AI slop" (Inter/Roboto/Arial, cookie-cutter layouts, predictable purple gradients).
- Typography: Use distinct, interesting, modern fonts.
- Color & Theme: Commit to cohesive aesthetics (CSS variables). Use dominant colors with sharp accents. Light/Dark mode toggles.
- Contextual Backgrounds: Layer gradients or use geometric patterns for depth.
- Motion: Use well-orchestrated stagger animations and high-impact micro-interactions. Create delight. Think outside the box!
</frontend_aesthetics>
```

---

## 5. Harness Design for Long-Running Agents

Without harnesses, agents either (A) one-shot everything and run out of context or (B) declare premature completion.

### 5.1 Memory & Compaction

- **Structured Note-Taking:** Have the agent write to an external file (e.g., `claude-progress.txt`) incrementally to persist state across heavy context windows.
- **Compaction:** When context maxes out, summarize the conversation history, preserving unresolved bugs and architecture decisions, but discarding raw tool outputs. (Opus 4.6 auto-compacts well natively).

### 5.2 The 3-Agent Orchestration Pattern

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ PLANNER  │ ──▶ │GENERATOR │ ◀─▶ │EVALUATOR │
│ Expands  │     │ Builds   │     │ Grades   │
│ Spec     │     │ features │     │ (Live test)│
└──────────┘     └──────────┘     └──────────┘
```

1. **Planner:** Writes the full product spec from a short user prompt.
2. **Generator (Coding Agent):** Implements _one feature at a time_, leaving a clean state (commit) between features.
3. **Evaluator (QA):** Uses browser automation (e.g., Playwright MCP) to test the app like a human. It provides skeptical feedback to the generator. _Note: Opus 4.6 is capable enough that it can self-correct many issues, pushing the Evaluator's usefulness to edge cases._

---

## 6. Pipeline Forensic Application

For ADK Pipeline and other local workflows:

- **Phase Gates:** Stick to `planning.md` — adversarial review first, code second.
- **TripleCheck:** Manage session state properly (`TripleCheck.md`).
- **Evaluator Loops:** Whenever diagnosing "PIPELINE FAILURE" or 429 timeouts, use the Evaluator-Optimizer loop to iterate on fixes with concrete testing evidence (e.g., tracing upstream data dependencies and running the localized script).
