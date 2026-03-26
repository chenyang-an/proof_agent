# QED

QED is a multi-agent pipeline that takes a mathematical problem statement in LaTeX and produces a rigorous natural-language proof. The pipeline uses Claude as the underlying LLM, orchestrated through the [Agent Framework](https://github.com/microsoft/agent-framework). For hard problems, it optionally runs Claude, Codex (GPT-5.4), and Gemini in parallel to maximize the chance of finding a correct proof. It performs stronger than chatbot versions of various models on math proving tasks, since it uses agentic loops to search, decompose, and verify math proofs instead of answering in one shot.

## Math Research Problems that are solved by QED, verified by domain experts.

1. Search a smooth space–time weight function (with auxiliary parameters) for the wave operator on a half-infinite domain such that it satisfies global pseudoconvexity, growth, and positivity conditions required to validate a Carleman estimate, and characterize the admissible parameter regime ensuring these conditions hold with proofs. (GitHub link will be released soon after paper arxived) (The proof produced by QED has been validated by domain experts)

## How It Works

The pipeline runs in three stages:

**Stage 0 — Literature Survey.** A survey agent reads the problem and first evaluates its difficulty (Easy / Medium / Hard), then conducts an investigation of the mathematical landscape scaled to that difficulty: classifying the problem, identifying applicable theorems, and cataloguing related results. Easy problems get a brief survey; hard problems get the full treatment. The results are saved to `related_info/` for the proof agent to reference. The survey agent does NOT produce proof strategies — that is the proof search agent's job.

**Stage 1 — Proof Search Loop.** An iterative loop runs up to `max_proof_iterations` rounds (default 9). The behavior adapts to the problem's difficulty:

**Hard problems with multi-model enabled — 6 steps per round (parallel):**

1. **Proof Search (parallel)** — All available models (Claude, Codex, Gemini) attack the problem simultaneously. Each writes its own `proof.md` in an isolated subdirectory.
2. **Decomposition (parallel)** — Claude decomposes all proofs into numbered **miniclaims** with dependency graphs. One decomposition per model's proof.
3. **Verification (parallel)** — Claude verifies all decomposed proofs independently. One verification report per model's proof.
4. **Selector Agent** — Reads all verification reports and selects the single most promising proof based on: problem-statement integrity, overall verdict, fewest failures, quality of partial progress, and structural completeness. Writes `selection.md`.
5. **Apply Selection** — The winning proof is copied to the main `proof.md`.
6. **Verdict Agent** — Reads ONLY the selected model's verification report and returns `DONE` or `CONTINUE`.

**Medium / Hard (single-model) problems — 4 steps per round:**

1. **Proof Search Agent** — Reads the problem, the literature survey, any previous-round feedback, and any human guidance from `human_help/`. Writes or refines a complete natural-language proof in `proof.md`.
2. **Decomposition Agent** — Decomposes the proof into numbered miniclaims, each with a verbatim miniproof quote, dependency list, and type classification. Also produces a Proof Architecture. Writes `proof_decomposition.md`.
3. **Verification Agent** — Verifies each miniclaim individually (logical validity, mathematical correctness, computational checks via SymPy/Z3/NumPy). Then verifies hierarchical composition and runs global checks. Writes `verification_result.md`.
4. **Verdict Agent** — Reads the verification result and returns `DONE` or `CONTINUE`.

**Easy problems — 3 steps per round:**

1. **Proof Search Agent** — Same as above.
2. **Verification Agent (lightweight)** — Skips decomposition. Does a direct read-through checking logical flow, correctness, completeness, and problem-statement integrity. Writes `verification_result.md`.
3. **Verdict Agent** — Same as above.

If the verdict is `DONE`, the pipeline stops. Otherwise the next round begins, with the proof search agent reading the previous round's verification feedback and proof status log to avoid repeating failed approaches.

**Stage 2 — Proof Effort Summary.** After the proof loop finishes (either success or max iterations), a summary agent reads all generated files and writes `proof_effort_summary.md`.

All agents receive `skill/super_math_skill.md` as a system-level instruction — a guide to mathematical proof methodology.

**Human guidance.** You can drop hints, suggestions, or corrections into `human_help/` at any time during a run. The proof search agent checks this directory at the start of every round.

**Resume support.** If the pipeline is interrupted and re-run with the same output directory, it automatically detects prior progress: skips the literature survey if complete, detects which step within a round was last completed (including parallel steps), cleans up incomplete state, restores `proof.md` from backup if needed, and resumes from exactly where it left off.

**Smoke test.** `run.sh` automatically runs the smoke test before the pipeline starts. The smoke test validates prompts, skills, Claude connectivity, and — when multi-model is enabled — Codex and Gemini connectivity. If any test fails, the pipeline does not start.

Token usage is tracked across all agent calls and all providers, written to `TOKEN_USAGE.md` and `token_usage.json` after every call. When multiple providers are used, a per-provider summary table is included.

## File Structure

```
proof_agent/
├── README.md                          # This file
├── config.yaml                        # Pipeline, Claude, Codex, Gemini configuration
├── run.sh                             # Entry point (runs smoke test, then pipeline)
├── .gitignore
│
├── code/
│   ├── pipeline.py                    # Main orchestrator (all stages, logging, token tracking)
│   ├── model_runner.py                # Unified async wrappers for Claude, Codex, Gemini
│   └── smoke_test.py                  # Validation (prompts, skills, connectivity for all enabled models)
│
├── prompts/
│   ├── literature_survey.md           # Stage 0: literature survey agent prompt
│   ├── proof_search.md               # Stage 1: proof search agent prompt
│   ├── proof_decompose.md            # Stage 1: decomposition agent prompt (medium/hard)
│   ├── proof_verify.md               # Stage 1: full verification agent prompt (medium/hard)
│   ├── proof_verify_easy.md          # Stage 1: lightweight verification prompt (easy)
│   ├── proof_select.md              # Stage 1: selector agent prompt (multi-model hard only)
│   ├── verdict_proof.md              # Stage 1: verdict agent prompt
│   └── proof_effort_summary.md       # Stage 2: proof effort summary agent prompt
│
├── problem/
│   └── problem.tex                    # Placeholder — put your problem statement here
│
├── human_help/
│   └── human_help.md                  # Drop hints/suggestions here during a run
│
└── skill/
    └── super_math_skill.md            # System prompt: principles for proof construction
```

### Prompt Templates

Each prompt file in `prompts/` is a Markdown template with `{placeholder}` variables filled at runtime by `pipeline.py`:

| Prompt | Placeholders |
|--------|-------------|
| `literature_survey.md` | `problem_file`, `related_info_dir`, `output_dir` |
| `proof_search.md` | `problem_file`, `proof_file`, `output_dir`, `related_info_dir`, `round_num`, `proof_status_file`, `previous_round_instructions`, `human_help_dir` |
| `proof_decompose.md` | `problem_file`, `proof_file`, `output_file`, `output_dir` |
| `proof_verify.md` | `problem_file`, `proof_file`, `decomposition_file`, `output_file`, `output_dir` |
| `proof_verify_easy.md` | `problem_file`, `proof_file`, `output_file`, `output_dir` |
| `proof_select.md` | `problem_file`, `verify_claude`, `verify_codex`, `verify_gemini`, `proof_claude`, `proof_codex`, `proof_gemini`, `selection_file` |
| `verdict_proof.md` | `verification_result_file` |
| `proof_effort_summary.md` | `output_dir`, `outcome`, `total_rounds`, `max_rounds`, `summary_file` |

## Output Structure

Given an output directory `<output>/`, a complete run produces:

### Single-model output (easy / medium / hard with multi-model disabled)

```
<output>/
├── problem.tex                        # Copy of the input problem
├── proof.md                           # The final proof
├── proof_effort_summary.md            # Stage 2: comprehensive summary
├── TOKEN_USAGE.md                     # Human-readable token usage
├── token_usage.json                   # Machine-readable token usage
│
├── related_info/                      # Stage 0: literature survey output
│   ├── difficulty_evaluation.md       #   Difficulty classification (Easy/Medium/Hard)
│   ├── problem_analysis.md            #   Problem classification, key objects, edge cases
│   └── related_theorems.md            #   Applicable theorems, lemmas, counterexamples
│
├── literature_survey_log/             # Stage 0: agent logs
│   ├── AUTO_RUN_STATUS.md
│   ├── AUTO_RUN_STATUS.md.history
│   └── AUTO_RUN_LOG.txt
│
├── verification/                      # Stage 1: proof loop logs
│   ├── AUTO_RUN_STATUS.md
│   ├── AUTO_RUN_STATUS.md.history
│   ├── AUTO_RUN_LOG.txt
│   ├── round_1/
│   │   ├── proof_before_round.md      #   Backup of proof.md before this round
│   │   ├── proof_status.md            #   Proof search agent's log of what it tried
│   │   ├── proof_decomposition.md     #   Miniclaim breakdown (medium/hard only)
│   │   └── verification_result.md     #   Verification verdict
│   └── round_2/ ...
│
├── summary_log/                       # Stage 2: summary agent logs
│   ├── AUTO_RUN_STATUS.md
│   ├── AUTO_RUN_STATUS.md.history
│   └── AUTO_RUN_LOG.txt
│
└── tmp/                               # Temporary files (scratch work)
```

### Multi-model output (hard problems with multi-model enabled)

Each round has per-model subdirectories:

```
verification/
  round_N/
    proof_before_round.md              # Backup of main proof.md
    claude/
      proof.md                         # Claude's proof attempt
      proof_status.md                  # Claude's approach log
      proof_decomposition.md           # Decomposition of Claude's proof
      verification_result.md           # Verification of Claude's proof
    codex/
      proof.md                         # Codex's proof attempt
      proof_status.md
      proof_decomposition.md
      verification_result.md
    gemini/
      proof.md                         # Gemini's proof attempt
      proof_status.md
      proof_decomposition.md
      verification_result.md
    selection.md                       # Selector agent's pick + reasoning
```

The main `proof.md` at the output root always holds the current best (selected) proof.

### Log Files

Each stage writes three log files:

| File | Purpose |
|------|---------|
| `AUTO_RUN_STATUS.md` | Current status table (iteration, step, state, timestamps, PID). Overwritten each update. |
| `AUTO_RUN_STATUS.md.history` | Append-only timestamped event log. |
| `AUTO_RUN_LOG.txt` | Full streaming output from all agent calls — tool invocations, text output, token stats. |

Log directories: `literature_survey_log/`, `verification/`, `summary_log/`.

### Token Usage

`TOKEN_USAGE.md` is updated after every agent call and contains:

- **Summary table**: total input/output tokens, total elapsed time, number of agent calls.
- **Per-provider summary** (when multiple providers used): breakdown by Claude/Codex/Gemini.
- **Per-call breakdown**: each agent call with its provider, token counts, elapsed time, and cumulative totals.

`token_usage.json` contains the same data in JSON format for programmatic consumption.

## Dependencies

### System Requirements

| Dependency | Purpose | Install |
|------------|---------|---------|
| Python 3.11+ | Pipeline runtime | `conda create -n agent python=3.11` |
| [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) | Agent execution backend | `npm install -g @anthropic-ai/claude-code` |
| Codex CLI (optional) | Multi-model proof search | `npm install -g @openai/codex` |
| Gemini CLI (optional) | Multi-model proof search | `npm install -g @anthropic-ai/gemini` |

Codex and Gemini CLIs are only required when `multi_model.enabled: true` in `config.yaml`.

### Python Packages

| Package | Purpose | Install |
|---------|---------|---------|
| `pyyaml` | Config file parsing | `pip install pyyaml` |
| `agent-framework` | ClaudeAgent orchestration | `pip install agent-framework --pre` |

The `agent_framework` package is from the [Microsoft Agent Framework](https://github.com/microsoft/agent-framework). It provides the `ClaudeAgent` class used to orchestrate all agent calls (`from agent_framework.anthropic import ClaudeAgent`).

### Claude Provider Setup

The pipeline supports three Claude providers. Configure exactly one in `config.yaml`:

#### Option 1: Claude Subscription (Pro/Max)

No API key needed; the Claude CLI authenticates through your browser session. Claude Max is required for `opus`; Claude Pro supports `sonnet`.

```yaml
claude:
  provider: "subscription"
  subscription:
    model: "opus"    # or "sonnet", "haiku"
```

#### Option 2: AWS Bedrock

Requires AWS credentials configured (e.g., via `aws configure`).

```yaml
claude:
  provider: "bedrock"
  bedrock:
    model: "us.anthropic.claude-opus-4-6-v1[1m]"
    aws_profile: "default"
```

#### Option 3: Anthropic API Key

Requires an Anthropic API key.

```yaml
claude:
  provider: "api_key"
  api_key:
    model: "claude-opus-4-6-20250609"
    key: "sk-ant-..."
```

### Gemini Provider Setup

When `multi_model.enabled: true` and using Gemini for parallel proof search, if you are using Gemini through API, then you must provide a Google Gemini API key in config. Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey).

```yaml
gemini:
  cli_path: "gemini"
  model: "gemini-3.1-pro-preview"
  api_key: "your-gemini-api-key-here"
```

The pipeline will set the `GEMINI_API_KEY` environment variable automatically when calling the Gemini CLI.

### Codex Provider Setup
When `multi_model.enabled: true` and using Codex for parallel proof search, you don't need to put api key of codex in config, even if you are using Codex through API. Just make sure you can call codex CLI.

## Installation

```bash
# 1. Install Claude CLI
npm install -g @anthropic-ai/claude-code

# 2. (Optional) Install Codex and Gemini CLIs for multi-model mode
npm install -g @openai/codex
# Install Gemini CLI per Google's instructions

# 3. Verify each CLI works with the model you configured in config.yaml
#    Don't just check --version — actually send a test prompt to confirm
#    the model is accessible with your credentials/subscription.
claude "say hello"
codex "say hello"              # optional, only if multi_model enabled
gemini -m gemini-3.1-pro-preview "say hello"  # optional, use your configured model

# 4. Create and activate the agent conda environment
conda create -n agent python=3.11 -y
conda activate agent

# 5. Install Python dependencies
pip install pyyaml
pip install agent-framework --pre

# 6. Configure config.yaml
#    - Set Claude provider (subscription/bedrock/api_key)
#    - Set multi_model.enabled to true/false
#    - Configure codex/gemini sections if using multi-model
#    - Set gemini.api_key if using Gemini (get key from Google AI Studio)

# 7. Run the smoke test to verify everything works
conda activate agent
python code/smoke_test.py
```

## Usage

### Quick Start

1. Place your problem statement in `problem/problem.tex`.
2. Optionally drop hints or guidance into `human_help/`.
3. Run the pipeline:

```bash
# Uses problem/problem.tex by default
bash run.sh

# Or specify a custom problem file and/or output directory
bash run.sh /path/to/problem.tex /path/to/output

# Directly via Python (skips smoke test)
python code/pipeline.py \
    --input problem/problem.tex \
    --output proof_output \
    --config config.yaml
```

`run.sh` runs the smoke test first — if any check fails, the pipeline does not start.

### Input Format

Place your problem in `problem/problem.tex`. The file should contain a mathematical problem statement in LaTeX. For example:

```latex
\begin{problem}
Let $f: [0,1] \to \mathbb{R}$ be a continuous function satisfying
$f(0) = f(1) = 0$ and $f(x) > 0$ for all $x \in (0,1)$.
Prove that there exists $c \in (0,1)$ such that
\[
  \frac{f'(c)}{f(c)} = \frac{1}{1-c}.
\]
\end{problem}
```

### Human Guidance

You can influence the proof search by placing files in `human_help/`. The proof search agent reads this directory at the start of every round. Use it to:

- Suggest a proof strategy or technique
- Point out an error you noticed in a previous round's proof
- Provide a hint about a key lemma or theorem
- Steer the agent away from a dead-end approach

You can add or update files while the pipeline is running — the agent picks up changes at the start of the next round.

### Smoke Test

The smoke test validates the setup before the pipeline runs:

```bash
python code/smoke_test.py
```

It checks:
1. All prompt files exist
2. All skill files exist
3. Prompt templates render without unresolved placeholders
4. Skill file loads correctly
5. ClaudeAgent can connect and respond
6. Config file has required fields
7. Selector prompt (`proof_select.md`) renders correctly
8. **When `multi_model.enabled: true`:** Codex and Gemini CLIs are installed and respond correctly. If either is missing or broken, the test **fails** — fix them or set `multi_model.enabled: false`.

### Monitoring a Run

While the pipeline is running:

```bash
# Current status
cat <output>/verification/AUTO_RUN_STATUS.md

# Event history
cat <output>/verification/AUTO_RUN_STATUS.md.history

# Token usage so far
cat <output>/TOKEN_USAGE.md

# Full streaming log
tail -f <output>/verification/AUTO_RUN_LOG.txt

# Literature survey log
cat <output>/literature_survey_log/AUTO_RUN_LOG.txt

# Summary agent log
cat <output>/summary_log/AUTO_RUN_LOG.txt

# Check a specific round's artifacts
cat <output>/verification/round_1/proof_decomposition.md
cat <output>/verification/round_1/verification_result.md

# Multi-model: check per-model proofs and selection
cat <output>/verification/round_1/claude/proof.md
cat <output>/verification/round_1/codex/proof.md
cat <output>/verification/round_1/selection.md
```

## Configuration Reference

`config.yaml` fields:

```yaml
pipeline:
  max_proof_iterations: 9       # Max rounds before stopping. Default: 9.

  multi_model:
    enabled: true               # true: hard problems use Claude+Codex+Gemini in parallel
                                # false: all problems use Claude only (no selector needed)
    difficulty_threshold: "hard" # "hard" or "medium" — trigger threshold for multi-model

claude:
  cli_path: "claude"
  permission_mode: "bypassPermissions"
  provider: "subscription"      # "subscription", "bedrock", or "api_key"

  subscription:
    model: "opus"               # "opus", "sonnet", or "haiku"
  bedrock:
    model: "us.anthropic.claude-opus-4-6-v1[1m]"
    aws_profile: "default"
  api_key:
    model: "claude-opus-4-6-20250609"
    key: ""

codex:
  cli_path: "codex"
  model: "gpt-5.4"
  reasoning_effort: "xhigh"

gemini:
  cli_path: "gemini"
  model: "gemini-3.1-pro-preview"  # or "gemini-3-flash-preview"
  api_key: ""                      # Google Gemini API key (required for Gemini CLI)
```

## Security Warning

This pipeline runs Claude CLI with `permission_mode: "bypassPermissions"`. This means the agent can read, write, and execute files **without confirmation**. When multi-model is enabled, Codex and Gemini also run with sandbox bypassed.

**Recommendations:**
- Review the prompts in `prompts/` before running.
- Run in an isolated environment (container or VM) when possible.
- Avoid running on machines with sensitive credentials or data.
- Monitor the agent logs (`AUTO_RUN_LOG.txt`) during execution.

## Architecture

```
                           problem.tex
                               |
                               v
                  +------------------------+
                  |  Literature Survey      |   Stage 0
                  |  Agent (Claude)         |   (classifies difficulty,
                  +------------------------+    surveys related work)
                               |
                     related_info/ (3 files)
                               |
                     difficulty = Easy / Medium / Hard
                               |
           +-------------------+-------------------+
           |                   |                   |
         Easy               Medium            Hard + multi_model
           |                   |                   |
           v                   v                   v
    [3-step round]     [4-step round]      [6-step parallel round]
                                                   |
                                          +--------+--------+
                                          |        |        |
                                        Claude   Codex   Gemini
                                          |        |        |
                                          v        v        v
                                       3 proofs (parallel)
                                          |        |        |
                                       3 decompositions (Claude, parallel)
                                          |        |        |
                                       3 verifications (Claude, parallel)
                                          |
                                          v
                                    Selector Agent
                                    (picks best proof)
                                          |
                                          v
                                    Verdict Agent
                                    (DONE / CONTINUE)
                                          |
                               +----------+----------+
                               |                     |
                             DONE               CONTINUE
                               |                     |
                               v                     v
                         +----------+          next round
                         | Summary  |
                         | Agent    |   Stage 2
                         +----------+
                               |
                               v
                    proof_effort_summary.md
```
