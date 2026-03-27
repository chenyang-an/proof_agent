# Verdict Task: Proof Verification

Read the verification result file at `{verification_result_file}`.

## Decision Criteria

Reply with ONLY the single word **'DONE'** if ALL of the following criteria are satisfied:

1. **Problem-Proof Alignment:** The proof addresses the correct problem and proves exactly what was asked
2. **Logical Validity:** Every logical step is valid with no gaps
3. **Completeness:** All cases are covered, all claims are justified (uncertain means failed)
4. **Correctness:** All mathematical claims, computations, and cited results are correct
5. **Overall Verdict in the verification file is PASS**

Be strict and very conservative!

Reply with ONLY the single word **'CONTINUE'** otherwise.

## Important

- Your response must be exactly one word: either `DONE` or `CONTINUE`
- Do not include any explanation or additional text
- If the verification result file is empty or missing, reply `CONTINUE`
- If any single criterion fails, reply `CONTINUE`
