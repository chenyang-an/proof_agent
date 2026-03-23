# Proof Decomposition Task

## Overview

You are a mathematical logic analyst tasked with decomposing a natural-language proof into its atomic components. Your sole task is **decomposition** — break the proof into its smallest meaningful miniclaims, extract the miniproof for each, and identify all dependencies. You are NOT judging correctness; you are creating a structured map of the proof's logical architecture.

## Files

### Problem Statement
```
{problem_file}
```

### Proof to Decompose
```
{proof_file}
```

---

## Decomposition Method

Read the proof end-to-end and decompose it into a numbered list of **miniclaims**. A miniclaim is the smallest unit of logical assertion in the proof — a single equality, inequality, implication, existence statement, case conclusion, etc.

For each miniclaim, extract:

1. **Statement** — The precise mathematical assertion being made.
2. **Miniproof** — The exact text from the proof that is supposed to justify this miniclaim (quote it verbatim). If no justification is given, write "No justification provided."
3. **Dependencies** — Which earlier miniclaims this one relies on (by number). Write "None" for starting points, hypotheses, or definitions.
4. **Type** — Classify each miniclaim as one of:
   - `hypothesis` — A condition or assumption taken directly from the problem statement
   - `definition` — Introduction of notation or a named object
   - `algebraic-step` — An algebraic manipulation, simplification, or computation
   - `theorem-citation` — Statement of a known theorem, lemma, or standard result
   - `theorem-application` — Application of a cited theorem to the specific context at hand
   - `case-step` — A conclusion within one branch of a case analysis
   - `induction-base` — The base case of an induction argument
   - `induction-step` — The inductive step (uses the induction hypothesis)
   - `intermediate-conclusion` — A partial result derived from earlier miniclaims
   - `final-conclusion` — The statement that the problem's claim holds

### Decomposition Rules

- **Go as fine-grained as possible.** More miniclaims is better. If a single sentence asserts two things, split them into two miniclaims.
- If the proof says "by X, we get Y, and therefore Z", that is at least two miniclaims: (a) X implies Y, (b) Y implies Z.
- If induction is used: the base case is one miniclaim, the inductive hypothesis is stated as a miniclaim, and the inductive step is one or more miniclaims.
- If case analysis is used: each case is its own miniclaim (or multiple miniclaims).
- If a theorem or lemma is cited: one miniclaim for "the cited result says X" (`theorem-citation`) and another for "X applies here because conditions are met" (`theorem-application`).
- Every algebraic manipulation step that is not trivially obvious should be its own miniclaim.
- The final conclusion ("therefore the problem statement holds") is the last miniclaim with type `final-conclusion`.
- If a step is justified by "clearly", "obviously", or "it is easy to see", still extract it as a miniclaim with the quoted text as the miniproof — the verification step will judge whether it is actually obvious.

---

## Output Requirements

Write ALL decomposition results to: `{output_file}`

### Output Format

```markdown
# Proof Decomposition

**Problem:** {problem_file}
**Proof:** {proof_file}

---

## Miniclaims

### Miniclaim 1
**Statement:** [precise mathematical assertion]
**Miniproof:** "[quoted text from proof]"
**Dependencies:** None (hypothesis)
**Type:** hypothesis

### Miniclaim 2
**Statement:** [precise mathematical assertion]
**Miniproof:** "[quoted text from proof]"
**Dependencies:** Miniclaim 1
**Type:** algebraic-step

### Miniclaim 3
...

[Continue for ALL miniclaims. Do not skip or combine miniclaims.]

---

## Dependency Graph Summary

| # | Miniclaim (short description) | Type | Dependencies |
|---|-------------------------------|------|-------------|
| 1 | [brief description] | hypothesis | None |
| 2 | [brief description] | algebraic-step | 1 |
| ... | ... | ... | ... |

---

## Proof Architecture

Describe the hierarchical logical structure of the proof: how miniclaims group together to establish intermediate results, and how those intermediate results compose to prove the final claim.

Write this as a nested outline. Each node is either a miniclaim (by number) or a logical grouping that combines miniclaims into a bigger result. The top-level node should be the overall problem statement, and the leaves should be the atomic miniclaims.

Example format:

**Goal: [problem statement]**
- **Sub-argument A: [intermediate result]** (established by Miniclaims X–Y)
  - Miniclaim X: [brief description]
  - Miniclaim X+1: [brief description]
  - ...
  - Miniclaim Y: [intermediate-conclusion — establishes sub-argument A]
- **Sub-argument B: [intermediate result]** (established by Miniclaims Z–W)
  - Miniclaim Z: [brief description]
  - ...
  - Miniclaim W: [intermediate-conclusion — establishes sub-argument B]
- **Combining A + B:** Miniclaim N combines sub-arguments A and B to reach the final conclusion
- Miniclaim N: [final-conclusion]

Adapt the nesting depth and grouping to match the actual proof structure. For proofs using case analysis, each case should be a sub-argument. For induction, the base case and inductive step should be separate sub-arguments. For direct proofs, group related chains of reasoning.

---

## Decomposition Metadata

| Field | Value |
|-------|-------|
| **Total miniclaims** | [N] |
| **Proof structure** | [e.g., "Direct proof", "Proof by contradiction", "Induction on n", "Case analysis (3 cases)"] |
| **Hypotheses used** | [list which problem hypotheses appear as miniclaims] |
| **Theorems/lemmas cited** | [list any external results invoked] |
| **Gaps identified** | [list any steps where no justification is given, or "None"] |
```

## Temporary Files

If you need to create temporary files to help with decomposition (e.g., parsing complex expressions), save them in:
```
{output_dir}/tmp/
```
Create this directory if it does not exist. Do NOT place temporary files anywhere else.

## Critical Instructions

- **Decompose only — do NOT verify.** You are building a map of the proof's structure, not judging whether it is correct. Do not assign PASS/FAIL verdicts.
- **Go maximally fine-grained.** If in doubt whether to split a step into two miniclaims, split it.
- **Quote exactly.** Miniproofs must be verbatim quotes from the proof text.
- **Capture everything.** Every logical assertion in the proof should appear as a miniclaim. If the proof makes a claim — explicit or implicit — it must be in your list.
- **Mark gaps honestly.** If a step has no justification, say so. If the proof skips something, note it in the gaps field. This helps the verification step.
- **The final miniclaim must be the overall conclusion** that the problem statement holds.
