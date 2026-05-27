import traceback

import pandas as pd
import plotly.express as px
import streamlit as st

from backend import get_domain_data, normalize_domain


st.set_page_config(page_title="Brand Domain Analyzer", layout="wide")

st.title("📊 Brand Domain Analyzer")
st.write(
    "Analyze how many pages/products mention specific brands across one or several domains, "
    "then compare brand visibility against estimated domain traffic."
)

with st.expander("Debug info"):
    st.write("App loaded successfully. If scanning fails, the error will appear here instead of crashing the app.")

st.sidebar.header("Inputs")

domain_input = st.sidebar.text_area(
    "Domains (one per line)",
    "ica.se\ncoop.se\nwillys.se",
)

brand_input = st.sidebar.text_area(
    "Brands (one per line)",
    "Coca-Cola\nPepsi\nRed Bull",
)

max_urls = st.sidebar.number_input(
    "Max URLs per domain",
    min_value=10,
    max_value=5000,
    value=500,
    step=50,
)

run_button = st.sidebar.button("Run Analysis", type="primary")

if run_button:
    try:
        domains = [
            normalize_domain(domain.strip())
            for domain in domain_input.split("\n")
            if domain.strip()
        ]
        domains = list(dict.fromkeys([d for d in domains if d]))

        brands = [brand.strip() for brand in brand_input.split("\n") if brand.strip()]
        brands = list(dict.fromkeys(brands))

        if not domains:
            st.error("Please enter at least one domain.")
            st.stop()

        if not brands:
            st.error("Please enter at least one brand.")
            st.stop()

        all_results = []
        discovery_rows = []

        for domain in domains:
            st.subheader(f"🌐 {domain}")

            with st.spinner(f"Scanning {domain}..."):
                domain_data = get_domain_data(
                    domain=domain,
                    brands=brands,
                    max_urls=int(max_urls),
                )

            discovery_rows.append(
                {
                    "Domain": domain,
                    "URLs Found": domain_data["urls_found"],
                    "URL Source": domain_data["url_source"],
                    "Estimated Traffic": domain_data["traffic"],
                    "Status": domain_data.get("status", "ok"),
                }
            )

            if domain_data["urls_found"] == 0:
                st.warning(f"No URLs found for {domain}. Try the www version, e.g. www.{domain}.")
                continue

            st.success(
                f"Found {domain_data['urls_found']:,} URLs via {domain_data['url_source']}"
            )

            all_results.extend(domain_data["results"])

        st.divider()

        st.subheader("🧭 URL Discovery Summary")
        discovery_df = pd.DataFrame(discovery_rows)
        st.dataframe(discovery_df, use_container_width=True)

        if not all_results:
            st.error("No usable results found.")
            st.stop()

        df = pd.DataFrame(all_results)

        st.subheader("📋 Brand Results")
        display_df = df.copy()
        display_df["Presence Rate"] = (display_df["Presence Rate"] * 100).round(2).astype(str) + "%"
        st.dataframe(display_df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download results as CSV",
            data=csv,
            file_name="brand-domain-analyzer-results.csv",
            mime="text/csv",
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Domains Analyzed", len(df["Domain"].unique()))
        c2.metric("Brands Analyzed", len(df["Brand"].unique()))
        c3.metric("Total Brand Page Mentions", f"{df['Mentions'].sum():,}")

        st.subheader("📊 Brand Mentions by Domain")
        fig_bar = px.bar(
            df,
            x="Brand",
            y="Mentions",
            color="Domain",
            barmode="group",
            text="Mentions",
            title="Brand Mentions Across Domains",
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(yaxis_title="Pages mentioning brand", xaxis_title="Brand")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("🔥 Brand Presence Heatmap")
        heatmap_df = df.pivot_table(
            index="Brand",
            columns="Domain",
            values="Mentions",
            aggfunc="sum",
            fill_value=0,
        )
        fig_heatmap = px.imshow(
            heatmap_df,
            text_auto=True,
            aspect="auto",
            title="Brand Mentions Heatmap",
            labels=dict(x="Domain", y="Brand", color="Mentions"),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)

        st.subheader("🌍 Traffic vs Brand Presence")
        fig_scatter = px.scatter(
            df,
            x="Traffic",
            y="Mentions",
            size="Mentions",
            color="Domain",
            symbol="Brand",
            hover_name="Brand",
            hover_data={
                "Domain": True,
                "Traffic": ":,",
                "Mentions": ":,",
                "URLs Scanned": ":,",
                "Presence Rate": ":.2%",
            },
            title="Traffic vs Brand Visibility",
        )
        fig_scatter.update_layout(
            xaxis_title="Estimated Monthly Visits",
            yaxis_title="Pages mentioning brand",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    except Exception:
        st.error("The app hit an error, but did not fully crash.")
        st.code(traceback.format_exc())

else:
    st.info("Enter domains and brands in the sidebar, then click **Run Analysis**.")
