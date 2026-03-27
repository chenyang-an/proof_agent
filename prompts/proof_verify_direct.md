# Direct Proof Verification Task

## Overview

You are a mathematical logic reviewer tasked with rigorously verifying a natural-language proof. There is NO separate decomposition — you must **identify the proof's logical steps yourself** and then verify each one, the overall structure, and the global checks.

You must be absolutely strict. If you are uncertain if the proof proved certain claim, then it fail to do so. You should always be very conservative on every respect. All judgement should be based on evidence.

## Files

### Problem Statement
```
{problem_file}
```

### Proof to Verify
```
{proof_file}
```

---

## Verification Method

### Phase 1: Identify and Verify Logical Steps

Read the proof end-to-end. Identify every key logical assertion (step) in the proof — each step should be a single, precise mathematical claim that the proof makes or relies on. Be maximally fine-grained: split complex reasoning into individual steps. For each step:

1. **State the step** — Write the precise mathematical assertion.
2. **Quote the justification** — Quote the relevant passage from the proof that justifies this step.
3. **List dependencies** — Which earlier steps does this step depend on?
4. **Check logical validity** — Does the step follow from its dependencies and the stated justification? Is the reasoning correct?
5. **Check mathematical correctness** — Are computations, cited theorems, and applied results correct? Are all conditions for cited results satisfied?
6. **Check completeness** — Is the justification sufficient, or is there a gap? Does "clearly" or "obviously" hide a non-trivial step?
7. **Computational check** — Whenever feasible, verify the step with code (SymPy, NumPy, Z3, etc.). Save scripts in `{output_dir}/tmp/`. Note the result (confirmed / contradicted / not checked).
8. **Assign a verdict** — PASS, FAIL, or UNCERTAIN (if you cannot determine correctness but suspect a gap).
9. **If FAIL or UNCERTAIN** — State precisely what is wrong or what is missing.

### Phase 2: Structural Completeness Check

After identifying and verifying each step, check whether the steps **together** constitute a complete proof:

1. **Chain completeness** — Does the dependency chain from the hypotheses (first steps) to the final conclusion (last step) have any breaks? Are there logical jumps between steps that aren't captured?
2. **Missing steps** — Are there assertions in the proof text that you did NOT capture as steps? Read the proof again and flag anything you missed.
3. **Redundancy** — Are any steps unused (no later step depends on them, and they are not the final conclusion)? This may indicate dead-end reasoning or missing connections.

---

## Global Checks

After step verification and structural completeness, perform these whole-proof checks:

### Problem-Statement Integrity

**This is the most critical check.** The proof search agent may — intentionally or accidentally — alter, weaken, or re-interpret the problem statement. You must catch this.

1. Read the **original** problem statement from `{problem_file}` verbatim.
2. Identify the claim the proof **actually proves** (look at what it states at the beginning and what it concludes).
3. Compare the two **word-by-word**. Flag ANY discrepancy, including but not limited to:
   - Changed quantifiers (e.g. "for all" → "there exists", or an added/dropped "for all")
   - Strengthened or weakened hypotheses (extra assumptions added, or conditions dropped)
   - Modified constants, bounds, or inequalities (e.g. strict vs. non-strict, changed exponents)
   - Restricted domain (e.g. proving for integers when the problem says reals)
   - Swapped conclusion and hypothesis (proving the converse instead of the original)
   - Subtle rephrasing that changes meaning (e.g. "at most" → "at least", "unique" dropped)
   - Proving a special case instead of the general statement
4. If the proof does not state the problem it is proving, that itself is a FAIL — the proof must clearly declare what it proves so the reader can verify alignment.

**If the problem the proof claims to solve differs from `{problem_file}` in ANY mathematically meaningful way, this check is FAIL — regardless of whether the proof of the altered statement is correct.**

### Problem-Proof Alignment

- Does the chain of steps actually connect the hypotheses to the conclusion?
- Are all conditions/hypotheses from the problem statement used somewhere in the step chain?
- Does the final step actually establish what the problem asks?

### Coverage Check

- Are all cases covered if case analysis is used?
- Are boundary/degenerate cases addressed?
- Are all hypotheses used? (If a hypothesis is unused, is the statement trivially true without it, or is there a gap?)

---

## Output Requirements

Write ALL verification results to: `{output_file}`

### CRITICAL — Write the file incrementally

The verification output will be large. **Do NOT try to write the entire file in a single tool call** — this will fail silently due to content-size limits. Instead:

1. **First call:** Write the file header (everything up to `## Step-by-Step Verification`) to `{output_file}`.
2. **Then append in batches:** After verifying every 5–10 steps, **append** those results to `{output_file}` (use shell `cat >> "{output_file}" << 'ENDOFBLOCK'` or Python `open(..., "a")`). Do NOT wait until you've verified all steps to start writing.
3. **Append remaining sections:** After all steps, append the Summary table, Structural Completeness, Global Checks, and Overall Verdict sections one at a time.

**After writing, verify the file exists and is non-empty** by running `wc -l "{output_file}"`. If the file is missing or empty, something went wrong — retry the write immediately.

### Output Format

```markdown
# Proof Verification Results

**Problem:** {problem_file}
**Proof:** {proof_file}
**Mode:** Direct verification (no separate decomposition)

---

## Step-by-Step Verification

### Step 1
**Assertion:** [precise mathematical claim]
**Justification in proof:** "[quote from proof]"
**Dependencies:** [list earlier step numbers, or "None (hypothesis)"]
**Verdict:** [PASS / FAIL / UNCERTAIN]
**Analysis:** [why this step is correct/incorrect/unclear]
**Computational check:** [confirmed / contradicted / not checked — describe what was tested]

### Step 2
**Assertion:** [precise mathematical claim]
**Justification in proof:** "[quote from proof]"
**Dependencies:** [list earlier step numbers]
**Verdict:** [PASS / FAIL / UNCERTAIN]
**Analysis:** [why this step is correct/incorrect/unclear]
**Computational check:** [confirmed / contradicted / not checked]

### Step 3
...

[Continue for ALL identified steps. Do not skip or combine steps.]

---

## Step Verification Summary

| # | Step (short description) | Verdict | Computational |
|---|--------------------------|---------|---------------|
| 1 | [brief description] | PASS/FAIL/UNCERTAIN | [confirmed/contradicted/not checked] |
| 2 | [brief description] | PASS/FAIL/UNCERTAIN | [confirmed/contradicted/not checked] |
| ... | ... | ... | ... |

**Steps passed:** X / N
**Steps failed:** Y / N
**Steps uncertain:** Z / N

---

## Structural Completeness

**Chain complete:** [YES / NO — is there an unbroken dependency path from hypotheses to conclusion?]
**Missing steps found:** [list any, or "None"]
**Unused steps:** [list any, or "None"]

---

## Global Checks

### Problem-Statement Integrity
**Status:** [PASS/FAIL]
**Original problem (from {problem_file}):** [quote verbatim]
**Problem as stated/implied in proof:** [quote what the proof claims to prove]
**Discrepancies:** [list every difference, or "None — exact match"]

### Problem-Proof Alignment
**Status:** [PASS/FAIL]
**Details:** [does the step chain connect hypotheses to conclusion?]

### Coverage
**Status:** [PASS/FAIL]
**Missing items:** [list any gaps — uncovered cases, unused hypotheses, missing edge cases]

---

## Summary

| Check | Status |
|-------|--------|
| Problem-Statement Integrity | [PASS/FAIL] |
| Problem-Proof Alignment | [PASS/FAIL] |
| All Steps Verified | [PASS/FAIL — FAIL if any step is FAIL or UNCERTAIN] |
| Structural Completeness | [PASS/FAIL] |
| Coverage | [PASS/FAIL] |

### Overall Verdict: [PASS/FAIL]

### Failed/Uncertain Steps (if any):
1. Step X: [what is wrong]
2. Step Y: [what is wrong]
...

### Specific Issues to Fix (if FAIL):
1. ...
2. ...
```

## Use Computational Tools to Verify Steps

You have access to a shell and can run code. **You should actively use computational tools to check individual steps** rather than relying only on manual inspection. Save scripts and their output in `{output_dir}/tmp/`.

### Keep tool output concise

Printing large expressions to stdout wastes your context window. Write large results to files in `{output_dir}/tmp/` and print only summaries or booleans. If `len(str(expr)) > 500`, write to file instead of printing.

### How to use tools for verification:

- **Check algebraic identities and simplifications** — Use SymPy (`pip install sympy`) to verify that claimed equalities, simplifications, and manipulations are correct. If SymPy says `simplify(lhs - rhs) != 0`, the proof has an error.
- **Test claims on concrete cases** — Use Python/NumPy/SageMath to evaluate key formulas at specific values and confirm they match what the proof claims.
- **Verify combinatorial and number-theoretic formulas** — Brute-force check formulas against direct computation for small cases using Python or SageMath.
- **Check boundary and degenerate cases computationally** — Plug in edge cases (n=0, n=1, empty set, etc.) into the proof's expressions and verify the claimed behavior.
- **Validate inequality claims** — Use numerical sampling or Z3 (`pip install z3-solver`) to check whether claimed inequalities hold.
- **Re-derive key computations independently** — If the proof performs a lengthy calculation, redo it in SymPy and compare.
- **Plot functions** — Use Matplotlib to visualize claims about function behavior (monotonicity, convexity, convergence).

**If a computational check contradicts a step, that is strong evidence of an error — mark that step as FAIL.**
**However, if an algorithmic run used for verification is longer than 3 minutes, stop it and skip this algorithm.**

## Temporary Files

If you need to create temporary files to help verify the proof (e.g., checking computations, testing edge cases, running verification scripts), save them in:
```
{output_dir}/tmp/
```
Create this directory if it does not exist. Do NOT place temporary files anywhere else.

## Critical Instructions

- **Identify every logical step in the proof and verify each one.** Be maximally fine-grained — split complex reasoning into individual assertions. Do NOT skip any step.
- Be thorough and skeptical. Your job is to find errors, not to approve proofs.
- If a hard problem is "easily" proved, be especially suspicious.
- Check that proof by contradiction actually uses the negated assumption.
- Check that induction proofs actually invoke the induction hypothesis.
- A proof that is "almost right" is still FAIL. Mathematical proofs are either correct or incorrect.
- If you find the proof is correct, say so clearly with a PASS verdict.
- **Use computational tools to independently verify steps.** Don't just read the proof — test it.
- **Whenever you feel you verified something, save your partial progress to the file!**
