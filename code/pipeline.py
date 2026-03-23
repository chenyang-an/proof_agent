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
import sys
from datetime import datetime

import yaml
from agent_framework.anthropic import ClaudeAgent


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
    """Build ClaudeAgent default_options from config.

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
        "permission_mode": claude_cfg.get("permission_mode", "bypassPermissions"),
        "cwd": working_dir,
        "env": env,
        # 1 GB buffer — the default 1 MB is too small for agents that run
        # symbolic computations producing large expressions.
        "max_buffer_size": 1000 * 1024 * 1024,
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


def detect_resume_state(output_dir: str) -> tuple[bool, int, str]:
    """Scan the output directory for progress from a previous run.

    Returns (skip_survey, start_round, resume_from_step):
      - skip_survey: True if the literature survey is already complete.
      - start_round: the round number to start (or resume) the proof loop from.
        1 means no prior rounds exist.
      - resume_from_step: which step to resume from within start_round:
          "proof_search"   — start the round from scratch
          "decomposition"  — proof search done, resume from decomposition
          "verification"   — proof search + decomposition done, resume from verification

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
        "proof_strategies.md",
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

    status_ok = _file_nonempty(os.path.join(last_dir, "proof_status.md"))
    decomp_ok = _file_nonempty(os.path.join(last_dir, "proof_decomposition.md"))
    verify_ok = _file_nonempty(os.path.join(last_dir, "verification_result.md"))

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
    after every update so the user can check TOKEN_USAGE.md at any time."""

    def __init__(self, output_dir: str, model: str):
        self.output_dir = output_dir
        self.model = model
        self.calls: list[dict] = []
        self.total_input = 0
        self.total_output = 0
        self.total_elapsed = 0.0
        self.md_path = os.path.join(output_dir, "TOKEN_USAGE.md")
        self.json_path = os.path.join(output_dir, "token_usage.json")
        self.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def record(self, call_name: str, input_tokens: int, output_tokens: int, elapsed: float):
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.total_elapsed += elapsed
        self.calls.append({
            "call": len(self.calls) + 1,
            "name": call_name,
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
            f"**Model:** `{self.model}`  ",
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
            "## Per-Call Breakdown\n",
            "| # | Agent | Input | Output | Time | Cumul In | Cumul Out |",
            "|---|-------|------:|-------:|-----:|---------:|----------:|",
        ]
        for c in self.calls:
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
            "calls": self.calls,
        }
        with open(self.json_path, "w") as f:
            json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Agent runners
# ---------------------------------------------------------------------------

def _format_content_for_log(content) -> str | None:
    """Format a Content object into a human-readable log line."""
    ctype = getattr(content, "type", None)
    if ctype is None:
        return None

    ctype_str = str(ctype)

    if "function_call" in ctype_str:
        name = getattr(content, "name", "") or ""
        args = getattr(content, "arguments", "") or ""
        if isinstance(args, dict):
            cmd = args.get("command", "")
            if cmd:
                preview = cmd[:200] + ("..." if len(cmd) > 200 else "")
                return f">>> Tool: {name} - {preview}"
            args_preview = str(args)[:150]
            return f">>> Tool: {name}({args_preview})"
        return f">>> Tool: {name}"

    if "shell_tool" in ctype_str or "shell_command" in ctype_str:
        cmds = getattr(content, "commands", None) or []
        cmd_str = "; ".join(cmds)[:200] if cmds else ""
        return f">>> Shell: {cmd_str}" if cmd_str else None

    if "function_result" in ctype_str:
        name = getattr(content, "name", "") or ""
        exc = getattr(content, "exception", None)
        if exc:
            return f"<<< Result ({name}): ERROR - {str(exc)[:100]}"
        return None

    if "text" in ctype_str:
        text = getattr(content, "text", "") or ""
        if len(text) > 20:
            return text[:300] + ("..." if len(text) > 300 else "")
        return None

    return None


async def run_agent(
    claude_opts: dict,
    prompt: str,
    logger: PipelineLogger | None = None,
    tools: list | None = None,
    instructions: str | None = None,
    tracker: TokenTracker | None = None,
    call_name: str = "",
) -> str:
    """Run a single ClaudeAgent call with streaming output logged in real time."""
    start_time = datetime.now()
    text_buffer = ""

    def flush_text():
        nonlocal text_buffer
        if logger and text_buffer.strip():
            logger.log(text_buffer.rstrip())
        text_buffer = ""

    agent_kwargs = {}
    if tools:
        agent_kwargs["tools"] = tools
    if instructions:
        agent_kwargs["instructions"] = instructions

    # Import ResultMessage to capture usage from the CLI's result event
    from agent_framework_claude._agent import ResultMessage

    result_msg = None  # Will capture the ResultMessage during streaming

    async with ClaudeAgent(default_options=claude_opts, **agent_kwargs) as agent:
        # Intercept at the client level to capture ResultMessage
        if hasattr(agent, "_client") and agent._client:
            original_receive = agent._client.receive_response

            async def _patched_receive():
                nonlocal result_msg
                async for message in original_receive():
                    if isinstance(message, ResultMessage):
                        result_msg = message
                    yield message

            agent._client.receive_response = _patched_receive

        stream = agent.run(prompt, stream=True)
        async for update in stream:
            if logger and hasattr(update, "contents") and update.contents:
                for content in update.contents:
                    ctype_str = str(getattr(content, "type", ""))
                    if "text" in ctype_str:
                        delta = getattr(content, "text", "") or ""
                        text_buffer += delta
                        while "\n" in text_buffer:
                            line, text_buffer = text_buffer.split("\n", 1)
                            if line.strip():
                                logger.log(line)
                    else:
                        flush_text()
                        line = _format_content_for_log(content)
                        if line:
                            logger.log(line)

        flush_text()
        final = await stream.get_final_response()
        elapsed = (datetime.now() - start_time).total_seconds()
        final_text = final.text or ""

        # Extract token counts — try usage_details first, then captured ResultMessage
        input_tokens = 0
        output_tokens = 0
        usage = getattr(final, "usage_details", None)
        if usage:
            input_tokens = (usage.get("input_token_count", 0) if isinstance(usage, dict)
                            else getattr(usage, "input_token_count", 0)) or 0
            output_tokens = (usage.get("output_token_count", 0) if isinstance(usage, dict)
                             else getattr(usage, "output_token_count", 0)) or 0

        # Fallback: use captured ResultMessage from CLI
        if not (input_tokens or output_tokens) and result_msg and result_msg.usage:
            ru = result_msg.usage
            # input_tokens only counts non-cached input; add cache tokens for the real total
            input_tokens = (
                (ru.get("input_tokens", 0) or 0)
                + (ru.get("cache_creation_input_tokens", 0) or 0)
                + (ru.get("cache_read_input_tokens", 0) or 0)
            )
            output_tokens = ru.get("output_tokens", 0) or 0

        if tracker:
            tracker.record(call_name or "agent", input_tokens, output_tokens, elapsed)

        return final_text


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
) -> bool:
    """Run the proof search/decomposition/verification/verdict loop.

    Args:
        start_round: Round number to begin from (for resume support).
            Rounds before this are assumed already complete on disk.
        resume_from_step: Which step to resume from within start_round:
            "proof_search"  — start the round from scratch
            "decomposition" — skip proof search, start from decomposition
            "verification"  — skip proof search + decomposition, start from verification

    Returns True if successful (DONE), False if max iterations reached.
    """
    proof_file = os.path.join(output_dir, "proof.md")
    verify_dir = os.path.join(output_dir, "verification")

    logger = PipelineLogger(verify_dir, "Proof Search")

    # Create initial empty proof file
    if not os.path.exists(proof_file):
        with open(proof_file, "w") as f:
            f.write("<!-- Proof will be written here by the proof search agent -->\n")

    # --- Resume check: parse the last complete round's verdict from disk ---
    if start_round > 1 and resume_from_step == "proof_search":
        prev_complete = start_round - 1
        prev_verify_file = os.path.join(
            verify_dir, f"round_{prev_complete}", "verification_result.md",
        )
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
        proof_status_file = os.path.join(round_dir, "proof_status.md")
        decomp_file = os.path.join(round_dir, "proof_decomposition.md")
        verify_result_file = os.path.join(round_dir, "verification_result.md")

        prev_verify = os.path.join(verify_dir, f"round_{i-1}", "verification_result.md")
        prev_proof_status = os.path.join(verify_dir, f"round_{i-1}", "proof_status.md")

        logger.log(f"\n========================================")
        logger.log(f"=== ITERATION {i} of {max_iterations} ===")
        logger.log(f"========================================")
        logger.append_history(f"Iteration {i} started (round dir: round_{i})")

        # Determine which steps to skip for this round (resume case)
        skip_proof_search = (i == start_round and resume_from_step in ("decomposition", "verification"))
        skip_decomposition = (i == start_round and resume_from_step == "verification")

        # ------------------------------------------------------------------
        # Step 1/4: Proof Search
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

            logger.update_status(i, max_iterations, "1/4 Proof Search", "RUNNING", "Running proof search agent...")
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
            )
            search_prompt += f"\n\nThis is round {i}. Write or refine the proof. If one approach doesn't work after much effort, try a completely different proof strategy."

            await run_agent(claude_opts, search_prompt, logger, instructions=proving_skill or None,
                            tracker=tracker, call_name=f"Proof Search R{i}")
            logger.append_history(f"Iteration {i}: Proof search completed")

        # ------------------------------------------------------------------
        # Step 2/4: Proof Decomposition
        # ------------------------------------------------------------------
        if skip_decomposition:
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

        # ------------------------------------------------------------------
        # Step 3/4: Verification
        # ------------------------------------------------------------------
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
        logger.append_history(f"Iteration {i}: Verification completed")

        # ------------------------------------------------------------------
        # Step 4/4: Verdict
        # ------------------------------------------------------------------
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

    # Build ClaudeAgent options
    claude_opts = make_claude_options(claude_cfg, output_dir)

    # Token usage tracker — writes TOKEN_USAGE.md after every agent call
    tracker = TokenTracker(output_dir, claude_opts["model"])

    # -------------------------------------------------------
    # Detect resume state
    # -------------------------------------------------------
    skip_survey, start_round, resume_from_step = detect_resume_state(output_dir)

    print("=" * 60)
    print("  Proof Agent Pipeline")
    print("=" * 60)
    print(f"  Problem:    {problem_file}")
    print(f"  Output:     {output_dir}")
    print(f"  Max rounds: {max_proof}")
    print(f"  Token log:  {tracker.md_path}")
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
    # Stage 1: Proof Search Loop
    # -------------------------------------------------------
    print()
    print("=" * 60)
    if resume_from_step == "decomposition":
        print(f"STAGE 1: Proof Search  [RESUMING round {start_round} from decomposition]")
    elif resume_from_step == "verification":
        print(f"STAGE 1: Proof Search  [RESUMING round {start_round} from verification]")
    elif start_round > 1:
        print(f"STAGE 1: Proof Search  [RESUMING from round {start_round}]")
    else:
        print("STAGE 1: Proof Search")
    print("=" * 60)
    ok = await run_proof_loop(
        output_dir, problem_file, claude_opts, prompts_dir,
        max_proof, related_info_dir=related_info_dir,
        proving_skill=proving_skill, tracker=tracker,
        start_round=start_round,
        resume_from_step=resume_from_step,
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

        summary_prompt = load_prompt(
            prompts_dir, "proof_effort_summary.md",
            output_dir=output_dir,
            outcome=outcome,
            total_rounds=total_rounds,
            max_rounds=max_proof,
            summary_file=summary_file,
        )
        await run_agent(claude_opts, summary_prompt, tracker=tracker,
                        call_name="Proof Effort Summary")
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
