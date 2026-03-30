# Proof Selection Task

> **Agentic task.** Read the input files first, then think, plan, and work — use bash, computational tools, or any available resources as needed. Write the output files using tool calls according to the instructions. All input/output file paths and format specifications are at the end of this prompt.

## Overview

You are a mathematical proof evaluation expert. Three independent AI models have each attempted to prove the same mathematical problem. Each proof has been independently verified. You must select the **single most promising proof** to carry forward.

## Your Task

Read all three verification reports carefully. Then select the **single best proof** to carry forward to the next round (or to accept as the final proof if it passes).

## Selection Criteria (in priority order)

1. **Problem-Statement Integrity** (HIGHEST PRIORITY): Any proof that alters, weakens, or misrepresents the original problem is **immediately disqualified**, regardless of how elegant the rest of the proof is. Check the "Problem-Statement Integrity" section of each verification report.

2. **Overall Verdict**: A proof with an overall PASS verdict is strictly preferred over one with FAIL.

3. **Fewest Failures**: Among FAIL verdicts, prefer the proof with the fewest FAIL or UNCERTAIN claims (miniclaims or steps, depending on the verification format). A proof that is 90% correct with one fixable gap is far more valuable than one that is 50% correct.

4. **Quality of Partial Progress**: If failure counts are similar, consider:
   - Which proof has the strongest correct core argument?
   - Which proof's failures are most likely fixable in the next round?
   - Which proof demonstrates deeper understanding of the problem?

5. **Structural Completeness**: Prefer proofs with complete dependency chains (hypotheses → conclusion) over those with structural gaps, even if individual miniclaims are correct.

## Important

- **If any tool or script you run takes longer than 3 minutes, stop it and try a different approach or skip that computation.**
- You MUST read all three verification reports before making your selection.
- You MUST write the selection file — do not just output your answer to stdout.
- The `SELECTED:` line must contain exactly one of: `claude`, `codex`, `gemini` (lowercase).
- If one or two models produced empty or invalid proofs, note this and select from the valid ones.
- If ALL three proofs are disqualified (e.g., all alter the problem statement), select the least-bad option and note the critical issues in "Notes for Next Round".

---

## HERE ARE THE INPUT FILE PATHS:

### Problem Statement

The original problem is located at:
```
{problem_file}
```

### Verification Reports

Three independent verification reports are available:

- **Claude's proof verification:** `{verify_claude}`
- **Codex's proof verification:** `{verify_codex}`
- **Gemini's proof verification:** `{verify_gemini}`

### Proof Files

The corresponding proofs are at:

- **Claude's proof:** `{proof_claude}`
- **Codex's proof:** `{proof_codex}`
- **Gemini's proof:** `{proof_gemini}`

## HERE ARE THE OUTPUT FILE PATHS:

Write your selection to `{selection_file}` using this exact format:

```markdown
# Proof Selection Report

## Summary Table

| Model | Overall Verdict | Claims PASS | Claims FAIL | Claims UNCERTAIN | Problem-Statement Integrity |
|-------|----------------|-----------------|-----------------|---------------------|---------------------------|
| Claude | ... | ... | ... | ... | ... |
| Codex | ... | ... | ... | ... | ... |
| Gemini | ... | ... | ... | ... | ... |

## Selection

**SELECTED: <claude|codex|gemini>**

## Reasoning

(Explain why this proof was selected over the other two. Be specific — reference claim/step numbers, structural issues, or verification findings. Keep this to 2-4 sentences.)

## Notes for Next Round

(If the selected proof has failures: briefly describe the key issues that need to be fixed in the next round. This helps the proof search agent focus its effort.)
```

## Error Log

If you encounter any errors during this call — tool failures, runtime exceptions, file I/O issues, context window limits, or unexpected behavior — record them in:
```
{error_file}
```
**Always create this file.** If no errors occur, write an empty file. If errors occur, include the error message, what you were doing when it occurred, and any workaround you applied.
