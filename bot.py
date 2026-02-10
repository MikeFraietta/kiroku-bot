from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from codeops import CodeOps, CodeOpsConfig, CodeOpsError, parse_task_id, parse_title_and_instructions


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kiroku-bot")


@dataclass
class BotConfig:
    discord_token: str
    command_prefix: str
    admin_channel_ids: set[int]
    allowed_user_ids: set[int]
    weekly_channel_id: int | None
    weekly_schedule_enabled: bool
    repo_path: Path
    tasks_file: Path
    base_branch: str
    remote_name: str
    verify_command: str | None
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_csv(value: str | None) -> set[int]:
    if not value:
        return set()
    out: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if not item.isdigit():
            raise ValueError(f"Invalid numeric ID in CSV: {item}")
        out.add(int(item))
    return out


def load_config() -> BotConfig:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise ValueError("DISCORD_TOKEN is required.")

    admin_channels = _parse_int_csv(os.getenv("ADMIN_CHANNEL_IDS"))
    if not admin_channels:
        # Backward-compatible fallback to old CHANNEL_ID env
        fallback = os.getenv("CHANNEL_ID", "").strip()
        if fallback.isdigit():
            admin_channels = {int(fallback)}

    allowed_users = _parse_int_csv(os.getenv("ALLOWED_USER_IDS"))

    weekly_channel_raw = os.getenv("WEEKLY_POST_CHANNEL_ID", "").strip() or os.getenv("CHANNEL_ID", "").strip()
    weekly_channel_id = int(weekly_channel_raw) if weekly_channel_raw.isdigit() else None

    repo_path = Path(os.getenv("REPO_PATH", ".")).expanduser().resolve()
    tasks_file = Path(os.getenv("TASKS_FILE", ".kiroku/tasks.json")).expanduser()
    if not tasks_file.is_absolute():
        tasks_file = repo_path / tasks_file

    return BotConfig(
        discord_token=token,
        command_prefix=os.getenv("BOT_COMMAND_PREFIX", "!kiroku").strip() or "!kiroku",
        admin_channel_ids=admin_channels,
        allowed_user_ids=allowed_users,
        weekly_channel_id=weekly_channel_id,
        weekly_schedule_enabled=_env_bool("ENABLE_WEEKLY_EVENTS", bool(weekly_channel_id)),
        repo_path=repo_path,
        tasks_file=tasks_file,
        base_branch=os.getenv("BASE_BRANCH", "main").strip() or "main",
        remote_name=os.getenv("GIT_REMOTE", "origin").strip() or "origin",
        verify_command=(os.getenv("VERIFY_COMMAND", "").strip() or None),
        openai_api_key=(os.getenv("OPENAI_API_KEY", "").strip() or None),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1",
    )


CONFIG = load_config()


intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
scheduler = AsyncIOScheduler()

ops = CodeOps(
    CodeOpsConfig(
        repo_path=CONFIG.repo_path,
        tasks_file=CONFIG.tasks_file,
        base_branch=CONFIG.base_branch,
        remote_name=CONFIG.remote_name,
        openai_api_key=CONFIG.openai_api_key,
        openai_model=CONFIG.openai_model,
        openai_base_url=CONFIG.openai_base_url,
        verify_command=CONFIG.verify_command,
    )
)


READ_COMMANDS = {"help", "status", "tasks", "show", "preview", "repo"}
MUTATING_COMMANDS = {"task", "plan", "diff", "apply", "commit", "pr", "run"}


def _is_admin_channel(channel_id: int) -> bool:
    if not CONFIG.admin_channel_ids:
        return True
    return channel_id in CONFIG.admin_channel_ids


def _is_allowed_user(user_id: int) -> bool:
    if not CONFIG.allowed_user_ids:
        return False
    return user_id in CONFIG.allowed_user_ids


async def _send_chunks(channel: discord.abc.Messageable, text: str) -> None:
    data = text.strip() or "(empty)"
    chunk_size = 1800
    parts = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
    for part in parts:
        await channel.send(part)


def _repo_overview() -> str:
    branch = subprocess.run(
        ["git", "-C", str(CONFIG.repo_path), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(CONFIG.repo_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return (
        f"repo={CONFIG.repo_path}\n"
        f"branch={branch or 'unknown'}\n"
        f"dirty={'yes' if dirty else 'no'}\n"
        f"tasks_file={CONFIG.tasks_file}"
    )


def _task_summary_line(task) -> str:
    return f"#{task.task_id} [{task.status}] {task.title} (branch: {task.branch})"


async def _handle_help(message: discord.Message) -> None:
    text = (
        f"Kiroku commands ({CONFIG.command_prefix} ...):\n"
        "- help\n"
        "- status\n"
        "- repo\n"
        "- tasks [all]\n"
        "- show <id>\n"
        "- task <title> || <instructions>\n"
        "- plan <id>\n"
        "- diff <id>\n"
        "- preview <id>\n"
        "- apply <id>\n"
        "- commit <id> [commit message]\n"
        "- pr <id>\n"
        "- run <id> (plan+diff+apply+commit+pr)\n"
    )
    await _send_chunks(message.channel, text)


async def _handle_status(message: discord.Message) -> None:
    tasks = await ops.list_tasks(include_closed=False)
    total = len(tasks)
    by_status: dict[str, int] = {}
    for task in tasks:
        by_status[task.status] = by_status.get(task.status, 0) + 1

    status_line = " ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    text = (
        "Kiroku status\n"
        f"command_prefix={CONFIG.command_prefix}\n"
        f"admin_channels={','.join(str(x) for x in sorted(CONFIG.admin_channel_ids)) or 'ALL'}\n"
        f"allowed_users={','.join(str(x) for x in sorted(CONFIG.allowed_user_ids)) or 'NONE'}\n"
        f"model={'configured' if CONFIG.openai_api_key else 'missing OPENAI_API_KEY'}\n"
        f"tasks_open={total}\n"
        f"task_statuses={status_line or 'none'}"
    )
    await _send_chunks(message.channel, text)


async def _handle_tasks(message: discord.Message, args: str) -> None:
    include_all = args.strip().lower() == "all"
    tasks = await ops.list_tasks(include_closed=include_all)
    if not tasks:
        await _send_chunks(message.channel, "No tasks found.")
        return

    lines = [_task_summary_line(task) for task in tasks[:20]]
    suffix = "\n(truncated to latest 20 tasks)" if len(tasks) > 20 else ""
    await _send_chunks(message.channel, "Tasks:\n" + "\n".join(lines) + suffix)


async def _handle_show(message: discord.Message, args: str) -> None:
    task = await ops.get_task(parse_task_id(args.strip()))
    text = (
        f"Task #{task.task_id}\n"
        f"status={task.status}\n"
        f"title={task.title}\n"
        f"requested_by={task.requested_by} ({task.requested_by_id})\n"
        f"branch={task.branch}\n"
        f"files={', '.join(task.files) if task.files else 'n/a'}\n"
        f"commit={task.commit_sha or 'n/a'}\n"
        f"compare_url={task.compare_url or 'n/a'}\n"
        f"updated_at={task.updated_at}\n"
        f"instructions:\n{task.instructions[:1200]}"
    )
    await _send_chunks(message.channel, text)


async def _handle_preview(message: discord.Message, args: str) -> None:
    task = await ops.get_task(parse_task_id(args.strip()))
    if not task.patch.strip():
        await _send_chunks(message.channel, f"Task #{task.task_id} has no patch yet.")
        return

    lines = task.patch.splitlines()
    preview = "\n".join(lines[:120])
    suffix = "\n... (truncated)" if len(lines) > 120 else ""
    await _send_chunks(message.channel, f"Patch preview for task #{task.task_id}:\n{preview}{suffix}")


async def _handle_task_create(message: discord.Message, args: str) -> None:
    title, instructions = parse_title_and_instructions(args)
    task = await ops.create_task(
        title=title,
        instructions=instructions,
        requested_by=str(message.author),
        requested_by_id=str(message.author.id),
    )
    await _send_chunks(message.channel, f"Created {_task_summary_line(task)}")


async def _handle_plan(message: discord.Message, args: str) -> None:
    task_id = parse_task_id(args.strip())
    task = await ops.plan_task(task_id)
    body = task.plan.strip() or "(empty plan)"
    await _send_chunks(message.channel, f"Planned {_task_summary_line(task)}\n\n{body[:4000]}")


async def _handle_diff(message: discord.Message, args: str) -> None:
    task_id = parse_task_id(args.strip())
    task = await ops.patch_task(task_id)
    lines = task.patch.splitlines()
    preview = "\n".join(lines[:80])
    suffix = "\n... (truncated)" if len(lines) > 80 else ""
    await _send_chunks(
        message.channel,
        f"Generated patch for {_task_summary_line(task)}\n"
        f"patch_lines={len(lines)}\n"
        f"preview:\n{preview}{suffix}",
    )


async def _handle_apply(message: discord.Message, args: str) -> None:
    task_id = parse_task_id(args.strip())
    task = await ops.apply_task(task_id)
    await _send_chunks(message.channel, f"Applied {_task_summary_line(task)}")


async def _handle_commit(message: discord.Message, args: str) -> None:
    raw = args.strip()
    if not raw:
        raise CodeOpsError("Usage: commit <id> [commit message]")

    first, _, rest = raw.partition(" ")
    task_id = parse_task_id(first)
    commit_message = rest.strip() or None
    task = await ops.commit_task(task_id, commit_message)
    await _send_chunks(
        message.channel,
        f"Committed {_task_summary_line(task)}\nsha={task.commit_sha}",
    )


async def _handle_pr(message: discord.Message, args: str) -> None:
    task_id = parse_task_id(args.strip())
    task = await ops.publish_task(task_id)
    await _send_chunks(
        message.channel,
        f"Published {_task_summary_line(task)}\n"
        f"compare_url={task.compare_url}",
    )


async def _handle_run(message: discord.Message, args: str) -> None:
    task_id = parse_task_id(args.strip())
    await _send_chunks(message.channel, f"Running end-to-end pipeline for task #{task_id} ...")

    task = await ops.plan_task(task_id)
    await _send_chunks(message.channel, f"1/5 planned: {_task_summary_line(task)}")

    task = await ops.patch_task(task_id)
    await _send_chunks(message.channel, f"2/5 patch generated: lines={len(task.patch.splitlines())}")

    task = await ops.apply_task(task_id)
    await _send_chunks(message.channel, f"3/5 patch applied: {_task_summary_line(task)}")

    task = await ops.commit_task(task_id)
    await _send_chunks(message.channel, f"4/5 committed: sha={task.commit_sha}")

    task = await ops.publish_task(task_id)
    await _send_chunks(message.channel, f"5/5 published: {task.compare_url}")


async def _dispatch_command(message: discord.Message, command: str, args: str) -> None:
    cmd = command.lower().strip()

    if cmd in READ_COMMANDS:
        if cmd == "help":
            await _handle_help(message)
        elif cmd == "status":
            await _handle_status(message)
        elif cmd == "tasks":
            await _handle_tasks(message, args)
        elif cmd == "show":
            await _handle_show(message, args)
        elif cmd == "preview":
            await _handle_preview(message, args)
        elif cmd == "repo":
            await _send_chunks(message.channel, _repo_overview())
        return

    if cmd in MUTATING_COMMANDS:
        if not _is_allowed_user(message.author.id):
            await _send_chunks(message.channel, f"Unauthorized: <@{message.author.id}> cannot run `{cmd}`.")
            return

        if cmd == "task":
            await _handle_task_create(message, args)
        elif cmd == "plan":
            await _handle_plan(message, args)
        elif cmd == "diff":
            await _handle_diff(message, args)
        elif cmd == "apply":
            await _handle_apply(message, args)
        elif cmd == "commit":
            await _handle_commit(message, args)
        elif cmd == "pr":
            await _handle_pr(message, args)
        elif cmd == "run":
            await _handle_run(message, args)
        return

    await _send_chunks(message.channel, f"Unknown command `{cmd}`. Use `{CONFIG.command_prefix} help`.")


@bot.event
async def on_ready() -> None:
    logger.info("%s connected", bot.user)
    logger.info("admin channels: %s", sorted(CONFIG.admin_channel_ids) if CONFIG.admin_channel_ids else "ALL")
    logger.info("allowed users: %s", sorted(CONFIG.allowed_user_ids) if CONFIG.allowed_user_ids else "NONE")
    logger.info("repo path: %s", CONFIG.repo_path)
    logger.info("tasks file: %s", CONFIG.tasks_file)

    if CONFIG.weekly_schedule_enabled and CONFIG.weekly_channel_id and not scheduler.running:
        scheduler.add_job(
            post_weekly_update,
            CronTrigger(day_of_week=0, hour=9, minute=0),
            id="weekly_events",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("weekly scheduler started for channel=%s", CONFIG.weekly_channel_id)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if not _is_admin_channel(message.channel.id):
        return

    content = (message.content or "").strip()
    if not content.lower().startswith(CONFIG.command_prefix.lower()):
        return

    payload = content[len(CONFIG.command_prefix) :].strip()
    if not payload:
        await _send_chunks(message.channel, f"Usage: {CONFIG.command_prefix} help")
        return

    command, _, args = payload.partition(" ")
    try:
        async with message.channel.typing():
            await _dispatch_command(message, command, args)
    except CodeOpsError as exc:
        msg = str(exc)
        m = re.search(r"#(\d+)", f"{command} {args}")
        if m and m.group(1).isdigit():
            try:
                await ops.fail_task(int(m.group(1)), msg)
            except Exception:
                pass
        await _send_chunks(message.channel, f"Command failed: {msg}")
    except Exception as exc:
        logger.exception("Unhandled command error")
        await _send_chunks(message.channel, f"Unhandled error: {exc}")


async def post_weekly_update() -> None:
    if not CONFIG.weekly_channel_id:
        return
    channel = bot.get_channel(CONFIG.weekly_channel_id)
    if channel is None:
        logger.error("Weekly channel not found: %s", CONFIG.weekly_channel_id)
        return

    embed = discord.Embed(
        title="Weekly Kiroku Ops Update",
        description=(
            "Admin channel controls are live. Use `!kiroku help` in admin chat "
            "to create tasks and run controlled code-change workflows."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Ops Reminder",
        value="All mutating commands are restricted to allowed users only.",
        inline=False,
    )
    embed.set_footer(text="Kiroku Bot")
    await channel.send(embed=embed)


def run_bot() -> None:
    bot.run(CONFIG.discord_token)


if __name__ == "__main__":
    run_bot()
