"""
Simple Streamlit dashboard for ClawGold news database.
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(os.getenv("NEWS_DB_PATH", "data/news.db"))


def load_count(conn: sqlite3.Connection, table_name: str) -> int:
    cursor = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def load_recent_news(conn: sqlite3.Connection, limit: int = 20) -> pd.DataFrame:
    query = """
        SELECT title, source, symbol, category, published_at, sentiment
        FROM news_articles
        ORDER BY published_at DESC
        LIMIT ?
    """
    return pd.read_sql_query(query, conn, params=(limit,))


def load_recent_sentiment(conn: sqlite3.Connection, limit: int = 50) -> pd.DataFrame:
    query = """
        SELECT timestamp, symbol, overall_sentiment, weighted_score, news_count
        FROM sentiment_history
        ORDER BY timestamp DESC
        LIMIT ?
    """
    return pd.read_sql_query(query, conn, params=(limit,))


def main() -> None:
    st.set_page_config(page_title="ClawGold Dashboard", page_icon="🦞", layout="wide")
    st.title("ClawGold Dashboard")
    st.caption(f"Database: {DB_PATH}")

    if not DB_PATH.exists():
        st.error(f"Database file not found: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    try:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("News Articles", load_count(conn, "news_articles"))
        col2.metric("AI Research", load_count(conn, "ai_research"))
        col3.metric("Market Events", load_count(conn, "market_events"))
        col4.metric("Sentiment Rows", load_count(conn, "sentiment_history"))

        st.subheader("Recent News")
        st.dataframe(load_recent_news(conn), use_container_width=True)

        st.subheader("Recent Sentiment")
        sentiment_df = load_recent_sentiment(conn)
        st.dataframe(sentiment_df, use_container_width=True)

        if not sentiment_df.empty:
            chart_df = sentiment_df.copy()
            chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"], errors="coerce")
            chart_df = chart_df.dropna(subset=["timestamp"]).sort_values("timestamp")
            chart_df = chart_df.set_index("timestamp")
            st.line_chart(chart_df[["overall_sentiment", "weighted_score"]])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
