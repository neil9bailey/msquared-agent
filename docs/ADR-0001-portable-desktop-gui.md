# ADR-0001: Portable Windows Desktop GUI

## Status
Accepted

## Context
The Phase 0 application currently exposes a Streamlit interface. That is useful for development, but it requires a command line, a Python environment, and a browser. The requested delivery target is a simplified GUI that can be distributed as a portable Windows executable.

## Decision
Add a native Tkinter desktop interface as `msquared_agent.desktop_ui` and package it with PyInstaller as a single-file Windows executable. Keep the existing Streamlit UI available for development.

Bundled read-only resources such as `config/` and `prompts/` are resolved from PyInstaller's temporary resource directory when frozen. Writable runtime files such as `data/approval_queue.json` and `data/audit.log.jsonl` are stored next to the executable, preserving portable-app behavior.

## Consequences
- The desktop app has no browser or local web server requirement.
- The Phase 0 safety model remains unchanged: drafts are generated locally and nothing is posted or emailed.
- The executable can be moved with its generated `data/` folder to preserve queue and audit history.
- Future write/send features must keep the explicit feature flags and human-approval guardrails visible in the desktop UI.
