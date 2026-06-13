# Email Workflow

1. Website contact and request-more-information emails arrive at `msquared@diiac.io`.
2. The operator console imports messages through local/manual intake or the IMAP connector when `ENABLE_EMAIL_READ=true`.
3. MSquared classifies the message and drafts a response.
4. The draft enters the approval queue.
5. A human approves or rejects it.
6. The app can prepare an email payload after approval.
7. Sending remains blocked unless `ENABLE_EMAIL_SEND=true` and credentials are configured.

Legal, compliance, and security emails should be treated as review/escalation items.
