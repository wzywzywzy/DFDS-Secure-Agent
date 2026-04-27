"""Streamlit approval UI + Scoreboard.

Three tabs:
  • Scoreboard - headline numbers, where each attack was caught
  • Queue      - list of pending decisions, click to inspect
  • Detail     - one email's full pipeline trace + approve/reject

Run with:
    streamlit run src/ui/app.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src.pipeline.stage2_scan import INJECTION_PHRASES, SUSPICIOUS_TOKENS


RESULTS_PATH = ROOT / "audit_logs" / "latest_results.json"

st.set_page_config(
    page_title="DFDS Secure Agent",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------
@st.cache_data
def load_results() -> dict:
    if not RESULTS_PATH.exists():
        return {"summaries": [], "headline": {}}
    return json.loads(RESULTS_PATH.read_text())


def reload_results() -> None:
    load_results.clear()


# ------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------
RISK_COLOR = {"low": "#2e7d32", "medium": "#ef6c00", "high": "#c62828"}
TRUST_COLOR = {
    "internal": "#1b5e20",
    "matched":  "#2e7d32",
    "unknown":  "#757575",
    "lookalike": "#ef6c00",
    "mismatch": "#c62828",
}
OUTCOME_BADGE = {
    "auto":         ("AUTO", "#2e7d32"),
    "needs_human":  ("HUMAN", "#1565c0"),
    "blocked":      ("BLOCKED", "#c62828"),
    "rejected":     ("REJECTED", "#c62828"),
}


def badge(text: str, color: str) -> str:
    return (
        f"<span style='background:{color};color:white;padding:2px 8px;"
        f"border-radius:6px;font-weight:600;font-size:0.85em;'>{text}</span>"
    )


def highlight_email(body: str) -> str:
    """Wrap injection phrases in red highlights for the rendered email."""
    out = body
    for phrase in INJECTION_PHRASES + SUSPICIOUS_TOKENS:
        try:
            out = re.sub(
                phrase if phrase.startswith("\\") or "(" in phrase else re.escape(phrase),
                lambda m: f"<mark style='background:#ffcdd2;color:#b71c1c;'>{m.group(0)}</mark>",
                out, flags=re.IGNORECASE | re.MULTILINE,
            )
        except re.error:
            pass
    return out.replace("\n", "<br/>")


def stage_pill(stage: int | None) -> str:
    if stage is None:
        return badge("PASSED", "#2e7d32")
    return badge(f"BLOCKED @ STAGE {stage}", "#c62828")


# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------
data = load_results()
summaries = data.get("summaries", [])
headline = data.get("headline", {})

st.title("DFDS Secure Agent — Carrier Support PoC")

if not summaries:
    st.warning("No evaluation results yet.")
    st.code("python tests/run_evaluation.py", language="bash")
    st.stop()

if st.button("↻ Reload latest results"):
    reload_results()
    st.rerun()

tab_score, tab_queue, tab_detail, tab_audit = st.tabs(
    ["📊 Scoreboard", "📥 Queue", "🔎 Decision Detail", "📜 Audit Log"]
)


# ───────── Scoreboard ─────────
with tab_score:
    h = headline
    legit_pass = h.get("legit_pass", 0)
    total_legit = h.get("total_legit", 1)
    poison_block = h.get("poison_block", 0)
    total_poison = h.get("total_poison", 1)
    false_approvals = h.get("false_approvals", 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Legit passed", f"{legit_pass}/{total_legit}",
              f"{100*legit_pass/total_legit:.0f}%")
    c2.metric("Poison blocked", f"{poison_block}/{total_poison}",
              f"{100*poison_block/total_poison:.0f}%")
    c3.metric("False approvals", false_approvals,
              delta_color="inverse" if false_approvals == 0 else "normal")
    avg_ms = sum(s.get("wall_ms", 0) for s in summaries) / max(len(summaries), 1)
    c4.metric("Avg latency", f"{avg_ms:.0f} ms")

    st.divider()

    # Where each attack was caught
    st.subheader("Defense layers — where attacks were caught")
    poison_summaries = [s for s in summaries if s["category"] != "legit"]
    stage_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for s in poison_summaries:
        stg = s.get("blocked_at_stage")
        if stg:
            stage_counts[stg] = stage_counts.get(stg, 0) + 1
        else:
            # Not blocked — counted as "reached human review"
            stage_counts[5] = stage_counts.get(5, 0) + 1
    df = pd.DataFrame(
        {
            "stage": [
                "1 — Preprocess",
                "2 — Input scan",
                "3 — LLM refusal",
                "4 — Authorization",
                "5 — Reached human",
            ],
            "count": [stage_counts.get(i, 0) for i in range(1, 6)],
        }
    )
    st.bar_chart(df, x="stage", y="count")

    # Per-category outcome breakdown
    st.subheader("Per-category outcomes")
    rows = []
    for cat in ["legit", "poison", "extended"]:
        cs = [s for s in summaries if s["category"] == cat]
        outcomes = {"auto": 0, "needs_human": 0, "blocked": 0, "rejected": 0}
        for s in cs:
            outcomes[s["outcome"]] = outcomes.get(s["outcome"], 0) + 1
        rows.append({"category": cat, **outcomes, "total": len(cs)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ───────── Queue ─────────
with tab_queue:
    st.subheader("Decision Queue")
    queue_df = pd.DataFrame([
        {
            "file": Path(s["source"]).name,
            "category": s["category"],
            "sender": s["sender"],
            "trust": s["sender_trust"],
            "scan": f"{s['scan_verdict']} ({s['scan_score']})",
            "decision": s["decision"],
            "outcome": s["outcome"],
            "blocked@": s.get("blocked_at_stage") or "—",
            "n_changes": len(s["changes"]),
        }
        for s in summaries
    ])
    st.dataframe(queue_df, use_container_width=True, hide_index=True)


# ───────── Decision detail ─────────
with tab_detail:
    options = [Path(s["source"]).name for s in summaries]
    chosen = st.selectbox("Email", options, key="detail_pick")
    s = next(x for x in summaries if Path(x["source"]).name == chosen)

    out_label, out_color = OUTCOME_BADGE[s["outcome"]]
    st.markdown(
        f"### {Path(s['source']).name} &nbsp; "
        f"{badge(out_label, out_color)} &nbsp; "
        f"{stage_pill(s.get('blocked_at_stage'))}",
        unsafe_allow_html=True,
    )

    left, mid, right = st.columns([1.4, 1.0, 0.9])

    # Original email with highlights
    with left:
        st.markdown("#### Original email")
        body = Path(s["source"]).read_text(encoding="utf-8")
        st.markdown(
            f"<div style='font-family:monospace;font-size:0.86em;line-height:1.5;"
            f"border:1px solid #ddd;padding:8px;border-radius:6px;background:#fafafa;'>"
            f"{highlight_email(body)}</div>",
            unsafe_allow_html=True,
        )

    # Proposed actions + risk badges
    with mid:
        st.markdown("#### AI-proposed changes")
        if not s["changes"]:
            st.info("No changes proposed (extraction refused or empty).")
        for c in s["changes"]:
            risk_color = RISK_COLOR.get(c["risk"], "#757575")
            ok_badge = badge("AUTHORIZED" if c["authorized"] else "REJECTED",
                             "#2e7d32" if c["authorized"] else "#c62828")
            st.markdown(
                f"**{c['booking']}** &nbsp; {badge(c['risk'].upper(), risk_color)} &nbsp; {ok_badge}<br/>"
                f"<code>{c['field']} → {c['new_value']}</code>",
                unsafe_allow_html=True,
            )
            if c["reasons"]:
                st.markdown(
                    "<small style='color:#c62828;'>✗ "
                    + "<br/>✗ ".join(c["reasons"])
                    + "</small>",
                    unsafe_allow_html=True,
                )
            if c["flags"]:
                st.markdown(
                    "<small style='color:#ef6c00;'>⚠ "
                    + "<br/>⚠ ".join(c["flags"])
                    + "</small>",
                    unsafe_allow_html=True,
                )
            if c.get("owner_email"):
                st.caption(f"booking owner: {c['owner_email']}")
            st.divider()

    # Authorization summary + actions
    with right:
        st.markdown("#### Authorization")
        trust = s["sender_trust"]
        st.markdown(
            f"sender trust: {badge(trust.upper(), TRUST_COLOR.get(trust, '#757575'))}",
            unsafe_allow_html=True,
        )
        st.metric("trust score", f"{s['trust_score']:.2f}")
        st.metric("scan score (injection)", f"{s['scan_score']:.2f}")

        if s.get("scan_matches"):
            st.markdown("**Matched patterns:**")
            for m in s["scan_matches"]:
                st.code(m, language="text")
        if s.get("scan_notes"):
            st.markdown("**Preprocessor notes:**")
            for n in s["scan_notes"]:
                st.markdown(f"- {n}")

        if s.get("block_reason"):
            st.error(s["block_reason"])

        st.divider()
        st.markdown("#### Decide")
        col_a, col_r, col_q = st.columns(3)
        col_a.button("✓ Approve", disabled=s["outcome"] == "blocked",
                     use_container_width=True, key=f"appr_{chosen}")
        col_r.button("✗ Reject", use_container_width=True, key=f"rej_{chosen}")
        col_q.button("? Ask sender", use_container_width=True,
                     key=f"ask_{chosen}")
        st.caption("(buttons are demo-only — wire to executor in prod)")


# ───────── Audit log ─────────
with tab_audit:
    st.subheader("Audit log")
    log_dir = ROOT / "audit_logs"
    log_files = sorted(log_dir.glob("run-*.jsonl"), reverse=True)
    if not log_files:
        st.info("no audit log files yet")
    else:
        chosen_log = st.selectbox("file", [f.name for f in log_files])
        path = log_dir / chosen_log
        lines = path.read_text(encoding="utf-8").splitlines()
        st.caption(f"{len(lines)} audit records")
        for ln in lines[-200:]:
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                st.text(ln)
                continue
            with st.expander(
                f"{rec['ts'][11:19]} · {rec['stage']} · run={rec['run_id']}"
            ):
                st.json(rec["payload"])
