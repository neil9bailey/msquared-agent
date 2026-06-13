# X Workflow

1. X monitoring imports supplied mentions/replies or read-only monitored posts.
2. MSquared can draft original posts from themes or replies to supplied mentions/replies.
3. Keyword-search auto-replies are blocked by default.
4. Drafts enter the approval queue with claim and automation risk checks.
5. A human approves or rejects.
6. Approved items can produce a `/2/tweets` payload.
7. Live posting remains blocked unless `ENABLE_X_WRITE=true` and X credentials are configured.

Do not implement bulk DMs, trend manipulation, duplicate posting, or unsolicited outreach.
