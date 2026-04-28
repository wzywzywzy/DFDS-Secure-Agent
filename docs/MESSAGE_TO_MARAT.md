# Message draft — to Marat (Discord DM or email)

Two versions: short (Discord) and long (email/follow-up).

---

## Version A — Short Discord DM

> Hey Marat! Spent the evening looking at your repo — really like the
> Kong + Ollama + redaction setup, that's a much cleaner production
> shape than what I had.
>
> I built a parallel solution that's strong in different places:
> email preprocessing (NFKC / zero-width / homoglyph / base64), an
> anti-hallucination check that forces the LLM to cite an exact
> email substring, 12 extra poison emails generated from 3 OSS
> attack datasets, and a Streamlit Scoreboard page.
>
> Want to merge? My proposal: your repo stays the source of truth,
> I push 5 small PRs onto a fork, and we present together.
> I drafted a full alignment doc here:
> https://github.com/wzywzywzy/DFDS-Secure-Agent/blob/main/docs/ALIGNMENT.md
>
> Got 5 min to chat tomorrow morning?

---

## Version B — Longer email / Notion message

> Subject: Merging our two DFDS hackathon solutions?
>
> Hi Marat,
>
> I've been working on the same DFDS Secure Agent challenge in
> parallel with you — repo at https://github.com/wzywzywzy/DFDS-Secure-Agent.
> Our two solutions have very different strengths and I think
> merging them gets us a notably stronger submission than either
> alone.
>
> **What you built that I didn't:**
> - Kong AI Gateway with prompt-guard / decorator / proxy plugins —
>   directly addresses the sponsor angle
> - Late-binding redaction (sensitive fields → tokens before LLM,
>   rehydrated after) — directly addresses one of the four phrases
>   in Martin's brief
> - `/score` endpoint diffing current.csv vs expected.csv — the
>   literal evaluation criterion
> - Working FastAPI + Ollama stack with `make dev` one-shot startup
>
> **What I built that you didn't:**
> - Email preprocessing layer (NFKC normalization, zero-width
>   character stripping, base64 decode-and-flag, homoglyph
>   detection) — catches a class of attacks (e.g. Cyrillic-i in
>   "ignore previous") that regex deny-lists alone miss
> - `reason_quote` anti-hallucination anchor — the LLM must cite an
>   exact email substring for every proposed change; we drop any
>   change whose quote can't be verified. Kills a class of
>   fabricated-action attacks at near-zero cost
> - Extended red-team set: 12 additional poison emails generated
>   from HackAPrompt + Lakera Gandalf + AgentDojo patterns, with a
>   manifest CSV mapping each to dataset / family / expected defense
>   layer
> - Architecture & demo docs: PLAN.md, DESCRIPTION.md, 6 screenshots
>   walking through the Streamlit Scoreboard / Queue / Decision
>   Detail / Audit Log pages
>
> **Proposed merge:**
> Your repo as source of truth. I open 5 small, review-friendly PRs:
>
> 1. Drop in the 12 extended poison emails + red_team adapter
>    (no logic conflicts)
> 2. Add preprocessing layer (NFKC / zero-width / base64 /
>    homoglyph) before your `parse_email_file`
> 3. Add `reason_quote` requirement to the Kong prompt decorator
>    + verification pass in `kong_client.py`
> 4. Add a `/scoreboard` route + HTML view (mirrors the headline
>    metrics from my Streamlit version)
> 5. Drop in PLAN.md / DESCRIPTION.md / screenshots and rewrite the
>    top-level README
>
> Full plan with division of work, timeline, and 6 questions to
> settle on a quick call:
> https://github.com/wzywzywzy/DFDS-Secure-Agent/blob/main/docs/ALIGNMENT.md
>
> I'm happy to do all 5 PRs as the contributor; you stay maintainer
> of `main`. Should take ~3 hours of focused work spread over two
> days.
>
> If you'd rather we submit separately or you want a different
> division of labor, totally fine — let me know either way.
>
> Could we do a 5-minute call tomorrow morning to settle the
> repo-of-record / branch strategy / demo machine / speaker roles?
>
> Thanks!
> — wangziyi

---

## What to NOT say in the message

- Don't lead with "your README is just the challenge brief" — that's
  true but reads as a dig.
- Don't quote the false-approval scoreboard from our repo without
  context — Marat hasn't run it on his side and the comparison can
  feel like a win/loss frame.
- Don't share the actual OpenRouter API key in any chat. (Already
  exposed once; needs rotation regardless.)
- Don't promise to do PR-3 (reason_quote) before showing him a
  prototype works — it's the most invasive change to his code.
