# Proof Agent

A multi-agent pipeline that takes a mathematical problem statement in LaTeX and produces a rigorous natural-language proof. The pipeline uses Claude as the underlying LLM, orchestrated through the [Agent Framework](https://github.com/microsoft/agent-framework). It certainly perform stronger than chatbot version of various models on math proving tasks, since it uses agentic loops to search and verify math proofs instead of answering question in one shot.

## How It Works

The pipeline runs in three stages:

**Stage 0 — Literature Survey.** A survey agent reads the problem and first evaluates its difficulty (Easy / Medium / Hard), then conducts an investigation of the mathematical landscape scaled to that difficulty: classifying the problem, identifying applicable theorems, cataloguing proof techniques, and flagging likely dead ends. Easy problems get a brief survey; hard problems get the full treatment. The results are saved to `related_info/` for the proof agent to reference.

**Stage 1 — Proof Search Loop.** An iterative loop of three agents runs up to `max_proof_iterations` rounds (default 9):

1. **Proof Search Agent** — Reads the problem, the literature survey, and any previous-round feedback. Writes or refines a complete natural-language proof in `proof.md`.
2. **Verification Agent** — Independently reviews the proof for logical validity, completeness, correctness of cited results, and alignment with the problem statement. Writes a structured verdict to a per-round verification result file.
3. **Verdict Agent** — Reads the verification result and returns a single word: `DONE` (proof is correct) or `CONTINUE` (try again).

If the verdict is `DONE`, the pipeline stops. Otherwise the next round begins, with the proof search agent reading the previous round's verification feedback and proof status log to avoid repeating failed approaches.

**Stage 2 — Proof Effort Summary.** After the proof loop finishes (either success or max iterations), a summary agent reads all generated files and writes `proof_effort_summary.md` — a comprehensive report covering the problem, final proof status, round-by-round history, approaches tried, key insights, and resource usage.

All agents receive `skill/super_math_skill.md` as a system-level instruction — a 38-principle guide to mathematical proof methodology.

**Resume support.** If the pipeline is interrupted and re-run with the same output directory, it automatically detects prior progress: skips the literature survey if already complete, deletes any incomplete last round, restores `proof.md` from a backup, and resumes from where it left off.

Token usage is tracked across all agent calls and written to `TOKEN_USAGE.md` (human-readable) and `token_usage.json` (machine-readable) after every call.

## File Structure

```
proof_agent/
├── README.md                          # This file
├── config.yaml                        # Pipeline and Claude provider configuration
├── run.sh                             # Entry point shell script
│
├── code/
│   ├── pipeline.py                    # Main orchestrator (all stages, logging, token tracking)
│   └── smoke_test.py                  # Quick validation (prompts, skills, agent connectivity)
│
├── prompts/
│   ├── literature_survey.md           # Stage 0: literature survey agent prompt
│   ├── proof_search.md               # Stage 1, Step 1: proof search agent prompt
│   ├── proof_verify.md               # Stage 1, Step 2: verification agent prompt
│   ├── verdict_proof.md              # Stage 1, Step 3: verdict agent prompt
│   └── proof_effort_summary.md       # Stage 2: proof effort summary agent prompt
│
└── skill/
    └── super_math_skill.md            # System prompt: 38 principles for proof construction
```

### Prompt Templates

Each prompt file in `prompts/` is a Markdown template with `{placeholder}` variables that are filled at runtime by `pipeline.py`. The placeholders for each prompt:

| Prompt | Placeholders |
|--------|-------------|
| `literature_survey.md` | `problem_file`, `related_info_dir`, `output_dir` |
| `proof_search.md` | `problem_file`, `proof_file`, `output_dir`, `related_info_dir`, `round_num`, `proof_status_file`, `previous_round_instructions` |
| `proof_verify.md` | `problem_file`, `proof_file`, `output_file`, `output_dir` |
| `verdict_proof.md` | `verification_result_file` |
| `proof_effort_summary.md` | `output_dir`, `outcome`, `total_rounds`, `max_rounds`, `summary_file` |

## Output Structure

Given an output directory `<output>/`, a complete run produces:

```
<output>/
├── problem.tex                        # Copy of the input problem
├── proof.md                           # The final proof (written/refined by proof search agent)
├── proof_effort_summary.md            # Stage 2: comprehensive summary of the entire proof effort
├── TOKEN_USAGE.md                     # Human-readable token usage summary table
├── token_usage.json                   # Machine-readable token usage data
│
├── related_info/                      # Stage 0: literature survey output
│   ├── difficulty_evaluation.md       #   Difficulty classification (Easy/Medium/Hard) with justification
│   ├── problem_analysis.md            #   Problem classification, key objects, edge cases
│   ├── related_theorems.md            #   Applicable theorems, lemmas, counterexamples
│   └── proof_strategies.md            #   Candidate techniques, analogous proofs, dead ends
│
├── literature_survey_log/             # Stage 0: agent logs
│   ├── AUTO_RUN_STATUS.md             #   Current status snapshot
│   ├── AUTO_RUN_STATUS.md.history     #   Timestamped event history
│   └── AUTO_RUN_LOG.txt               #   Full text log (streaming agent output)
│
├── verification/                      # Stage 1: proof loop logs
│   ├── AUTO_RUN_STATUS.md             #   Current status snapshot
│   ├── AUTO_RUN_STATUS.md.history     #   Timestamped event history
│   ├── AUTO_RUN_LOG.txt               #   Full text log
│   ├── round_1/
│   │   ├── proof_status.md            #   Proof search agent's log of what it tried
│   │   └── verification_result.md     #   Verification agent's structured verdict
│   ├── round_2/
│   │   ├── proof_status.md
│   │   └── verification_result.md
│   └── ...                            #   One directory per round
│
└── tmp/                               # Temporary files created by agents (scratch work)
```

### Log Files

Each stage writes three log files:

| File | Purpose |
|------|---------|
| `AUTO_RUN_STATUS.md` | Current status table (iteration, step, state, timestamps, PID). Overwritten each update. |
| `AUTO_RUN_STATUS.md.history` | Append-only timestamped event log (e.g., "Iteration 2: Proof search started"). |
| `AUTO_RUN_LOG.txt` | Full streaming output from all agent calls — tool invocations, text output, token stats. |

### Token Usage

`TOKEN_USAGE.md` is updated after every agent call and contains:

- **Summary table**: total input/output tokens, total elapsed time, estimated cost, number of agent calls.
- **Per-call breakdown**: each agent call with its token counts, elapsed time, cumulative totals, and estimated cost.

Pricing is looked up from `MODEL_PRICING` in `pipeline.py`. Subscription models (`opus`, `sonnet`, `haiku`) show `subscription` instead of a dollar amount. API/Bedrock models show USD estimates.

`token_usage.json` contains the same data in JSON format for programmatic consumption.

## Dependencies

### System Requirements

| Dependency | Purpose | Install |
|------------|---------|---------|
| Python 3.11+ | Pipeline runtime | `conda create -n agent python=3.11` |
| [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) | Agent execution backend | `npm install -g @anthropic-ai/claude-code` |

### Python Packages

| Package | Purpose | Install |
|---------|---------|---------|
| `pyyaml` | Config file parsing | `pip install pyyaml` |
| `agent-framework` | ClaudeAgent orchestration | `pip install agent-framework --pre` |

The `agent_framework` package is from the [Microsoft Agent Framework](https://github.com/microsoft/agent-framework). It provides the `ClaudeAgent` class used to orchestrate all agent calls (`from agent_framework.anthropic import ClaudeAgent`).

### Claude Provider Setup

The pipeline supports three Claude providers. Configure exactly one in `config.yaml`:

#### Option 1: Claude Subscription (Pro/Max)

If you purchased a Claude plan through the [Anthropic website](https://claude.ai) (i.e., you log in at claude.ai and pay for Claude Pro or Claude Max), you are a **subscription** user — use this option. No API key is needed; the Claude CLI authenticates through your browser session. Claude Max is required for `opus`; Claude Pro supports `sonnet`.

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

## Installation

```bash
# 1. Install Claude CLI
npm install -g @anthropic-ai/claude-code

# 2. Verify Claude CLI works standalone
#    Run `claude` in your terminal and confirm it launches and responds.
#    If using a subscription, log in via browser when prompted.
#    If using Bedrock, ensure `aws configure` is set up first.
#    If using an API key, set ANTHROPIC_API_KEY or configure later in config.yaml.
claude --version

# 3. Create and activate the agent conda environment
conda create -n agent python=3.11 -y
conda activate agent

# 4. Install Python dependencies
pip install pyyaml
pip install agent-framework --pre

# 5. Configure your Claude provider in config.yaml
#    Edit config.yaml and set `provider` to one of:
#    "subscription", "bedrock", or "api_key"
#    Then fill in the corresponding section.

# 6. Run the smoke test to verify everything works
conda activate agent
python code/smoke_test.py
```

## Usage

### Quick Start

1. Place your problem statement in `problem/problem.tex`.
2. Run the pipeline:

```bash
# Uses problem/problem.tex by default
bash run.sh

# Or specify a custom problem file and/or output directory
bash run.sh /path/to/problem.tex /path/to/output

# Directly via Python
python code/pipeline.py \
    --input problem/problem.tex \
    --output proof_output \
    --config config.yaml
```

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

The file can use any LaTeX formatting — theorem environments, custom macros, etc. The agents read the raw LaTeX source directly.

### Smoke Test

The smoke test validates the setup without making expensive agent calls (except one short connectivity check):

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

### Monitoring a Run

While the pipeline is running, you can check progress:

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
```

## Configuration Reference

`config.yaml` fields:

```yaml
pipeline:
  max_proof_iterations: 9    # Maximum rounds of proof search/verify/verdict
                              # before the pipeline stops. Default: 9.

claude:
  cli_path: "claude"          # Path to the Claude CLI binary.
  permission_mode: "bypassPermissions"  # Permission mode for Claude CLI.

  provider: "subscription"    # One of: "subscription", "bedrock", "api_key"

  subscription:
    model: "opus"             # Shorthand: "opus", "sonnet", or "haiku"

  bedrock:
    model: "us.anthropic.claude-opus-4-6-v1[1m]"
    aws_profile: "default"    # AWS profile name for credentials

  api_key:
    model: "claude-opus-4-6-20250609"
    key: ""                   # Your Anthropic API key
```

## Security Warning

This pipeline runs Claude CLI with `permission_mode: "bypassPermissions"` (configured in `config.yaml`). This means the agent can read, write, and execute files on your system **without asking for confirmation**. While this is necessary for unattended multi-agent operation, it carries inherent security risks — the agent has unrestricted access to your filesystem and can execute arbitrary commands during its run.

**Recommendations:**
- Review the prompts in `prompts/` before running to understand what the agents are instructed to do.
- Run the pipeline in an isolated environment (e.g., a container or VM) when possible.
- Avoid running on machines with sensitive credentials or data that the agent should not access.
- Monitor the agent logs (`AUTO_RUN_LOG.txt`) during execution.

## Architecture

```
                          problem.tex
                              |
                              v
                 +------------------------+
                 |  Literature Survey      |   Stage 0
                 |  Agent                  |
                 +------------------------+
                              |
                    related_info/ (4 files)
                              |
          +-------------------+-------------------+
          |                                       |
          v                                       |
+-------------------+                             |
| Proof Search      |  <-- reads related_info/    |
| Agent             |  <-- reads prev round       |   Stage 1
+-------------------+  --> writes proof.md        |
          |                                       |
          v                                       |
+-------------------+                             |
| Verification      |                             |
| Agent             |                             |
+-------------------+  --> verification_result.md |
          |                                       |
          v                                       |
+-------------------+                             |
| Verdict Agent     |                             |
+-------------------+                             |
     |         |                                  |
   DONE    CONTINUE ------> next round -----------+
     |
     v
+-------------------+
| Summary Agent     |   Stage 2
+-------------------+
     |
     v
  proof_effort_summary.md
```
