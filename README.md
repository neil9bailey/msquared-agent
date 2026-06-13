# MSquared Governed Brand Agent

Transparent, human-supervised AI brand agent for DIIaC Ltd.

## Phase 0/1 MVP
- Monitor X and website email intake through local/manual intake or read-only connectors.
- Draft original X posts, X replies to supplied mentions/replies, and email responses as MSquared.
- Strict claim guard, risk classifier, opt-out checks, approval queue, and audit trail.
- Prepare X/email payloads only after approval.
- Operator diagnostics for connector failures, skipped reads, approvals, and post/send attempts.

Human approval required before any public action.

## Setup
```bash
cd msquared-agent
pip install -e .
```

## Usage
```bash
# Run portable desktop GUI from source
msquared-gui

# Run UI (recommended)
streamlit run src/msquared_agent/ui.py

# Or CLI
msquared
```

## Build Windows exe
```powershell
.\scripts\build_windows_exe.ps1
```

The portable executable is written to `dist\MSquaredAgent.exe`. Runtime data is stored next to the exe in `data\`.

## Package portable folder
```powershell
.\scripts\package_portable.ps1
```

This creates `dist\MSquaredAgent-portable\` and `dist\MSquaredAgent-portable.zip` with the exe, editable `config\`, `.env.example`, docs, and empty `data\`.

For a private local-only build that includes your existing `dist\.env` credentials beside the portable exe:

```powershell
.\scripts\package_portable.ps1 -IncludeLocalEnv
```

The default command excludes `.env`; use the override only for your own machine/private zip.

## Operator workflow
1. Open the desktop console.
2. Use **Monitor** to refresh X/email intake or paste a manual X/email item.
3. Filter intake by status and channel when you need only X or email messages.
4. Use **Agent** to ask MSquared about selected intake/drafts, summarize context, or create an approval draft.
5. Select an intake item and draft an X reply, X post, or email response.
6. Use **Approval** to approve or reject drafts.
7. Use **Prepare Payload** to inspect the approved X/email request.
8. Use **Post/Send** only after reviewing the prepared payload. Live posting/sending requires connector readiness and a typed confirmation.
9. Use **Diagnostics** to see app logs, audit records, connector readiness, and runtime file paths.

## Admin settings
Open **Settings -> Admin** in the desktop console to enter X API credentials, email IMAP/SMTP credentials, monitor settings, and feature flags. Click **Save Admin Settings** to persist them beside the exe:

- `.env` stores connector credentials and admin-entered flag values.
- `config\feature_flags.yaml` stores the feature flags.
- Secrets are hidden in the UI by default and omitted or masked in readiness output.

The app asks for confirmation if you enable `ENABLE_X_WRITE` or `ENABLE_EMAIL_SEND`, and asks again before a live post/send action is executed.

The X section uses the same wording as the X Developer Portal: Client ID, Client Secret, Bearer Token, Consumer Key, Consumer Key Secret, Access Token, Access Token Secret, App permissions, Type of App, callback URL, website URL, organization, Terms, and Privacy Policy.

For X OAuth 2.0 user-context access, enter **OAuth 2.0 Access Token** and **OAuth 2.0 Refresh Token** in Admin. The app uses the OAuth 2.0 access token as a Bearer token for read/write calls and can refresh it with the refresh token when X returns an unauthorized response. OAuth 1.0a Consumer/Access Token fields remain available as fallback.

The **AI Agent** fields are optional. Without `OPENAI_API_KEY`, the Agent tab uses the local governed fallback. With `OPENAI_API_KEY` and `OPENAI_MODEL`, the Agent tab uses OpenAI's Responses API for interactive operator chat and OpenAI-backed draft creation while still creating drafts only through the approval queue. The default model is `gpt-5.4-mini`; if OpenAI returns an authorization, model-access, quota, or network error, the Agent logs the reason and creates a local governed fallback draft instead of blocking the approval workflow.

The Agent product context is packaged in `prompts\MSQUARED_PRODUCT_CONTEXT.md`. It combines DIIaC IT Enterprise / IT Services and M2 product knowledge, including the split between DIIaC as governed decision assurance infrastructure and M2 as the advisory interpretability/evaluation layer.

The Agent tab also has a local product knowledge index for detailed technical questions. Click **Refresh Product Knowledge** to scan the configured local repos in `PRODUCT_KNOWLEDGE_ROOTS`. Public posts and email drafts use public-safe context only. Internal technical snippets stay local in `technical_local` mode; `technical_openai` only sends selected internal snippets to OpenAI when `ALLOW_OPENAI_TECHNICAL_CONTEXT=true`.

Use **Copy Validation Packet** to copy the current question and retrieved source excerpts for review in Codex/Coding Chat.

The Email Connector section is set up for Porkbun defaults:

- IMAP incoming: `imap.porkbun.com`, port `993`, `SSL/TLS`.
- SMTP outgoing: `smtp.porkbun.com`, port `587`, `STARTTLS`.
- SMTP alternatives: port `50587` with `STARTTLS Alt.` or port `465` with `Implicit TLS`.
- POP reference: `pop.porkbun.com`, port `995`, `SSL/TLS`.
- Webmail: `https://webmail.porkbun.com/`.

Mail sorting/import uses IMAP, while approved outbound responses use SMTP. Use the password set for `msquared@diiac.io`, not the Porkbun account password.

## Safe live connector enablement
Defaults are safe:

```yaml
ENABLE_X_WRITE: false
ENABLE_EMAIL_SEND: false
REQUIRE_HUMAN_APPROVAL: true
ALLOW_KEYWORD_SEARCH_AUTO_REPLY: false
ALLOW_UNSOLICITED_DM: false
```

To enable read-only monitoring, set `ENABLE_X_READ=true` and/or `ENABLE_EMAIL_READ=true`, then provide the matching environment variables from `.env.example`.

To enable live posting or sending, keep `REQUIRE_HUMAN_APPROVAL=true`, provide X or SMTP credentials, and only enable `ENABLE_X_WRITE` or `ENABLE_EMAIL_SEND` after testing approved payloads locally.

For X profile monitoring, set `X_MONITOR_USER_ID=2065865497237729280` for `@MSQUARED_2026`. A handle can be entered, but that requires X's user lookup endpoint first; using the numeric id avoids that extra paid/API lookup. Search monitoring can also use `X_MONITOR_QUERY`, but replies to search-derived items remain blocked by default.

## Diagnostics and logs
Open **Diagnostics** in the desktop console to inspect:

- `data\app.log.jsonl` for operator-visible app events.
- `data\audit.log.jsonl` for approval and final-action records.
- Connector readiness and runtime paths.

Logs are redacted before writing and reading. Secret-looking values and large content fields are omitted or hashed.

## Release safety
The packaging scripts refuse to build or package when generated runtime credentials/data are present under `dist\.env` or `dist\data`. The portable zip contains `.env.example` and an empty `data\` folder only unless you explicitly run `.\scripts\package_portable.ps1 -IncludeLocalEnv` for a private local build.

If credentials were pasted into chat, committed, emailed, or stored in a shared artifact, rotate them in X and the mailbox provider before live use.
