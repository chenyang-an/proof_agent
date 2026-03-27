#!/usr/bin/env python3
"""
Proof Agent pipeline: takes a problem.tex (LaTeX) and produces a natural-language proof.

Three-stage pipeline:
  Stage 0 — Literature Survey agent: deep-dives into the problem context and related results
  Stage 1 — Proof Search Loop (iterative, up to max_proof_iterations rounds):
    1a. Proof Search agent    — writes/refines the proof (informed by the survey)
    1b. Decomposition agent   — decomposes the proof into miniclaims/miniproofs
    1c. Verification agent    — checks each miniclaim and the full proof for correctness
    1d. Verdict agent         — decides DONE or CONTINUE
  Stage 2 — Summary agent: reads all generated files and writes proof_effort_summary.md

Supports resuming interrupted runs: detects prior progress on disk, skips
completed stages, deletes incomplete rounds, and restores proof.md from backups.
"""

import asyncio
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_prompt(prompts_dir: str, name: str, **kwargs) -> str:
    """Load a prompt template and fill placeholders."""
    path = os.path.join(prompts_dir, name)
    with open(path) as f:
        template = f.read()
    return template.format(**kwargs)


def make_claude_options(claude_cfg: dict, working_dir: str) -> dict:
    """Build options dict for the Claude CLI subprocess runner.

    Supports three providers:
      - "subscription": Claude Pro/Max subscription (no keys, shorthand model names)
      - "bedrock": AWS Bedrock (requires AWS credentials)
      - "api_key": Anthropic API key (requires ANTHROPIC_API_KEY)
    """
    provider = claude_cfg.get("provider", "subscription")
    env = {}

    if provider == "subscription":
        sub_cfg = claude_cfg.get("subscription", {})
        model = sub_cfg.get("model", "opus")
    elif provider == "api_key":
        api_cfg = claude_cfg.get("api_key", {})
        model = api_cfg.get("model", "claude-opus-4-6-20250609")
        key = api_cfg.get("key", "")
        if not key:
            raise ValueError("config.yaml: claude.api_key.key is empty. Set your Anthropic API key.")
        env["ANTHROPIC_API_KEY"] = key
    elif provider == "bedrock":
        bedrock_cfg = claude_cfg.get("bedrock", {})
        model = bedrock_cfg.get("model", "us.anthropic.claude-opus-4-6-v1[1m]")
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
        env["AWS_PROFILE"] = bedrock_cfg.get("aws_profile", "default")
    else:
        raise ValueError(f"config.yaml: unknown claude.provider '{provider}'. Use 'subscription', 'bedrock', or 'api_key'.")

    return {
        "cli_path": claude_cfg.get("cli_path", "claude"),
        "model": model,
        "cwd": working_dir,
        "env": env,
    }


def check_prerequisites():
    """Check that required tools are available."""
    missing = []
    for cmd in ["claude", "python3"]:
        if shutil.which(cmd) is None:
            missing.append(cmd)
    if missing:
        print(f"ERROR: Missing required tools: {', '.join(missing)}")
        print("Please install them before running the pipeline.")
        sys.exit(1)
    try:
        import yaml as _y  # noqa: F401
    except ImportError:
        missing.append("pyyaml (pip install pyyaml)")
    if missing:
        print(f"ERROR: Missing Python packages: {', '.join(missing)}")
        sys.exit(1)


def check_multi_model_providers(config: dict) -> list[str]:
    """Check which multi-model providers are available.

    Returns a list of available providers (always includes "claude").
    Prints warnings for missing CLIs but does not exit.
    """
    providers = ["claude"]
    for name, cfg_key in [("codex", "codex"), ("gemini", "gemini")]:
        cli = config.get(cfg_key, {}).get("cli_path", name)
        if shutil.which(cli) is not None:
            providers.append(name)
        else:
            print(f"  WARNING: '{cli}' CLI not found — {name} will be excluded from multi-model runs")
    return providers


def _file_nonempty(path: str) -> bool:
    """Return True if *path* exists and has non-whitespace content."""
    if not os.path.exists(path):
        return False
    with open(path) as f:
        return bool(f.read().strip())


def _parse_verdict_from_file(path: str) -> str:
    """Parse the Overall Verdict from a verification_result.md file.

    Looks for a line containing 'Overall Verdict' with PASS or FAIL.
    Returns 'PASS', 'FAIL', or 'UNKNOWN'.
    """
    with open(path) as f:
        for line in f:
            if "overall verdict" in line.lower():
                upper = line.upper()
                if "PASS" in upper:
                    return "PASS"
                if "FAIL" in upper:
                    return "FAIL"
    return "UNKNOWN"


def _parse_difficulty(output_dir: str) -> str:
    """Parse the difficulty classification from difficulty_evaluation.md.

    Looks for a line like '## Classification: Easy' (or Medium / Hard).
    Returns 'easy', 'medium', 'hard', or 'unknown'.
    """
    path = os.path.join(output_dir, "related_info", "difficulty_evaluation.md")
    if not os.path.exists(path):
        return "unknown"
    with open(path) as f:
        for line in f:
            if "classification" in line.lower():
                upper = line.upper()
                if "EASY" in upper:
                    return "easy"
                if "MEDIUM" in upper:
                    return "medium"
                if "HARD" in upper:
                    return "hard"
    return "unknown"


def _is_parallel_round(round_dir: str) -> bool:
    """Return True if round_dir contains per-model subdirectories (parallel mode)."""
    return any(
        os.path.isdir(os.path.join(round_dir, m))
        for m in ("claude", "codex", "gemini")
    )


def _parallel_round_complete(round_dir: str) -> bool:
    """Return True if a parallel round has a selection.md (fully complete)."""
    return _file_nonempty(os.path.join(round_dir, "selection.md"))


def detect_resume_state(output_dir: str, skip_decomposition: bool = False) -> tuple[bool, int, str]:
    """Scan the output directory for progress from a previous run.

    Returns (skip_survey, start_round, resume_from_step):
      - skip_survey: True if the literature survey is already complete.
      - start_round: the round number to start (or resume) the proof loop from.
        1 means no prior rounds exist.
      - resume_from_step: which step to resume from within start_round.

        For **single-model** (easy/medium) rounds:
          "proof_search"   — start the round from scratch
          "decomposition"  — proof search done, resume from decomposition
          "verification"   — proof search + decomposition done, resume from verification

        For **parallel** (hard) rounds:
          "proof_search"   — start the round from scratch
          "parallel_decomposition"  — proof searches done, resume from decomposition
          "parallel_verification"   — decompositions done, resume from verification
          "parallel_selection"      — verifications done, resume from selector

        When skip_decomposition=True, "decomposition" and "parallel_decomposition"
        are never returned — rounds go directly from proof search to verification.

    Side effects:
      - Deletes the last round directory if proof search did NOT complete
        (no proof_status.md), and restores proof.md from backup.
    """
    # --- Check literature survey completeness ---
    related_info_dir = os.path.join(output_dir, "related_info")
    survey_files = [
        "difficulty_evaluation.md",
        "problem_analysis.md",
        "related_theorems.md",
    ]
    skip_survey = all(
        _file_nonempty(os.path.join(related_info_dir, f)) for f in survey_files
    )

    # --- Scan round directories ---
    verify_dir = os.path.join(output_dir, "verification")
    if not os.path.isdir(verify_dir):
        return skip_survey, 1, "proof_search"

    # Collect round numbers that have a directory
    round_nums: list[int] = []
    for name in os.listdir(verify_dir):
        if name.startswith("round_"):
            try:
                round_nums.append(int(name.split("_", 1)[1]))
            except ValueError:
                continue
    if not round_nums:
        return skip_survey, 1, "proof_search"

    round_nums.sort()
    last = round_nums[-1]
    last_dir = os.path.join(verify_dir, f"round_{last}")

    # ====== Parallel (hard mode) round ======
    if _is_parallel_round(last_dir):
        if _parallel_round_complete(last_dir):
            return skip_survey, last + 1, "proof_search"

        # Check per-model completion to find resume point
        models_with_proof = []
        models_with_decomp = []
        models_with_verify = []
        for m in ("claude", "codex", "gemini"):
            mdir = os.path.join(last_dir, m)
            if not os.path.isdir(mdir):
                continue
            if _file_nonempty(os.path.join(mdir, "proof_status.md")):
                models_with_proof.append(m)
            if _file_nonempty(os.path.join(mdir, "proof_decomposition.md")):
                models_with_decomp.append(m)
            if _file_nonempty(os.path.join(mdir, "verification_result.md")):
                models_with_verify.append(m)

        if len(models_with_verify) >= len(models_with_proof) and models_with_verify:
            # All completed models have verifications — just need selector
            print(f"  Round {last}: verifications complete, selection incomplete — will resume from selection")
            return skip_survey, last, "parallel_selection"

        if skip_decomposition:
            # No decomposition step — go directly from proof search to verification
            if models_with_proof:
                print(f"  Round {last}: proof search complete, verification incomplete — will resume from verification")
                return skip_survey, last, "parallel_verification"
        else:
            if len(models_with_decomp) >= len(models_with_proof) and models_with_decomp:
                print(f"  Round {last}: decompositions complete, verification incomplete — will resume from verification")
                return skip_survey, last, "parallel_verification"

            if models_with_proof:
                print(f"  Round {last}: proof search complete for {models_with_proof}, decomposition incomplete — will resume from decomposition")
                return skip_survey, last, "parallel_decomposition"

        # No proof search completed — delete and restart
        proof_file = os.path.join(output_dir, "proof.md")
        backup = os.path.join(last_dir, "proof_before_round.md")
        if os.path.exists(backup):
            shutil.copy2(backup, proof_file)
            print(f"  Restored proof.md from round {last} backup")
        shutil.rmtree(last_dir)
        print(f"  Deleted incomplete parallel round_{last}")
        return skip_survey, last, "proof_search"

    # ====== Single-model (easy/medium) round ======
    status_ok = _file_nonempty(os.path.join(last_dir, "proof_status.md"))
    decomp_ok = _file_nonempty(os.path.join(last_dir, "proof_decomposition.md"))
    verify_ok = _file_nonempty(os.path.join(last_dir, "verification_result.md"))

    if skip_decomposition:
        # No decomposition file expected — only check proof_status and verification
        if status_ok and verify_ok:
            return skip_survey, last + 1, "proof_search"
        if status_ok and not verify_ok:
            print(f"  Round {last}: proof search complete, verification incomplete — will resume from verification")
            return skip_survey, last, "verification"
    else:
        if status_ok and decomp_ok and verify_ok:
            # Last round is fully complete — resume from the next one.
            return skip_survey, last + 1, "proof_search"

        if status_ok and decomp_ok and not verify_ok:
            # Proof search + decomposition completed but verification didn't.
            print(f"  Round {last}: decomposition complete, verification incomplete — will resume from verification")
            return skip_survey, last, "verification"

        if status_ok and not decomp_ok:
            # Proof search completed but decomposition didn't.
            print(f"  Round {last}: proof search complete, decomposition incomplete — will resume from decomposition")
            return skip_survey, last, "decomposition"

    # Proof search didn't complete — delete the round and restore proof.md.
    proof_file = os.path.join(output_dir, "proof.md")
    backup = os.path.join(last_dir, "proof_before_round.md")
    if os.path.exists(backup):
        shutil.copy2(backup, proof_file)
        print(f"  Restored proof.md from round {last} backup")

    shutil.rmtree(last_dir)
    print(f"  Deleted incomplete round_{last}")

    # Redo this round from scratch.
    return skip_survey, last, "proof_search"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class PipelineLogger:
    """Persistent logging to AUTO_RUN_STATUS.md, .history, and AUTO_RUN_LOG.txt."""

    def __init__(self, log_dir: str, phase: str):
        os.makedirs(log_dir, exist_ok=True)
        self.log_dir = log_dir
        self.phase = phase
        self.status_file = os.path.join(log_dir, "AUTO_RUN_STATUS.md")
        self.history_file = os.path.join(log_dir, "AUTO_RUN_STATUS.md.history")
        self.log_file = os.path.join(log_dir, "AUTO_RUN_LOG.txt")
        self.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.pid = os.getpid()

        # Append to history (not truncate) so resumed runs preserve prior history
        self.append_history(f"{phase} started")

    def update_status(self, iteration: int, max_iter: int, step: str, state: str, details: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history = ""
        if os.path.exists(self.history_file):
            with open(self.history_file) as f:
                history = f.read()
        with open(self.status_file, "w") as f:
            f.write(f"# {self.phase} - Auto Status\n\n")
            f.write("| Field | Value |\n|-------|-------|\n")
            f.write(f"| **Status** | {state} |\n")
            f.write(f"| **Current Iteration** | {iteration} / {max_iter} |\n")
            f.write(f"| **Current Step** | {step} |\n")
            f.write(f"| **Started At** | {self.start_time} |\n")
            f.write(f"| **Last Updated** | {now} |\n")
            f.write(f"| **PID** | {self.pid} |\n\n")
            f.write(f"## Current Activity\n{details}\n\n")
            f.write(f"## Progress History\n{history}\n")

    def append_history(self, msg: str):
        now = datetime.now().strftime("%H:%M:%S")
        with open(self.history_file, "a") as f:
            f.write(f"- [{now}] {msg}\n")

    def log(self, msg: str):
        print(msg)
        with open(self.log_file, "a") as f:
            f.write(msg + "\n")

    def finalize(self, iteration: int, max_iter: int, exit_state: str, details: str):
        self.update_status(iteration, max_iter, exit_state, exit_state, details)
        self.append_history(f"Process ended: {exit_state}")


# ---------------------------------------------------------------------------
# Token usage tracking
# ---------------------------------------------------------------------------

class TokenTracker:
    """Accumulates token usage across all agent calls and persists to disk
    after every update so the user can check TOKEN_USAGE.md at any time.

    Supports multi-provider tracking: each call can specify a provider
    (claude/codex/gemini) and model name. Per-provider subtotals are shown
    in TOKEN_USAGE.md when more than one provider is used.
    """

    def __init__(self, output_dir: str, model: str):
        self.output_dir = output_dir
        self.model = model  # default model label (backward compat)
        self.calls: list[dict] = []
        self.total_input = 0
        self.total_output = 0
        self.total_elapsed = 0.0
        self.per_provider: dict[str, dict] = {}  # provider → {input, output, calls, model}
        self.md_path = os.path.join(output_dir, "TOKEN_USAGE.md")
        self.json_path = os.path.join(output_dir, "token_usage.json")
        self.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def record(self, call_name: str, input_tokens: int, output_tokens: int,
               elapsed: float, provider: str = "claude", model: str = ""):
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.total_elapsed += elapsed

        # Per-provider tracking
        if provider not in self.per_provider:
            self.per_provider[provider] = {
                "input": 0, "output": 0, "calls": 0,
                "model": model or self.model,
            }
        self.per_provider[provider]["input"] += input_tokens
        self.per_provider[provider]["output"] += output_tokens
        self.per_provider[provider]["calls"] += 1

        self.calls.append({
            "call": len(self.calls) + 1,
            "name": call_name,
            "provider": provider,
            "model": model or self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "elapsed_s": round(elapsed, 1),
            "cumul_input": self.total_input,
            "cumul_output": self.total_output,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save()

    def _save(self):
        """Write both TOKEN_USAGE.md and token_usage.json."""
        # --- Markdown ---
        lines = [
            "# Token Usage\n",
            f"**Primary Model:** `{self.model}`  ",
            f"**Started:** {self.start_time}  ",
            f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n",
            "## Summary\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total input tokens | {self.total_input:,} |",
            f"| Total output tokens | {self.total_output:,} |",
            f"| Total tokens | {self.total_input + self.total_output:,} |",
            f"| Total elapsed | {self.total_elapsed:.0f}s |",
            f"| Agent calls | {len(self.calls)} |\n",
        ]

        # Per-provider summary (only shown when multiple providers used)
        if len(self.per_provider) > 1:
            lines.append("## Per-Provider Summary\n")
            lines.append("| Provider | Model | Input | Output | Total | Calls |")
            lines.append("|----------|-------|------:|-------:|------:|------:|")
            for prov, stats in sorted(self.per_provider.items()):
                total = stats['input'] + stats['output']
                lines.append(
                    f"| {prov} | {stats['model']} "
                    f"| {stats['input']:,} | {stats['output']:,} "
                    f"| {total:,} | {stats['calls']} |"
                )
            lines.append("")

        lines.append("## Per-Call Breakdown\n")
        if len(self.per_provider) > 1:
            lines.append("| # | Agent | Provider | Input | Output | Time | Cumul In | Cumul Out |")
            lines.append("|---|-------|----------|------:|-------:|-----:|---------:|----------:|")
        else:
            lines.append("| # | Agent | Input | Output | Time | Cumul In | Cumul Out |")
            lines.append("|---|-------|------:|-------:|-----:|---------:|----------:|")

        for c in self.calls:
            if len(self.per_provider) > 1:
                lines.append(
                    f"| {c['call']} | {c['name']} | {c.get('provider', 'claude')} "
                    f"| {c['input_tokens']:,} | {c['output_tokens']:,} "
                    f"| {c['elapsed_s']}s "
                    f"| {c['cumul_input']:,} | {c['cumul_output']:,} |"
                )
            else:
                lines.append(
                    f"| {c['call']} | {c['name']} "
                    f"| {c['input_tokens']:,} | {c['output_tokens']:,} "
                    f"| {c['elapsed_s']}s "
                    f"| {c['cumul_input']:,} | {c['cumul_output']:,} |"
                )
        lines.append("")

        with open(self.md_path, "w") as f:
            f.write("\n".join(lines))

        # --- JSON ---
        data = {
            "model": self.model,
            "started": self.start_time,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_input_tokens": self.total_input,
            "total_output_tokens": self.total_output,
            "total_tokens": self.total_input + self.total_output,
            "total_elapsed_s": round(self.total_elapsed, 1),
            "per_provider": self.per_provider,
            "calls": self.calls,
        }
        with open(self.json_path, "w") as f:
            json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------

async def run_agent(
    claude_opts: dict,
    prompt: str,
    logger: PipelineLogger | None = None,
    tools: list | None = None,
    instructions: str | None = None,
    tracker: TokenTracker | None = None,
    call_name: str = "",
) -> str:
    """Run a Claude CLI call via subprocess and return the response text.

    Uses ``claude -p --output-format json`` to get structured output with
    token usage. The agent runs in the working directory specified by
    ``claude_opts["cwd"]`` and has full tool access (file read/write, bash).
    """
    cli_path = claude_opts.get("cli_path", "claude")
    model = claude_opts.get("model", "opus")
    cwd = claude_opts.get("cwd", ".")
    extra_env = claude_opts.get("env", {})

    cmd = [
        cli_path,
        "-p",
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--model", model,
    ]
    if instructions:
        cmd += ["--append-system-prompt", instructions]
    cmd.append(prompt)

    start_time = datetime.now()
    if logger:
        logger.log(f"[Claude] Starting {call_name} (model={model})")

    # Build environment with provider-specific vars (bedrock, api_key)
    env = None
    if extra_env:
        env = os.environ.copy()
        env.update(extra_env)

    def _call():
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _call)
    except Exception as exc:
        elapsed = (datetime.now() - start_time).total_seconds()
        if logger:
            logger.log(f"[Claude] ERROR: {exc}")
        if tracker:
            tracker.record(call_name or "agent", 0, 0, elapsed)
        return ""

    elapsed = (datetime.now() - start_time).total_seconds()

    # Parse JSON output
    response = ""
    input_tokens = 0
    output_tokens = 0

    try:
        data = json.loads(result.stdout)
        response = data.get("result", "")

        for _, model_stats in data.get("modelUsage", {}).items():
            input_tokens += model_stats.get("inputTokens", 0)
            output_tokens += model_stats.get("outputTokens", 0)
    except (json.JSONDecodeError, ValueError) as exc:
        if logger:
            logger.log(f"[Claude] JSON parse error: {exc}")
        response = result.stdout.strip()

    if result.returncode != 0 and logger:
        logger.log(f"[Claude] Non-zero exit code: {result.returncode}")

    # Log the response (truncated for readability)
    if logger and response:
        preview = response[:500] + ("..." if len(response) > 500 else "")
        for line in preview.splitlines():
            if line.strip():
                logger.log(line)

    if tracker:
        tracker.record(call_name or "agent", input_tokens, output_tokens, elapsed)

    if logger:
        logger.log(f"[Claude] Completed {call_name} in {elapsed:.0f}s "
                   f"({input_tokens} in / {output_tokens} out)")

    return response


async def run_agent_for_verdict(
    claude_opts: dict,
    prompt: str,
    logger: PipelineLogger | None = None,
    tools: list | None = None,
    tracker: TokenTracker | None = None,
    call_name: str = "",
) -> str:
    """Run agent and extract DONE/CONTINUE verdict from response."""
    text = await run_agent(claude_opts, prompt, logger, tools=tools,
                           tracker=tracker, call_name=call_name)
    for line in reversed(text.strip().splitlines()):
        stripped = line.strip().upper()
        if stripped == "DONE":
            return "DONE"
        if stripped == "CONTINUE":
            return "CONTINUE"
    for line in reversed(text.strip().splitlines()):
        stripped = line.strip().upper()
        if "DONE" in stripped:
            return "DONE"
        if "CONTINUE" in stripped:
            return "CONTINUE"
    return "CONTINUE"


# ---------------------------------------------------------------------------
# Literature survey
# ---------------------------------------------------------------------------

async def run_literature_survey(
    output_dir: str,
    problem_file: str,
    claude_opts: dict,
    prompts_dir: str,
    math_skill: str = "",
    tracker: TokenTracker | None = None,
) -> str:
    """Run the literature survey agent before proof search.
    Returns the path to the related_info directory.
    """
    related_info_dir = os.path.join(output_dir, "related_info")
    os.makedirs(related_info_dir, exist_ok=True)
    log_dir = os.path.join(output_dir, "literature_survey_log")

    logger = PipelineLogger(log_dir, "Literature Survey")
    logger.update_status(1, 1, "Literature Survey", "RUNNING", "Running literature survey agent...")

    survey_prompt = load_prompt(
        prompts_dir, "literature_survey.md",
        problem_file=problem_file,
        related_info_dir=related_info_dir,
        output_dir=output_dir,
    )

    await run_agent(claude_opts, survey_prompt, logger, instructions=math_skill or None,
                    tracker=tracker, call_name="Literature Survey")

    logger.finalize(1, 1, "FINISHED", "Literature survey complete.")
    return related_info_dir


# ---------------------------------------------------------------------------
# Proof search loop
# ---------------------------------------------------------------------------

async def _run_parallel_round(
    i: int,
    max_iterations: int,
    output_dir: str,
    problem_file: str,
    claude_opts: dict,
    prompts_dir: str,
    related_info_dir: str,
    proving_skill: str,
    tracker: TokenTracker | None,
    logger: "PipelineLogger",
    verify_dir: str,
    proof_file: str,
    config: dict,
    available_providers: list[str],
    human_help_dir: str,
    resume_from_step: str = "proof_search",
    skip_decomposition: bool = False,
) -> str:
    """Execute one parallel round for hard-mode. Returns 'DONE' or 'CONTINUE'.

    Steps: parallel proof search → parallel decomposition → parallel verification
           → selector → verdict.
    When skip_decomposition=True, the decomposition step is skipped entirely.
    """
    import asyncio as _asyncio
    from model_runner import run_model

    round_dir = os.path.join(verify_dir, f"round_{i}")
    providers = available_providers  # e.g. ["claude", "codex", "gemini"]

    # Create per-model subdirectories
    model_dirs = {}
    for m in providers:
        mdir = os.path.join(round_dir, m)
        os.makedirs(mdir, exist_ok=True)
        model_dirs[m] = mdir

    # Build previous-round instructions (shared by all models)
    prev_round_dir = os.path.join(verify_dir, f"round_{i-1}")
    prev_instructions = ""
    # For parallel rounds, previous verification is in the selected model's subdir,
    # or at the round level as selection.md
    if i > 1:
        # Try to find the selected model's verification from previous round
        prev_selection = os.path.join(prev_round_dir, "selection.md")
        if os.path.exists(prev_selection):
            prev_instructions += f"- Read the PREVIOUS round's proof selection report from {prev_selection}.\n"
        # Also point to each model's verification from previous round
        for m in providers:
            prev_v = os.path.join(prev_round_dir, m, "verification_result.md")
            prev_s = os.path.join(prev_round_dir, m, "proof_status.md")
            if os.path.exists(prev_v):
                prev_instructions += f"- Previous round's {m} verification result: {prev_v}\n"
            if os.path.exists(prev_s):
                prev_instructions += f"- Previous round's {m} proof status: {prev_s}\n"
    if not prev_instructions:
        prev_instructions = "- This is the first round. No previous round data available.\n"

    skip_proof_search = resume_from_step in (
        "parallel_decomposition", "parallel_verification", "parallel_selection",
    )
    skip_decomp_resume = resume_from_step in (
        "parallel_verification", "parallel_selection",
    )
    skip_verification = resume_from_step == "parallel_selection"

    total_steps = 5 if skip_decomposition else 6
    step = 0

    # ==================================================================
    # Step 1: PARALLEL PROOF SEARCH
    # ==================================================================
    step += 1
    if skip_proof_search:
        logger.log(f"--- Resuming round {i}: skipping proof search (already complete) ---")
        logger.append_history(f"Iteration {i}: Parallel proof search SKIPPED (resume)")
    else:
        # Back up proof.md before the round
        proof_backup = os.path.join(round_dir, "proof_before_round.md")
        if os.path.exists(proof_file):
            shutil.copy2(proof_file, proof_backup)

        logger.update_status(i, max_iterations, f"{step}/{total_steps} Parallel Proof Search", "RUNNING",
                             f"Running proof search on {len(providers)} models in parallel...")
        logger.append_history(f"Iteration {i}: Parallel proof search started ({', '.join(providers)})")

        async def _proof_search(provider):
            mdir = model_dirs[provider]
            m_proof = os.path.join(mdir, "proof.md")
            m_status = os.path.join(mdir, "proof_status.md")
            # Each model writes to its own proof.md and proof_status.md
            search_prompt = load_prompt(
                prompts_dir, "proof_search.md",
                problem_file=problem_file,
                proof_file=m_proof,
                output_dir=output_dir,
                related_info_dir=related_info_dir,
                round_num=i,
                proof_status_file=m_status,
                previous_round_instructions=prev_instructions,
                human_help_dir=human_help_dir,
            )
            search_prompt += (
                f"\n\nThis is round {i}. Write or refine the proof. "
                f"If one approach doesn't work after much effort, try a completely different proof strategy."
            )
            # Copy the current best proof into the model's working dir as starting point
            if os.path.exists(proof_file) and not os.path.exists(m_proof):
                shutil.copy2(proof_file, m_proof)

            await run_model(
                provider, search_prompt, output_dir, config,
                claude_opts=claude_opts, logger=logger, tracker=tracker,
                call_name=f"Proof Search R{i} [{provider}]",
                instructions=proving_skill or None,
            )

        await _asyncio.gather(*[_proof_search(p) for p in providers])
        logger.append_history(f"Iteration {i}: Parallel proof search completed")

    # ==================================================================
    # Step 2: PARALLEL DECOMPOSITION (all Claude) — skipped when skip_decomposition
    # ==================================================================
    if skip_decomposition:
        logger.log(f"--- Round {i}: skipping decomposition (skip_decomposition enabled) ---")
        logger.append_history(f"Iteration {i}: Parallel decomposition SKIPPED (config)")
    elif skip_decomp_resume:
        logger.log(f"--- Resuming round {i}: skipping decomposition (already complete) ---")
        logger.append_history(f"Iteration {i}: Parallel decomposition SKIPPED (resume)")
    else:
        step += 1
        logger.update_status(i, max_iterations, f"{step}/{total_steps} Parallel Decomposition", "RUNNING",
                             f"Decomposing {len(providers)} proofs in parallel (Claude)...")
        logger.append_history(f"Iteration {i}: Parallel decomposition started")

        async def _decompose(provider):
            mdir = model_dirs[provider]
            m_proof = os.path.join(mdir, "proof.md")
            m_decomp = os.path.join(mdir, "proof_decomposition.md")
            decomp_prompt = load_prompt(
                prompts_dir, "proof_decompose.md",
                problem_file=problem_file,
                proof_file=m_proof,
                output_file=m_decomp,
                output_dir=output_dir,
            )
            decomp_prompt += f"\n\nThis is round {i}. Decomposing {provider}'s proof. Write to {m_decomp}."
            await run_agent(claude_opts, decomp_prompt, logger,
                            tracker=tracker, call_name=f"Decomposition R{i} [{provider}]")

        await _asyncio.gather(*[_decompose(p) for p in providers])
        logger.append_history(f"Iteration {i}: Parallel decomposition completed")

    # ==================================================================
    # Step 3 (or 2 if skip_decomposition): PARALLEL VERIFICATION (all Claude)
    # ==================================================================
    step += 1
    if skip_verification:
        logger.log(f"--- Resuming round {i}: skipping verification (already complete) ---")
        logger.append_history(f"Iteration {i}: Parallel verification SKIPPED (resume)")
    else:
        verify_label = "direct" if skip_decomposition else "full"
        logger.update_status(i, max_iterations, f"{step}/{total_steps} Parallel Verification ({verify_label})", "RUNNING",
                             f"Verifying {len(providers)} proofs in parallel (Claude)...")
        logger.append_history(f"Iteration {i}: Parallel verification started ({verify_label})")

        async def _verify(provider):
            mdir = model_dirs[provider]
            m_proof = os.path.join(mdir, "proof.md")
            m_verify = os.path.join(mdir, "verification_result.md")

            if skip_decomposition:
                verify_prompt = load_prompt(
                    prompts_dir, "proof_verify_direct.md",
                    problem_file=problem_file,
                    proof_file=m_proof,
                    output_file=m_verify,
                    output_dir=output_dir,
                )
            else:
                m_decomp = os.path.join(mdir, "proof_decomposition.md")
                verify_prompt = load_prompt(
                    prompts_dir, "proof_verify.md",
                    problem_file=problem_file,
                    proof_file=m_proof,
                    decomposition_file=m_decomp,
                    output_file=m_verify,
                    output_dir=output_dir,
                )
            verify_prompt += f"\n\nThis is round {i}. Verifying {provider}'s proof. Write to {m_verify}."
            await run_agent(claude_opts, verify_prompt, logger,
                            tracker=tracker, call_name=f"Verification R{i} [{provider}]")

            if not _file_nonempty(m_verify):
                logger.log(f"WARNING — {m_verify} missing or empty after verification agent returned! "
                           f"The agent may have failed to write the file (e.g. output too large for a single Write call).")
                logger.append_history(f"Iteration {i}: WARNING — {provider} verification_result.md missing!")

        await _asyncio.gather(*[_verify(p) for p in providers])
        logger.append_history(f"Iteration {i}: Parallel verification completed")

    # ==================================================================
    # Step 4 (or 3): SELECTOR AGENT (Claude)
    # ==================================================================
    step += 1
    selection_file = os.path.join(round_dir, "selection.md")
    logger.update_status(i, max_iterations, f"{step}/{total_steps} Proof Selection", "RUNNING",
                         "Selecting best proof from verification reports...")
    logger.append_history(f"Iteration {i}: Proof selection started")

    # Build paths for selector prompt — handle missing providers gracefully
    verify_paths = {}
    proof_paths = {}
    for m in ("claude", "codex", "gemini"):
        mdir = os.path.join(round_dir, m)
        vf = os.path.join(mdir, "verification_result.md")
        pf = os.path.join(mdir, "proof.md")
        verify_paths[m] = vf if os.path.exists(vf) else "(not available — model not used)"
        proof_paths[m] = pf if os.path.exists(pf) else "(not available — model not used)"

    select_prompt = load_prompt(
        prompts_dir, "proof_select.md",
        problem_file=problem_file,
        verify_claude=verify_paths["claude"],
        verify_codex=verify_paths["codex"],
        verify_gemini=verify_paths["gemini"],
        proof_claude=proof_paths["claude"],
        proof_codex=proof_paths["codex"],
        proof_gemini=proof_paths["gemini"],
        selection_file=selection_file,
    )
    await run_agent(claude_opts, select_prompt, logger,
                    tracker=tracker, call_name=f"Proof Selection R{i}")
    logger.append_history(f"Iteration {i}: Proof selection completed")

    # ==================================================================
    # Step 5 (or 4): Copy selected proof to main proof.md
    # ==================================================================
    step += 1
    logger.update_status(i, max_iterations, f"{step}/{total_steps} Applying Selection", "RUNNING",
                         "Copying selected proof to main proof.md...")
    selected_model = _parse_selected_model(selection_file, providers)
    logger.log(f"Iteration {i}: Selected model = {selected_model}")
    logger.append_history(f"Iteration {i}: Selected model = {selected_model}")

    selected_proof = os.path.join(round_dir, selected_model, "proof.md")
    if os.path.exists(selected_proof):
        shutil.copy2(selected_proof, proof_file)

    # ==================================================================
    # Step 6 (or 5): VERDICT AGENT (Claude) — uses ONLY selected verification
    # ==================================================================
    step += 1
    selected_verify = os.path.join(round_dir, selected_model, "verification_result.md")
    logger.update_status(i, max_iterations, f"{step}/{total_steps} Checking Verdict", "RUNNING",
                         "Analyzing selected verification results...")
    logger.append_history(f"Iteration {i}: Checking verdict (using {selected_model}'s verification)")

    verdict_prompt = load_prompt(
        prompts_dir, "verdict_proof.md",
        verification_result_file=selected_verify,
    )
    decision = await run_agent_for_verdict(claude_opts, verdict_prompt, logger,
                                           tracker=tracker, call_name=f"Verdict R{i}")
    logger.log(f"Iteration {i}: Decision is {decision}")
    logger.append_history(f"Iteration {i}: Decision = {decision}")
    return decision


def _parse_selected_model(selection_file: str, available: list[str]) -> str:
    """Parse 'SELECTED: <model>' from selection.md. Falls back to first available."""
    if not os.path.exists(selection_file):
        return available[0]
    with open(selection_file) as f:
        for line in f:
            upper = line.upper()
            if "SELECTED:" in upper:
                for m in ("claude", "codex", "gemini"):
                    if m in line.lower():
                        return m
    return available[0]


async def run_proof_loop(
    output_dir: str,
    problem_file: str,
    claude_opts: dict,
    prompts_dir: str,
    max_iterations: int,
    related_info_dir: str,
    proving_skill: str = "",
    tracker: TokenTracker | None = None,
    start_round: int = 1,
    resume_from_step: str = "proof_search",
    difficulty: str = "unknown",
    multi_model_config: dict | None = None,
    skip_decomposition: bool = False,
) -> bool:
    """Run the proof search/decomposition/verification/verdict loop.

    Args:
        start_round: Round number to begin from (for resume support).
            Rounds before this are assumed already complete on disk.
        resume_from_step: Which step to resume from within start_round:
            "proof_search"  — start the round from scratch
            "decomposition" — skip proof search, start from decomposition
            "verification"  — skip proof search + decomposition, start from verification
            "parallel_decomposition" — parallel round, skip proof search
            "parallel_verification"  — parallel round, skip proof search + decomposition
            "parallel_selection"     — parallel round, skip to selector
        difficulty: Problem difficulty from the literature survey
            ("easy", "medium", "hard", or "unknown"). Easy problems skip
            decomposition and use a lightweight verification prompt.
        multi_model_config: Dict with keys "providers" (list[str]), "config" (full
            config dict). When set and difficulty is hard, enables parallel
            multi-model proof search.
        skip_decomposition: When True, non-easy problems skip the decomposition
            step and use direct verification (proof_verify_direct.md).

    Returns True if successful (DONE), False if max iterations reached.
    """
    easy_mode = (difficulty == "easy")
    hard_parallel = (
        multi_model_config is not None
        and not easy_mode
        and difficulty == "hard"
    )
    proof_file = os.path.join(output_dir, "proof.md")
    verify_dir = os.path.join(output_dir, "verification")

    # Resolve human_help_dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_base = os.path.dirname(script_dir)
    human_help_dir = os.path.join(project_base, "human_help")

    logger = PipelineLogger(verify_dir, "Proof Search")

    # Create initial empty proof file
    if not os.path.exists(proof_file):
        with open(proof_file, "w") as f:
            f.write("<!-- Proof will be written here by the proof search agent -->\n")

    # --- Resume check: parse the last complete round's verdict from disk ---
    if start_round > 1 and resume_from_step == "proof_search":
        prev_complete = start_round - 1
        prev_round_dir = os.path.join(verify_dir, f"round_{prev_complete}")
        # Check single-model verification or parallel selection
        prev_verify_file = os.path.join(prev_round_dir, "verification_result.md")
        if not os.path.exists(prev_verify_file) and _is_parallel_round(prev_round_dir):
            # For parallel rounds, check if selected model's verification passed
            selected = _parse_selected_model(
                os.path.join(prev_round_dir, "selection.md"),
                multi_model_config.get("providers", ["claude"]) if multi_model_config else ["claude"],
            )
            prev_verify_file = os.path.join(prev_round_dir, selected, "verification_result.md")
        if _file_nonempty(prev_verify_file):
            verdict = _parse_verdict_from_file(prev_verify_file)
            logger.log(f"\n--- Resuming: round {prev_complete} verdict from file = {verdict} ---")
            logger.append_history(f"Resume: parsed verdict for round {prev_complete} = {verdict}")
            if verdict == "PASS":
                logger.finalize(prev_complete, max_iterations, "FINISHED",
                                "Proof already verified in previous run!")
                logger.append_history("SUCCESS - Proof already verified (resume check)")
                return True

    for i in range(start_round, max_iterations + 1):
        round_dir = os.path.join(verify_dir, f"round_{i}")
        os.makedirs(round_dir, exist_ok=True)

        logger.log(f"\n========================================")
        logger.log(f"=== ITERATION {i} of {max_iterations} ===")
        logger.log(f"========================================")
        logger.append_history(f"Iteration {i} started (round dir: round_{i})")

        if hard_parallel:
            # ==============================================================
            # HARD MODE: parallel proof search across multiple models
            # ==============================================================
            # Determine resume step for this specific round
            round_resume = "proof_search"
            if i == start_round and resume_from_step.startswith("parallel_"):
                round_resume = resume_from_step

            decision = await _run_parallel_round(
                i=i,
                max_iterations=max_iterations,
                output_dir=output_dir,
                problem_file=problem_file,
                claude_opts=claude_opts,
                prompts_dir=prompts_dir,
                related_info_dir=related_info_dir,
                proving_skill=proving_skill,
                tracker=tracker,
                logger=logger,
                verify_dir=verify_dir,
                proof_file=proof_file,
                config=multi_model_config["config"],
                available_providers=multi_model_config["providers"],
                human_help_dir=human_help_dir,
                resume_from_step=round_resume,
                skip_decomposition=skip_decomposition,
            )

            if decision == "DONE":
                logger.finalize(i, max_iterations, "FINISHED", "Proof verified successfully!")
                logger.append_history("SUCCESS - Proof verified")
                return True

        else:
            # ==============================================================
            # SINGLE-MODEL MODE (easy / medium / unknown)
            # ==============================================================
            proof_status_file = os.path.join(round_dir, "proof_status.md")
            decomp_file = os.path.join(round_dir, "proof_decomposition.md")
            verify_result_file = os.path.join(round_dir, "verification_result.md")

            prev_verify = os.path.join(verify_dir, f"round_{i-1}", "verification_result.md")
            prev_proof_status = os.path.join(verify_dir, f"round_{i-1}", "proof_status.md")

            # Determine which steps to skip for this round (resume case)
            skip_proof_search = (i == start_round and resume_from_step in ("decomposition", "verification"))
            skip_decomp_resume = (i == start_round and resume_from_step == "verification")

            # Step labels depend on mode: easy/skip_decomp = 3 steps, normal = 4 steps
            total_steps = 3 if (easy_mode or skip_decomposition) else 4

            # ------------------------------------------------------------------
            # Step 1: Proof Search
            # ------------------------------------------------------------------
            if skip_proof_search:
                logger.log(f"--- Resuming round {i}: skipping proof search (already complete) ---")
                logger.append_history(f"Iteration {i}: Proof search SKIPPED (resume)")
            else:
                # Build previous-round instructions
                prev_instructions = ""
                if os.path.exists(prev_verify):
                    prev_instructions += f"- Read the PREVIOUS round's verification result from {prev_verify}.\n"
                if os.path.exists(prev_proof_status):
                    prev_instructions += f"- Read the PREVIOUS round's proof status from {prev_proof_status}. It contains which approaches were tried and FAILED — do NOT repeat these.\n"
                if not prev_instructions:
                    prev_instructions = "- This is the first round. No previous round data available.\n"

                # Back up proof.md before the proof search agent modifies it
                proof_backup = os.path.join(round_dir, "proof_before_round.md")
                if os.path.exists(proof_file):
                    shutil.copy2(proof_file, proof_backup)

                logger.update_status(i, max_iterations, f"1/{total_steps} Proof Search", "RUNNING", "Running proof search agent...")
                logger.append_history(f"Iteration {i}: Proof search started")

                search_prompt = load_prompt(
                    prompts_dir, "proof_search.md",
                    problem_file=problem_file,
                    proof_file=proof_file,
                    output_dir=output_dir,
                    related_info_dir=related_info_dir,
                    round_num=i,
                    proof_status_file=proof_status_file,
                    previous_round_instructions=prev_instructions,
                    human_help_dir=human_help_dir,
                )
                search_prompt += f"\n\nThis is round {i}. Write or refine the proof. If one approach doesn't work after much effort, try a completely different proof strategy."

                await run_agent(claude_opts, search_prompt, logger, instructions=proving_skill or None,
                                tracker=tracker, call_name=f"Proof Search R{i}")
                logger.append_history(f"Iteration {i}: Proof search completed")

            if easy_mode:
                # ==============================================================
                # EASY MODE: skip decomposition, use lightweight verification
                # ==============================================================

                # Step 2/3: Easy Verification
                logger.update_status(i, max_iterations, "2/3 Verification (easy)", "RUNNING", "Running easy verification agent...")
                logger.append_history(f"Iteration {i}: Easy verification started")

                verify_prompt = load_prompt(
                    prompts_dir, "proof_verify_easy.md",
                    problem_file=problem_file,
                    proof_file=proof_file,
                    output_file=verify_result_file,
                    output_dir=output_dir,
                )
                verify_prompt += f"\n\nThis is round {i}. Write results to {verify_result_file}."

                await run_agent(claude_opts, verify_prompt, logger,
                                tracker=tracker, call_name=f"Verification (easy) R{i}")

                if not _file_nonempty(verify_result_file):
                    logger.log(f"WARNING — {verify_result_file} missing or empty after verification agent returned! "
                               f"The agent may have failed to write the file (e.g. output too large for a single Write call).")
                    logger.append_history(f"Iteration {i}: WARNING — verification_result.md missing!")

                logger.append_history(f"Iteration {i}: Easy verification completed")

                # Step 3/3: Verdict
                logger.update_status(i, max_iterations, "3/3 Checking Verdict", "RUNNING", "Analyzing verification results...")
                logger.append_history(f"Iteration {i}: Checking verdict")

            elif skip_decomposition:
                # ==============================================================
                # SKIP-DECOMPOSITION MODE: direct verification (no miniclaims)
                # ==============================================================

                # Step 2/3: Direct Verification
                logger.update_status(i, max_iterations, "2/3 Verification (direct)", "RUNNING", "Running direct verification agent...")
                logger.append_history(f"Iteration {i}: Direct verification started")

                verify_prompt = load_prompt(
                    prompts_dir, "proof_verify_direct.md",
                    problem_file=problem_file,
                    proof_file=proof_file,
                    output_file=verify_result_file,
                    output_dir=output_dir,
                )
                verify_prompt += f"\n\nThis is round {i}. Write results to {verify_result_file}."

                await run_agent(claude_opts, verify_prompt, logger,
                                tracker=tracker, call_name=f"Verification (direct) R{i}")

                if not _file_nonempty(verify_result_file):
                    logger.log(f"WARNING — {verify_result_file} missing or empty after verification agent returned! "
                               f"The agent may have failed to write the file (e.g. output too large for a single Write call).")
                    logger.append_history(f"Iteration {i}: WARNING — verification_result.md missing!")

                logger.append_history(f"Iteration {i}: Direct verification completed")

                # Step 3/3: Verdict
                logger.update_status(i, max_iterations, "3/3 Checking Verdict", "RUNNING", "Analyzing verification results...")
                logger.append_history(f"Iteration {i}: Checking verdict")

            else:
                # ==============================================================
                # NORMAL MODE: decomposition → full verification → verdict
                # ==============================================================

                # Step 2/4: Proof Decomposition
                if skip_decomp_resume:
                    logger.log(f"--- Resuming round {i}: skipping decomposition (already complete) ---")
                    logger.append_history(f"Iteration {i}: Decomposition SKIPPED (resume)")
                else:
                    logger.update_status(i, max_iterations, "2/4 Decomposition", "RUNNING", "Running decomposition agent...")
                    logger.append_history(f"Iteration {i}: Decomposition started")

                    decomp_prompt = load_prompt(
                        prompts_dir, "proof_decompose.md",
                        problem_file=problem_file,
                        proof_file=proof_file,
                        output_file=decomp_file,
                        output_dir=output_dir,
                    )
                    decomp_prompt += f"\n\nThis is round {i}. Write decomposition to {decomp_file}."

                    await run_agent(claude_opts, decomp_prompt, logger,
                                    tracker=tracker, call_name=f"Decomposition R{i}")
                    logger.append_history(f"Iteration {i}: Decomposition completed")

                # Step 3/4: Verification
                logger.update_status(i, max_iterations, "3/4 Verification", "RUNNING", "Running verification agent...")
                logger.append_history(f"Iteration {i}: Verification started")

                verify_prompt = load_prompt(
                    prompts_dir, "proof_verify.md",
                    problem_file=problem_file,
                    proof_file=proof_file,
                    decomposition_file=decomp_file,
                    output_file=verify_result_file,
                    output_dir=output_dir,
                )
                verify_prompt += f"\n\nThis is round {i}. Write results to {verify_result_file}."

                await run_agent(claude_opts, verify_prompt, logger,
                                tracker=tracker, call_name=f"Verification R{i}")

                if not _file_nonempty(verify_result_file):
                    logger.log(f"WARNING — {verify_result_file} missing or empty after verification agent returned! "
                               f"The agent may have failed to write the file (e.g. output too large for a single Write call).")
                    logger.append_history(f"Iteration {i}: WARNING — verification_result.md missing!")

                logger.append_history(f"Iteration {i}: Verification completed")

                # Step 4/4: Verdict
                logger.update_status(i, max_iterations, "4/4 Checking Verdict", "RUNNING", "Analyzing verification results...")
                logger.append_history(f"Iteration {i}: Checking verdict")

            verdict_prompt = load_prompt(
                prompts_dir, "verdict_proof.md",
                verification_result_file=verify_result_file,
            )
            decision = await run_agent_for_verdict(claude_opts, verdict_prompt, logger,
                                                   tracker=tracker, call_name=f"Verdict R{i}")
            logger.log(f"Iteration {i}: Decision is {decision}")
            logger.append_history(f"Iteration {i}: Decision = {decision}")

            if decision == "DONE":
                logger.finalize(i, max_iterations, "FINISHED", "Proof verified successfully!")
                logger.append_history("SUCCESS - Proof verified")
                return True

        await asyncio.sleep(2)

    logger.finalize(max_iterations, max_iterations, "STOPPED", "Max iterations reached.")
    logger.append_history("STOPPED - Max iterations reached")
    return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Proof Agent: natural-language proof search pipeline")
    parser.add_argument("--input", required=True, help="Path to problem.tex file")
    parser.add_argument("--output", required=True, help="Output directory for proof and logs")
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    args = parser.parse_args()

    check_prerequisites()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    pipeline_cfg = config.get("pipeline", {})
    claude_cfg = config.get("claude", {})
    max_proof = pipeline_cfg.get("max_proof_iterations", 9)
    skip_decomp = pipeline_cfg.get("skip_decomposition", False)

    problem_file = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)

    if not os.path.exists(problem_file):
        print(f"ERROR: Input file not found: {problem_file}")
        sys.exit(1)

    # Resolve paths relative to project root (one level up from code/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_base = os.path.dirname(script_dir)  # proof_agent/
    prompts_dir = os.path.join(project_base, "prompts")
    skill_dir = os.path.join(project_base, "skill")

    # Load math skill (used as system prompt for proof search agent)
    math_skill_path = os.path.join(skill_dir, "super_math_skill.md")
    proving_skill = ""
    if os.path.exists(math_skill_path):
        with open(math_skill_path) as f:
            proving_skill = f.read()

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Copy problem file into output for reference
    problem_copy = os.path.join(output_dir, "problem.tex")
    if not os.path.exists(problem_copy):
        shutil.copy2(problem_file, problem_copy)

    # Build Claude CLI options
    claude_opts = make_claude_options(claude_cfg, output_dir)

    # Token usage tracker — writes TOKEN_USAGE.md after every agent call
    tracker = TokenTracker(output_dir, claude_opts["model"])

    # -------------------------------------------------------
    # Detect resume state
    # -------------------------------------------------------
    skip_survey, start_round, resume_from_step = detect_resume_state(output_dir, skip_decomp)

    print("=" * 60)
    print("  Proof Agent Pipeline")
    print("=" * 60)
    print(f"  Problem:    {problem_file}")
    print(f"  Output:     {output_dir}")
    print(f"  Max rounds: {max_proof}")
    print(f"  Token log:  {tracker.md_path}")
    if skip_decomp:
        print(f"  Skip decomposition: ON (direct verification for medium/hard)")
    if skip_survey or start_round > 1 or resume_from_step != "proof_search":
        print()
        print("  RESUMING previous run:")
        if skip_survey:
            print("    - Literature survey: SKIP (already complete)")
        if resume_from_step == "decomposition":
            print(f"    - Proof loop: resuming round {start_round} from decomposition step")
        elif resume_from_step == "verification":
            print(f"    - Proof loop: resuming round {start_round} from verification step")
        elif start_round > 1:
            print(f"    - Proof loop: resuming from round {start_round}")
    print()

    # -------------------------------------------------------
    # Stage 0: Literature Survey
    # -------------------------------------------------------
    related_info_dir = os.path.join(output_dir, "related_info")
    if skip_survey:
        print("=" * 60)
        print("STAGE 0: Literature Survey  [SKIPPED — already complete]")
        print("=" * 60)
        print(f"  Using existing survey at: {related_info_dir}")
    else:
        print("=" * 60)
        print("STAGE 0: Literature Survey")
        print("=" * 60)
        related_info_dir = await run_literature_survey(
            output_dir, problem_file, claude_opts, prompts_dir,
            math_skill=proving_skill, tracker=tracker,
        )
        print(f"  Survey saved to: {related_info_dir}")

    # -------------------------------------------------------
    # Parse difficulty for adaptive verification
    # -------------------------------------------------------
    difficulty = _parse_difficulty(output_dir)
    if difficulty != "unknown":
        print(f"  Difficulty: {difficulty.upper()}")
        if difficulty == "easy":
            print("  (Easy mode: skipping decomposition, using lightweight verification)")
    print()

    # -------------------------------------------------------
    # Multi-model setup (for hard problems)
    # -------------------------------------------------------
    multi_model_config = None
    mm_cfg = pipeline_cfg.get("multi_model", {})
    threshold = mm_cfg.get("difficulty_threshold", "hard")
    difficulty_levels = {"easy": 1, "medium": 2, "hard": 3, "unknown": 2}
    if mm_cfg.get("enabled", False) and difficulty_levels.get(difficulty, 2) >= difficulty_levels.get(threshold, 3):
        available_providers = check_multi_model_providers(config)
        if len(available_providers) > 1:
            multi_model_config = {
                "providers": available_providers,
                "config": config,
            }
            print(f"  Multi-model mode: ACTIVE")
            print(f"  Providers: {', '.join(available_providers)}")
        else:
            print("  Multi-model mode: DISABLED (only Claude available)")
    print()

    # -------------------------------------------------------
    # Stage 1: Proof Search Loop
    # -------------------------------------------------------
    print("=" * 60)
    if resume_from_step.startswith("parallel_"):
        print(f"STAGE 1: Proof Search  [RESUMING round {start_round} from {resume_from_step}]")
    elif resume_from_step == "decomposition":
        print(f"STAGE 1: Proof Search  [RESUMING round {start_round} from decomposition]")
    elif resume_from_step == "verification":
        print(f"STAGE 1: Proof Search  [RESUMING round {start_round} from verification]")
    elif start_round > 1:
        print(f"STAGE 1: Proof Search  [RESUMING from round {start_round}]")
    else:
        print("STAGE 1: Proof Search")
    if multi_model_config:
        print(f"  (Parallel mode: {', '.join(multi_model_config['providers'])})")
    print("=" * 60)
    ok = await run_proof_loop(
        output_dir, problem_file, claude_opts, prompts_dir,
        max_proof, related_info_dir=related_info_dir,
        proving_skill=proving_skill, tracker=tracker,
        start_round=start_round,
        resume_from_step=resume_from_step,
        difficulty=difficulty,
        multi_model_config=multi_model_config,
        skip_decomposition=skip_decomp,
    )

    # -------------------------------------------------------
    # Stage 2: Proof Effort Summary
    # -------------------------------------------------------
    summary_file = os.path.join(output_dir, "proof_effort_summary.md")

    if _file_nonempty(summary_file):
        print()
        print("=" * 60)
        print("STAGE 2: Proof Effort Summary  [SKIPPED — already exists]")
        print("=" * 60)
        print(f"  Using existing summary at: {summary_file}")
    else:
        # Count how many rounds actually exist on disk
        verify_dir = os.path.join(output_dir, "verification")
        total_rounds = 0
        if os.path.isdir(verify_dir):
            total_rounds = sum(
                1 for name in os.listdir(verify_dir) if name.startswith("round_")
            )

        outcome = "PASS — Proof verified successfully" if ok else "FAIL — Maximum iterations reached without a verified proof"

        print()
        print("=" * 60)
        print("STAGE 2: Proof Effort Summary")
        print("=" * 60)

        summary_log_dir = os.path.join(output_dir, "summary_log")
        summary_logger = PipelineLogger(summary_log_dir, "Proof Effort Summary")
        summary_logger.update_status(1, 1, "Summary", "RUNNING", "Writing proof effort summary...")

        summary_prompt = load_prompt(
            prompts_dir, "proof_effort_summary.md",
            output_dir=output_dir,
            outcome=outcome,
            total_rounds=total_rounds,
            max_rounds=max_proof,
            summary_file=summary_file,
        )
        await run_agent(claude_opts, summary_prompt, logger=summary_logger,
                        tracker=tracker, call_name="Proof Effort Summary")
        summary_logger.finalize(1, 1, "FINISHED", "Summary complete.")
        print(f"  Summary saved to: {summary_file}")

    # -------------------------------------------------------
    # Done
    # -------------------------------------------------------
    print()
    print("=" * 60)
    if ok:
        print("  PIPELINE COMPLETE — Proof verified!")
    else:
        print("  PIPELINE STOPPED — Max iterations reached")
    print("=" * 60)
    print(f"  Proof at:    {os.path.join(output_dir, 'proof.md')}")
    print(f"  Summary at:  {summary_file}")
    print(f"  Token usage: {tracker.md_path}")
    print(f"  Output:      {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
