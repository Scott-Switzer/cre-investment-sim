"""
Dataset Downloads — the pre-class half of the game.

This is where a student gets the data they will model BEFORE class. It is part
of the PREP mode; nothing here is available during a timed round.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

PACKET_DIR = Path("student_packet")

FILES = [
    (
        "historical_training.csv",
        "Historical transactions with KNOWN outcomes",
        "Build and validate your model here. Contains realized next-year NOI, "
        "cap rate and value, so you can measure your error before you play.",
    ),
    (
        "game_candidates.csv",
        "The properties the game will offer (no future outcomes)",
        "Every id here is a property the live game can present. Predict all of them. "
        "No future value is exposed — that is the point.",
    ),
    (
        "data_dictionary.csv",
        "Column-by-column documentation",
        "What every column means, its units, and its provenance tag.",
    ),
    (
        "prediction_submission_template.csv",
        "The submission contract you must fill in",
        "One row per candidate property. Upload the finished file at Model Check-In.",
    ),
    (
        "GAME_RULES.md",
        "The rules you are playing under",
        "Rounds, capital, sealed-bid auctions, reserve price, tie-breaks, and how "
        "you win.",
    ),
]


def _read(name: str) -> pd.DataFrame | None:
    path = PACKET_DIR / name
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def show():
    st.title("Dataset Downloads")
    st.caption("Everything you need BEFORE class — build your model outside the game")

    st.markdown(
        """
### The instructional pattern

```
historical data -> you build a model -> predictions + an investment policy
    -> bring it into the live game -> decisions -> realized results -> feedback
```

The game does not build the model for you. It is the **decision environment**;
your model is the **analytical engine**. Keep those two layers separate — that is
the skill this course is after.
"""
    )

    if not PACKET_DIR.exists():
        st.error(
            "Student packet has not been generated yet. Run:\n\n"
            "```bash\npython scripts/build_student_game_packet.py\n```"
        )
        return

    st.markdown("---")
    st.subheader("Files")

    for name, subtitle, description in FILES:
        path = PACKET_DIR / name
        with st.container(border=True):
            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"**{name}**")
                st.caption(subtitle)
                st.markdown(description)
            with col2:
                if path.exists():
                    st.download_button(
                        f"Download {name}",
                        data=path.read_bytes(),
                        file_name=name,
                        mime="text/markdown" if name.endswith(".md") else "text/csv",
                        key=f"dl_{name}",
                        use_container_width=True,
                    )
                    st.caption(f"{path.stat().st_size / 1024:.0f} KB")
                else:
                    st.warning("Not generated yet")

    st.markdown("---")
    st.subheader("Preview")

    candidates = _read("game_candidates.csv")
    historical = _read("historical_training.csv")

    tab1, tab2, tab3 = st.tabs(["Training data", "Game candidates", "Data dictionary"])

    with tab1:
        if historical is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Observations", f"{len(historical):,}")
            c2.metric("Vintages", historical["date"].nunique() if "date" in historical else 0)
            c3.metric("Columns", len(historical.columns))
            st.caption(
                "Outcome columns are the `next_year_*` and `*_realized` fields. "
                "Those are your targets."
            )
            st.dataframe(historical.head(20), use_container_width=True, hide_index=True)
        else:
            st.info("historical_training.csv not found")

    with tab2:
        if candidates is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Candidate properties", f"{len(candidates):,}")
            c2.metric(
                "Total asking price",
                f"${candidates['asking_price'].sum():,.0f}M",
            )
            c3.metric(
                "Avg asking price",
                f"${candidates['asking_price'].mean():,.1f}M",
            )
            st.caption(
                "No future outcome appears here. Everything on this table is "
                "knowable before the game starts."
            )
            st.dataframe(candidates.head(20), use_container_width=True, hide_index=True)
        else:
            st.info("game_candidates.csv not found")

    with tab3:
        dictionary = _read("data_dictionary.csv")
        if dictionary is not None:
            st.dataframe(dictionary, use_container_width=True, hide_index=True)
        else:
            st.info("data_dictionary.csv not found")

    st.markdown("---")
    st.markdown(
        """
### Next steps

1. Model the candidates with whatever tool you like.
2. Produce a `max_bid` for each property — that is where analysis becomes policy.
3. Upload at **Model Check-In**.
4. Review your plan on the **Strategy Card**.
"""
    )


if __name__ == "__main__":
    show()
