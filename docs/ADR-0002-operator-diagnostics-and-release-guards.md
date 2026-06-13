# ADR-0002: Operator Diagnostics and Release Guards

## Status
Accepted

## Context
The desktop console needs to show what the agent is doing when X or email monitoring fails, skips, or succeeds. A release artifact must also avoid shipping local credentials or runtime logs.

## Decision
Add a persistent redacted application log at `data/app.log.jsonl` and expose it in a desktop **Diagnostics** tab alongside the audit trail, connector readiness, and runtime paths.

Connector refreshes and guarded post/send attempts write explicit app-log events for started, skipped, completed, failed, and cancelled states. Logs redact known secret values, secret-looking keys, private content fields, and email addresses before writing and again when reading.

X OAuth 2.0 user-context tokens are first-class Admin settings. Read/write calls prefer the OAuth 2.0 access token, and the app can refresh it with the stored refresh token. OAuth 1.0a credentials remain supported as fallback.

Release scripts refuse to build or package if `dist\.env` or `dist\data` exists. The portable package includes an empty `data\` folder, `.env.example`, docs, config, and the exe by default.

A local-only override, `.\scripts\package_portable.ps1 -IncludeLocalEnv`, may copy `dist\.env` into the portable folder and zip when the operator intentionally wants a private build for their own machine.

## Consequences
- Operators can diagnose bad credentials, missing flags, rate/API failures, and skipped connectors without opening raw files.
- Public post/send actions require an approved item, prepared payload, enabled live flag, connector readiness, and typed execution confirmation.
- Runtime data remains portable beside the exe, but distributable artifacts should be clean unless the local-only `.env` override is explicitly used.
- Credentials are still stored in a plaintext local `.env` for this MVP; Windows Credential Manager/DPAPI remains the next enterprise hardening step.
