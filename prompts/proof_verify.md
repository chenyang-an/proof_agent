# Natural Language Proof Verification Task

## Overview

You are a mathematical logic reviewer tasked with rigorously verifying a natural-language proof. A separate decomposition step has already broken the proof into numbered **miniclaims** with miniproofs and organized them into a hierarchical **Proof Architecture** showing how miniclaims group into sub-arguments that prove intermediate results, and how those compose to prove the final claim. Your job is to **verify at every level**: each individual miniclaim, each sub-argument's composition, and the overall proof.

## Files

### Problem Statement
```
{problem_file}
```

### Proof to Verify
```
{proof_file}
```

### Proof Decomposition (miniclaims to verify)
```
{decomposition_file}
```

---

## Verification Method

### Phase 1: Verify Each Miniclaim

Read the decomposition file and go through the numbered miniclaim list one by one. For each miniclaim:

1. **Check logical validity** — Does the miniclaim follow from its stated dependencies and the miniproof? Is the reasoning correct? Cross-reference against the full proof text to ensure the miniproof is accurately quoted and in context.
2. **Check mathematical correctness** — Are computations, cited theorems, and applied results correct? Are all conditions for cited results satisfied?
3. **Check completeness** — Is the justification sufficient, or is there a gap? Does "clearly" or "obviously" hide a non-trivial step?
4. **Computational check** — Whenever feasible, verify the miniclaim with code (SymPy, NumPy, Z3, etc.). Save scripts in `{output_dir}/tmp/`. Note the result (confirmed / contradicted / not checked).
5. **Assign a verdict** — PASS, FAIL, or UNCERTAIN (if you cannot determine correctness but suspect a gap).
6. **If FAIL or UNCERTAIN** — State precisely what is wrong or what is missing.

### Phase 2: Structural Completeness Check

After verifying each miniclaim, check whether the miniclaims **together** constitute a complete proof:

1. **Chain completeness** — Does the dependency chain from the hypotheses (first miniclaims) to the final conclusion (last miniclaim) have any breaks? Are there logical jumps between miniclaims that aren't captured?
2. **Missing steps** — Are there assertions in the full proof text that were NOT captured as miniclaims? Read the full proof again and flag anything the decomposition missed.
3. **Redundancy** — Are any miniclaims unused (no later miniclaim depends on them, and they are not the final conclusion)? This may indicate dead-end reasoning or missing connections.

If you find missing steps, add them as additional miniclaims in the "Additional Miniclaims" section of your output and verify them.

### Phase 3: Sub-argument Composition Verification

The decomposition file contains a **Proof Architecture** section that shows how miniclaims group into sub-arguments, and how sub-arguments compose to prove larger claims up to the final conclusion. You must verify this hierarchical structure bottom-up:

1. **For each sub-argument:** Do its constituent miniclaims (all passing) actually establish the intermediate result the sub-argument claims? It is possible for every miniclaim within a group to be individually correct, yet the group fails to prove what it claims — for example, the miniclaims may prove something slightly different, or there may be a logical gap between the last miniclaim in the group and the stated intermediate result.

2. **For each composition step:** When sub-arguments A and B are combined to prove a larger claim, does that combination actually work? Check that:
   - The intermediate results from A and B are exactly what is needed as premises for the next step.
   - No silent additional assumptions are smuggled in at the composition level.
   - The logical connective (and/or/implies) between sub-arguments is correct.

3. **For the top-level goal:** Do all the top-level sub-arguments together actually prove the problem statement? This is the ultimate check — even if every sub-argument is internally valid, the proof fails if they don't compose to establish the claimed result.

Assign a verdict (PASS / FAIL / UNCERTAIN) to each sub-argument and each composition step. If a sub-argument fails because one of its miniclaims failed, note that — but also check whether the composition logic itself is sound independent of the miniclaim failure.

---

## Global Checks

After miniclaim verification, structural completeness, and sub-argument composition verification, perform these whole-proof checks:

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

- Does the chain of miniclaims actually connect the hypotheses to the conclusion?
- Are all conditions/hypotheses from the problem statement used somewhere in the miniclaim chain?
- Does the final miniclaim actually establish what the problem asks?

### Coverage Check

- Are all cases covered if case analysis is used?
- Are boundary/degenerate cases addressed?
- Are all hypotheses used? (If a hypothesis is unused, is the statement trivially true without it, or is there a gap?)

---

## Output Requirements

Write ALL verification results to: `{output_file}`

### Output Format

```markdown
# Proof Verification Results

**Problem:** {problem_file}
**Proof:** {proof_file}
**Decomposition:** {decomposition_file}

---

## Miniclaim Verification

### Miniclaim 1
**Statement:** [from decomposition]
**Miniproof:** "[from decomposition]"
**Dependencies:** [from decomposition]
**Type:** [from decomposition]
**Verdict:** [PASS / FAIL / UNCERTAIN]
**Analysis:** [why this miniclaim is correct/incorrect/unclear]
**Computational check:** [confirmed / contradicted / not checked — describe what was tested]

### Miniclaim 2
**Statement:** [from decomposition]
**Miniproof:** "[from decomposition]"
**Dependencies:** [from decomposition]
**Type:** [from decomposition]
**Verdict:** [PASS / FAIL / UNCERTAIN]
**Analysis:** [why this miniclaim is correct/incorrect/unclear]
**Computational check:** [confirmed / contradicted / not checked]

### Miniclaim 3
...

[Continue for ALL miniclaims. Do not skip or combine miniclaims.]

---

## Additional Miniclaims (found during structural completeness check)

[If the decomposition missed any steps, add and verify them here. Otherwise write "None — decomposition was complete."]

---

## Miniclaim Verification Summary

| # | Miniclaim (short description) | Type | Verdict | Computational |
|---|-------------------------------|------|---------|---------------|
| 1 | [brief description] | [type] | PASS/FAIL/UNCERTAIN | [confirmed/contradicted/not checked] |
| 2 | [brief description] | [type] | PASS/FAIL/UNCERTAIN | [confirmed/contradicted/not checked] |
| ... | ... | ... | ... | ... |

**Miniclaims passed:** X / N
**Miniclaims failed:** Y / N
**Miniclaims uncertain:** Z / N

---

## Structural Completeness

**Chain complete:** [YES / NO — is there an unbroken dependency path from hypotheses to conclusion?]
**Missing steps found:** [list any, or "None"]
**Unused miniclaims:** [list any, or "None"]

---

## Sub-argument Composition Verification

For each sub-argument from the Proof Architecture, verify that its miniclaims actually prove the claimed intermediate result, and that sub-arguments compose correctly at each level.

### Sub-argument A: [intermediate result from decomposition]
**Miniclaims:** [list the miniclaim numbers in this group]
**Do these miniclaims establish the claimed result?** [YES / NO — explain]
**Verdict:** [PASS / FAIL / UNCERTAIN]
**Issues:** [if FAIL/UNCERTAIN, what goes wrong at the composition level?]

### Sub-argument B: [intermediate result from decomposition]
**Miniclaims:** [list the miniclaim numbers in this group]
**Do these miniclaims establish the claimed result?** [YES / NO — explain]
**Verdict:** [PASS / FAIL / UNCERTAIN]
**Issues:** [if FAIL/UNCERTAIN, what goes wrong?]

[Continue for ALL sub-arguments in the Proof Architecture.]

### Top-level composition: [problem statement]
**Sub-arguments combined:** [list which sub-arguments feed into the final conclusion]
**Do they together prove the problem statement?** [YES / NO — explain]
**Silent assumptions at composition level?** [list any, or "None"]
**Verdict:** [PASS / FAIL / UNCERTAIN]

---

## Global Checks

### Problem-Statement Integrity
**Status:** [PASS/FAIL]
**Original problem (from {problem_file}):** [quote verbatim]
**Problem as stated/implied in proof:** [quote what the proof claims to prove]
**Discrepancies:** [list every difference, or "None — exact match"]

### Problem-Proof Alignment
**Status:** [PASS/FAIL]
**Details:** [does the miniclaim chain connect hypotheses to conclusion?]

### Coverage
**Status:** [PASS/FAIL]
**Missing items:** [list any gaps — uncovered cases, unused hypotheses, missing edge cases]

---

## Summary

| Check | Status |
|-------|--------|
| Problem-Statement Integrity | [PASS/FAIL] |
| Problem-Proof Alignment | [PASS/FAIL] |
| All Miniclaims Verified | [PASS/FAIL — FAIL if any miniclaim is FAIL or UNCERTAIN] |
| Structural Completeness | [PASS/FAIL] |
| Sub-argument Composition | [PASS/FAIL — FAIL if any sub-argument or top-level composition fails] |
| Coverage | [PASS/FAIL] |

### Overall Verdict: [PASS/FAIL]

### Failed/Uncertain Miniclaims (if any):
1. Miniclaim X: [what is wrong]
2. Miniclaim Y: [what is wrong]
...

### Specific Issues to Fix (if FAIL):
1. ...
2. ...
```

## Use Computational Tools to Verify Miniclaims

You have access to a shell and can run code. **You should actively use computational tools to check individual miniclaims** rather than relying only on manual inspection. Save scripts and their output in `{output_dir}/tmp/`.

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

**If a computational check contradicts a miniclaim, that is strong evidence of an error — mark that miniclaim as FAIL.**

## Temporary Files

If you need to create temporary files to help verify the proof (e.g., checking computations, testing edge cases, running verification scripts), save them in:
```
{output_dir}/tmp/
```
Create this directory if it does not exist. Do NOT place temporary files anywhere else.

## Critical Instructions

- **Verify every miniclaim from the decomposition.** Do NOT skip any. Every miniclaim gets its own entry with a verdict.
- Be thorough and skeptical. Your job is to find errors, not to approve proofs.
- If a hard problem is "easily" proved, be especially suspicious.
- Check that proof by contradiction actually uses the negated assumption.
- Check that induction proofs actually invoke the induction hypothesis.
- A proof that is "almost right" is still FAIL. Mathematical proofs are either correct or incorrect.
- If you find the proof is correct, say so clearly with a PASS verdict.
- **Use computational tools to independently verify miniclaims.** Don't just read the proof — test it.
- **Check the decomposition for completeness.** If steps are missing, add and verify them.
