import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from backend import (
    get_domain_data,
)

st.set_page_config(page_title="Brand Domain Analyzer", layout="wide")

st.title("📊 Brand Domain Analyzer V2")

st.write(
    "Compare brand visibility across multiple domains and compare against estimated organic traffic."
)

# Sidebar
st.sidebar.header("Inputs")

domains_input = st.sidebar.text_area(
    "Domains (one per line)",
    "ica.se\ncoop.se\nwillys.se",
)

brands_input = st.sidebar.text_area(
    "Brands (one per line)",
    "Coca-Cola",
)

run_button = st.sidebar.button("Run Analysis")

if run_button:

    domains = [d.strip() for d in domains_input.split("\n") if d.strip()]
    brands = [b.strip() for b in brands_input.split("\n") if b.strip()]

    if not domains or not brands:
        st.error("Please enter at least one domain and one brand.")
        st.stop()

    all_results = []

    progress = st.progress(0)

    for i, domain in enumerate(domains):

        result = get_domain_data(domain, brands)

        all_results.append(result)

        progress.progress((i + 1) / len(domains))

    df = pd.DataFrame(all_results)

    st.subheader("📋 Results Table")
    st.dataframe(df, use_container_width=True)

    # GRAPH
    st.subheader("📈 Estimated Organic Traffic vs Brand Mentions")

    fig = go.Figure()

    # Brand mentions
    fig.add_trace(
        go.Bar(
            x=df["Domain"],
            y=df["Brand Mentions"],
            name="Pages Mentioning Brand",
        )
    )

    # Total traffic
    fig.add_trace(
        go.Bar(
            x=df["Domain"],
            y=df["Estimated Traffic"],
            name="Total Estimated Traffic",
        )
    )

    fig.update_layout(
        barmode="group",
        xaxis_title="Domains",
        yaxis_title="Estimated Monthly Traffic",
        height=600,
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🔍 Key Insights")

    top_domain = df.sort_values("Brand Mentions", ascending=False).iloc[0]

    st.success(
        f"{top_domain['Domain']} has the highest visibility with "
        f"{top_domain['Brand Mentions']} brand mentions."
    )
