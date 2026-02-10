# Discord CodeOps Quickstart

## Preconditions

- Bot is online (`python bot.py`)
- You are posting inside one of `ADMIN_CHANNEL_IDS`
- `OPENAI_API_KEY` is set for patch generation
- If `ALLOWED_USER_IDS` is set, you are included in it.
- If `ALLOWED_USER_IDS` is empty, bootstrap mode allows anyone in admin channels.

## Happy path

1. Create task:

```text
!kiroku task Improve README structure || Rewrite README with setup, command list, and safety notes for admin operators.
```

2. Generate plan:

```text
!kiroku plan 1
```

3. Generate patch:

```text
!kiroku diff 1
```

4. Review patch preview:

```text
!kiroku preview 1
```

5. Apply patch to task branch:

```text
!kiroku apply 1
```

6. Commit:

```text
!kiroku commit 1 docs: improve README structure
```

7. Publish PR compare link:

```text
!kiroku pr 1
```

## One-shot mode

```text
!kiroku run 1
```

## Troubleshooting

- `Unauthorized`:
  - Your Discord user ID is not in `ALLOWED_USER_IDS`.
  - Or you are posting outside `ADMIN_CHANNEL_IDS`.
- `OPENAI_API_KEY is not set`:
  - Add key to `.env` and restart bot.
- `Patch apply failed`:
  - Regenerate with clearer scope; task may be too broad.
- `git push` failed:
  - Fix git auth for bot runtime user (SSH recommended).

## ID helpers

Use:

```text
!kiroku id
```

to get your `user_id`, current `channel_id`, and `guild_id`.
