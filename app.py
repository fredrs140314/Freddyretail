import streamlit as st
import pandas as pd
import plotly.express as px

from backend import (
    get_sitemap_urls,
    count_brand_mentions,
    estimate_traffic,
)

st.set_page_config(page_title="Brand Domain Analyzer", layout="wide")

st.title("📊 Brand Domain Analyzer")
st.write(
    "Analyze how many products/pages a domain has for specific brands and compare it to estimated domain traffic."
)

# Sidebar Inputs
st.sidebar.header("Inputs")

domain = st.sidebar.text_input("Domain", "ica.se")
brand_input = st.sidebar.text_area(
    "Brands (one per line)",
    "Coca-Cola\nPepsi\nRed Bull",
)

run_button = st.sidebar.button("Run Analysis")

if run_button:
    brands = [brand.strip() for brand in brand_input.split("\n") if brand.strip()]

    with st.spinner("Fetching sitemap URLs..."):
        urls = get_sitemap_urls(domain)

    if not urls:
        st.error("No URLs found. Check the domain or sitemap.")
    else:
        st.success(f"Found {len(urls)} URLs")

        with st.spinner("Analyzing brand mentions..."):
            results = count_brand_mentions(urls, brands)

        traffic = estimate_traffic(domain)

        df = pd.DataFrame(results)

        st.subheader("📈 Domain Traffic")
        st.metric(label="Estimated Monthly Visits", value=f"{traffic:,}")

        st.subheader("📋 Brand Results")
        st.dataframe(df, use_container_width=True)

        st.subheader("📊 Product/Page Mentions by Brand")
        fig = px.bar(
            df,
            x="Brand",
            y="Mentions",
            title="Brand Mentions on Domain",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("🌍 Traffic vs Brand Presence")

        df["Traffic"] = traffic

        fig2 = px.scatter(
            df,
            x="Traffic",
            y="Mentions",
            size="Mentions",
            hover_name="Brand",
            title="Traffic vs Brand Visibility",
        )

        st.plotly_chart(fig2, use_container_width=True)
