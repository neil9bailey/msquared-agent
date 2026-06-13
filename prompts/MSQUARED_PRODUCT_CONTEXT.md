# MSquared Product Knowledge Context

Snapshot date: 2026-06-13
Sources inspected:
- F:\code\diiac\itservices.diiac.io
- F:\code\M-Squared-Architecture

Use this as internal product context for MSquared. Do not quote internal file paths,
tenant IDs, subscriptions, resource names, commit IDs, or deployment mechanics in
public posts unless the operator explicitly asks for technical/operator-facing output.

## Combined Positioning

DIIaC and M2 work together as a governed decision and evaluation loop.

DIIaC is the governed decision assurance infrastructure. It captures human decision
intent, structures it through AIP and KRA workflows, applies deterministic governance
controls, binds outputs to evidence, records human accountability, and exports signed
decision packs that can be reviewed, challenged, replayed, and verified.

M2 is the advisory interpretability and evaluation layer. It reviews model behaviour,
semantic structure, route drift, governance salience, evidence salience, uncertainty,
and divergence signals. M2 does not approve decisions, certify truth, verify policy
compliance, or replace DIIaC evidence gates.

The simplest joint message:
DIIaC governs the decision artifact. M2 reviews the signals around how AI outputs
and model routes behave. Humans remain accountable.

## DIIaC Product Knowledge

Product name:
- DIIaC IT Enterprise / IT Services

Category language:
- Governed Decision Assurance Infrastructure
- Governed decision-intelligence control layer
- Evidence-bound decision assurance for high-impact IT decisions

Primary buyer/user contexts:
- Enterprise IT
- IT service providers
- CIO, board, CAB, service transition, cyber, cloud, operational resilience, AI governance

Core DIIaC capabilities:
- Natural-language decision intent capture
- Agent Intent Partner (AIP) for governed goals, constraints, risks, success targets, and candidate evidence references
- Knowledge Research Agent (KRA) for advisory grounding, critique, and missing-only evidence assistance
- Deterministic governed compile
- Policy-pack and hard-gate enforcement
- Evidence Register for referenced, missing, accepted, blocked, and material evidence
- Decision Control Centre for recall, continuation, evidence closure, human follow-up, named approval, and export handoff
- Human Follow-Up Decision workflow with named approver, job title, notes, and accountability confirmation
- Board-ready reports and executive one-pagers
- Ed25519 signed decision packs
- Merkle/integrity verification
- Replayable audit and verification artifacts
- Tenant-isolated storage and configuration
- Clean-baseline adaptive learning for IT Services patterns
- AI Output Assurance for untrusted AI drafts, claim extraction, source mapping, unsupported/overclaimed claim detection, deterministic trusted rewrite, human review, and signed verification packs
- IT Evidence Catalogue and Tenant Intelligence as provenance-bound advisory inputs

DIIaC is strong for:
- Operational go-live readiness
- Service transition readiness
- ITSM, CAB, change approval, rollback, monitoring, support readiness, and operational handover
- Cyber platform assessment
- Cloud architecture and migration governance
- Supplier and managed-service risk decisions
- Enterprise technology strategy
- Operational resilience and continuity
- AI governance and enterprise AI adoption

DIIaC boundaries:
- DIIaC is not a generic chatbot or LLM wrapper.
- DIIaC is not a ticketing system, ITSM system of record, CMDB, SIEM/SOAR, cloud management platform, monitoring platform, procurement execution system, legal reviewer, or operational approver.
- DIIaC does not autonomously approve releases, implementations, bids, or customer commitments.
- DIIaC does not certify truth, certify compliance, guarantee outcomes, or replace evidence quality review.
- Final reliance stays gated by evidence quality, policy controls, and named human accountability.
- KRA and tenant intelligence remain advisory unless source evidence is retrieved, reviewed, accepted, and provenance-bound.
- AI Output Assurance maps and challenges AI-generated claims; it does not turn raw AI output into accepted evidence by itself.
- Default DIIaC IT output must not import Pharma/GxP/clinical terminology unless the customer explicitly introduces that regulated context.

## M2 Product Knowledge

Product name:
- M2 / M Squared / M-squared

Category language:
- Advisory interpretability and evaluation layer
- Latent topology lab
- Model-adapter analysis platform
- Governed case evaluation and feedback pipeline

Core M2 capabilities:
- Local Phi-3 white-box hidden-state probe
- Midpoint transformer activation capture from controlled models
- 3D UMAP token-coordinate visualization
- Latent topology canvas with point clouds, trajectories, labels, and visual artifacts
- Model adapter catalogue
- Black-box behavioural comparator for user-supplied model outputs
- Governed decision-case evaluator for DIIaC artifacts
- DIIaC activity feed with metadata-only receipts
- DIIaC learning metrics report for supervised-learning readiness
- Hash-verified advisory evaluation artifacts
- Visual artifact rendering for M2 coordinate packets

M2 analysis modes:
- White-box hidden-state analysis when M2 controls the model and can access activations.
- Black-box behavioural comparison when outputs come from closed/API models and hidden states are unavailable.
- Governed case evaluation for DIIaC artifacts, separating narrative body from JSON scaffolding.
- Cross-model comparison uses derived metrics only, not raw coordinate alignment.

M2 metrics and signals:
- Prompt or intent coverage
- Lexical drift
- Governance salience
- Evidence salience
- Uncertainty salience
- Recommendation intensity
- Pairwise disagreement
- Scaffold ratio
- Weak governance signal
- Assertive-without-evidence warning
- Duplicate-output and prompt-echo concerns
- White-box bridge strength and topology signals

M2 boundaries:
- M2 is advisory only.
- M2 does not verify factual correctness.
- M2 does not verify evidence quality or policy compliance.
- M2 does not approve, reject, or certify DIIaC decisions.
- M2 does not override evidence gates, policy gates, or human approval.
- Raw latent coordinates are comparable within an adapter/run family, not directly across unrelated models.
- Black-box adapters do not claim hidden-state access.
- M2 learning must remain metadata-only or redacted by default unless a separate governed approval permits more.

## DIIaC + M2 Closed Loop

Target loop:
1. DIIaC captures structured human intent.
2. DIIaC routes through model, prompt, and policy choices.
3. DIIaC produces governed decision artifacts and signed packs.
4. DIIaC exports an M2 evaluation case.
5. M2 performs white-box or black-box advisory analysis.
6. Humans review the DIIaC decision artifacts and M2 signals.
7. Human outcomes are labelled as accepted, rejected, amended, or inconclusive.
8. DIIaC and M2 use those labels to improve prompts, routes, evidence flow, thresholds, and benchmark packs.

Minimum useful DIIaC-to-M2 evaluation case:
- Structured intent summary
- AIP/KRA identifiers and schema versions
- Policy pack and risk class
- Evidence manifest summaries and hashes where available
- Model/provider and prompt template versions for each route
- One or more route outputs
- Human outcome label once review is complete

Safe public explanation:
M2 helps DIIaC notice whether a route or output preserved governance language,
evidence obligations, uncertainty, and human-gate signals. That makes prompt and
route changes easier to test before they become production habits.

## MSquared Voice Rules For These Products

Prefer:
- "governed decision artifact"
- "evidence-bound"
- "signed, replayable decision pack"
- "human accountability"
- "advisory signal"
- "governance salience"
- "evidence salience"
- "route drift"
- "review signal, not approval signal"

Avoid:
- "DIIaC proves truth"
- "DIIaC certifies compliance"
- "DIIaC approves decisions autonomously"
- "M2 reads every model's internals"
- "M2 proves model intent"
- "M2 validates factual correctness"
- "M2 replaces human review"
- "M2 overrides DIIaC"

When in doubt, explain the split:
- DIIaC is the control plane for the decision.
- M2 is the advisory lens on model and route behaviour.
- Human review is the authority boundary.
