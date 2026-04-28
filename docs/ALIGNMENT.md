# Team Alignment — Marat × Wangziyi

Working doc for merging the two parallel solutions for the DFDS Secure
Agentic AI hackathon. Goal: ONE submission that combines the strongest
pieces of both codebases without throwing away work either side has
already invested.

> If you're reading this and haven't seen both repos:
> - Marat: https://github.com/maratart/2026-04-AI-governance-hackathon-DFDS
> - Ours:  https://github.com/wzywzywzy/DFDS-Secure-Agent

## 1. Goal of the merge

Hit **all four** of the literal phrases in Martin's challenge brief —
*per-carrier data isolation, pre/post-LLM redaction, late binding of
sensitive fields, auditability* — while keeping the depth-of-defense
work (preprocessing, anti-hallucination, extended red team) and the
production-shape work (Kong gateway, redaction, scorer, REST API) both
visible to the judges.

## 2. Who's strong at what (honest read)

| Area | Marat | Wangziyi |
|---|---|---|
| Kong AI Gateway wiring | ✅ working with 3 plugins | ❌ docs-only |
| Late binding / token redaction | ✅ `redaction.py` | ❌ missing |
| `/score` CSV diff endpoint | ✅ `scorer.py` | ⚠️ outcome-only |
| Real DB write-back after approve | ✅ `bookings.apply_changes` | ⚠️ stage5_executor unwired |
| Docker + Ollama, no API cost | ✅ `make dev` | ❌ depends on OpenRouter |
| REST API + HTML approval UI | ✅ FastAPI + Jinja2 | ❌ Streamlit only |
| Email preprocessing (NFKC, zero-width, base64, homoglyph) | ❌ only strips `>` | ✅ full layer |
| Anti-hallucination `reason_quote` | ❌ | ✅ verified anchor |
| Extended red team (3 OSS datasets, 12 generated) | ❌ original 9 only | ✅ + manifest CSV |
| PLAN / DESCRIPTION / 6 screenshots | ❌ README is challenge brief | ✅ |
| Mock LLM (offline demo) | ❌ needs Ollama up | ✅ MOCK_LLM=true |

Reading: Marat owns *production shape & literal-brief coverage*;
Wangziyi owns *defense depth, attacker model, evaluator legibility*.
Neither dominates; they're complementary.

## 3. Decision: Marat's repo is the source of truth

Reasons to choose his as base over ours:
- His Docker + Kong + Ollama wiring is the most expensive thing to
  rebuild and the most impressive thing to demo. We don't want to
  redo it.
- His `redaction.py` directly implements the "late binding of sensitive
  fields" requirement from the challenge brief. We don't have an
  equivalent.
- His `/score` endpoint is the literal evaluation criterion.

Reasons not to choose ours as base:
- Our advantage is in modules we can drop in (preprocess, reason_quote,
  red team, docs), not in scaffolding.
- Our Streamlit UI is replaceable; the HTML approval he has works fine.

So: **we work on Marat's repo as a fork, push our differentiators in
as 5 small PRs, and add him as collaborator on our screenshots/docs.**

## 4. Merged architecture (target)

```
EMAIL (.txt)
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ① email_parser.py  +  preprocess.py  ← FROM US       │
│   Marat's parser already strips ">" lines.           │
│   We add NFKC, zero-width strip, base64 decode,      │
│   homoglyph detection on top.                        │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ② entitlement.py  ← MARAT, unchanged                  │
│   Sender-domain ↔ BookingEmail check.                │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ③ redaction.redact()  ← MARAT, unchanged              │
│   Sensitive fields → opaque tokens before LLM.       │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ④ Kong AI Gateway  ← MARAT, unchanged                 │
│   ai-prompt-guard + ai-prompt-decorator + ai-proxy   │
│   → Ollama gemma4 (local, no API cost)               │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ⑤ kong_client.py  + reason_quote check  ← FROM US     │
│   • Add `reason_quote` to LLM JSON schema             │
│   • Verify each proposed change cites a real          │
│     substring of the email body; drop unverifiable.   │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ⑥ redaction.rehydrate()  ← MARAT                      │
│   Token → real value; drop changes targeting          │
│   sensitive fields.                                  │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ⑦ risk.classify()  ← MARAT                            │
│   LOW / MEDIUM / HIGH / BLOCK                        │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ⑧ Approval UI (approval.html)  ← MARAT                │
│   + Scoreboard view  ← FROM US                        │
│   New /scoreboard route renders headline numbers,     │
│   per-stage block chart, naive-vs-defended diff.     │
└──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────┐
│ ⑨ bookings.apply_changes()  ← MARAT                   │
│   Writes back to phoenix_bookings_current.csv.        │
└──────────────────────────────────────────────────────┘

   ── audit_log.jsonl ── event-typed log across all stages
```

What this gets us per challenge theme:

| Theme | Layer that addresses it |
|---|---|
| a) Prompt-injection defense | ① preprocess + ④ Kong prompt-guard + ⑤ reason_quote |
| b) Intent scoping | ② entitlement |
| c) Action risk classification | ⑦ risk.classify |
| d) Human-in-the-loop | ⑧ approval UI + Scoreboard |
| e) Sender authenticity | ② entitlement (domain match) |
| **late binding of sensitive fields** | ③ redact + ⑥ rehydrate |
| **per-carrier data isolation** | ② entitlement |
| **pre/post-LLM redaction** | ③ + ⑥ |
| **auditability** | audit_log.jsonl |

All four literal challenge-brief phrases now show up on the diagram.

## 5. Division of work — 5 PRs to land in Marat's repo

Each PR is small and review-friendly. Order them so the high-impact /
low-conflict ones go first.

### PR-1 · Extended red team (no logic conflicts)
**Owner: Wangziyi** · **Est: 10 min**
- `cp -r emails/poisonous_extended/` → his repo
- `cp -r red_team/` → his repo
- Update `demo.sh` to add 3 sample extended cases
- Update README with the attack-coverage table

### PR-2 · Preprocessing layer
**Owner: Wangziyi** · **Est: 45 min**
- Add `src/app/preprocess.py` with NFKC + zero-width strip + base64
  detect + homoglyph flag. Lift code from our `stage1_preprocess.py`.
- Modify `email_parser.parse_email_file` to call `preprocess()` before
  scanning the body.
- Surface flags (`contained_homoglyph`, `contained_zero_width`,
  `base64_blocks`) in the `ParsedEmail` dataclass and pass them to the
  approval UI for display.

### PR-3 · `reason_quote` anti-hallucination
**Owner: Wangziyi** · **Est: 45 min**
- Modify `ai-prompt-decorator` config in `kong/kong.yml` so the system
  prompt now requires:
  ```
  "changes":[{"field":"","new_value":"","booking_ref":"",
              "reason_quote":"<exact substring of the email body>"}]
  ```
- In `kong_client._validate_structure`, add a quote-verification pass.
  Drop any change whose `reason_quote` is not a normalized-substring
  match of the email body. Surface dropped count in the audit log.
- Add a unit test that the existing 9 poison cases still get caught and
  the 6 legit cases still extract.

### PR-4 · Scoreboard view (HTML)
**Owner: Wangziyi** · **Est: 60 min**
- New route `/scoreboard` in `main.py` that aggregates `/score` +
  `/audit` into:
  - 4 headline metrics (legit pass / poison block / false approvals /
    avg latency)
  - per-stage block-distribution bar chart
  - "naive baseline vs governed" diff sample
- New template `scoreboard.html` that mirrors the visual style of our
  Streamlit screenshots (see `docs/screenshots/01_scoreboard.png`).
- Link from `approval.html` header.

### PR-5 · Documentation pack
**Owner: Wangziyi** · **Est: 30 min**
- Drop our `PLAN.md`, `DESCRIPTION.md`, `docs/screenshots/` into Marat's
  repo unchanged. Update relative paths.
- Rewrite Marat's top-level `README.md` (currently still the original
  challenge brief) into a real project README pointing at PLAN /
  DESCRIPTION / demo.sh.

### Marat's parallel work (no PRs from us)
- Continue tightening Kong prompt-guard patterns from review feedback
- Continue tuning the Ollama prompt for stable JSON output
- Make sure `make dev` works end-to-end on a fresh machine (this is
  the demo machine setup)

## 6. Decisions that need a 5-minute call with Marat

1. **Which repo is the final submission?**
   Proposed: Marat's. He becomes maintainer of `main`. Wangziyi pushes
   PRs from a fork.
2. **License?**
   Currently no LICENSE in either repo. Add `LICENSE` (MIT or
   Apache 2.0) before the submission deadline so a clean fork is OK.
3. **Branch strategy?**
   Proposed: `main` is demo-stable; PR branches like `wzy/preprocess`,
   `wzy/reason-quote`, etc.; Marat reviews and merges.
4. **Demo machine?**
   Whose laptop runs the live demo? Whose Colima/Docker/Ollama is
   fastest to boot? Practice both setups in case one fails.
5. **Speaking roles?**
   Proposed split:
   - Marat (1 min): architecture overview, late binding story
   - Wangziyi (1 min): attacker model + extended red team
   - Together (2 min): live demo (poison_03 piggyback + ext_06
     homoglyph + Scoreboard)
   - Marat closes (30 s): out-of-scope / next steps
6. **Where does our OpenRouter key fit?**
   Probably nowhere — Marat's Ollama path makes it irrelevant.
   We could keep it as a fallback (`MOCK_LLM=false` in our repo)
   but the demo runs Ollama. Don't put the key anywhere committed.

## 7. Timeline (assuming the deadline is in 2-3 days)

| When | What |
|---|---|
| Today, evening | Send Marat the alignment message (template in §8) |
| T+1 morning  | 5-minute call to settle the 6 questions in §6 |
| T+1 day      | PR-1, PR-2, PR-5 land (low-risk, parallelizable) |
| T+2 morning  | PR-3 (reason_quote) lands; full evaluator regression |
| T+2 afternoon| PR-4 (Scoreboard view) lands; demo dress rehearsal |
| T+2 evening  | Run `demo.sh` end-to-end on the demo laptop, capture video as backup |

If the deadline is tighter, drop PR-4 (Scoreboard view) — it's the
nicest-to-have, not the most-essential.

## 8. Message to send Marat (Discord / email)

See `docs/MESSAGE_TO_MARAT.md` for the draft.

## 9. Rejection criteria — when to abort the merge

We back out and submit our own repo separately if:
- Marat doesn't agree to the merge or wants a different division of
  labor we can't accommodate
- Marat's stack genuinely won't run on the demo laptop after 2 hours
  of attempts (Ollama / Colima / model weights are common pain points)
- Two people can't agree on the README structure within 30 minutes —
  in which case we ship two repos with cross-links instead

The point is: this is an offer, not a takeover. If it doesn't fit on
his side, we still have our own clean PoC.
