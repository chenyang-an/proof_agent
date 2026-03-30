# Proof Effort Summary Task

> **Agentic task.** Read the input files first, then think, plan, and work — use bash, computational tools, or any available resources as needed. Write the output files using tool calls according to the instructions. All input/output file paths and format specifications are at the end of this prompt.

## Overview

You are a mathematical research assistant tasked with writing a comprehensive summary of an entire proof effort. The pipeline has finished — either the proof was verified successfully or the maximum number of iterations was reached.

Your job is to read **all** generated files in the output directory and produce a clear, informative summary of what happened.

## Your Task

Write a summary to `{summary_file}` in Markdown. The summary should be useful to a mathematician who wants to quickly understand what happened without reading every file. Include:

### 1. Problem Overview
- Restate the problem concisely (in your own words, with LaTeX math notation).
- Classify it: area of mathematics, type of statement, estimated difficulty.

### 2. Final Proof Status
- Was a correct proof found? (PASS / FAIL)
- If PASS: summarize the proof strategy and key insight in 2-3 sentences.
- If FAIL: summarize the best attempt and what remains unresolved.

### 3. Round-by-Round Summary
For each round, write 2-3 sentences covering:
- What approach was tried
- What the verification found (pass/fail, specific issues)
- What changed between this round and the next

### 4. Approaches Tried
- List every distinct proof strategy that was attempted across all rounds.
- For each one, note whether it was abandoned (and why) or carried forward.

### 5. Key Mathematical Insights
- What did the agents discover about the problem during the effort?
- Any useful lemmas, counterexamples, or structural observations found along the way.
- What would you recommend trying next if the proof is not yet complete?

### 6. Resource Usage
- Summarize token usage from `TOKEN_USAGE.md` (total tokens, number of agent calls).
- How many rounds were used out of the maximum allowed.

## Format

Write the summary in clean Markdown to `{summary_file}`. Use LaTeX math notation (`$...$`, `$$...$$`) where appropriate.

## Critical Instructions

- **If any tool or script you run takes longer than 3 minutes, stop it and try a different approach or skip that computation.**
- **Read all the files** before writing. Don't guess — base every claim on what's actually in the generated files.
- **Be honest about the result.** If the proof has gaps, say so clearly. If it's correct, say so confidently.
- **Be concise but complete.** A reader should get the full picture in under 5 minutes of reading.

---

## HERE ARE THE INPUT FILE PATHS:

All generated files are in the output directory: `{output_dir}`

Read every relevant file in this directory and its subdirectories. Key files include:

| File / Directory | Contents |
|-----------------|----------|
| `problem.tex` | The original problem statement |
| `proof.md` | The final proof (or best attempt) |
| `related_info/difficulty_evaluation.md` | Difficulty classification (Easy/Medium/Hard) and justification |
| `related_info/problem_analysis.md` | Problem classification and key objects |
| `related_info/related_theorems.md` | Applicable theorems and related results |
| `verification/round_*/proof_status.md` | What each round tried and learned |
| `verification/round_*/verification_result.md` | Verification verdict for each round |
| `TOKEN_USAGE.md` | Token usage across all agent calls |

## HERE ARE THE OUTPUT FILE PATHS:

- **Summary file:** `{summary_file}`
- **Error log:** `{error_file}`

**Write the summary file incrementally.** Do NOT try to write the entire file in a single tool call — this will fail silently due to content-size limits. Instead:

1. **First call:** Write the file header and sections 1–2 (Problem Overview, Final Proof Status) to `{summary_file}`.
2. **Then append:** Append section 3 (Round-by-Round Summary) to `{summary_file}` using shell `cat >> "{summary_file}" << 'ENDOFBLOCK'` or Python `open(..., "a")`.
3. **Then append:** Append sections 4–5 (Approaches Tried, Key Mathematical Insights).
4. **Then append:** Append section 6 (Resource Usage).

**After writing, verify the file exists and is non-empty** by running `wc -l "{summary_file}"`. If the file is missing or empty, something went wrong — retry the write immediately.

## Pipeline Result

**Outcome:** {outcome}
**Total rounds used:** {total_rounds}
**Maximum rounds allowed:** {max_rounds}

## Error Log

If you encounter any errors during this call — tool failures, runtime exceptions, file I/O issues, context window limits, or unexpected behavior — record them in `{error_file}`.

**Always create this file.** If no errors occur, write an empty file. If errors occur, include the error message, what you were doing when it occurred, and any workaround you applied.
