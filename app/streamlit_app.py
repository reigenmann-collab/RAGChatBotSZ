"""
PM4 demo interface - the citizen-facing widget plus the caseworker's view.

The split screen is the point of the demo. The left column is what a citizen
would see on the municipal portal. The right column is what the pilot needs to
show the Traffic Department and the Governance Board: which signals produced the
routing decision, whether the coverage check fired, and what the caseworker
would receive on an escalation.

Visual design intentionally echoes gemeindeschwyz.ch (the actual corpus source)
rather than a generic chatbot skin, so a demo to the department or the
Governance Board reads as "this could sit on our portal" rather than "this is a
developer tool". Colours and type are taken from the site's own compiled CSS
(main.*.css custom properties), not eyeballed from a screenshot:
  --icms-gemeinde-bootstrap-primary:   #e10a12  (site red)
  --icms-gemeinde-bootstrap-secondary: #050924  (site dark navy)
  body font: Source Sans Pro (also Streamlit's own default font)
  wordmark/heading font: Barlow

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from google.genai import errors as genai_errors

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

st.set_page_config(page_title="Auskunfts-Assistent Strassenverkehr - PM4", layout="wide")

RED = "#e10a12"
NAVY = "#050924"

DECISION_STYLE = {
    "answer": ("Automatisch beantwortet", "#1c7a3c", "#e7f5ec"),
    "escalate_confidence": ("Eskaliert - Vertrauenswert unter Schwelle", "#a15c00", "#fff4e0"),
    "escalate_coverage": ("Eskaliert - Deckungsprüfung REQ-11", "#a15c00", "#fff4e0"),
    "hard_route": ("Hart geroutet - kein Antwortversuch", RED, "#fdeaea"),
}

EXAMPLES = [
    "Was kostet eine Gewerbeparkkarte in der Gemeinde Schwyz?",
    "Wie lange darf ich beim Hinterdorf parkieren?",
    "Gibt es in der Gemeinde Schwyz Anwohnerparkkarten für Privatpersonen?",
    "Was kostet eine Parkkarte für Mitarbeitende der Gemeinde?",
    "Ich habe eine Busse fürs Parkieren erhalten und möchte Einsprache erheben.",
    "Wie melde ich mein Auto beim Strassenverkehrsamt an?",
]


def inject_css() -> None:
    # A blank line inside this block ends Streamlit's markdown "raw HTML block"
    # parsing early (CommonMark rule), so everything after it gets rendered as
    # literal text instead of being read as CSS. The blank lines below are kept
    # for source readability and stripped before rendering.
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@600;700;800&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )
    css = f"""
        :root {{
            --gs-red: {RED};
            --gs-navy: {NAVY};
        }}

        /* ---- site-style top bar --------------------------------------- */
        .gs-topbar {{
            display: flex; align-items: center; gap: 1.25rem;
            padding: .75rem 1.25rem; margin: -1rem -1rem 0 -1rem;
            background: #fff; border-bottom: 1px solid #eee;
        }}
        .gs-menu-badge {{
            background: var(--gs-red); color: #fff; font-weight: 700;
            font-family: Barlow, sans-serif; letter-spacing: .04em;
            padding: .5rem .9rem; border-radius: 2px; font-size: .85rem;
            white-space: nowrap;
        }}
        .gs-wordmark {{ line-height: 1.05; }}
        .gs-wordmark .gs-line1 {{
            font-family: Barlow, sans-serif; font-weight: 600; font-size: .78rem;
            letter-spacing: .12em; color: #444; text-transform: uppercase;
        }}
        .gs-wordmark .gs-line2 {{
            font-family: Barlow, sans-serif; font-weight: 800; font-size: 1.35rem;
            letter-spacing: .08em; color: var(--gs-red); text-transform: lowercase;
        }}
        .gs-spacer {{ flex: 1; }}
        .gs-navlink {{
            font-family: Barlow, sans-serif; font-weight: 700; font-size: .7rem;
            letter-spacing: .08em; color: var(--gs-navy); text-transform: uppercase;
            text-decoration: none; padding: 0 .5rem;
        }}
        .gs-pilot-badge {{
            background: var(--gs-navy); color: #fff; font-family: Barlow, sans-serif;
            font-weight: 700; font-size: .72rem; letter-spacing: .08em;
            padding: .55rem .9rem; text-transform: uppercase;
        }}

        /* ---- breadcrumb -------------------------------------------------- */
        .gs-breadcrumb {{
            padding: .6rem 1.25rem; margin: 0 -1rem 1.25rem -1rem;
            background: #f8f9fa; border-bottom: 1px solid #eee;
            font-size: .82rem; color: #555;
        }}
        .gs-breadcrumb b {{ color: var(--gs-navy); }}
        .gs-breadcrumb .sep {{ color: var(--gs-red); margin: 0 .35rem; }}

        /* ---- section headings with the site's red accent bar ------------ */
        .gs-h1 {{
            font-family: Barlow, sans-serif; font-weight: 800; font-size: 2.1rem;
            color: var(--gs-navy); margin: 0 0 .15rem 0;
        }}
        .gs-h1-sub {{ color: #666; font-size: .95rem; margin-bottom: 1.4rem; }}
        .gs-section {{
            display: flex; align-items: center; gap: .6rem; margin: 1.4rem 0 .6rem 0;
        }}
        .gs-section .bar {{ width: 5px; height: 1.15rem; background: var(--gs-red); }}
        .gs-section .label {{
            font-family: Barlow, sans-serif; font-weight: 700; font-size: 1.05rem;
            color: var(--gs-navy); text-transform: none;
        }}

        /* ---- decision chip ------------------------------------------------ */
        .gs-chip {{
            display: inline-block; font-family: Barlow, sans-serif; font-weight: 700;
            font-size: .78rem; letter-spacing: .04em; text-transform: uppercase;
            padding: .35rem .8rem; border-radius: 3px; margin-bottom: .6rem;
        }}

        /* ---- source list, styled like the site's "Dokumente" table ------- */
        .gs-doclist {{ border-top: 1px solid #eee; margin-top: .3rem; }}
        .gs-docrow {{
            display: flex; align-items: center; justify-content: space-between;
            gap: 1rem; padding: .65rem 0; border-bottom: 1px solid #eee;
        }}
        .gs-docrow a {{ color: var(--gs-red); text-decoration: none; font-weight: 600; }}
        .gs-docrow a:hover {{ text-decoration: underline; }}
        .gs-doctype {{ color: #888; font-size: .78rem; margin-left: .4rem; }}
        .gs-docbadge {{
            border: 1.5px solid var(--gs-red); color: var(--gs-red);
            font-family: Barlow, sans-serif; font-weight: 700; font-size: .68rem;
            letter-spacing: .05em; text-transform: uppercase;
            padding: .3rem .7rem; border-radius: 3px; white-space: nowrap;
        }}
        .gs-docbadge.muted {{ border-color: #ccc; color: #999; }}

        /* ---- escalation card ---------------------------------------------- */
        .gs-card {{
            background: #f8f9fa; border-left: 4px solid var(--gs-navy);
            padding: 1rem 1.2rem; border-radius: 0 3px 3px 0; margin: .6rem 0;
        }}
        .gs-card h4 {{
            font-family: Barlow, sans-serif; font-weight: 700; color: var(--gs-navy);
            margin: 0 0 .4rem 0; font-size: 1rem;
        }}

        /* ---- restyle Streamlit's own widgets to match the site ------------ */
        div[data-testid="stButton"] button {{
            font-family: Barlow, sans-serif; font-weight: 700; letter-spacing: .02em;
            border-radius: 3px;
        }}
        div[data-testid="stButton"] button[kind="secondary"] {{
            background: #fff; color: var(--gs-red); border: 1.5px solid var(--gs-red);
        }}
        div[data-testid="stButton"] button[kind="secondary"]:hover {{
            background: var(--gs-red); color: #fff;
        }}
        div[data-testid="stButton"] button[kind="primary"] {{
            background: var(--gs-red); border-color: var(--gs-red); text-transform: uppercase;
        }}
        section[data-testid="stSidebar"] {{ border-right: 1px solid #eee; }}
        """
    css_no_blank_lines = "\n".join(line for line in css.splitlines() if line.strip())
    st.markdown(f"<style>\n{css_no_blank_lines}\n</style>", unsafe_allow_html=True)


def top_bar() -> None:
    st.markdown(
        """
        <div class="gs-topbar">
            <div class="gs-menu-badge">≡ MENÜ</div>
            <div class="gs-wordmark">
                <div class="gs-line1">Gemeinde</div>
                <div class="gs-line2">schwyz</div>
            </div>
            <div class="gs-spacer"></div>
            <a class="gs-navlink" href="#" onclick="return false;">INDEX</a>
            <a class="gs-navlink" href="#" onclick="return false;">BERICHT PM4</a>
            <div class="gs-pilot-badge">Pilot · PM4</div>
        </div>
        <div class="gs-breadcrumb">
            🏠&nbsp; Home <span class="sep">›</span> Einwohnerservices
            <span class="sep">›</span> Umwelt und Mobilität
            <span class="sep">›</span> <b>Auskunfts-Assistent (Pilot)</b>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(
        f'<div class="gs-section"><div class="bar"></div><div class="label">{label}</div></div>',
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def _load():
    from config import load_config
    from pipeline import answer_query
    from retrieve import index_stats
    from routing import active_threshold

    return load_config(), answer_query, index_stats, active_threshold


def sidebar(cfg, stats, threshold) -> bool:
    """Renders the sidebar and returns whether the pilot inspection view
    (the right-hand "Prüfansicht") should be shown. Defaults to on; a citizen
    demo can switch it off to show only what a real citizen would see."""
    st.sidebar.markdown(
        '<div style="font-family:Barlow,sans-serif;font-weight:800;font-size:1.1rem;'
        'color:#050924;">PM4 — Departementaler Pilot</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.caption("Verkehr / Strassenverkehr, Gemeinde Schwyz")

    show_inspection = st.sidebar.toggle(
        "Prüfansicht anzeigen",
        value=True,
        help="Blendet die rechte Spalte (Signale, Deckungsprüfung, Eskalation) "
        "aus - für eine Demo, die nur zeigt, was Bürgerinnen und Bürger sehen.",
    )
    st.sidebar.divider()

    st.sidebar.markdown("**Index**")
    st.sidebar.write(
        f"{stats['document_count']} Dokumente, {stats['chunk_count']} Chunks  \n"
        f"Dokumenttypen: {', '.join(stats['doc_types_indexed'])}  \n"
        f"Embeddings: `{stats['embedding_model']}` ({stats['dimension']}d)"
    )

    st.sidebar.markdown("**Routing**")
    calibrated = cfg["confidence"].get("calibrated_threshold")
    st.sidebar.metric("Schwellenwert", f"{threshold:.3f}")
    if calibrated is None:
        st.sidebar.warning(
            "Platzhalter-Schwelle. Der kalibrierte Wert entsteht erst aus "
            "`eval/calibrate.py` (Bericht 4.3)."
        )
    else:
        st.sidebar.success("Kalibrierter Schwellenwert aus dem Testset.")

    w = cfg["confidence"]["weights"]
    st.sidebar.caption(
        f"C = {w['s1_retrieval_strength']}·S1 + {w['s2_grounding']}·S2 "
        f"+ {w['s3_self_assessment']}·S3"
    )
    st.sidebar.caption(
        "Prototyp. Auskunft ohne Rechtsverbindlichkeit. "
        "Die Antwortgenerierung nutzt eine externe API - REQ-07 (Schweizer "
        "Infrastruktur) ist im Prototyp bewusst nicht erfüllt."
    )
    return show_inspection


def render_signals(result) -> None:
    signals = result.get("signals")
    if not signals:
        st.info(
            "Für hart geroutete Anfragen werden keine Signale berechnet - "
            "es wird bewusst kein Antwortversuch unternommen (Bericht 4.4)."
        )
        return

    cols = st.columns(4)
    cols[0].metric("S1 Retrieval", f"{signals['s1_retrieval_strength']:.3f}")
    cols[1].metric("S2 Grounding", f"{signals['s2_grounding']:.3f}")
    cols[2].metric("S3 Selbsteinschätzung", f"{signals['s3_self_assessment']:.3f}")
    cols[3].metric(
        "C gesamt",
        f"{signals['composite']:.3f}",
        delta=f"{signals['composite'] - result['threshold']:+.3f} zur Schwelle",
    )

    claims = result.get("claims") or []
    if claims:
        with st.expander(f"Faktenprüfung: {len(claims)} Aussage(n)"):
            for claim in claims:
                icon = {"gedeckt": "✓", "teilweise": "~", "nicht_gedeckt": "✗"}.get(
                    claim.get("verdict"), "?"
                )
                st.markdown(
                    f"{icon} **{claim.get('verdict')}** — {claim.get('claim')}  \n"
                    f"<span style='color:#888;font-size:0.85em'>"
                    f"{', '.join(claim.get('evidence_chunk_ids') or []) or 'keine Belegstelle'}"
                    f"</span>",
                    unsafe_allow_html=True,
                )


def render_coverage(result) -> None:
    cov = result.get("coverage")
    if not cov:
        return
    if cov["passed"]:
        st.success(f"REQ-11 Deckungsprüfung bestanden. {cov['reason']}")
    else:
        st.warning(f"REQ-11 Deckungsprüfung nicht bestanden. {cov['reason']}")
    st.caption(
        f"Erkannte Themen: {', '.join(cov['topics']) or 'keine'} · "
        f"Gefundene Dokumenttypen: {', '.join(cov['retrieved_doc_types']) or 'keine'}"
    )


def render_escalation(result) -> None:
    summary = result.get("escalation_summary")
    if not summary:
        return
    section("Eskalation an die Sachbearbeitung (REQ-03)")
    rows = [f"<h4>{summary['betreff']}</h4><p>{summary['anliegen']}</p>"]
    rows.append(f"<p style='color:#555;font-size:.88rem'><b>Grund:</b> {summary['eskalationsgrund']}</p>")
    if summary.get("gefundene_grundlagen"):
        rows.append("<p style='margin-bottom:.2rem'><b>Gefundene Grundlagen:</b></p><ul>")
        rows += [f"<li>{item}</li>" for item in summary["gefundene_grundlagen"]]
        rows.append("</ul>")
    if summary.get("offene_punkte"):
        rows.append("<p style='margin-bottom:.2rem'><b>Zu klären:</b></p><ul>")
        rows += [f"<li>{item}</li>" for item in summary["offene_punkte"]]
        rows.append("</ul>")
    st.markdown(f'<div class="gs-card">{"".join(rows)}</div>', unsafe_allow_html=True)
    if summary.get("summary_error"):
        st.error(
            "Zusammenfassung technisch fehlgeschlagen. Die Rohanfrage wird trotzdem "
            "in die Fallablage geschrieben - ein technischer Fehler darf eine "
            "Bürgeranfrage nie verlieren (Bericht 7.4)."
        )


def render_sources(sources: list[dict]) -> None:
    section("Quellen")
    rows = ['<div class="gs-doclist">']
    for src in sources:
        badge = "ZITIERT" if src["cited"] else "GEFUNDEN"
        badge_class = "" if src["cited"] else "muted"
        rows.append(
            '<div class="gs-docrow">'
            f'<div><a href="{src["url"]}" target="_blank">{src["doc_title"]}</a>'
            f'<span class="gs-doctype">{src["doc_type"]} · Ähnlichkeit {src["similarity"]:.3f}</span></div>'
            f'<div class="gs-docbadge {badge_class}">{badge}</div>'
            "</div>"
        )
    rows.append("</div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def main() -> None:
    inject_css()
    top_bar()

    cfg, answer_query, index_stats, active_threshold = _load()

    try:
        stats = index_stats()
    except Exception:
        st.error("Kein Index gefunden. Bitte zuerst `python src/ingest.py` und "
                 "`python src/chunk_index.py` ausführen.")
        return

    show_inspection = sidebar(cfg, stats, active_threshold())

    st.markdown('<div class="gs-h1">Auskunfts-Assistent Strassenverkehr</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="gs-h1-sub">Gemeinde Schwyz · Prototyp des departementalen Pilots (PM4)</div>',
        unsafe_allow_html=True,
    )

    st.write("**Beispielfragen**")
    cols = st.columns(3)
    for i, example in enumerate(EXAMPLES):
        if cols[i % 3].button(example, key=f"ex{i}", use_container_width=True):
            st.session_state.query = example

    if "query" not in st.session_state:
        st.session_state.query = EXAMPLES[0]

    query = st.text_input("Ihre Frage", key="query")
    submitted = st.button("Frage stellen", type="primary")

    if not (submitted or query):
        return
    if not query.strip():
        return

    try:
        with st.spinner("Suche in den Dokumenten der Gemeinde Schwyz ..."):
            result = answer_query(query)
    except RuntimeError as exc:
        # Our own errors (missing key, malformed model response) - the message
        # is already actionable, safe to show as-is.
        st.error(str(exc))
        return
    except genai_errors.ServerError as exc:
        # Transient 5xx from the model provider, still failing after llm.py's
        # own retry pass. Not our bug - shown as a retry prompt, not a crash,
        # so a live demo degrades gracefully instead of dumping a traceback.
        st.error(
            "Der Dienst ist momentan überlastet und antwortet nicht. Bitte "
            "versuchen Sie es in wenigen Sekunden erneut."
        )
        print(f"[gemini ServerError] {exc}")  # visible in Streamlit Cloud logs
        return
    except genai_errors.ClientError as exc:
        # 4xx: bad/expired key, quota exhausted, disallowed request. Retrying
        # would not help, so this is worded differently from the ServerError
        # case above.
        st.error(
            "Der Dienst konnte die Anfrage nicht verarbeiten (Konfigurations- "
            "oder Kontingentproblem). Bitte informieren Sie die Projektleitung."
        )
        print(f"[gemini ClientError] {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - last-resort safety net for a live demo
        st.error(
            "Es ist ein unerwarteter Fehler aufgetreten. Bitte versuchen Sie "
            "es erneut oder wenden Sie sich an die Projektleitung."
        )
        print(f"[unexpected error] {type(exc).__name__}: {exc}")
        return

    columns = st.columns([3, 2]) if show_inspection else [st.container()]
    left = columns[0]

    with left:
        section("Antwort für die Bürgerin oder den Bürger")
        label, fg, bg = DECISION_STYLE.get(result["decision"], (result["decision"], NAVY, "#eee"))
        st.markdown(
            f'<span class="gs-chip" style="color:{fg};background:{bg};">{label}</span>',
            unsafe_allow_html=True,
        )
        st.write(result["answer"])

        # The suppressed draft and the caseworker-facing escalation summary are
        # pilot-inspection content - a real citizen never sees either, so both
        # stay behind the same toggle as the right-hand "Prüfansicht".
        if show_inspection and result["escalate"] and result.get("draft_answer"):
            with st.expander("Nicht ausgelieferter Entwurf (nur zur Prüfung im Pilot)"):
                st.write(result["draft_answer"])

        if result["sources"]:
            render_sources(result["sources"])

    if show_inspection:
        with columns[1]:
            section("Prüfansicht (Pilot)")
            st.caption(f"Begründung: {result['reason']}")
            render_signals(result)
            render_coverage(result)
            st.metric("Antwortzeit", f"{result['latency_seconds']:.2f} s",
                      delta=f"{result['latency_seconds'] - 5:+.2f} s zum Ziel (REQ-06)",
                      delta_color="inverse")
            render_escalation(result)


if __name__ == "__main__":
    main()
