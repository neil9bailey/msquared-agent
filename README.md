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

## Operator Console (Updated Workflow)
The interface now follows a clear governed pipeline:

Intake - X mentions, search results, emails
Action Center - Select item -> Generate Draft
Draft Review - Raw MSquared draft + Legal review + Final version
Approval - Human review & edit
Preflight - Safety checks
Execute - Post / Send (with confirmation)

Manual drafting is available in an Advanced section for original posts.

## Operator workflow
1. Open the desktop console.
2. Use **Monitor** to refresh X/email intake or paste a manual X/email item.
3. Filter intake by status and channel when you need only X or email messages.
4. Select an intake item. The Agent tab **Action Center** shows the canonical intake ID, detected action, recommended next step, selected draft, and pipeline state.
5. Use **Generate Draft** to create a raw MSquared draft. The raw draft is preserved separately from Legal and final versions.
6. Use **Run Legal Review**. The Legal Agent only recommends or applies wording changes for clear legal, compliance, claim-boundary, or private-material issues.
7. Use **Edit Final** in Approval if the operator needs to adjust the final version before approval.
8. Use **Approve**, then **Preflight** / **Preflight Payload** to run final safety and payload checks.
9. Use **Execute** or **Post/Send** only after reviewing the preflight payload. Live posting/sending requires connector readiness and a typed confirmation.
10. Use **Diagnostics** to see app logs, audit records, connector readiness, pipeline counts, knowledge status, governed-learning counts, and runtime file paths.

## Admin settings
Open **Settings -> Admin** in the desktop console to enter X API credentials, email IMAP/SMTP credentials, monitor settings, and feature flags. Click **Save Admin Settings** to persist them beside the exe:

- `.env` stores connector credentials and admin-entered flag values.
- `config\feature_flags.yaml` stores the feature flags.
- Secrets are hidden in the UI by default and omitted or masked in readiness output.

The app asks for confirmation if you enable `ENABLE_X_WRITE` or `ENABLE_EMAIL_SEND`, and asks again before a live post/send action is executed.

The X section uses the same wording as the X Developer Portal: Client ID, Client Secret, Bearer Token, Consumer Key, Consumer Key Secret, Access Token, Access Token Secret, App permissions, Type of App, callback URL, website URL, organization, Terms, and Privacy Policy.

For X monitoring, enter the **App Bearer Token** and the numeric MSquared user id. Read monitoring uses the app-only Bearer token first, which avoids stale OAuth 2.0 user access tokens breaking feed refreshes.

For X OAuth 2.0 user-context posting, Client ID and Client Secret are not enough by themselves. Use **Generate OAuth 2 Tokens** in Admin to open X's consent screen, authorize the MSquared account, paste the final redirected URL/code, and let the app save `X_OAUTH2_ACCESS_TOKEN` and `X_OAUTH2_REFRESH_TOKEN`. The configured callback URI must exactly match the X Developer Portal callback URL. The app can refresh OAuth 2.0 user tokens when X returns an unauthorized response. OAuth 1.0a Consumer/Access Token fields remain available only as an explicit fallback when `X_ALLOW_OAUTH1_POSTING_FALLBACK=true`, provided the Access Token was regenerated after the app permissions were set to **Read and write** or **Read and write and Direct message**.

The OAuth 2 authorization URL is copied to the clipboard. If X shows **To use this App you have to be logged in to X**, sign in as `@MSQUARED_2026`, then paste the copied authorization URL into the same logged-in browser tab again.

The **AI Agent** fields are optional. Without `OPENAI_API_KEY`, the Agent tab uses the local governed fallback. With `OPENAI_API_KEY` and `OPENAI_MODEL`, the Agent tab uses OpenAI's Responses API for interactive operator chat and OpenAI-backed draft creation while still creating drafts only through the approval queue. The default model is `gpt-5.4-mini-2026-03-17`; if OpenAI returns an authorization, model-access, quota, or network error, the Agent logs the reason and creates a local governed fallback draft instead of blocking the approval workflow.

The Agent product context is packaged in `prompts\MSQUARED_PRODUCT_CONTEXT.md`. It combines DIIaC IT Enterprise / IT Services and M2 product knowledge, including the split between DIIaC as governed decision assurance infrastructure and M2 as the advisory interpretability/evaluation layer.

The Agent tab also has a local product knowledge index for detailed technical questions. Click **Update Knowledge Library** to scan the configured local repos in `PRODUCT_KNOWLEDGE_ROOTS`. Public posts and email drafts use public-safe context only. Internal technical snippets stay local in `technical_local` mode; `technical_openai` only sends selected internal snippets to OpenAI when `ALLOW_OPENAI_TECHNICAL_CONTEXT=true`.

The Knowledge Library status card shows last updated time, indexed document count, and public-safe vs internal source counts. Every generated draft can show **Knowledge Used**, including source titles, paths, sensitivity, confidence scores, and similar locally approved examples used for style guidance.

Governed learning is local and append-only in `data\agent_feedback.jsonl`. Approval and rejection events capture intake ID, draft ID, outcome, reason tags, final text, legal review result, and any human edit diff. Draft generation retrieves top similar approved local examples as style/context guidance without sending the feedback store anywhere.

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

## Troubleshooting X 401 Unauthorized
Use **Settings -> Readiness -> Test X Connection** to run a read-only check before refreshing feeds or posting approved items. The result is shown in the readiness panel and logged in Diagnostics.

Common 401 causes:

- The saved OAuth 2.0 access token has expired and no refresh token is configured.
- The access token was issued before the X app permissions were changed to **Read and write**.
- The token is an app-only bearer token where the workflow needs OAuth 2.0 user-context access.
- The OAuth 2.0 scopes are missing `users.read`, `tweet.read`, `tweet.write`, or `offline.access`.
- The token belongs to a different X user than the configured MSquared account.

Fix sequence:

1. In the X Developer Portal, confirm app permissions are **Read and write** or **Read and write and Direct message**.
2. Re-generate OAuth 2.0 user-context access and refresh tokens for the MSquared account.
3. Save both tokens in **Settings -> Admin**.
4. Confirm `X_MONITOR_USER_ID` is the numeric user id for `@MSQUARED_2026` to avoid an extra handle lookup call.
5. Click **Test X Connection**, then refresh X once the test passes.

## Troubleshooting X 403 OAuth 1.0a App Permissions
If posting fails with `Your client app is not configured with the appropriate oauth1 app permissions for this endpoint`, the app has fallen back to OAuth 1.0a credentials and X is rejecting them for `/2/tweets`. New builds block this earlier in preflight unless OAuth 1.0a fallback has been explicitly enabled.

Preferred fix:

1. In **Settings -> Admin**, confirm `X_CLIENT_ID`, `X_CLIENT_SECRET`, and `X_CALLBACK_URI` are filled in.
2. Click **Generate OAuth 2 Tokens**.
3. Authorize the MSquared X account in the browser.
4. Paste the final redirected URL or `code` value back into the prompt.
5. Confirm **Readiness & Paths** shows `write_auth_mode` as `oauth2_user`.
6. Run **Test X Connection**, then preflight and post the approved draft again.

Fallback fix:

1. In the X Developer Portal, set app permissions to **Read and write**.
2. Regenerate the OAuth 1.0a access token and access token secret after the permission change.
3. Save the new OAuth 1.0a values in **Settings -> Admin**.
4. Set `X_ALLOW_OAUTH1_POSTING_FALLBACK=true` only if you deliberately want the app to try OAuth 1.0a posting.

## Diagnostics and logs
Open **Diagnostics** in the desktop console to inspect:

- `data\app.log.jsonl` for operator-visible app events.
- `data\audit.log.jsonl` for approval and final-action records.
- `data\agent_feedback.jsonl` for governed local approval/rejection learning.
- Connector readiness and runtime paths.
- Pipeline status per intake/draft stage, Knowledge Library status, and governed-learning summary.

Logs are redacted before writing and reading. Secret-looking values and large content fields are omitted or hashed.

## Release safety
The packaging scripts refuse to build or package when generated runtime credentials/data are present under `dist\.env` or `dist\data`. The portable zip contains `.env.example` and an empty `data\` folder only unless you explicitly run `.\scripts\package_portable.ps1 -IncludeLocalEnv` for a private local build.

If credentials were pasted into chat, committed, emailed, or stored in a shared artifact, rotate them in X and the mailbox provider before live use.
