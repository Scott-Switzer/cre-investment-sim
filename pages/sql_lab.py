from __future__ import annotations

import streamlit as st
import pandas as pd


def show():
    st.title("5 · SQL Lab")
    st.caption("Query the analytical dataset in DuckDB. SELECT only inside the app.")

    from src.data.duckdb import DuckDBBackend
    db = DuckDBBackend()
    try:
        tables = db.list_tables()
        st.subheader("Available tables")
        st.dataframe({"table": tables}, hide_index=True, use_container_width=True)

        with st.expander("Table schemas"):
            for t in tables:
                st.markdown(f"**{t}**")
                try:
                    sch = db.table_schema(t)
                    st.dataframe(sch, hide_index=True, use_container_width=True)
                except Exception as e:
                    st.caption(f"schema error: {e}")

        st.markdown("---")
        st.subheader("Query console (SELECT / WITH / SHOW / DESCRIBE / EXPLAIN only)")
        if "sql_input" not in st.session_state:
            st.session_state.sql_input = ""
        default_sql = st.session_state.get("sql_default", "SELECT property_id, type, submarket, asking_price, current_noi, going_in_cap, occupancy FROM properties ORDER BY going_in_cap LIMIT 10;")
        sql = st.text_area("SQL query", value=default_sql, height=140, key="sql_input")
        st.session_state.sql_default = sql

        col_run, col_examples = st.columns([1, 2])
        with col_run:
            st.info("This in-app console blocks mutations. To run arbitrary SQL, use the `data/processed/real605.duckdb` file with DuckDB CLI / DBeaver / python.")
            if st.button("Run query", use_container_width=True):
                try:
                    res = db.safe_query(sql)
                    st.dataframe(res, use_container_width=True, height=360)
                    st.caption(f"Rows returned: {len(res)} · Query: {sql[:80]}...")
                except PermissionError as e:
                    st.error(f"Blocked: {e}")
                except Exception as e:
                    st.error(f"Query error: {e}")

        with col_examples:
            st.subheader("Example tasks (not answered automatically)")
            tasks = db.example_tasks()
            for i, t in enumerate(tasks, 1):
                with st.expander(f"Task {i}: {t['task']}"):
                    st.code(t["query"], language="sql")
                    if st.button(f"Load task {i}", key=f"sql_task_{i}"):
                        st.session_state.sql_input = t["query"]
                        st.rerun()

        st.markdown("---")
        st.subheader("Persistent DuckDB file")
        st.markdown(
            "A persistent DuckDB file is written to `data/processed/real605.duckdb`. Students can query it externally:\n"
            "```\n"
            "duckdb data/processed/real605.duckdb\n"
            "```\n"
            "Then run any SQL, including analytical queries and joins."
        )
        st.download_button(
            "Download DuckDB file",
            data=open("data/processed/real605.duckdb", "rb").read(),
            file_name="real605.duckdb",
            mime="application/octet-stream",
            use_container_width=True,
        )

    finally:
        db.close()

    st.markdown("---")
    st.link("?valuation=1", label="→ Next: Valuation Lab", use_container_width=True)
