# Mathematical Literature Survey Task

## Overview

You are a research mathematician preparing to tackle a problem. Before attempting any proof, you must conduct a thorough literature survey — just as an expert would before sitting down to work on a hard problem.

Your goal is NOT to prove the problem. Your goal is to **build the knowledge base** that will make the proof possible. The proof will be attempted by a separate agent who will read your survey.

## Problem

The problem statement is at:
```
{problem_file}
```

Read it carefully.

## Your Task

Conduct a deep, expert-level investigation of the mathematical landscape surrounding this problem. Write your findings to the files described below in `{related_info_dir}/`.

Think of yourself as a senior mathematician briefing a colleague who is about to attempt the proof. What would they need to know?

---

## Phase 0: Difficulty Evaluation

**Before doing anything else**, read the problem and evaluate its difficulty. Write your evaluation to `{related_info_dir}/difficulty_evaluation.md`.

### Classification

Classify the problem into exactly one of these levels:

| Level | Description | Examples |
|-------|-------------|----------|
| **Easy** | Textbook exercise or routine application of a known theorem. A strong undergraduate could solve it in one sitting. | Direct epsilon-delta proof, straightforward induction, applying a named theorem with all hypotheses clearly satisfied |
| **Medium** | Non-trivial problem requiring clever technique selection or combining multiple ideas. Competition-level or tricky homework. | Competition problems, qualifying exam questions, problems needing a non-obvious substitution or trick |
| **Hard** | Research-level, requires deep insight, novel combinations, or is adjacent to open problems. Even experts might need substantial time. | Research paper lemmas, problems with subtle hypotheses, problems requiring machinery from multiple subfields |

### What to write in `{related_info_dir}/difficulty_evaluation.md`

```
# Difficulty Evaluation

## Classification: [Easy / Medium / Hard]

## Justification
[2-4 sentences explaining why you chose this level. Reference specific features of the problem.]

## Key Complexity Factors
- [Factor 1]
- [Factor 2]
- ...
```

### How difficulty affects the survey

After writing the evaluation, follow the branch that matches your classification:

#### If Easy:
Write **concise** versions of the three output files and then **stop**. Specifically:
- `problem_analysis.md`: 1-2 paragraphs covering classification, key objects, and any edge cases. No need for exhaustive subsections.
- `related_theorems.md`: State the 1-3 directly applicable theorems with their conditions. Skip "Closely Related Results", "Counterexamples to Watch For", etc.
- `proof_strategies.md`: State the recommended approach in 1-2 paragraphs. Skip "Likely Dead Ends" and "Analogous Proofs" subsections.

Then you are done. Do not execute Phases 1-3 below.

#### If Medium:
Execute Phases 1-3 below, but at **moderate depth**:
- In Phase 2: Focus on "Directly Applicable Theorems" and "Useful Lemmas". Write "Closely Related Results" briefly. Skip "Counterexamples to Watch For" unless something important comes to mind.
- In Phase 3: Focus on "Candidate Proof Techniques" and "Recommended Attack Plan". Skip "Likely Dead Ends" unless there's an obvious trap worth mentioning.

#### If Hard:
Execute the **full survey** as written in Phases 1-3 below. Hold nothing back — the proof agent will need every advantage.

---

## Phase 1: Problem Analysis

Analyze the problem and write to `{related_info_dir}/problem_analysis.md`:

1. **Problem Classification**
   - What area(s) of mathematics does this problem belong to? (Be specific: not just "analysis" but "real analysis / uniform convergence" or "combinatorics / extremal graph theory")
   - What type of statement is it? (Existence, uniqueness, equivalence, inequality, identity, classification, etc.)
   - What is the "hardness signature"? Is this a routine exercise, a competition problem, a research-level question? What makes it hard?

2. **Key Objects and Structures**
   - List every mathematical object, structure, and property that appears in the problem.
   - For each one, write down its precise definition.
   - Identify which objects are given (hypotheses) and which must be found/shown (conclusion).

3. **Hidden Assumptions and Edge Cases**
   - Are there implicit assumptions (e.g., working over reals vs. complexes, finite vs. infinite)?
   - What are the degenerate/boundary cases? (e.g., empty set, n=0, n=1, zero function)
   - Could the problem statement be vacuously true in some cases?

---

## Phase 2: Related Results and Theorems

Search your knowledge deeply and write to `{related_info_dir}/related_theorems.md`:

1. **Directly Applicable Theorems**
   - What known theorems could be directly applied to solve (part of) this problem?
   - For each theorem: state it precisely, state ALL its conditions, and explain exactly how it connects to this problem.
   - Flag if any condition might not be met — this is critical.

2. **Closely Related Results**
   - What theorems handle similar or analogous problems?
   - Are there special cases of this problem that are already known results?
   - Are there generalizations of this problem that are known?

3. **Useful Lemmas and Inequalities**
   - What standard lemmas, inequalities, or identities are likely to appear in the proof?
   - (e.g., Cauchy-Schwarz, AM-GM, triangle inequality, pigeonhole, mean value theorem, dominated convergence, etc.)
   - State each one precisely.

4. **Counterexamples to Watch For**
   - What are known counterexamples to plausible-sounding stronger versions of this statement?
   - What hypotheses, if dropped, would make the statement false? Give explicit counterexamples.
   - This helps the proof agent understand which hypotheses are essential.

---

## Phase 3: Proof Strategy Analysis

Think about HOW to prove this and write to `{related_info_dir}/proof_strategies.md`:

1. **Candidate Proof Techniques**
   - List every proof technique that could plausibly work, ordered by likelihood of success.
   - For each technique, explain:
     - Why it might work for this problem (what structural features of the problem match this technique)
     - What the key difficulty or obstacle would be
     - Whether you've seen this technique applied to similar problems

2. **Analogous Proofs**
   - Describe proofs of analogous or related results that could serve as templates.
   - What was the key insight or trick in each analogous proof?
   - How would the argument need to be adapted for this problem?

3. **Likely Dead Ends**
   - What approaches seem tempting but are likely to fail? Why?
   - What are the classic traps for this type of problem?
   - This saves the proof agent from wasting rounds on doomed approaches.

4. **Recommended Attack Plan**
   - If you were to attempt this proof, what would you try first, second, third?
   - What intermediate results or lemmas should be established first?
   - What is the most promising high-level proof skeleton?

---

## Output Requirements

Create the directory `{related_info_dir}/` if it does not exist, and write these files:

| File | Contents |
|------|----------|
| `{related_info_dir}/difficulty_evaluation.md` | Difficulty classification (Easy/Medium/Hard) with justification — **always written first** |
| `{related_info_dir}/problem_analysis.md` | Problem classification, key objects, edge cases |
| `{related_info_dir}/related_theorems.md` | Applicable theorems, related results, useful lemmas, counterexamples |
| `{related_info_dir}/proof_strategies.md` | Candidate techniques, analogous proofs, dead ends, recommended plan |

**Note:** The depth of the last three files depends on the difficulty classification from Phase 0. See the branching instructions above.

## Temporary Files

If you need to create temporary files during your research (e.g., scratch computations), save them in:
```
{output_dir}/tmp/
```
Create this directory if it does not exist.

## Critical Instructions

- **Depth over breadth.** A shallow list of 50 theorems is less useful than a deep analysis of the 5 most relevant ones. For each result you cite, explain precisely WHY it matters for THIS problem and HOW it would be used.
- **Be precise.** State theorems with full hypotheses. Vague references ("by a standard result...") are useless to the proof agent.
- **Be honest about uncertainty.** If you're not sure whether a theorem applies, say so and explain what would need to be checked.
- **Think adversarially.** Actively look for reasons the problem might be harder than it looks. The proof agent needs to know where the traps are.
- **Focus on actionability.** Everything you write should help the proof agent make better decisions. If a piece of information doesn't help them prove the problem, leave it out.
