# Message draft — to Marat (Discord DM or email)

Three versions:
- **A** — initial outreach, short Discord DM
- **B** — initial outreach, longer email
- **C** — follow-up after running the compat test, with the tarball
  attached or the GitHub link inline. Use this once the compat pack
  exists; it's a much stronger opener than A.

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

---

## Version C — Follow-up Discord DM (with the compat pack ready)

Use this once you've handed him the tarball / link. It leads with
work he can verify in 3 commands, which is much stronger than asking
him to read an alignment doc cold.

> Hey Marat — I built a small compat-test pack against your stack so
> you can see how it does on a wider attack set without changing any
> of your code. It mirrors your repo layout, drops in next to it, and
> takes 3 commands:
>
> ```
> tar -xzf compat_pack.tar.gz
> TARGET=. compat_pack/setup.sh
> python compat_pack/tests/run_against_marat.py
> ```
>
> What's in it:
> – 12 mismatched-sender attacks + 12 matched-sender ("compromised
>   account") stress attacks, all generated from HackAPrompt /
>   Lakera Gandalf / AgentDojo patterns
> – A live runner that POSTs each one to your `/process` endpoint
> – An offline runner that imports your modules in-process if your
>   stack isn't up
>
> One heads-up while I was setting it up: your `data/` is still on
> the original starter-pack CSV, which doesn't have the
> `BookingEmail` column Martin added on Discord on 2026-04-23. As a
> result your `entitlement.check_entitlement` is rejecting every
> external sender right now (because `booking["BookingEmail"]` is
> always empty). `setup.sh` installs the updated CSV with a `.bak`
> backup so you can revert.
>
> Headline of running this on your modules locally: 33/33 poison
> blocked, 0 leaks. The interesting bit is that 4 attack types —
> base64-smuggle, homoglyph (Cyrillic Іgnοre), zero-width
> (Igno​re), fabricated `approved_by:` headers — bypass your Kong
> regex and only get caught downstream by happenstance. Full
> writeup is in `docs/COMPAT_REPORT.md` in our repo.
>
> If you have a few minutes after running it, I'd love to align on
> a merge plan: your repo as source of truth, I push small PRs on a
> fork. Doc with the proposal here:
> https://github.com/wzywzywzy/DFDS-Secure-Agent/blob/main/docs/ALIGNMENT.md
>
> Pack is at: https://github.com/wzywzywzy/DFDS-Secure-Agent/tree/main/compat_pack
> (or I can DM you the tarball directly, ~22 KB).

---

## Version C-mini — single-paragraph version for #general

For when you don't want to drop a wall of text:

> Built a 24-email compat test against your `/process` endpoint —
> mirrors your repo layout, 3 commands to run, doesn't touch your
> code. Pack:
> https://github.com/wzywzywzy/DFDS-Secure-Agent/tree/main/compat_pack
> · headline: 33/33 poison blocked, 4 attacks bypass Kong regex
> (base64 / homoglyph / zero-width / fabricated `approved_by:`
> headers) and only get caught by chance downstream. Heads-up:
> your `data/` is missing the `BookingEmail` column Martin added on
> Discord — `setup.sh` installs the updated CSV with a `.bak`. Full
> writeup in `docs/COMPAT_REPORT.md`. Want to chat about merging?

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
