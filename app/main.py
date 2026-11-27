"""Swiss public-transport assistant: Streamlit prototype (UC-060).

    uv run streamlit run app/main.py                 # processed data (data/processed)
    uv run streamlit run app/main.py -- --sample     # synthetic fixture

Query parameters preset a question and the view, e.g.
    ?hub=Olten&arr_line=S3&time_band=midday&day=all&margin=4&view=answer
All texts and numbers come from the Answer via `assistant.render` (pure, tested); no LLM is
called at runtime.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data import AppData, cached_llm_answer, lines_at, load  # noqa: E402
from urban_computing.assistant.contract import Question  # noqa: E402
from urban_computing.assistant.engine import (  # noqa: E402
    NoDataError,
    answer,
    connection_segment,
    hub_arrivals,
    own_arrivals,
    personal_slack,
)
from urban_computing.assistant.render import answer_view_model, chatbot_view_model  # noqa: E402

VIEWS = {"answer": "Answer", "official": "Official view", "chatbot": "Chatbot view"}
DAYS = {
    "all": "All days",
    "weekday": "Weekdays",
    "monday": "Mondays",
    "friday": "Fridays",
    "weekend": "Weekends",
}
BADGE_COLORS = {"green": "#1a7f37", "amber": "#b26a00", "red": "#c62828", "gray": "#6e7781"}


def _args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="use the synthetic fixture")
    return ap.parse_known_args(sys.argv[1:])[0]


@st.cache_resource(show_spinner="Loading data …")
def _data(sample: bool) -> AppData:
    return load(sample)


def _param(name: str, default: str | None = None) -> str | None:
    return st.query_params.get(name, default)


def _pick(label: str, options: list[str], value: str | None, fmt=str, key: str | None = None):
    index = options.index(value) if value in options else 0
    return st.selectbox(label, options, index=index, format_func=fmt, key=key)


def _badge(label: str, color: str) -> str:
    c = {"orange": "#b26a00", "green": "#1a7f37", "red": "#c62828"}.get(color, "#6e7781")
    return (
        f"<span style='background:{c};color:white;padding:0.3em 0.9em;border-radius:1em;"
        f"font-size:1.4em;font-weight:600'>{label}</span>"
    )


def _form(data: AppData) -> tuple[Question | None, str]:
    cfg = data.config
    with st.sidebar:
        st.header("Your connection")
        hub = _pick("Station (hub)", list(cfg["connections"]["hubs"]), _param("hub"))
        lines = lines_at(data, hub) or ["(no data)"]
        arr = _pick("Arriving train (line)", lines, _param("arr_line"))
        deps = ["any"] + lines_at(data, hub, "dep_line")
        dep = _pick("Departing train (line)", deps, _param("dep_line", "any"))
        bands = list(cfg["time_bands"])
        band = _pick(
            "Time of day", bands, _param("time_band", "morning_peak"), lambda b: b.replace("_", " ")
        )
        day = _pick("Days", list(DAYS), _param("day", "all"), DAYS.get)
        margin = st.slider(
            "Your time to change (minutes)", 2.0, 15.0, float(_param("margin", "4")), 0.5
        )
        st.caption("Stations and times come from the study configuration.")
    if arr == "(no data)":
        return None, "No connections are available for this station."
    q = Question(
        hub=hub,
        arr_line=arr,
        dep_line=None if dep == "any" else dep,
        time_band=band,
        weekday_group=day,
        margin_min=margin,
    )
    return q, ""


def _answer_view(vm: dict) -> None:
    st.markdown(_badge(vm["decision"]["label"], vm["decision"]["color"]), unsafe_allow_html=True)
    st.caption(vm["question"])
    st.subheader("Why")
    for e in vm["explanations"]:
        st.markdown(e["sentence"])
        if e["truth"] is None:
            st.caption(f"Measured share, {e['n_text']}.")
        else:
            st.markdown(e["bar_html"], unsafe_allow_html=True)
            st.caption(f"truth {e['truth']}")
            cov = f", coverage {e['coverage']}" if e["coverage"] else ""
            st.caption(f"{e['n_text']}{cov}")
    if vm["fallback_note"]:
        st.info(vm["fallback_note"])


def _official_view(vm: dict) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Your view")
        st.markdown(
            _badge(vm["decision"]["label"], vm["decision"]["color"]), unsafe_allow_html=True
        )
        st.caption("Based on your time to change.")
        for s in vm["own_sentences"]:
            st.markdown(s)
    with right:
        st.subheader("Official view")
        if vm["official"] is None:
            st.write("No official punctuality figure for this train.")
        else:
            off = vm["official"]
            st.markdown(_badge(off["label"], off["color"]), unsafe_allow_html=True)
            st.caption("Punctual = less than 3 minutes late; your time to change is ignored.")
            for s in off["sentences"]:
                st.markdown(s)


def _chatbot_view(data: AppData, q: Question) -> None:
    cached = cached_llm_answer(q)
    if cached is None:
        st.write(
            "No cached chatbot answer for this question. The prototype never calls a "
            "language model; answers exist only for questions of the evaluation set."
        )
        return
    from urban_computing.llm.checkers import check
    from urban_computing.llm.parser import load_lexicon, parse_output

    qid, raw = cached
    seg = connection_segment(q, data.connections)
    own = own_arrivals(hub_arrivals(q, data.arrivals, data.config), q)
    min_transfer = float(data.config["connections"]["min_transfer_minutes_default"])
    values = {
        "arrival_delay_minutes": own["delay_min"].astype("float64").to_numpy(),
        "time_band": own["time_band"].to_numpy(),
        "weekday": own["weekday"].to_numpy(),
        "connection_slack_minutes": personal_slack(seg, q.margin_min, min_transfer),
        "connection_slack_minutes.time_band": seg["time_band"].to_numpy(),
        "connection_slack_minutes.weekday": seg["weekday"].to_numpy(),
    }
    claims = parse_output(qid, raw, load_lexicon())
    vm = chatbot_view_model(raw, [check(c, values, data.vocab, data.config) for c in claims])
    st.markdown(vm["text"])
    for c in vm["claims"]:
        color = BADGE_COLORS[c["badge"]]
        value = c["truth"] if c["truth"] is not None else c["note"]
        st.markdown(
            f"<span style='color:{color}'>●</span> {c['text']} — {value}", unsafe_allow_html=True
        )


def main() -> None:
    args = _args()
    st.set_page_config(page_title="Swiss public-transport assistant", layout="wide")
    st.title("Is my connection reliable?")
    st.caption("Swiss public-transport assistant · explanations from fuzzy linguistic summaries")
    data = _data(args.sample)
    if data.sample:
        st.warning("Synthetic sample data (test fixture), not real measurements.")
    q, problem = _form(data)
    view = _param("view", "answer")
    keys = list(VIEWS)
    choice = st.radio(
        "View",
        keys,
        index=keys.index(view) if view in keys else 0,
        format_func=VIEWS.get,
        horizontal=True,
        label_visibility="collapsed",
    )
    if q is None:
        st.write(problem)
        return
    try:
        ans = answer(q, data.connections, data.arrivals, data.vocab, data.config)
    except NoDataError as err:
        st.write(f"Not enough data to answer: {err}")
        return
    vm = answer_view_model(ans)
    if choice == "answer":
        _answer_view(vm)
    elif choice == "official":
        _official_view(vm)
    else:
        _chatbot_view(data, q)
    st.divider()
    st.caption(vm["footer"])


main()
