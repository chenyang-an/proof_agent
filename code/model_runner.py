#!/usr/bin/env python3
"""Unified multi-model runner for Claude, Codex, and Gemini.

Provides async wrappers around each provider's CLI, returning response text
and feeding token usage into the pipeline's TokenTracker.

All three providers are invoked via their respective CLIs (subprocess),
wrapped in ``asyncio`` executors so the main event loop stays non-blocking.
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime


# ---------------------------------------------------------------------------
# Claude wrapper
# ---------------------------------------------------------------------------

async def run_claude_agent(
    prompt: str,
    working_dir: str,
    claude_opts: dict,
    logger=None,
    tracker=None,
    call_name: str = "",
    instructions: str | None = None,
) -> str:
    """Run the Claude CLI as a proof-search agent. Returns response text.

    Args:
        prompt: The full prompt string to send.
        working_dir: Directory the agent operates in (cwd for subprocess).
        claude_opts: Dict with keys: cli_path, model, env.
        logger: Optional PipelineLogger for streaming output.
        tracker: Optional TokenTracker for recording token usage.
        call_name: Human-readable label for this call.
        instructions: Optional system prompt to append.
    """
    cli_path = claude_opts.get("cli_path", "claude")
    model = claude_opts.get("model", "opus")
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
            cwd=working_dir,
            env=env,
        )

    start = datetime.now()
    if logger:
        logger.log(f"[Claude] Starting {call_name} (model={model})")

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _call)
    except Exception as exc:
        if logger:
            logger.log(f"[Claude] ERROR: {exc}")
        if tracker:
            elapsed = (datetime.now() - start).total_seconds()
            tracker.record(call_name or "claude", 0, 0, elapsed,
                           provider="claude", model=model)
        return ""

    elapsed = (datetime.now() - start).total_seconds()

    # --- Parse JSON output ---
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

    if logger:
        logger.log(f"[Claude] Completed {call_name} in {elapsed:.0f}s "
                    f"({input_tokens} in / {output_tokens} out)")

    if tracker:
        tracker.record(call_name or "claude", input_tokens, output_tokens,
                       elapsed, provider="claude", model=model)

    return response


# ---------------------------------------------------------------------------
# Codex wrapper
# ---------------------------------------------------------------------------

async def run_codex_agent(
    prompt: str,
    working_dir: str,
    codex_config: dict,
    logger=None,
    tracker=None,
    call_name: str = "",
) -> str:
    """Run the Codex CLI as a proof-search agent. Returns response text.

    Args:
        prompt: The full prompt string to send.
        working_dir: Directory the agent operates in (cwd for subprocess).
        codex_config: Dict with keys: cli_path, model, reasoning_effort.
        logger: Optional PipelineLogger for streaming output.
        tracker: Optional TokenTracker for recording token usage.
        call_name: Human-readable label for this call.
    """
    cli_path = codex_config.get("cli_path", "codex")
    model = codex_config.get("model", "gpt-5.4")
    reasoning = codex_config.get("reasoning_effort", "xhigh")

    cmd = [
        cli_path,
        "--search",
        "-m", model,
        "-c", f'model_reasoning_effort="{reasoning}"',
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", working_dir,
        prompt,
    ]

    def _call():
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            cwd=working_dir,
        )

    start = datetime.now()
    if logger:
        logger.log(f"[Codex] Starting {call_name} (model={model})")

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _call)
    except Exception as exc:
        if logger:
            logger.log(f"[Codex] ERROR: {exc}")
        if tracker:
            elapsed = (datetime.now() - start).total_seconds()
            tracker.record(call_name or "codex", 0, 0, elapsed,
                           provider="codex", model=model)
        return ""

    elapsed = (datetime.now() - start).total_seconds()

    # --- Parse JSONL output (adapted from test_call.py:41-67) ---
    response = ""
    input_tokens = 0
    output_tokens = 0

    try:
        lines = result.stdout.strip().split("\n")
        events = [json.loads(line) for line in lines if line.strip()]

        for event in events:
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    response = item.get("text", "")
            elif event.get("type") == "turn.completed":
                usage = event.get("usage", {})
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
    except (json.JSONDecodeError, ValueError) as exc:
        if logger:
            logger.log(f"[Codex] JSON parse error: {exc}")
        # Fall back to raw stdout as response
        response = result.stdout.strip()

    if logger:
        logger.log(f"[Codex] Completed {call_name} in {elapsed:.0f}s "
                    f"({input_tokens} in / {output_tokens} out)")

    if tracker:
        tracker.record(call_name or "codex", input_tokens, output_tokens,
                       elapsed, provider="codex", model=model)

    return response


# ---------------------------------------------------------------------------
# Gemini wrapper
# ---------------------------------------------------------------------------

async def run_gemini_agent(
    prompt: str,
    working_dir: str,
    gemini_config: dict,
    logger=None,
    tracker=None,
    call_name: str = "",
) -> str:
    """Run the Gemini CLI as a proof-search agent. Returns response text.

    Args:
        prompt: The full prompt string to send.
        working_dir: Directory the agent operates in (cwd for subprocess).
        gemini_config: Dict with keys: cli_path, model, api_key.
        logger: Optional PipelineLogger for streaming output.
        tracker: Optional TokenTracker for recording token usage.
        call_name: Human-readable label for this call.
    """
    cli_path = gemini_config.get("cli_path", "gemini")
    model = gemini_config.get("model", "gemini-3-flash-preview")
    api_key = gemini_config.get("api_key", "")

    cmd = [
        cli_path,
        "-m", model,
        "-y",           # auto-approve
        "-o", "json",   # JSON output for metadata extraction
        "-p", prompt,
    ]

    def _call():
        import os
        env = os.environ.copy()
        if api_key:
            env["GEMINI_API_KEY"] = api_key
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            cwd=working_dir,
            env=env,
        )

    start = datetime.now()
    if logger:
        logger.log(f"[Gemini] Starting {call_name} (model={model})")

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _call)
    except Exception as exc:
        if logger:
            logger.log(f"[Gemini] ERROR: {exc}")
        if tracker:
            elapsed = (datetime.now() - start).total_seconds()
            tracker.record(call_name or "gemini", 0, 0, elapsed,
                           provider="gemini", model=model)
        return ""

    elapsed = (datetime.now() - start).total_seconds()

    # --- Parse JSON output (adapted from test_call.py:74-121) ---
    response = ""
    input_tokens = 0
    output_tokens = 0

    try:
        data = json.loads(result.stdout)
        response = data.get("response", "")

        for _, model_stats in data.get("stats", {}).get("models", {}).items():
            tokens = model_stats.get("tokens", {})
            input_tokens += tokens.get("input", 0)
            output_tokens += tokens.get("candidates", 0)
            output_tokens += tokens.get("thoughts", 0)  # include thinking tokens
    except (json.JSONDecodeError, ValueError) as exc:
        if logger:
            logger.log(f"[Gemini] JSON parse error: {exc}")
        response = result.stdout.strip()

    if logger:
        logger.log(f"[Gemini] Completed {call_name} in {elapsed:.0f}s "
                    f"({input_tokens} in / {output_tokens} out)")

    if tracker:
        tracker.record(call_name or "gemini", input_tokens, output_tokens,
                       elapsed, provider="gemini", model=model)

    return response


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

async def run_model(
    provider: str,
    prompt: str,
    working_dir: str,
    config: dict,
    *,
    claude_opts: dict | None = None,
    logger=None,
    tracker=None,
    call_name: str = "",
    instructions: str | None = None,
) -> str:
    """Dispatch a prompt to the specified model provider.

    Args:
        provider: One of "claude", "codex", "gemini".
        prompt: The full prompt string.
        working_dir: Agent's working directory.
        config: Full pipeline config dict (with claude/codex/gemini sections).
        claude_opts: Claude CLI options dict (required when provider="claude").
        logger: Optional PipelineLogger.
        tracker: Optional TokenTracker.
        call_name: Human-readable label.
        instructions: System instructions (used only for Claude).

    Returns:
        The agent's response text.
    """
    if provider == "claude":
        return await run_claude_agent(
            prompt, working_dir, claude_opts or {},
            logger=logger, tracker=tracker, call_name=call_name,
            instructions=instructions,
        )
    elif provider == "codex":
        return await run_codex_agent(
            prompt, working_dir, config.get("codex", {}),
            logger=logger, tracker=tracker, call_name=call_name,
        )
    elif provider == "gemini":
        return await run_gemini_agent(
            prompt, working_dir, config.get("gemini", {}),
            logger=logger, tracker=tracker, call_name=call_name,
        )
    else:
        raise ValueError(f"Unknown model provider: {provider!r}. "
                         f"Expected 'claude', 'codex', or 'gemini'.")
