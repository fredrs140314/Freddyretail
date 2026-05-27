import traceback

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend import get_domain_product_data, normalize_domain


st.set_page_config(page_title="Brand Product Analyzer", layout="wide")

st.title("🛒 Brand Product Page Analyzer")
st.write(
    "Analyze brand product-page presence across retailer domains and compare it with estimated organic traffic."
)

st.sidebar.header("Inputs")

domain_input = st.sidebar.text_area(
    "Domains (one per line)",
    "ica.se\ncoop.se\nwillys.se\nhemkop.se",
)

brand_input = st.sidebar.text_area(
    "Brands (one per line)",
    "Coca-Cola\nPepsi\nRed Bull",
)

max_urls = st.sidebar.number_input(
    "Max URLs per domain",
    min_value=100,
    max_value=20000,
    value=3000,
    step=100,
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
            st.error("Please add at least one domain.")
            st.stop()

        if not brands:
            st.error("Please add at least one brand.")
            st.stop()

        all_results = []
        summary_rows = []

        for domain in domains:
            st.subheader(f"🌐 {domain}")

            with st.spinner(f"Scanning product pages for {domain}..."):
                domain_data = get_domain_product_data(
                    domain=domain,
                    brands=brands,
                    max_urls=int(max_urls),
                )

            summary_rows.append(
                {
                    "Domain": domain,
                    "Total URLs Found": domain_data["urls_found"],
                    "Likely Product Pages": domain_data["product_urls_found"],
                    "Estimated Traffic": domain_data["traffic"],
                    "URL Source": domain_data["url_source"],
                }
            )

            st.success(
                f"Found {domain_data['product_urls_found']:,} likely product pages from {domain_data['urls_found']:,} URLs"
            )

            all_results.extend(domain_data["results"])

        st.divider()

        summary_df = pd.DataFrame(summary_rows)

        st.subheader("📋 Domain Summary")
        st.dataframe(summary_df, use_container_width=True)

        if not all_results:
            st.warning("No product-page results found.")
            st.stop()

        df = pd.DataFrame(all_results)

        st.subheader("📋 Brand Product Presence")

        display_df = df.copy()
        display_df["Assortment Share"] = (
            (display_df["Assortment Share"] * 100).round(2).astype(str) + "%"
        )
        display_df["Estimated Brand Opportunity"] = display_df[
            "Estimated Brand Opportunity"
        ].map("{:,.0f}".format)
        display_df["Traffic"] = display_df["Traffic"].map("{:,.0f}".format)

        st.dataframe(display_df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="brand-product-analysis.csv",
            mime="text/csv",
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Domains", len(df["Domain"].unique()))
        c2.metric("Brands", len(df["Brand"].unique()))
        c3.metric("Total Product Pages", f"{summary_df['Likely Product Pages'].sum():,}")
        c4.metric("Brand Product Pages", f"{df['Product Pages'].sum():,}")

        st.divider()

        st.subheader("📈 Search Intelligence")

        selected_brand = st.selectbox(
            "Select brand",
            sorted(df["Brand"].unique()),
        )

        brand_df = df[df["Brand"] == selected_brand].copy()
        brand_df = brand_df.sort_values("Traffic", ascending=True)

        coverage_color_map = {
            "High": "#72BF44",
            "Medium": "#F5B700",
            "Low": "#D90429",
        }

        fig_si = go.Figure()

        fig_si.add_trace(
            go.Bar(
                x=brand_df["Domain"],
                y=brand_df["Estimated Brand Opportunity"],
                name=f"{selected_brand} estimated opportunity",
                marker_color="#9ADFE3",
            )
        )

        fig_si.add_trace(
            go.Bar(
                x=brand_df["Domain"],
                y=brand_df["Traffic"],
                name="Total estimated traffic",
                marker_color="#4F5EF7",
            )
        )

        for _, row in brand_df.iterrows():
            fig_si.add_trace(
                go.Scatter(
                    x=[row["Domain"]],
                    y=[row["Traffic"] * 1.04],
                    mode="markers",
                    marker=dict(
                        size=22,
                        color=coverage_color_map.get(row["Coverage"], "#D90429"),
                        line=dict(width=1, color="white"),
                    ),
                    name=f"{row['Coverage']} coverage",
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{row['Domain']}</b><br>"
                        f"Brand: {selected_brand}<br>"
                        f"Coverage: {row['Coverage']}<br>"
                        f"Product pages: {row['Product Pages']}<br>"
                        f"Assortment share: {row['Assortment Share']:.2%}<br>"
                        "<extra></extra>"
                    ),
                )
            )

        fig_si.update_layout(
            title=f"Where {selected_brand} Has the Biggest Opportunity",
            barmode="group",
            height=650,
            xaxis_title="Retailer domains",
            yaxis_title="Estimated organic traffic / opportunity",
            legend_title="Metric",
            margin=dict(l=40, r=40, t=80, b=60),
        )

        st.plotly_chart(fig_si, use_container_width=True)

        st.caption(
            "Coverage dots are based on brand product-page share of the retailer's detected product assortment. "
            "Green = high coverage, yellow = medium coverage, red = low coverage."
        )

        st.divider()

        st.subheader("📊 Brand Product Pages by Domain")

        fig_bar = px.bar(
            df,
            x="Brand",
            y="Product Pages",
            color="Domain",
            barmode="group",
            text="Product Pages",
            title="Brand Product Pages Across Domains",
        )
        fig_bar.update_traces(textposition="outside")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("🥧 Assortment Share by Brand")

        fig_share = px.bar(
            df,
            x="Brand",
            y="Assortment Share",
            color="Domain",
            barmode="group",
            title="Brand Share of Detected Product Assortment",
        )
        fig_share.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig_share, use_container_width=True)

        st.subheader("🌍 Traffic vs Product Presence")

        fig_scatter = px.scatter(
            df,
            x="Traffic",
            y="Product Pages",
            size="Product Pages",
            color="Domain",
            symbol="Brand",
            hover_name="Brand",
            hover_data={
                "Domain": True,
                "Traffic": ":,",
                "Product Pages": ":,",
                "Assortment Share": ":.2%",
                "Coverage": True,
            },
            title="Traffic vs Brand Product Presence",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

        st.subheader("🔥 Product Presence Heatmap")

        heatmap_df = df.pivot_table(
            index="Brand",
            columns="Domain",
            values="Product Pages",
            aggfunc="sum",
            fill_value=0,
        )

        fig_heatmap = px.imshow(
            heatmap_df,
            text_auto=True,
            aspect="auto",
            title="Brand Product Page Heatmap",
            labels=dict(x="Domain", y="Brand", color="Product Pages"),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)

    except Exception:
        st.error("The app hit an error.")
        st.code(traceback.format_exc())

else:
    st.info("Add retailer domains and brands in the sidebar, then click **Run Analysis**.")
