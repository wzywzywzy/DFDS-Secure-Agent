# Blake's 30s slot — taxonomy slide version

Better fit for Blake's role than a single-email walkthrough:
**a one-slide map of the attack landscape**, then hand-off to Marat
who will show ONE of these caught live.

This way:
- You cover **all 9** attacks without spending air time on each.
- Marat's live-demo email is no longer "the only attack we showed"
  — it becomes "the example from family X".
- The slide is reusable for Q&A: every attack category has a place
  on screen.

---

## The slide

**Title:** *"What attackers actually try"*

**Body — a 5-row table:**

| Attack family            | What the attacker does                                        | Examples in our 9 |
|--------------------------|---------------------------------------------------------------|-------------------|
| **Prompt injection**     | "Ignore previous instructions" / fake system blocks / hidden in quoted reply / inside pasted OCR | poison_01, poison_02, poison_08 |
| **Authority pressure**   | Fake CEO escalation, "skip the human", 15-min SLA threat      | poison_07         |
| **Unauthorized action**  | Piggyback on a legit request, or modify someone else's booking | poison_03, poison_04 |
| **Out-of-scope / exfil** | "List all bookings for X" / "Book me a hotel"                 | poison_05, poison_06 |
| **Identity fraud**       | Sender claims to be a known customer from a different domain  | poison_09         |

**Footer (small):** *"Plus 124 additional adversarial emails our
team generated — HackAPrompt + Lakera Gandalf + AgentDojo + memory
poisoning by Qi"*

**Visual cue:** colour-code the family names. Red = directly attacks
the LLM (row 1), Orange = attacks the human (row 2), Yellow =
attacks policy (row 3), Brown = attacks data (row 4), Grey = attacks
the gateway (row 5). The whole slide is then a heatmap of where
attacks aim.

---

## Spoken script — tight version (≈75 words ≈ 27s)

> "Our nine starter emails fall into **five attack families**.
>
> *[scan the slide left-to-right]*
>
> Prompt injection. Authority pressure. Unauthorized actions.
> Out-of-scope or data exfiltration. And identity fraud —
> sending from the wrong domain.
>
> Each family targets a different layer: the LLM, the human, the
> policy, the data, the gateway.
>
> **No single defense catches all five.**
>
> Marat will show next how the architecture handles them in depth."

---

## Spoken script — longer version (≈100 words ≈ 35-38s if you have the air)

> "Our nine starter emails fall into five attack families.
>
> *[point to row 1]* Three try **direct prompt injection** —
> 'ignore previous instructions' and variants, sometimes hidden
> in a quoted reply or pasted OCR.
>
> *[row 2]* One uses **authority pressure** — a fake CEO
> escalation with a fifteen-minute SLA threat.
>
> *[row 3]* Two attempt **unauthorized actions** — piggybacking
> malicious requests on a legitimate one, against bookings the
> sender doesn't own.
>
> *[row 4]* Two are **out-of-scope or exfiltration** — 'book me
> a hotel', 'list every booking for this customer'.
>
> *[row 5]* And one is **identity fraud** — wrong domain.
>
> No single defense catches all five. Marat?"

---

## Why this beats picking one email for Blake's slot

| Single-email walkthrough | Taxonomy slide |
|---|---|
| Visceral, but covers 1/9 of the corpus | Covers 9/9 in 30s |
| Audience remembers the email | Audience remembers the **map** — useful in Q&A |
| Repeats whatever Marat shows in live demo | Sets up Marat's demo as "an example from family 1" |
| 30s feels light if Marat is the deep dive | 30s feels structural — you're the brief, he's the dive |

Marat's live demo then **picks one row** from your slide and
explodes it into detail. Cleaner division of labour.

---

## Delivery notes

- The first time you point to a row, the audience will read it.
  **Don't read the cell aloud word-for-word** after — paraphrase.
- The single most important sentence is **"No single defense
  catches all five."** Slow down on it. It's the bridge to Marat.
- If the room laughs at "book me a hotel" — let them. Then keep
  moving.
- Watch the room: if their eyes stay on the slide longer than
  4 seconds per row, drop a sentence. The slide is doing your job.

---

## Suggested colour palette for the slide

If you're using Anthropic-style or DFDS-style brand colours, map the
families like this:

```
row 1 — Prompt injection      → deep red       (LLM target)
row 2 — Authority pressure    → orange         (human target)
row 3 — Unauthorized action   → amber          (policy target)
row 4 — Out-of-scope / exfil  → muted brown    (data target)
row 5 — Identity fraud        → cool grey      (gateway target)
```

A small footnote at the bottom explains the colour code:
*"Colour shows what the attacker is targeting."*

---

## Hand-off line to Marat

> "...how the architecture handles them in depth. **Marat?**"

If your delivery slowed and you're at 32-33s, drop the words "in
depth" — same meaning, half a second saved.
