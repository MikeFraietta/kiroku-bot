from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp


TASK_STATUS_NEW = "new"
TASK_STATUS_PLANNED = "planned"
TASK_STATUS_PATCHED = "patched"
TASK_STATUS_APPLIED = "applied"
TASK_STATUS_COMMITTED = "committed"
TASK_STATUS_PUBLISHED = "published"
TASK_STATUS_FAILED = "failed"


@dataclass
class CodeTask:
    task_id: int
    title: str
    instructions: str
    requested_by: str
    requested_by_id: str
    status: str
    branch: str
    created_at: str
    updated_at: str
    plan: str = ""
    patch: str = ""
    files: list[str] = field(default_factory=list)
    commit_sha: str = ""
    compare_url: str = ""
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "instructions": self.instructions,
            "requested_by": self.requested_by,
            "requested_by_id": self.requested_by_id,
            "status": self.status,
            "branch": self.branch,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "plan": self.plan,
            "patch": self.patch,
            "files": self.files,
            "commit_sha": self.commit_sha,
            "compare_url": self.compare_url,
            "last_error": self.last_error,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CodeTask":
        return CodeTask(
            task_id=int(data["task_id"]),
            title=str(data.get("title", "")),
            instructions=str(data.get("instructions", "")),
            requested_by=str(data.get("requested_by", "")),
            requested_by_id=str(data.get("requested_by_id", "")),
            status=str(data.get("status", TASK_STATUS_NEW)),
            branch=str(data.get("branch", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            plan=str(data.get("plan", "")),
            patch=str(data.get("patch", "")),
            files=[str(x) for x in data.get("files", [])],
            commit_sha=str(data.get("commit_sha", "")),
            compare_url=str(data.get("compare_url", "")),
            last_error=str(data.get("last_error", "")),
        )


@dataclass
class CodeOpsConfig:
    repo_path: Path
    tasks_file: Path
    base_branch: str = "main"
    remote_name: str = "origin"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"
    verify_command: str | None = None
    max_context_files: int = 6
    max_context_chars_per_file: int = 8000


class CodeOpsError(RuntimeError):
    pass


class CodeOps:
    def __init__(self, config: CodeOpsConfig):
        self.config = config
        self.config.repo_path = self.config.repo_path.resolve()
        self.config.tasks_file = self.config.tasks_file.resolve()
        self.config.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_git_repo()
        self._state_lock = asyncio.Lock()
        self._init_store_if_missing()

    def _ensure_git_repo(self) -> None:
        git_dir = self.config.repo_path / ".git"
        if not git_dir.exists():
            raise CodeOpsError(f"Not a git repository: {self.config.repo_path}")

    def _run(self, cmd: list[str], check: bool = True) -> str:
        proc = subprocess.run(
            cmd,
            cwd=self.config.repo_path,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise CodeOpsError(
                f"Command failed ({' '.join(cmd)}): {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout.strip()

    def _run_shell(self, cmd: str, check: bool = True) -> str:
        proc = subprocess.run(
            cmd,
            cwd=self.config.repo_path,
            text=True,
            capture_output=True,
            check=False,
            shell=True,
            executable="/bin/bash",
        )
        if check and proc.returncode != 0:
            raise CodeOpsError(
                f"Command failed ({cmd}): {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout.strip()

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_store_if_missing(self) -> None:
        if self.config.tasks_file.exists():
            return
        payload = {"next_id": 1, "tasks": []}
        self.config.tasks_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_store(self) -> dict[str, Any]:
        try:
            raw = self.config.tasks_file.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            raise CodeOpsError(f"Failed reading task store: {exc}") from exc

        if not isinstance(payload, dict):
            raise CodeOpsError("Task store is invalid (expected object).")
        if "next_id" not in payload or "tasks" not in payload:
            raise CodeOpsError("Task store missing keys: next_id/tasks.")
        if not isinstance(payload["tasks"], list):
            raise CodeOpsError("Task store invalid: tasks must be list.")
        return payload

    def _save_store(self, payload: dict[str, Any]) -> None:
        self.config.tasks_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _tasks(self) -> list[CodeTask]:
        payload = self._load_store()
        return [CodeTask.from_dict(t) for t in payload.get("tasks", [])]

    def _upsert_task(self, task: CodeTask) -> None:
        payload = self._load_store()
        tasks = payload.get("tasks", [])
        replaced = False
        for i, current in enumerate(tasks):
            if int(current.get("task_id", -1)) == task.task_id:
                tasks[i] = task.to_dict()
                replaced = True
                break
        if not replaced:
            tasks.append(task.to_dict())
        payload["tasks"] = tasks
        self._save_store(payload)

    def _next_id(self) -> int:
        payload = self._load_store()
        nxt = int(payload.get("next_id", 1))
        payload["next_id"] = nxt + 1
        self._save_store(payload)
        return nxt

    def _infer_files_from_text(self, text: str) -> list[str]:
        candidates = re.findall(r"[A-Za-z0-9_./-]+\.(?:py|md|json|yaml|yml|toml|js|ts|html|css|gs)", text)
        seen: set[str] = set()
        out: list[str] = []
        tracked = set(self._run(["git", "ls-files"], check=True).splitlines())
        for item in candidates:
            path = item.strip()
            if path in tracked and path not in seen:
                seen.add(path)
                out.append(path)
        return out

    def _infer_files_for_task(self, task: CodeTask) -> list[str]:
        if task.files:
            return task.files

        files = self._infer_files_from_text(task.instructions + "\n" + task.plan)
        if files:
            return files[: self.config.max_context_files]

        # fallback to key entry points
        defaults = [
            "bot.py",
            "codeops.py",
            "README.md",
            "website/kiroku_outreach_automation.gs",
        ]
        tracked = set(self._run(["git", "ls-files"], check=True).splitlines())
        return [f for f in defaults if f in tracked][: self.config.max_context_files]

    def _looks_like_unified_diff(self, text: str) -> bool:
        candidate = (text or "").strip()
        if not candidate:
            return False
        if re.search(r"(?m)^diff --git\s", candidate):
            return True
        if re.search(r"(?m)^---\s", candidate) and re.search(r"(?m)^\+\+\+\s", candidate):
            return True
        return False

    def _extract_unified_diff(self, raw: str) -> str:
        text = (raw or "").replace("\r\n", "\n").strip()
        if not text:
            return ""

        # Prefer extracting a fenced diff block if present.
        fenced = re.findall(r"```(?:diff)?\s*\n(.*?)```", text, flags=re.S)
        for block in fenced:
            block = block.strip()
            if self._looks_like_unified_diff(block):
                return block.strip() + "\n"

        # Otherwise, extract from the first diff marker.
        m = re.search(r"(?m)^diff --git\s", text)
        if m:
            return text[m.start() :].strip() + "\n"
        m = re.search(r"(?m)^---\sa/", text)
        if m:
            return text[m.start() :].strip() + "\n"

        # Fallback to returning the full text (caller can validate and raise).
        return text.strip() + "\n"

    def _sanitize_diff_text(self, diff_text: str) -> str:
        """
        Normalize model output into something `git apply` is more likely to accept.

        LLMs frequently hallucinate `index <sha>..<sha>` lines (sometimes with non-hex chars),
        but git doesn't need them for text patches.
        """
        text = (diff_text or "").replace("\r\n", "\n").strip("\n")
        if not text.strip():
            return ""

        lines = [ln for ln in text.splitlines() if not ln.startswith("index ")]
        cleaned = "\n".join(lines).strip("\n")
        return cleaned + "\n" if cleaned else ""

    def _is_placeholder_task(self, task: CodeTask) -> bool:
        def _is_placeholder(s: str) -> bool:
            s = (s or "").strip()
            return bool(re.fullmatch(r"<[^>]+>", s))

        return _is_placeholder(task.title) or _is_placeholder(task.instructions) or "<instructions>" in task.instructions

    def _remote_slug(self) -> str:
        remote_url = self._run(["git", "remote", "get-url", self.config.remote_name], check=True)
        remote_url = remote_url.strip()

        # git@host:owner/repo.git
        m_ssh = re.match(r"git@[^:]+:([^\s]+?)(?:\.git)?$", remote_url)
        if m_ssh:
            return m_ssh.group(1)

        # https://host/owner/repo(.git)
        m_https = re.match(r"https?://[^/]+/([^\s]+?)(?:\.git)?$", remote_url)
        if m_https:
            return m_https.group(1)

        raise CodeOpsError(f"Could not parse remote URL: {remote_url}")

    async def create_task(self, title: str, instructions: str, requested_by: str, requested_by_id: str) -> CodeTask:
        async with self._state_lock:
            task_id = self._next_id()
            now = self._iso_now()
            branch = f"codex/task-{task_id}"
            task = CodeTask(
                task_id=task_id,
                title=title.strip()[:120],
                instructions=instructions.strip(),
                requested_by=requested_by,
                requested_by_id=requested_by_id,
                status=TASK_STATUS_NEW,
                branch=branch,
                created_at=now,
                updated_at=now,
            )
            task.files = self._infer_files_from_text(task.instructions)
            self._upsert_task(task)
            return task

    async def list_tasks(self, include_closed: bool = False) -> list[CodeTask]:
        async with self._state_lock:
            tasks = self._tasks()
            tasks.sort(key=lambda t: t.task_id, reverse=True)
            if include_closed:
                return tasks
            return [t for t in tasks if t.status not in {"closed"}]

    async def get_task(self, task_id: int) -> CodeTask:
        async with self._state_lock:
            for task in self._tasks():
                if task.task_id == task_id:
                    return task
        raise CodeOpsError(f"Task {task_id} not found.")

    async def plan_task(self, task_id: int) -> CodeTask:
        async with self._state_lock:
            task = self._get_task_unlocked(task_id)
            if self._is_placeholder_task(task):
                raise CodeOpsError(
                    "Task looks like placeholders (`<title>` / `<instructions>`). "
                    "Create a new task with real instructions, e.g. "
                    "`!kiroku task Add ping command || Add a read command ping that replies pong.`"
                )
            files = self._infer_files_for_task(task)
            task.files = files

            if self._llm_available():
                task.plan = await self._llm_plan(task)
            else:
                task.plan = self._fallback_plan(task, files)

            task.status = TASK_STATUS_PLANNED
            task.updated_at = self._iso_now()
            task.last_error = ""
            self._upsert_task(task)
            return task

    async def patch_task(self, task_id: int) -> CodeTask:
        async with self._state_lock:
            task = self._get_task_unlocked(task_id)
            if self._is_placeholder_task(task):
                raise CodeOpsError(
                    "Task looks like placeholders (`<title>` / `<instructions>`). "
                    "Create a new task with real instructions, then run diff/run again."
                )
            if not task.plan:
                files = self._infer_files_for_task(task)
                task.plan = self._fallback_plan(task, files)
                task.files = files

            if not self._llm_available():
                raise CodeOpsError(
                    "No LLM provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env to enable patch generation."
                )

            raw1 = await self._llm_patch(task, strict=False)
            candidate = self._sanitize_diff_text(self._extract_unified_diff(raw1))

            if not self._looks_like_unified_diff(candidate):
                # Retry once with a stricter prompt if the model responded with prose.
                raw2 = await self._llm_patch(task, strict=True)
                candidate2 = self._sanitize_diff_text(self._extract_unified_diff(raw2))
                if self._looks_like_unified_diff(candidate2):
                    candidate = candidate2
                else:
                    preview = "\n".join((raw2 or "").strip().splitlines()[:20])
                    raise CodeOpsError(
                        "Model output did not contain a valid unified diff. "
                        "Try narrowing scope and naming target files. "
                        f"First lines of output:\n{preview}"
                    )

            task.patch = candidate

            task.status = TASK_STATUS_PATCHED
            task.updated_at = self._iso_now()
            task.last_error = ""
            self._upsert_task(task)
            return task

    def _llm_available(self) -> bool:
        return bool(self.config.anthropic_api_key or self.config.openai_api_key)

    async def apply_task(self, task_id: int) -> CodeTask:
        async with self._state_lock:
            task = self._get_task_unlocked(task_id)
            if not task.patch.strip():
                raise CodeOpsError("Task has no patch. Run patch step first.")

            self._prepare_branch(task.branch)
            self._apply_patch_text(task.patch)

            if self.config.verify_command:
                self._run_shell(self.config.verify_command, check=True)

            task.status = TASK_STATUS_APPLIED
            task.updated_at = self._iso_now()
            task.last_error = ""
            self._upsert_task(task)
            return task

    async def commit_task(self, task_id: int, message: str | None = None) -> CodeTask:
        async with self._state_lock:
            task = self._get_task_unlocked(task_id)
            self._run(["git", "checkout", task.branch], check=True)
            self._run(["git", "add", "-A"], check=True)

            has_changes = self._run(["git", "diff", "--cached", "--name-only"], check=True)
            if not has_changes.strip():
                raise CodeOpsError("No staged changes to commit.")

            commit_msg = message.strip() if message else f"task({task.task_id}): {task.title}"
            self._run(["git", "commit", "-m", commit_msg], check=True)
            sha = self._run(["git", "rev-parse", "HEAD"], check=True)

            task.commit_sha = sha
            task.status = TASK_STATUS_COMMITTED
            task.updated_at = self._iso_now()
            task.last_error = ""
            self._upsert_task(task)
            return task

    async def publish_task(self, task_id: int) -> CodeTask:
        async with self._state_lock:
            task = self._get_task_unlocked(task_id)
            self._run(["git", "checkout", task.branch], check=True)
            self._run(["git", "push", "-u", self.config.remote_name, task.branch], check=True)

            slug = self._remote_slug()
            task.compare_url = (
                f"https://github.com/{slug}/compare/"
                f"{self.config.base_branch}...{task.branch}?expand=1"
            )
            task.status = TASK_STATUS_PUBLISHED
            task.updated_at = self._iso_now()
            task.last_error = ""
            self._upsert_task(task)
            return task

    async def fail_task(self, task_id: int, error: str) -> None:
        async with self._state_lock:
            task = self._get_task_unlocked(task_id)
            task.status = TASK_STATUS_FAILED
            task.last_error = error[:2000]
            task.updated_at = self._iso_now()
            self._upsert_task(task)

    def _get_task_unlocked(self, task_id: int) -> CodeTask:
        for task in self._tasks():
            if task.task_id == task_id:
                return task
        raise CodeOpsError(f"Task {task_id} not found.")

    def _prepare_branch(self, branch: str) -> None:
        self._run(["git", "fetch", self.config.remote_name], check=True)
        self._run(["git", "checkout", self.config.base_branch], check=True)
        self._run(["git", "pull", "--ff-only", self.config.remote_name, self.config.base_branch], check=True)
        self._run(["git", "checkout", "-B", branch], check=True)

    def _apply_patch_text(self, patch_text: str) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False, encoding="utf-8") as tmp:
            tmp.write(patch_text)
            patch_path = tmp.name

        try:
            self._run(["git", "apply", "--index", "--whitespace=fix", patch_path], check=True)
        except CodeOpsError as exc:
            raise CodeOpsError(f"Patch apply failed: {exc}") from exc
        finally:
            try:
                os.remove(patch_path)
            except OSError:
                pass

    def _fallback_plan(self, task: CodeTask, files: list[str]) -> str:
        file_lines = "\n".join(f"- {p}" for p in files) if files else "- determine impacted files"
        return (
            "1. Confirm scope and expected behavior from task instructions.\n"
            "2. Update targeted files with minimal, testable changes.\n"
            "3. Run verification command (if configured) and inspect git diff.\n"
            "4. Commit on task branch and publish PR.\n"
            "\n"
            "Likely files:\n"
            f"{file_lines}"
        )

    def _build_context(self, files: list[str]) -> str:
        chunks: list[str] = []
        for path_str in files[: self.config.max_context_files]:
            path = (self.config.repo_path / path_str).resolve()
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            content = content[: self.config.max_context_chars_per_file]
            chunks.append(f"FILE: {path_str}\n{content}\n")
        return "\n".join(chunks)

    async def _llm_plan(self, task: CodeTask) -> str:
        files = self._infer_files_for_task(task)
        context = self._build_context(files)

        system = (
            "You are a senior software engineer. Build an execution plan for a coding task. "
            "Respond with concise steps and a short list of target files."
        )
        user = (
            f"Task title: {task.title}\n"
            f"Instructions:\n{task.instructions}\n\n"
            f"Repo context:\n{context}\n\n"
            "Output format:\n"
            "Plan:\n- ...\n"
            "Files:\n- path"
        )
        return await self._chat_completion(system, user)

    async def _llm_patch(self, task: CodeTask, strict: bool) -> str:
        files = self._infer_files_for_task(task)
        context = self._build_context(files)

        system = (
            "You are an expert software engineer. "
            "Return ONLY a valid unified diff patch against the repository root. "
            "Do not include markdown fences, explanations, or any text before/after the diff. "
            "Your first line MUST start with `diff --git`."
        )
        if strict:
            system = (
                "You are a patch generator. "
                "Your entire response must be a valid unified diff patch. "
                "The FIRST line MUST start with `diff --git`. "
                "No prose, no markdown, no code fences."
            )
        user = (
            f"Task title: {task.title}\n"
            f"Instructions:\n{task.instructions}\n\n"
            f"Execution plan:\n{task.plan}\n\n"
            f"Repository file context:\n{context}\n\n"
            "Constraints:\n"
            "- Keep changes minimal and coherent.\n"
            "- Preserve existing style and behavior unless task requests otherwise.\n"
            "- Return a single unified diff."
        )
        return await self._chat_completion(system, user)

    async def _chat_completion(self, system: str, user: str) -> str:
        # Prefer Anthropic when available (OpenAI key may be out of quota).
        if self.config.anthropic_api_key:
            return await self._anthropic_messages(system, user)
        if self.config.openai_api_key:
            return await self._openai_chat_completion(system, user)
        raise CodeOpsError("No LLM provider configured (set ANTHROPIC_API_KEY or OPENAI_API_KEY).")

    async def _openai_chat_completion(self, system: str, user: str) -> str:
        url = f"{self.config.openai_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.openai_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.config.openai_api_key}",
            "Content-Type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                text = await response.text()
                if response.status >= 300:
                    raise CodeOpsError(f"Model request failed ({response.status}): {text[:800]}")
                try:
                    data = json.loads(text)
                    return data["choices"][0]["message"]["content"].strip()
                except Exception as exc:
                    raise CodeOpsError(f"Invalid model response: {text[:500]}") from exc

    async def _anthropic_messages(self, system: str, user: str) -> str:
        url = f"{self.config.anthropic_base_url.rstrip('/')}/v1/messages"
        payload = {
            "model": self.config.anthropic_model,
            "max_tokens": 4000,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": str(self.config.anthropic_api_key),
            "anthropic-version": self.config.anthropic_version,
            "content-type": "application/json",
        }

        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                text = await response.text()
                if response.status >= 300:
                    raise CodeOpsError(f"Model request failed ({response.status}): {text[:800]}")
                try:
                    data = json.loads(text)
                    parts = data.get("content", [])
                    out = "".join(str(p.get("text", "")) for p in parts if p.get("type") == "text")
                    return out.strip()
                except Exception as exc:
                    raise CodeOpsError(f"Invalid model response: {text[:500]}") from exc


def parse_task_id(value: str) -> int:
    cleaned = str(value or "").strip()
    # Accept common Discord-friendly formats like "1", "#1", or "#1)".
    # Disallow sticking additional word characters right after the ID (e.g. "1abc").
    m = re.match(r"^#?([0-9]+)(?=$|[^0-9A-Za-z_])", cleaned)
    if not m:
        raise CodeOpsError("Task ID must be a number (example: `1` or `#1`).")
    return int(m.group(1))


def parse_title_and_instructions(raw: str) -> tuple[str, str]:
    content = (raw or "").strip()
    if not content:
        raise CodeOpsError("Usage: !kiroku task <title> || <instructions>")

    if "||" in content:
        title, instructions = content.split("||", 1)
        title = title.strip()
        instructions = instructions.strip()
    else:
        title = content[:100]
        instructions = content

    if not title:
        raise CodeOpsError("Task title cannot be empty.")
    if not instructions:
        raise CodeOpsError("Task instructions cannot be empty.")
    if re.fullmatch(r"<[^>]+>", title.strip()) or re.fullmatch(r"<[^>]+>", instructions.strip()):
        raise CodeOpsError(
            "It looks like you pasted placeholders (`<title>` / `<instructions>`). "
            "Replace them with real text, e.g. "
            "`!kiroku task Add ping command || Add a read command ping that replies pong.`"
        )
    return title, instructions
