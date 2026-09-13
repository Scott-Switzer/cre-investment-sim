"""
Shared UI fragments.

Kept out of ``pages/`` because Streamlit ignores modules there that do not map to
a page, and this is a reusable renderer rather than a page.
"""

from __future__ import annotations

from src.game.manager import game_stage, stage_steps

_STAGE_CSS = """
<style>
.stage-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin: 6px 0 18px 0;
    padding: 10px 12px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
}
.stage-chip {
    padding: 5px 14px;
    border-radius: 3px;
    font-size: 0.78em;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    background: #edf2f7;
    color: #718096;
    border: 1px solid #e2e8f0;
}
.stage-chip.done {
    background: #f0fff4;
    color: #276749;
    border-color: #9ae6b4;
}
.stage-chip.current {
    background: #1a365d;
    color: #ffffff;
    border-color: #1a365d;
    box-shadow: 0 0 0 2px rgba(26,54,93,0.18);
}
.stage-arrow { color: #cbd5e0; font-size: 0.85em; }
</style>
"""


def render_stage_bar(game_manager, caption: str | None = None) -> None:
    """Render the PRACTICE / ROUND 1..N / DEBRIEF progress strip.

    The instructor's manual transitions are the only clock in the MVP, so this is
    the one place that answers "where are we?" for both the professor and the
    students. Chips before the current one are marked done.
    """
    import streamlit as st

    steps = stage_steps(game_manager)
    current = game_stage(game_manager)

    st.markdown(_STAGE_CSS, unsafe_allow_html=True)

    # Anything up to and including the current stage reads as reached. A stage is
    # "done" once the game has moved past it.
    reached_index = steps.index(current) if current in steps else 0

    chips = []
    for i, step in enumerate(steps):
        if step == current:
            cls = "stage-chip current"
        elif i < reached_index:
            cls = "stage-chip done"
        else:
            cls = "stage-chip"
        chips.append(f'<span class="{cls}">{step}</span>')

    body = '<span class="stage-arrow">›</span>'.join(chips)
    st.markdown(
        f'<div class="stage-bar">{body}</div>',
        unsafe_allow_html=True,
    )
    if caption:
        st.caption(caption)
