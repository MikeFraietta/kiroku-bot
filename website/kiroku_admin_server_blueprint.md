# Kiroku Admin Discord Blueprint

## Recommendation
Use a separate private Discord server named `Kiroku Admin` for operations, testing, and approvals before anything is posted or automated in the TDC server.

This solves your current access constraint (only one NoMachine session) because Mariam can operate approvals from browser + Discord while Kiroku automation runs from Google Apps Script.

## Team model (3 members)
- Owner: You
- Ops Lead: Mariam
- Automation identity: Kiroku (webhook + service account)

## Roles and permissions
- `Owner`:
- Full admin
- Webhook management
- Trigger and rollback authority

- `Ops-Lead` (Mariam):
- Manage messages in ops channels
- Approval authority for outreach rows
- No server-level admin required

- `Automation`:
- Post-only in `#outreach-ops`
- No read access outside designated channels

## Channel structure
- `#welcome-readme`:
- Purpose, escalation path, who approves what

- `#outreach-ops`:
- Webhook alerts from Apps Script (send runs, failures, new replies)
- Kiroku automation output only

- `#approvals`:
- Human decisions and launch commands
- Mariam confirms "approve wave" and "unlock rows"

- `#sandbox-tests`:
- Test notifications and workflow changes
- Required stop before production triggers are enabled

- `#incident-log`:
- Failed sends, auth errors, webhook failures, remediation notes

- `#tdc-rollout`:
- What graduates from admin server to TDC production process

## Standard operating flow
1. Kiroku prepares rows in Google Sheet (`PENDING_REVIEW`).
2. Mariam approves/unlocks pilot rows.
3. Script sends from Kiroku mailbox.
4. Script posts status into `#outreach-ops`.
5. Team decides in `#approvals` whether to unlock next wave.
6. Optional command path: `!kiroku ...` in approved command channels for status/approvals/send runs.

## Security baseline
- Enable Discord server 2FA requirement for moderation actions.
- Keep server invite links disabled by default.
- Rotate webhook URL every 30 days or immediately after any leak.
- Never paste webhook URL into shared sheets or docs.

## Minimal rollout policy to TDC server
- Do not connect automation directly to TDC until:
- two successful send cycles in `Kiroku Admin`
- zero unresolved failures in `#incident-log`
- Mariam sign-off in `#approvals`

## Practical note
If you cannot add Kiroku as a friend, that is fine. A private server + role-based channels is the correct model; friend relationships are not required for ops.

You cannot directly place this Codex assistant as a native Discord participant. Use Discord for your human+automation ops loop, and use this workspace thread for engineering changes.
