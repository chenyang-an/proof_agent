# Proof Verification Task (Easy Problem)

> **Agentic task.** Read the input files first, then think, plan, and work — use bash, computational tools, or any available resources as needed. Write the output files using tool calls according to the instructions. All input/output file paths and format specifications are at the end of this prompt.

## Overview

You are a mathematical logic reviewer. This problem has been classified as **Easy** — a textbook exercise or routine application of a known theorem. Perform a direct, streamlined verification of the proof without a separate decomposition step.

---

## Verification Method

Read the proof end-to-end and check it directly. You do NOT need to decompose into miniclaims — just verify the proof as a whole.

### Step 1: Check the Proof

1. **Logical flow** — Does each step follow from the previous one? Are there any gaps or unjustified leaps?
2. **Mathematical correctness** — Are computations, cited theorems, and applied results correct? Are all conditions satisfied?
3. **Completeness** — Are all cases covered? Are edge cases addressed? Does "clearly" or "obviously" hide anything non-trivial?
4. **Computational spot-check** — Use code (SymPy, NumPy, Z3) to verify at least one key claim or computation. Save scripts in `{output_dir}/tmp/`.

### Step 2: Problem-Statement Integrity

**This is the most critical check.** The proof search agent may alter the problem statement.

1. Read the **original** problem statement from `{problem_file}` verbatim.
2. Compare it **word-by-word** with what the proof claims to prove.
3. Flag ANY discrepancy: changed quantifiers, weakened hypotheses, modified bounds, restricted domain, proving a special case, etc.

**If the problem the proof claims to solve differs from `{problem_file}` in ANY mathematically meaningful way, this check is FAIL.**

### Step 3: Alignment and Coverage

- Does the proof actually prove what the problem asks?
- Are all hypotheses used?
- Are all cases covered?

---

## Use Computational Tools

You have access to a shell. Use code to spot-check at least one key claim. Save scripts in `{output_dir}/tmp/`.

### Keep tool output concise

Write large results to files in `{output_dir}/tmp/` and print only summaries or booleans.

**If any tool or script you run takes longer than 3 minutes, stop it and try a different approach or skip that computation.**

## Critical Instructions

- This is an easy problem — be efficient, but still be correct.
- The most important check is **problem-statement integrity**. Even easy problems can have the statement subtly altered.
- A proof that is "almost right" is still FAIL.
- If the proof is correct, say PASS clearly.

---

## HERE ARE THE INPUT FILE PATHS:

### Problem Statement
```
{problem_file}
```

### Proof to Verify
```
{proof_file}
```

## HERE ARE THE OUTPUT FILE PATHS:

### Verification Results

Write ALL verification results to:
```
{output_file}
```

### Output Format

```markdown
# Proof Verification Results

**Problem:** {problem_file}
**Proof:** {proof_file}
**Difficulty:** Easy (streamlined verification)

**No output files means the proof failed directly. Always put the verification result in the correct path.**

---

## Proof Review

**Logical flow:** [correct / has gaps — describe]
**Mathematical correctness:** [correct / errors found — describe]
**Completeness:** [complete / missing items — describe]
**Computational spot-check:** [what was tested, result]

---

## Global Checks

### Problem-Statement Integrity
**Status:** [PASS/FAIL]
**Original problem:** [quote verbatim]
**Problem as stated in proof:** [quote]
**Discrepancies:** [list any, or "None — exact match"]

### Alignment and Coverage
**Status:** [PASS/FAIL]
**Details:** [does the proof prove what was asked? all cases covered?]

---

## Summary

| Check | Status |
|-------|--------|
| Problem-Statement Integrity | [PASS/FAIL] |
| Logical Flow | [PASS/FAIL] |
| Mathematical Correctness | [PASS/FAIL] |
| Completeness | [PASS/FAIL] |

### Overall Verdict: [PASS/FAIL]

### Issues Found (if FAIL):
1. ...
2. ...
```

### Error Log

If you encounter any errors during this call — tool failures, runtime exceptions, file I/O issues, context window limits, or unexpected behavior — record them in:
```
{error_file}
```
**Always create this file.** If no errors occur, write an empty file. If errors occur, include the error message, what you were doing when it occurred, and any workaround you applied.

### Temporary Files

If you need to create temporary files (e.g., verification scripts, computational checks), save them in:
```
{output_dir}/tmp/
```
Create this directory if it does not exist. Do NOT place temporary files anywhere else.
