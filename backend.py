import gzip
import random
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BrandProductAnalyzer/1.0)"
}

REQUEST_TIMEOUT = 10
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
]


def normalize_domain(domain):
    domain = str(domain).strip().lower()
    domain = domain.replace("http://", "").replace("https://", "")
    domain = domain.split("/")[0]
    return domain.strip()


def estimate_traffic(domain):
    domain = normalize_domain(domain).replace("www.", "", 1)

    mock_traffic = {
        "ica.se": 12000000,
        "coop.se": 5800000,
        "willys.se": 7200000,
        "hemkop.se": 2200000,
        "citygross.se": 1800000,
        "foodora.se": 4600000,
        "wolt.com": 10300000,
        "lidl.se": 22000000,
    }

    return mock_traffic.get(domain, random.randint(100000, 5000000))


def _candidate_base_urls(domain):
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


def _get(url):
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


def _decode_content(response):
    content = response.content
    content_type = response.headers.get("content-type", "").lower()

    if response.url.endswith(".gz") or "gzip" in content_type:
        try:
            return gzip.decompress(content)
        except Exception:
            return content

    return content


def _extract_sitemaps_from_robots(base_url):
    sitemaps = []
    robots = _get(urljoin(base_url + "/", "robots.txt"))

    if not robots:
        return sitemaps

    for line in robots.text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(sitemap_url)

    return sitemaps


def _common_sitemap_urls(base_url):
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


def _strip_namespace(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_sitemap(content):
    page_urls = []
    sitemap_urls = []

    try:
        root = ET.fromstring(content)
    except Exception:
        return page_urls, sitemap_urls

    root_tag = _strip_namespace(root.tag).lower()

    if root_tag == "sitemapindex":
        for sitemap_node in root:
            for child in sitemap_node:
                if _strip_namespace(child.tag).lower() == "loc" and child.text:
                    sitemap_urls.append(child.text.strip())

    elif root_tag == "urlset":
        for url_node in root:
            for child in url_node:
                if _strip_namespace(child.tag).lower() == "loc" and child.text:
                    page_urls.append(child.text.strip())

    return page_urls, sitemap_urls


def get_sitemap_urls(domain, max_urls=3000, max_sitemaps=80):
    domain = normalize_domain(domain)
    discovered = []

    for base_url in _candidate_base_urls(domain):
        discovered.extend(_extract_sitemaps_from_robots(base_url))
        discovered.extend(_common_sitemap_urls(base_url))

    discovered = list(dict.fromkeys(discovered))

    queue = discovered[:]
    seen_sitemaps = set()
    urls = []

    while queue and len(urls) < max_urls and len(seen_sitemaps) < max_sitemaps:
        sitemap = queue.pop(0)

        if sitemap in seen_sitemaps:
            continue

        seen_sitemaps.add(sitemap)

        response = _get(sitemap)
        if not response:
            continue

        content = _decode_content(response)
        page_urls, sitemap_urls = _parse_sitemap(content)

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

    # homepage fallback, mostly for debugging
    for base_url in _candidate_base_urls(domain):
        response = _get(base_url)
        if response:
            return [response.url], "homepage fallback"

    return [], "none"


def is_likely_product_url(url):
    url_lower = url.lower()

    if any(pattern in url_lower for pattern in CATEGORY_ONLY_PATTERNS):
        return False

    if any(pattern in url_lower for pattern in PRODUCT_URL_PATTERNS):
        return True

    # Common ecommerce URL pattern: long slug with numeric article/product id
    path = urlparse(url_lower).path
    has_number = bool(re.search(r"\d{4,}", path))
    has_slug = path.count("/") >= 2 and "-" in path

    if has_number and has_slug:
        return True

    return False


def extract_product_urls(urls):
    return [url for url in urls if is_likely_product_url(url)]


def fetch_product_text(url):
    response = _get(url)

    if not response:
        return ""

    content_type = response.headers.get("content-type", "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        return ""

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.get_text(" ", strip=True) if soup.title else ""

        h1 = ""
        h1_tag = soup.find("h1")
        if h1_tag:
            h1 = h1_tag.get_text(" ", strip=True)

        meta_description = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and meta_tag.get("content"):
            meta_description = meta_tag["content"]

        og_title = ""
        og_tag = soup.find("meta", attrs={"property": "og:title"})
        if og_tag and og_tag.get("content"):
            og_title = og_tag["content"]

        return " ".join([title, h1, meta_description, og_title]).lower()

    except Exception:
        return ""


def _normalize_brand_for_url(brand):
    brand = brand.lower()
    brand = brand.replace("å", "a").replace("ä", "a").replace("ö", "o")
    brand = re.sub(r"[^a-z0-9]+", "-", brand)
    brand = brand.strip("-")
    return brand


def _brand_matches_product(url, page_text, brand):
    brand_text = brand.lower()
    brand_url = _normalize_brand_for_url(brand)

    url_lower = url.lower()

    if brand_text in page_text:
        return True

    if brand_url and brand_url in url_lower:
        return True

    # Flexible brand token match, useful for Coca-Cola vs coca cola vs coca-cola
    tokens = [t for t in re.split(r"[^a-z0-9]+", brand_text) if len(t) > 1]
    if tokens and all(token in page_text or token in url_lower for token in tokens):
        return True

    return False


def _scan_product_url(url, brands):
    page_text = fetch_product_text(url)

    result = {}
    for brand in brands:
        result[brand] = _brand_matches_product(url, page_text, brand)

    return result


def count_brand_product_pages(product_urls, brands):
    counts = {brand: 0 for brand in brands}

    if not product_urls:
        return counts

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(_scan_product_url, url, brands)
            for url in product_urls
        ]

        for future in as_completed(futures):
            try:
                result = future.result()

                for brand, found in result.items():
                    if found:
                        counts[brand] += 1

            except Exception:
                continue

    return counts


def _coverage_label(assortment_share):
    if assortment_share >= 0.08:
        return "High"
    if assortment_share >= 0.03:
        return "Medium"
    return "Low"


def get_domain_product_data(domain, brands, max_urls=3000):
    domain = normalize_domain(domain)
    urls, source = get_sitemap_urls(domain, max_urls=max_urls)
    product_urls = extract_product_urls(urls)

    counts = count_brand_product_pages(product_urls, brands)
    traffic = estimate_traffic(domain)
    total_products = len(product_urls)

    results = []

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
                "Coverage": _coverage_label(assortment_share),
                "Traffic": traffic,
                "Estimated Brand Opportunity": estimated_brand_opportunity,
            }
        )

    return {
        "domain": domain,
        "urls_found": len(urls),
        "url_source": source,
        "product_urls_found": total_products,
        "traffic": traffic,
        "results": results,
    }
