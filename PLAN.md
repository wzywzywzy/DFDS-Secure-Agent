# DFDS Secure Agentic AI — Project Plan

## 1. The Goal (one sentence)

Build a 5-stage governance pipeline that takes carrier-support emails,
extracts structured booking changes via Gemini, and routes them to a
human approver — blocking prompt injection, cross-account access,
data exfiltration, and unauthorized actions before any LLM call has
real-world side effects.

## 2. What "done" looks like

| Demo artifact | What it shows |
|---|---|
| Working pipeline | 6/6 legit emails produce the expected `phoenix_bookings_expected.csv` diff |
| Working pipeline | 9/9 main poison + 12/12 extended poison are blocked or quarantined; **0** false approvals |
| Streamlit approval UI | Side-by-side: original email + AI's structured proposal + risk reasons |
| Scoreboard page | Live numbers, latency, cost, where each attack was caught |
| Audit log viewer | One JSONL line per stage transition, queryable |
| `promptfoo` red-team report (Day 3) | OWASP-LLM-style HTML report |

## 3. Architecture

```
EMAIL (.txt)
   │
   ▼
Stage 1: Preprocess  (pure Python, no LLM)
   • parse headers (From / Subject / Body)
   • NFKC unicode normalization
   • strip zero-width characters
   • strip quoted reply chains  ("-----Original Message-----", ">>>", etc.)
   • strip HTML/Markdown comments
   • detect & decode base64-looking blocks (flag, don't auto-execute)
   │
   ▼
Stage 2: Input Scan  (LLM Guard if installed, else regex fallback)
   • prompt injection classifier (Meta Prompt Guard 2 via LLM Guard)
   • banned-substring deny-list ("ignore previous", "system:", etc.)
   • PII detection (Presidio if installed)
   ⚠️ on fail → quarantine queue, no LLM call
   │
   ▼
Stage 3: LLM Intent Extraction  (Gemini via OpenRouter, single call)
   • system prompt: "you are an EXTRACTOR, not an executor"
   • email body wrapped in <untrusted_email> tags
   • Pydantic-enforced output schema: ProposedAction
   • mandatory `reason_quote` field (LLM must cite the email line that
     justifies the change — anti-hallucination)
   │
   ▼
Stage 4: Authorization & Risk  (pure rules)
   • sender domain ↔ booking owner email domain match
   • risk classification (LOW / MED / HIGH) per field
   • cross-account check (sender entitled to modify each referenced booking?)
   • numeric-change anomaly (>50% delta → flag)
   • forbidden-action rejection (cannot set hold fields from email)
   │
   ▼
Stage 5: Human Approval UI  (Streamlit)
   • show original email with malicious spans highlighted
   • show ProposedAction card with risk badge
   • show authorization verdict + why
   • [Approve] [Reject] [Ask Sender for Clarification]
   │
   ▼
Stage 6: Executor  (pure CSV writer)
   • write phoenix_bookings_current.csv ONLY after Approve
   • record decision in audit log
```

**Audit log bus** runs across all stages — one JSONL line per stage,
recording inputs, outputs, scanner scores, decisions.

## 4. Tech stack (frozen)

| Layer | Choice | Why |
|---|---|---|
| LLM | Gemini via OpenRouter | What the hackathon provides |
| LLM client | LiteLLM | One-line provider swap, stable streaming |
| Structured output | Pydantic v2 | Type-safe, plays well with Gemini JSON mode |
| Input scan | LLM Guard (`protectai/llm-guard`) + regex fallback | Wraps Meta Prompt Guard 2; MIT license |
| API | FastAPI | Lightweight, easy to wire to Streamlit |
| UI | Streamlit | 30-line approval pages, live charts |
| Storage | CSV (the "Phoenix" mock DB) | What the starter pack uses |
| Audit | JSONL files | No infra, easy to grep/visualize |
| Red-team | promptfoo + own extended set + manual | Dataset-backed coverage |

## 5. Defense layers vs. the 5 hackathon themes

| Theme (from README.md) | Where we address it |
|---|---|
| **a) Prompt-injection defence** | Stages 1 + 2 + 3 (XML isolation in prompt) |
| **b) Intent scoping** | Stage 4 sender↔BookingEmail check |
| **c) Action risk classification** | Stage 4 risk dictionary, drives UI color + queue |
| **d) Human-in-the-loop that the human uses** | Stage 5 highlighting, "Ask sender" 3rd option |
| **e) Sender authenticity** | Stage 4 trust score (DFDS domain > matched domain > lookalike > unknown) |

## 6. Repository layout

```
starter-pack/
├── PLAN.md                          ← this file
├── README.md                        ← run instructions, architecture diagram
├── requirements.txt
├── .env.example                     ← OPENROUTER_API_KEY=
├── .gitignore                       ← .env, audit_logs/, __pycache__
│
├── data_update/                     ← the canonical dataset (with BookingEmail)
├── emails/
│   ├── legit/                       ← 6 starter emails
│   ├── poisonous/                   ← 9 starter attacks
│   └── poisonous_extended/          ← 12 generated from OSS datasets
│
├── red_team/                        ← already built — pattern lib + adapter
│
├── src/
│   ├── schemas.py                   ← Pydantic models: ParsedEmail, ProposedAction, ...
│   ├── pipeline/
│   │   ├── stage1_preprocess.py
│   │   ├── stage2_scan.py
│   │   ├── stage3_extract.py
│   │   ├── stage4_authorize.py
│   │   ├── stage5_executor.py
│   │   └── orchestrator.py          ← chains 1→5, writes audit log
│   ├── llm/
│   │   └── client.py                ← OpenRouter call + mock-mode for dev
│   ├── audit/
│   │   └── logger.py
│   └── ui/
│       └── app.py                   ← Streamlit approval + scoreboard
│
├── tests/
│   └── run_evaluation.py            ← runs every email, prints scoreboard
│
└── audit_logs/                      ← JSONL output, one file per run
```

## 7. Build order (the actual plan)

1. **Skeleton** — dirs + requirements + .env.example + .gitignore
2. **Schemas** — `ParsedEmail`, `ScanResult`, `ProposedAction`, `AuthorizationResult`, `PipelineDecision`
3. **Stage 1** — pure functions, fully unit-testable, no external deps
4. **Stage 2** — LLM Guard if installed, else regex fallback (so the project runs out of the box)
5. **Stage 3** — LiteLLM client with `MOCK_LLM=true` env switch (so it works without the API key while developing)
6. **Stage 4** — rules engine; reads BookingEmail column for the entitlement check
7. **Stage 5** — CSV writer (only invoked after approval)
8. **Orchestrator** — wires 1→5, writes audit JSONL
9. **Evaluation script** — loops over `emails/*` and renders a scoreboard table to stdout + JSON
10. **Streamlit UI** — three tabs: queue / decision detail / scoreboard
11. **End-to-end smoke** — every legit email produces correct CSV diff; every poison produces empty diff
12. **README** — run instructions, demo script, attack-coverage table

## 8. Risk register (what could fail)

| Risk | Mitigation |
|---|---|
| LLM Guard install is heavy / slow | Provide regex fallback that runs without LLM Guard installed |
| OpenRouter Gemini latency / cost spikes | Mock-mode by default in dev; cache responses keyed by email hash |
| Gemini structured output unreliable | Pydantic strict mode + `reason_quote` validation; one retry on parse fail |
| Streamlit CSS is ugly under time pressure | Use a clean default theme, no custom CSS |
| Demo machine has no network | All evaluation can run with `MOCK_LLM=true` |

## 9. Demo script (5 minutes)

1. **0:00–0:30** Open the Scoreboard page. Read the headline numbers.
2. **0:30–1:30** "Architecture in one slide" — point at each Stage in
   the pipeline.
3. **1:30–3:00** Walk through ONE poison email end-to-end in the UI.
   Show: original → highlighted suspicious spans → AI proposal →
   authorization verdict → why-rejected card.
4. **3:00–3:45** Side-by-side: same email through "naive baseline" vs
   our system. Naive approves, ours blocks.
5. **3:45–4:30** Open `promptfoo` HTML report — point at OWASP LLM
   Top 10 categories all green/yellow.
6. **4:30–5:00** "Honest limits" slide — what we don't defend, next
   steps.

## 10. Out of scope (deliberately)

- Real DKIM/SPF/DMARC verification (we approximate via From: domain)
- Multi-turn conversation memory (each email is processed independently)
- Real Phoenix DB integration (CSV stand-in)
- User accounts / auth on the approver UI (one approver, no login)
- Production observability (Prometheus etc.)

These get one slide at the end as "future work."
