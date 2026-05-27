import gzip
import re
import traceback
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, unquote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ----------------------------
# CONFIG
# ----------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BrandProductAnalyzer/1.0)"
}

REQUEST_TIMEOUT = 12
MAX_WORKERS = 10

PRODUCT_URL_PATTERNS = [
    "/produkt/",
    "/produkter/",
    "/product/",
    "/products/",
    "/vara/",
    "/varor/",
    "/artiklar/",
    "/artikel/",
    "/p/",
    "/dp/",
    "/handla/",
    "/shop/",
    "/sortiment/",
]

CATEGORY_ONLY_PATTERNS = [
    "/kategori/",
    "/category/",
    "/recept/",
    "/recipe/",
    "/inspiration/",
    "/kampanj/",
    "/erbjudanden/",
    "/butik/",
    "/stores/",
    "/kundservice/",
]


DEFAULT_TRAFFIC = {
    "ica.se": 12000000,
    "coop.se": 5800000,
    "willys.se": 7200000,
    "hemkop.se": 2200000,
    "citygross.se": 1800000,
    "foodora.se": 4600000,
    "wolt.com": 10300000,
    "lidl.se": 22000000,
}


# ----------------------------
# BASIC HELPERS
# ----------------------------

def normalize_domain(domain):
    domain = str(domain).strip().lower()
    domain = domain.replace("http://", "").replace("https://", "")
    domain = domain.split("/")[0]
    return domain.strip()


def slugify(text):
    text = str(text).lower()
    text = text.replace("å", "a").replace("ä", "a").replace("ö", "o")
    text = text.replace("é", "e").replace("è", "e").replace("ü", "u")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def brand_aliases(brand):
    """
    Generate flexible aliases for brand matching.
    Example: Coca-Cola -> coca-cola, coca cola, cocacola, coca
    """
    brand = brand.strip()
    lower = brand.lower()
    slug = slugify(brand)
    compact = re.sub(r"[^a-z0-9]+", "", slug)

    aliases = {
        lower,
        slug,
        slug.replace("-", " "),
        compact,
    }

    # Useful special cases for common brands
    special = {
        "coca-cola": ["coca cola", "cocacola", "coca-cola", "coca"],
        "coca cola": ["coca cola", "cocacola", "coca-cola", "coca"],
        "pepsi": ["pepsi", "pepsi max", "pepsimax"],
        "red-bull": ["red bull", "redbull", "red-bull"],
        "red bull": ["red bull", "redbull", "red-bull"],
    }

    aliases.update(special.get(slug, []))
    aliases.update(special.get(lower, []))

    return sorted([a for a in aliases if a])


def estimate_traffic(domain):
    domain = normalize_domain(domain).replace("www.", "", 1)

    try:
        url = f"https://data.similarweb.com/api/v1/data?domain={domain}"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)

        if response.status_code == 200:
            data = response.json()
            monthly_visits = data.get("EstimatedMonthlyVisits", {})

            if monthly_visits:
                latest_key = sorted(monthly_visits.keys())[-1]
                traffic = monthly_visits.get(latest_key)
                if traffic:
                    return int(traffic)

            engagements = data.get("Engagments", {})
            visits = engagements.get("Visits")
            if visits:
                return int(float(visits))

    except Exception:
        pass

    return DEFAULT_TRAFFIC.get(domain, 0)


def candidate_base_urls(domain):
    domain = normalize_domain(domain)
    candidates = [
        "https://" + domain,
        "https://www." + domain,
        "http://" + domain,
        "http://www." + domain,
    ]

    if domain.startswith("www."):
        without_www = domain.replace("www.", "", 1)
        candidates.extend(["https://" + without_www, "http://" + without_www])

    return list(dict.fromkeys(candidates))


def http_get(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if response.status_code < 400:
            return response
    except Exception:
        return None

    return None


# ----------------------------
# SITEMAP DISCOVERY
# ----------------------------

def decode_content(response):
    content = response.content
    content_type = response.headers.get("content-type", "").lower()

    if response.url.endswith(".gz") or "gzip" in content_type:
        try:
            return gzip.decompress(content)
        except Exception:
            return content

    return content


def extract_sitemaps_from_robots(base_url):
    sitemaps = []
    robots = http_get(urljoin(base_url + "/", "robots.txt"))

    if not robots:
        return sitemaps

    for line in robots.text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(sitemap_url)

    return sitemaps


def common_sitemap_urls(base_url):
    paths = [
        "sitemap.xml",
        "sitemap_index.xml",
        "sitemap-index.xml",
        "sitemap/sitemap.xml",
        "sitemaps/sitemap.xml",
        "wp-sitemap.xml",
        "sitemap.xml.gz",
    ]
    return [urljoin(base_url + "/", path) for path in paths]


def strip_namespace(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_sitemap(content):
    page_urls = []
    sitemap_urls = []

    try:
        root = ET.fromstring(content)
    except Exception:
        return page_urls, sitemap_urls

    root_tag = strip_namespace(root.tag).lower()

    if root_tag == "sitemapindex":
        for sitemap_node in root:
            for child in sitemap_node:
                if strip_namespace(child.tag).lower() == "loc" and child.text:
                    sitemap_urls.append(child.text.strip())

    elif root_tag == "urlset":
        for url_node in root:
            for child in url_node:
                if strip_namespace(child.tag).lower() == "loc" and child.text:
                    page_urls.append(child.text.strip())

    return page_urls, sitemap_urls


def get_sitemap_urls(domain, max_urls=5000, max_sitemaps=150):
    domain = normalize_domain(domain)
    discovered = []

    for base_url in candidate_base_urls(domain):
        discovered.extend(extract_sitemaps_from_robots(base_url))
        discovered.extend(common_sitemap_urls(base_url))

    discovered = list(dict.fromkeys(discovered))

    queue = discovered[:]
    seen_sitemaps = set()
    urls = []

    while queue and len(urls) < max_urls and len(seen_sitemaps) < max_sitemaps:
        sitemap = queue.pop(0)

        if sitemap in seen_sitemaps:
            continue

        seen_sitemaps.add(sitemap)

        response = http_get(sitemap)
        if not response:
            continue

        content = decode_content(response)
        page_urls, sitemap_urls = parse_sitemap(content)

        urls.extend(page_urls)

        for nested_sitemap in sitemap_urls:
            if nested_sitemap not in seen_sitemaps:
                queue.append(nested_sitemap)

        urls = list(dict.fromkeys(urls))[:max_urls]

    root_no_www = domain.replace("www.", "", 1)
    cleaned_urls = []

    for url in urls:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "", 1)
        if host.endswith(root_no_www):
            cleaned_urls.append(url)

    cleaned_urls = list(dict.fromkeys(cleaned_urls))[:max_urls]

    if cleaned_urls:
        return cleaned_urls, "sitemap"

    # Fallback to homepage
    for base_url in candidate_base_urls(domain):
        response = http_get(base_url)
        if response:
            return [response.url], "homepage fallback"

    return [], "none"


# ----------------------------
# PRODUCT + BRAND MATCHING
# ----------------------------

def is_likely_product_url(url):
    url_lower = unquote(url.lower())

    if any(pattern in url_lower for pattern in CATEGORY_ONLY_PATTERNS):
        return False

    if any(pattern in url_lower for pattern in PRODUCT_URL_PATTERNS):
        return True

    path = urlparse(url_lower).path
    has_number = bool(re.search(r"\d{4,}", path))
    has_slug = path.count("/") >= 2 and "-" in path

    if has_number and has_slug:
        return True

    return False


def extract_product_urls(urls):
    return [url for url in urls if is_likely_product_url(url)]


def fetch_product_text(url):
    response = http_get(url)

    if not response:
        return ""

    content_type = response.headers.get("content-type", "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        return ""

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        parts = []

        if soup.title:
            parts.append(soup.title.get_text(" ", strip=True))

        for selector in ["h1", "h2"]:
            for tag in soup.find_all(selector)[:3]:
                parts.append(tag.get_text(" ", strip=True))

        for meta_attrs in [
            {"name": "description"},
            {"property": "og:title"},
            {"property": "og:description"},
        ]:
            meta_tag = soup.find("meta", attrs=meta_attrs)
            if meta_tag and meta_tag.get("content"):
                parts.append(meta_tag["content"])

        # Also include schema JSON-LD because product/brand is often there
        for script in soup.find_all("script", attrs={"type": "application/ld+json"})[:5]:
            parts.append(script.get_text(" ", strip=True))

        return " ".join(parts).lower()

    except Exception:
        return ""


def brand_matches_product(url, page_text, brand):
    url_text = slugify(unquote(url))
    normal_text = str(page_text).lower()
    slug_text = slugify(normal_text)
    compact_text = re.sub(r"[^a-z0-9]+", "", slug_text)

    aliases = brand_aliases(brand)

    for alias in aliases:
        alias_lower = alias.lower()
        alias_slug = slugify(alias_lower)
        alias_compact = re.sub(r"[^a-z0-9]+", "", alias_slug)

        if alias_lower and alias_lower in normal_text:
            return True

        if alias_slug and alias_slug in url_text:
            return True

        if alias_slug and alias_slug in slug_text:
            return True

        if alias_compact and alias_compact in compact_text:
            return True

    return False


def scan_product_url(url, brands):
    page_text = fetch_product_text(url)

    result = {}
    matched_by = {}

    for brand in brands:
        found = brand_matches_product(url, page_text, brand)
        result[brand] = found
        matched_by[brand] = url if found else ""

    return result, matched_by


def count_brand_product_pages(product_urls, brands):
    counts = {brand: 0 for brand in brands}
    examples = {brand: [] for brand in brands}

    if not product_urls:
        return counts, examples

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(scan_product_url, url, brands) for url in product_urls]

        for future in as_completed(futures):
            try:
                result, matched_by = future.result()

                for brand, found in result.items():
                    if found:
                        counts[brand] += 1
                        if len(examples[brand]) < 5:
                            examples[brand].append(matched_by[brand])

            except Exception:
                continue

    return counts, examples


def coverage_label(assortment_share):
    if assortment_share >= 0.08:
        return "High"
    if assortment_share >= 0.03:
        return "Medium"
    return "Low"


def get_domain_product_data(domain, brands, max_urls=5000):
    domain = normalize_domain(domain)

    urls, source = get_sitemap_urls(domain, max_urls=max_urls)
    product_urls = extract_product_urls(urls)

    counts, examples = count_brand_product_pages(product_urls, brands)

    traffic = estimate_traffic(domain)
    total_products = len(product_urls)

    results = []
    example_rows = []

    for brand in brands:
        product_pages = counts.get(brand, 0)
        assortment_share = product_pages / total_products if total_products else 0
        estimated_brand_opportunity = int(traffic * assortment_share)

        results.append(
            {
                "Domain": domain,
                "Brand": brand,
                "Product Pages": product_pages,
                "Total Product Pages": total_products,
                "Assortment Share": assortment_share,
                "Coverage": coverage_label(assortment_share),
                "Traffic": traffic,
                "Estimated Brand Opportunity": estimated_brand_opportunity,
                "Aliases Used": ", ".join(brand_aliases(brand)[:8]),
            }
        )

        for example_url in examples.get(brand, []):
            example_rows.append(
                {
                    "Domain": domain,
                    "Brand": brand,
                    "Matched Product URL": example_url,
                }
            )

    return {
        "domain": domain,
        "urls_found": len(urls),
        "url_source": source,
        "product_urls_found": total_products,
        "traffic": traffic,
        "results": results,
        "examples": example_rows,
        "sample_product_urls": product_urls[:20],
    }


# ----------------------------
# STREAMLIT APP
# ----------------------------

st.set_page_config(page_title="Brand Product Analyzer", layout="wide")

st.title("🛒 Brand Product Page Analyzer")
st.write(
    "Analyze actual brand product-page presence across retailer domains and compare it with estimated organic traffic."
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
    max_value=30000,
    value=5000,
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
        all_examples = []
        all_sample_product_urls = []
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
            all_examples.extend(domain_data["examples"])

            for url in domain_data["sample_product_urls"]:
                all_sample_product_urls.append({"Domain": domain, "Sample Product URL": url})

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
        display_df["Traffic"] = display_df["Traffic"].map("{:,.0f}".format)
        display_df["Estimated Brand Opportunity"] = display_df["Estimated Brand Opportunity"].map("{:,.0f}".format)

        st.dataframe(display_df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download result CSV",
            data=csv,
            file_name="brand-product-analysis.csv",
            mime="text/csv",
        )

        if all_examples:
            st.subheader("🔎 Example Matched Product URLs")
            examples_df = pd.DataFrame(all_examples)
            st.dataframe(examples_df, use_container_width=True)
        else:
            st.warning(
                "No brand-specific product URL examples found. This means the app found product pages, "
                "but the brand names were not visible in URL/title/H1/meta/schema for the scanned pages."
            )

        with st.expander("Debug: sample detected product URLs"):
            if all_sample_product_urls:
                st.dataframe(pd.DataFrame(all_sample_product_urls), use_container_width=True)
            else:
                st.write("No product URLs detected.")

        st.divider()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Domains", len(df["Domain"].unique()))
        c2.metric("Brands", len(df["Brand"].unique()))
        c3.metric("Total Product Pages", f"{summary_df['Likely Product Pages'].sum():,}")
        c4.metric("Brand Product Pages", f"{df['Product Pages'].sum():,}")

        st.subheader("📈 Search Intelligence")

        selected_brand = st.selectbox("Select brand", sorted(df["Brand"].unique()))

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
                    y=[row["Traffic"] * 1.04 if row["Traffic"] else 1],
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
