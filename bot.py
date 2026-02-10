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
from outreach_ops import OutreachOps, OutreachOpsConfig, OutreachOpsError


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
    anthropic_api_key: str | None
    anthropic_model: str
    anthropic_base_url: str
    anthropic_version: str
    launch_agent_label: str
    outreach_state_dir: Path
    website_dir: Path
    outreach_sender_name: str
    outreach_sender_title: str
    outreach_sender_email: str
    outreach_calendar_link: str
    outreach_sponsorship_page_url: str
    outreach_cohort_date_window: str
    outreach_cohort_city: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    outreach_send_enabled: bool
    search_provider: str
    serpapi_api_key: str | None
    bing_search_api_key: str | None


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

    outreach_state_dir = Path(os.getenv("OUTREACH_STATE_DIR", ".kiroku/outreach")).expanduser()
    if not outreach_state_dir.is_absolute():
        outreach_state_dir = repo_path / outreach_state_dir
    website_dir = (repo_path / "website").resolve()

    smtp_port_raw = os.getenv("SMTP_PORT", "465").strip()
    smtp_port = int(smtp_port_raw) if smtp_port_raw.isdigit() else 465

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
        anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY", "").strip() or None),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest").strip() or "claude-3-5-sonnet-latest",
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
        or "https://api.anthropic.com",
        anthropic_version=os.getenv("ANTHROPIC_VERSION", "2023-06-01").strip() or "2023-06-01",
        launch_agent_label=os.getenv("LAUNCH_AGENT_LABEL", "com.kiroku.bot").strip() or "com.kiroku.bot",
        outreach_state_dir=outreach_state_dir,
        website_dir=website_dir,
        outreach_sender_name=os.getenv("OUTREACH_SENDER_NAME", "").strip(),
        outreach_sender_title=os.getenv("OUTREACH_SENDER_TITLE", "").strip(),
        outreach_sender_email=os.getenv("OUTREACH_SENDER_EMAIL", "").strip(),
        outreach_calendar_link=os.getenv("OUTREACH_CALENDAR_LINK", "").strip(),
        outreach_sponsorship_page_url=os.getenv("OUTREACH_SPONSORSHIP_PAGE_URL", "").strip(),
        outreach_cohort_date_window=os.getenv("OUTREACH_COHORT_DATE_WINDOW", "").strip(),
        outreach_cohort_city=os.getenv("OUTREACH_COHORT_CITY", "Tokyo").strip() or "Tokyo",
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com",
        smtp_port=smtp_port,
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
        outreach_send_enabled=_env_bool("OUTREACH_SEND_ENABLED", False),
        search_provider=os.getenv("SEARCH_PROVIDER", "").strip(),
        serpapi_api_key=(os.getenv("SERPAPI_API_KEY", "").strip() or None),
        bing_search_api_key=(os.getenv("BING_SEARCH_API_KEY", "").strip() or None),
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
        anthropic_api_key=CONFIG.anthropic_api_key,
        anthropic_model=CONFIG.anthropic_model,
        anthropic_base_url=CONFIG.anthropic_base_url,
        anthropic_version=CONFIG.anthropic_version,
        verify_command=CONFIG.verify_command,
    )
)

outreach = OutreachOps(
    OutreachOpsConfig(
        state_dir=CONFIG.outreach_state_dir,
        website_dir=CONFIG.website_dir,
        sender_name=CONFIG.outreach_sender_name,
        sender_title=CONFIG.outreach_sender_title,
        sender_email=CONFIG.outreach_sender_email,
        calendar_link=CONFIG.outreach_calendar_link,
        sponsorship_page_url=CONFIG.outreach_sponsorship_page_url,
        cohort_date_window=CONFIG.outreach_cohort_date_window,
        cohort_city=CONFIG.outreach_cohort_city,
        smtp_host=CONFIG.smtp_host,
        smtp_port=CONFIG.smtp_port,
        smtp_user=CONFIG.smtp_user,
        smtp_password=CONFIG.smtp_password,
        send_enabled=CONFIG.outreach_send_enabled,
        search_provider=CONFIG.search_provider,
        serpapi_api_key=CONFIG.serpapi_api_key or "",
        bing_api_key=CONFIG.bing_search_api_key or "",
    )
)

READ_COMMANDS = {"help", "status", "tasks", "show", "preview", "repo", "id", "ping"}
MUTATING_COMMANDS = {
    "task",
    "plan",
    "diff",
    "apply",
    "commit",
    "pr",
    "run",
    "merge",
    "deploy",
    "ship",
    "outreach",
    "do",
}


def _is_admin_channel(channel_id: int) -> bool:
    if not CONFIG.admin_channel_ids:
        return True
    return channel_id in CONFIG.admin_channel_ids


def _is_allowed_user(user_id: int) -> bool:
    if not CONFIG.allowed_user_ids:
        # Bootstrap mode: if explicit allow-list is not configured yet,
        # allow mutating commands only in admin channels.
        return True
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
        "- ping\n"
        "- status\n"
        "- id (show your user/channel/guild IDs)\n"
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
        "- merge <id> (merge task branch into main and push)\n"
        "- deploy --confirm DEPLOY (pull main and restart bot)\n"
        "- ship <id|title||instructions> --confirm SHIP (run+merge+deploy)\n"
        "- outreach help\n"
        "- do <freeform request> (shortcut for common outreach workflows)\n"
    )
    await _send_chunks(message.channel, text)


async def _handle_ping(message: discord.Message) -> None:
    await message.reply("pong")


async def _handle_status(message: discord.Message) -> None:
    tasks = await ops.list_tasks(include_closed=False)
    total = len(tasks)
    by_status: dict[str, int] = {}
    for task in tasks:
        by_status[task.status] = by_status.get(task.status, 0) + 1

    status_line = " ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    model_status = (
        f"anthropic:{CONFIG.anthropic_model}"
        if CONFIG.anthropic_api_key
        else (f"openai:{CONFIG.openai_model}" if CONFIG.openai_api_key else "missing LLM key")
    )
    text = (
        "Kiroku status\n"
        f"command_prefix={CONFIG.command_prefix}\n"
        f"admin_channels={','.join(str(x) for x in sorted(CONFIG.admin_channel_ids)) or 'ALL'}\n"
        f"allowed_users={','.join(str(x) for x in sorted(CONFIG.allowed_user_ids)) or 'ALL_IN_ADMIN_CHANNEL'}\n"
        f"model={model_status}\n"
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


def _git_run(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(CONFIG.repo_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise CodeOpsError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc.stdout.strip()


def _ensure_clean_worktree() -> None:
    dirty = _git_run(["status", "--porcelain"])
    if dirty.strip():
        raise CodeOpsError("Repo is dirty; refusing operation. Clean working tree first.")


async def _handle_merge(message: discord.Message, args: str) -> None:
    task_id = parse_task_id(args.strip())
    _ensure_clean_worktree()
    await _send_chunks(message.channel, f"Merging task #{task_id} into `{CONFIG.base_branch}` ...")
    task = await ops.merge_task(task_id)
    await _send_chunks(message.channel, f"Merged #{task.task_id} into `{CONFIG.base_branch}`.")


async def _handle_deploy(message: discord.Message, args: str) -> None:
    raw = (args or "").strip()
    if raw.strip().upper() != "--CONFIRM DEPLOY":
        raise CodeOpsError("Usage: deploy --confirm DEPLOY")

    _ensure_clean_worktree()

    await _send_chunks(
        message.channel,
        (
            f"Deploying: pulling `{CONFIG.base_branch}` and restarting bot (launch agent `{CONFIG.launch_agent_label}`).\n"
            "If the bot goes silent for a few seconds, that's expected."
        ),
    )

    # Pull latest main before restart.
    _git_run(["checkout", CONFIG.base_branch])
    _git_run(["pull", "--ff-only", CONFIG.remote_name, CONFIG.base_branch])

    # Kickstart after the reply is sent.
    await asyncio.sleep(1.0)
    label = f"gui/{os.getuid()}/{CONFIG.launch_agent_label}"
    subprocess.Popen(["launchctl", "kickstart", "-k", label])


def _strip_confirm_flag(raw: str, *, expected: str) -> tuple[str, bool]:
    parts = (raw or "").split()
    if "--confirm" not in parts:
        return (raw or "").strip(), False
    idx = parts.index("--confirm")
    token = parts[idx + 1] if idx + 1 < len(parts) else ""
    ok = token.strip().upper() == expected.upper()
    kept = parts[:idx] + parts[idx + 2 :]
    return " ".join(kept).strip(), ok


async def _handle_ship(message: discord.Message, args: str) -> None:
    stripped, ok = _strip_confirm_flag(args, expected="SHIP")
    if not ok:
        raise CodeOpsError("Refusing to ship without `--confirm SHIP`.")

    _ensure_clean_worktree()

    raw = stripped.strip()
    if not raw:
        raise CodeOpsError("Usage: ship <id|title> || <instructions> --confirm SHIP")

    # Either ship an existing task id, or create a new task from the message.
    first = raw.split()[0]
    task_id: int
    if re.match(r"^#?\\d+\\b", first):
        task_id = parse_task_id(first)
    else:
        title, instructions = parse_title_and_instructions(raw)
        task = await ops.create_task(
            title=title,
            instructions=instructions,
            requested_by=str(message.author),
            requested_by_id=str(message.author.id),
        )
        task_id = task.task_id
        await _send_chunks(message.channel, f"Created {_task_summary_line(task)}")

    await _send_chunks(message.channel, f"Shipping task #{task_id} (run+merge+deploy) ...")

    task = await ops.plan_task(task_id)
    await _send_chunks(message.channel, f"1/7 planned: {_task_summary_line(task)}")

    task = await ops.patch_task(task_id)
    await _send_chunks(message.channel, f"2/7 patch generated: lines={len(task.patch.splitlines())}")

    task = await ops.apply_task(task_id)
    await _send_chunks(message.channel, f"3/7 patch applied: {_task_summary_line(task)}")

    task = await ops.commit_task(task_id)
    await _send_chunks(message.channel, f"4/7 committed: sha={task.commit_sha}")

    task = await ops.publish_task(task_id)
    await _send_chunks(message.channel, f"5/7 published: {task.compare_url}")

    task = await ops.merge_task(task_id)
    await _send_chunks(message.channel, f"6/7 merged into `{CONFIG.base_branch}`")

    await _send_chunks(message.channel, f"7/7 deploying (restart) ...")
    await _handle_deploy(message, "--confirm DEPLOY")

def _resolve_outreach_path(arg: str) -> Path:
    raw = (arg or "").strip()
    if not raw:
        raise OutreachOpsError("Missing file path argument.")

    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    # If user passes a bare filename, default to outreach state dir.
    if "/" not in raw and "\\" not in raw:
        return (CONFIG.outreach_state_dir / raw).resolve()
    return (CONFIG.repo_path / p).resolve()


async def _handle_outreach(message: discord.Message, args: str) -> None:
    raw = (args or "").strip()
    if not raw or raw.lower() == "help":
        text = (
            "Outreach ops\n"
            "Usage:\n"
            f"- {CONFIG.command_prefix} outreach config\n"
            f"- {CONFIG.command_prefix} outreach generate housing <count>\n"
            f"- {CONFIG.command_prefix} outreach draft <leads_csv_path>\n"
            f"- {CONFIG.command_prefix} outreach list <outbox_csv_path> [--limit N] [--unsent-only|--all]\n"
            f"- {CONFIG.command_prefix} outreach approve <outbox_csv_path> (--all | --first N | --ids 1,2,3)\n"
            f"- {CONFIG.command_prefix} outreach send <outbox_csv_path> [--limit N] [--dry-run|--send] [--approved-only|--all] [--confirm SEND]\n"
            "\n"
            "Notes:\n"
            "- Lead generation requires SEARCH_PROVIDER + API key (SERPAPI_API_KEY or BING_SEARCH_API_KEY).\n"
            "- Sending requires SMTP_* + OUTREACH_SEND_ENABLED=true.\n"
            "- `send` defaults to dry-run; use `--send --confirm SEND` to actually send.\n"
        )
        await _send_chunks(message.channel, text)
        return

    sub, _, rest = raw.partition(" ")
    sub = sub.strip().lower()
    rest = rest.strip()

    if sub == "config":
        await _send_chunks(message.channel, outreach.config_summary())
        return

    if sub == "generate":
        parts = rest.split()
        if len(parts) < 2:
            raise OutreachOpsError("Usage: outreach generate housing <count>")
        kind = parts[0].strip().lower()
        if kind != "housing":
            raise OutreachOpsError("Only `housing` is supported right now.")
        if not parts[1].isdigit():
            raise OutreachOpsError("count must be a number, e.g. `100`.")
        count = int(parts[1])
        await _send_chunks(message.channel, f"Generating {count} housing leads (search_provider={CONFIG.search_provider or 'missing'}) ...")
        leads_path = await outreach.generate_housing_leads(count, city=CONFIG.outreach_cohort_city or "Tokyo", country="Japan")
        await _send_chunks(message.channel, f"Leads written: {leads_path.name}")
        await message.channel.send(file=discord.File(str(leads_path)))
        return

    if sub == "draft":
        if not rest:
            raise OutreachOpsError("Usage: outreach draft <leads_csv_path>")
        leads_path = _resolve_outreach_path(rest)
        outbox_path = outreach.draft_housing_emails(leads_path)
        await _send_chunks(message.channel, f"Drafted emails written: {outbox_path.name} (approve rows by setting approved=yes)")
        await message.channel.send(file=discord.File(str(outbox_path)))
        return

    if sub == "list":
        parts = rest.split()
        if not parts:
            raise OutreachOpsError("Usage: outreach list <outbox_csv_path> [--limit N] [--unsent-only|--all]")

        outbox_path = _resolve_outreach_path(parts[0])
        limit = 20
        unsent_only = True

        i = 1
        while i < len(parts):
            token = parts[i]
            if token == "--limit":
                if i + 1 >= len(parts) or not parts[i + 1].isdigit():
                    raise OutreachOpsError("--limit requires a number.")
                limit = int(parts[i + 1])
                i += 2
                continue
            if token == "--unsent-only":
                unsent_only = True
                i += 1
                continue
            if token == "--all":
                unsent_only = False
                i += 1
                continue
            raise OutreachOpsError(f"Unknown flag: {token}")

        preview = outreach.list_outbox(outbox_path, limit=limit, unsent_only=unsent_only)
        await _send_chunks(message.channel, preview)
        return

    if sub == "approve":
        parts = rest.split()
        if not parts:
            raise OutreachOpsError("Usage: outreach approve <outbox_csv_path> (--all | --first N | --ids 1,2,3)")

        outbox_path = _resolve_outreach_path(parts[0])
        approve_all = False
        first = 0
        ids: set[str] = set()

        i = 1
        while i < len(parts):
            token = parts[i]
            if token == "--all":
                approve_all = True
                i += 1
                continue
            if token == "--first":
                if i + 1 >= len(parts) or not parts[i + 1].isdigit():
                    raise OutreachOpsError("--first requires a number.")
                first = int(parts[i + 1])
                i += 2
                continue
            if token == "--ids":
                raw_ids = parts[i + 1] if i + 1 < len(parts) else ""
                ids = {x.strip() for x in raw_ids.split(",") if x.strip()}
                i += 2
                continue
            raise OutreachOpsError(f"Unknown flag: {token}")

        approved = outreach.approve_outbox(outbox_path, approve_all=approve_all, first=first, ids=ids or None)
        await _send_chunks(message.channel, f"Approved {approved} outbox rows: {outbox_path.name}")
        await message.channel.send(file=discord.File(str(outbox_path)))
        return

    if sub == "send":
        parts = rest.split()
        if not parts:
            raise OutreachOpsError("Usage: outreach send <outbox_csv_path> [--limit N] [--dry-run|--send] [--approved-only|--all] [--confirm SEND]")

        outbox_path = _resolve_outreach_path(parts[0])
        limit = 10
        dry_run = True
        approved_only = True
        confirm = ""

        i = 1
        while i < len(parts):
            token = parts[i]
            if token == "--limit":
                if i + 1 >= len(parts) or not parts[i + 1].isdigit():
                    raise OutreachOpsError("--limit requires a number.")
                limit = int(parts[i + 1])
                i += 2
                continue
            if token == "--dry-run":
                dry_run = True
                i += 1
                continue
            if token == "--send":
                dry_run = False
                i += 1
                continue
            if token == "--approved-only":
                approved_only = True
                i += 1
                continue
            if token == "--all":
                approved_only = False
                i += 1
                continue
            if token == "--confirm":
                confirm = parts[i + 1] if i + 1 < len(parts) else ""
                i += 2
                continue
            raise OutreachOpsError(f"Unknown flag: {token}")

        if not dry_run and confirm.strip().upper() != "SEND":
            raise OutreachOpsError("Refusing to send without `--confirm SEND`.")

        attempted, sent, _ = outreach.send_outbox(
            outbox_path,
            limit=limit,
            dry_run=dry_run,
            approved_only=approved_only,
        )
        await _send_chunks(
            message.channel,
            (
                f"Outbox processed: {outbox_path.name}\n"
                f"mode={'dry-run' if dry_run else 'send'} approved_only={'yes' if approved_only else 'no'} limit={limit}\n"
                f"attempted={attempted} sent={sent}"
            ),
        )
        await message.channel.send(file=discord.File(str(outbox_path)))
        return

    raise OutreachOpsError(f"Unknown outreach subcommand `{sub}`. Use `{CONFIG.command_prefix} outreach help`.")


async def _handle_do(message: discord.Message, args: str) -> None:
    text = (args or "").strip()
    if not text:
        raise OutreachOpsError("Usage: do <freeform request>")

    lower = text.lower()
    # Heuristic parser for the common request shape.
    count = 50
    m = re.search(r"\\b(\\d{1,4})\\b", lower)
    if m and m.group(1).isdigit():
        count = int(m.group(1))

    if "housing" not in lower and "hotel" not in lower and "accommodation" not in lower:
        raise OutreachOpsError(
            "For now, `do` only supports housing sponsor outreach. "
            "Try: `!kiroku do generate a list of 100 housing sponsors and draft emails`."
        )

    await _send_chunks(message.channel, f"Running outreach pipeline (housing, count={count}) ...")
    leads_path = await outreach.generate_housing_leads(count, city=CONFIG.outreach_cohort_city or "Tokyo", country="Japan")
    outbox_path = outreach.draft_housing_emails(leads_path)
    await _send_chunks(
        message.channel,
        (
            f"Done.\n"
            f"- Leads: {leads_path.name}\n"
            f"- Draft outbox: {outbox_path.name}\n"
            "\n"
            "Next steps:\n"
            f"1) Preview: {CONFIG.command_prefix} outreach list {outbox_path.name} --limit 10\n"
            f"2) Approve (example): {CONFIG.command_prefix} outreach approve {outbox_path.name} --first 5\n"
            f"3) Dry-run: {CONFIG.command_prefix} outreach send {outbox_path.name} --limit 5 --dry-run\n"
            f"4) Send: {CONFIG.command_prefix} outreach send {outbox_path.name} --limit 5 --send --confirm SEND"
        ),
    )
    await message.channel.send(file=discord.File(str(leads_path)))
    await message.channel.send(file=discord.File(str(outbox_path)))


async def _dispatch_command(message: discord.Message, command: str, args: str) -> None:
    cmd = command.lower().strip()

    if cmd in READ_COMMANDS:
        if cmd == "help":
            await _handle_help(message)
        elif cmd == "ping":
            await _handle_ping(message)
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
        elif cmd == "id":
            guild_id = message.guild.id if message.guild else "n/a"
            text = (
                f"user_id={message.author.id}\n"
                f"channel_id={message.channel.id}\n"
                f"guild_id={guild_id}"
            )
            await _send_chunks(message.channel, text)
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
        elif cmd == "merge":
            await _handle_merge(message, args)
        elif cmd == "deploy":
            await _handle_deploy(message, args)
        elif cmd == "ship":
            await _handle_ship(message, args)
        elif cmd == "outreach":
            await _handle_outreach(message, args)
        elif cmd == "do":
            await _handle_do(message, args)
        return

    await _send_chunks(message.channel, f"Unknown command `{cmd}`. Use `{CONFIG.command_prefix} help`.")


@bot.event
async def on_ready() -> None:
    logger.info("%s connected", bot.user)
    logger.info("admin channels: %s", sorted(CONFIG.admin_channel_ids) if CONFIG.admin_channel_ids else "ALL")
    logger.info(
        "allowed users: %s",
        sorted(CONFIG.allowed_user_ids) if CONFIG.allowed_user_ids else "ALL_IN_ADMIN_CHANNEL",
    )
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

    # Support multiple commands in one message (one per line), e.g.:
    #   !kiroku ping
    #   !kiroku status
    #   !kiroku outreach config
    raw_content = message.content or ""
    lines = [ln.strip() for ln in raw_content.splitlines() if ln.strip()]
    commands: list[tuple[str, str]] = []
    for ln in lines:
        if not ln.lower().startswith(CONFIG.command_prefix.lower()):
            continue
        payload = ln[len(CONFIG.command_prefix) :].strip()
        if not payload:
            commands.append(("help", ""))
            continue
        parts = payload.split(None, 1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        commands.append((command, args))

    if not commands:
        return

    async with message.channel.typing():
        for command, args in commands:
            try:
                await _dispatch_command(message, command, args)
            except (CodeOpsError, OutreachOpsError) as exc:
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
