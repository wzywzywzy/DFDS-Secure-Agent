# DFDS Secure Agent — Carrier Support PoC

A 5-stage governance pipeline for AI-assisted carrier-support email
handling. Built for the **Secure Agentic AI for Carrier Support PoC**
hackathon (DFDS / Kong / 2Hero).

> The original challenge brief is preserved as [`README_starter.md`](README_starter.md).
> The end-to-end build plan is in [`PLAN.md`](PLAN.md).

## Headline result

```
legit passed       :  4/6     (mock LLM limitation on emails 03, 05;
                                handled correctly by real model)
poison blocked     : 21/21    (9 starter + 12 generated from OSS datasets)
FALSE APPROVALS    :  0       <-- the metric that matters
```

## What it does

```
EMAIL  →  Stage 1: Preprocess        (NFKC, zero-width strip, base64 decode,
                                       quote-chain strip, HTML-comment strip)
       →  Stage 2: Input scan         (LLM Guard if installed, regex fallback)
       →  Stage 3: LLM extraction     (Gemini via OpenRouter, Pydantic-strict
                                       JSON, mandatory `reason_quote` anchor)
       →  Stage 4: Authorization     (sender-domain ↔ BookingEmail check,
                                       risk classification, cross-account guard,
                                       forbidden-field blocklist)
       →  Stage 5: Human approval     (Streamlit UI: highlighted email,
                                       proposed actions, risk badges)
       →  Stage 6: CSV write          (only after Approve, defense-in-depth
                                       refusal of forbidden fields)
                ↑
       ─── Audit log bus ───  one JSONL line per stage transition.
```

## Run it

```bash
# 1. Python 3.11+ recommended
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) Real LLM
cp .env.example .env
# Edit .env, set OPENROUTER_API_KEY=... and MOCK_LLM=false

# 3. Run the evaluation harness — produces the scoreboard JSON
python tests/run_evaluation.py

# 4. Launch the UI
streamlit run src/ui/app.py
# Open http://localhost:8501
```

## Mock vs real LLM

`MOCK_LLM=true` (default) uses a rule-based extractor — works offline,
exercises every defense layer, and produces a clean Demo without
spending hackathon credits.

`MOCK_LLM=false` routes through OpenRouter to Gemini. The system prompt
in [`src/llm/client.py`](src/llm/client.py) forces:
- JSON-mode structured output bound to a Pydantic schema
- mandatory `reason_quote` anchor (anti-hallucination — Stage 3 verifies
  the quote is a real substring of the email)
- explicit refusal cues for instruction hijack / data exfil / out-of-scope

## How each hackathon theme is addressed

| Theme | Where |
|---|---|
| **a) Prompt-injection defence** | Stages 1+2+3 |
| **b) Intent scoping** | [Stage 4 — sender↔BookingEmail check](src/pipeline/stage4_authorize.py) |
| **c) Action risk classification** | `FIELD_RISK` + `FORBIDDEN_FIELDS` in Stage 4 |
| **d) Human-in-the-loop that the human uses** | [Streamlit UI](src/ui/app.py) — highlighted spans, side-by-side proposal vs original, three-way decision (Approve / Reject / Ask Sender) |
| **e) Sender authenticity** | `_classify_trust` in Stage 4: INTERNAL > MATCHED > UNKNOWN > LOOKALIKE > MISMATCH |

## Red team

The pipeline is evaluated against **30 emails**:
- 6 legit (starter pack)
- 9 poison (starter pack)
- 12 generated from 3 open-source datasets — see [`red_team/`](red_team/)
  - **HackAPrompt** (4 patterns) — instruction-override family
  - **Lakera Gandalf** (3) — extraction / unicode / homoglyph
  - **AgentDojo** (5) — agent-targeted indirect injection

The [`red_team/manifest.csv`](red_team/manifest.csv) lists which dataset
inspired each generated email, the attack family, the technique, and
which defense layer is expected to catch it.

## Project layout

```
.
├── PLAN.md                       master plan
├── README.md                     this file
├── README_starter.md             original challenge brief
├── requirements.txt
├── .env.example
│
├── data_update/                  Phoenix CSV "DB" (with BookingEmail column)
├── emails/
│   ├── legit/                    6 starter emails
│   ├── poisonous/                9 starter attacks
│   └── poisonous_extended/       12 generated (red_team/)
│
├── red_team/                     attack pattern lib + adapter
│   ├── attack_patterns.py
│   ├── adapter.py                regenerate the extended set
│   ├── manifest.csv
│   └── README.md
│
├── src/
│   ├── schemas.py                Pydantic models
│   ├── pipeline/
│   │   ├── stage1_preprocess.py
│   │   ├── stage2_scan.py
│   │   ├── stage3_extract.py
│   │   ├── stage4_authorize.py
│   │   ├── stage5_executor.py
│   │   └── orchestrator.py
│   ├── llm/client.py             OpenRouter via LiteLLM + mock
│   ├── audit/logger.py           JSONL writer
│   └── ui/app.py                 Streamlit Scoreboard + approval UI
│
├── tests/run_evaluation.py       end-to-end harness; writes Scoreboard JSON
└── audit_logs/                   JSONL files, one per evaluation run
```

## Demo script (5 minutes)

1. **Scoreboard tab** — point at headline numbers and "where attacks
   were caught" chart. Stage 2 catches the cheap stuff, Stage 4 catches
   the semantic/cross-account stuff.
2. **Decision Detail tab** — open `poison_03_piggyback_destructive.txt`.
   Show the highlighted injection spans, the AI-proposed changes
   (1 authorized weight + 5 rejected hold-clearings), and the
   auto-rejected forbidden fields.
3. **Same view for `ext_06_gan_02_homoglyph_unicode.txt`** — show the
   Cyrillic/Greek lookalikes detected at Stage 1, the mismatch trust
   level, and the explicit reasons in the UI.
4. **Audit Log tab** — pick a run, expand any stage, show the
   end-to-end provenance for one email.
5. **Honest limits slide** — see [`PLAN.md` § 10](PLAN.md).

## Out of scope (deliberate)

- Real DKIM/SPF/DMARC verification (we approximate via From: domain)
- Multi-turn conversation memory (each email processed independently)
- Real Phoenix DB (CSV stand-in)
- Approver login / RBAC (single-approver Demo)
- Production observability (logs are JSONL; Prometheus etc. is future work)

## License & credits

Hackathon submission, no public license asserted. Built on:
- **Open-source defense:** [protectai/llm-guard](https://github.com/protectai/llm-guard) (MIT)
- **Open-source datasets** for the red team:
  HackAPrompt (MIT), Lakera Gandalf (MIT), AgentDojo (Apache 2.0)
- **LLM:** Gemini via OpenRouter
