import gzip
import random
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BrandDomainAnalyzer/1.0; "
        "+https://example.com/bot)"
    )
}

REQUEST_TIMEOUT = 10
MAX_WORKERS = 8


def normalize_domain(domain):
    domain = str(domain).strip().lower()
    domain = domain.replace("http://", "").replace("https://", "")
    domain = domain.split("/")[0]
    return domain.strip()


def _candidate_base_urls(domain):
    domain = normalize_domain(domain)
    candidates = [
        "https://" + domain,
        "http://" + domain,
    ]

    if not domain.startswith("www."):
        candidates.extend(["https://www." + domain, "http://www." + domain])
    else:
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


def _decode_response_content(response):
    content = response.content
    content_type = response.headers.get("content-type", "").lower()

    if response.url.endswith(".gz") or "gzip" in content_type:
        try:
            return gzip.decompress(content)
        except Exception:
            return content

    return content


def _extract_sitemaps_from_robots(base_url):
    response = _get(urljoin(base_url + "/", "robots.txt"))
    if not response:
        return []

    sitemaps = []
    for line in response.text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(sitemap_url)

    return list(dict.fromkeys(sitemaps))


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


def _parse_sitemap_xml(content):
    page_urls = []
    sitemap_urls = []

    try:
        root = ET.fromstring(content)
    except Exception:
        return page_urls, sitemap_urls

    root_tag = _strip_namespace(root.tag).lower()

    if root_tag == "sitemapindex":
        for sitemap in root:
            if _strip_namespace(sitemap.tag).lower() == "sitemap":
                for child in sitemap:
                    if _strip_namespace(child.tag).lower() == "loc" and child.text:
                        sitemap_urls.append(child.text.strip())

    elif root_tag == "urlset":
        for url_node in root:
            if _strip_namespace(url_node.tag).lower() == "url":
                for child in url_node:
                    if _strip_namespace(child.tag).lower() == "loc" and child.text:
                        page_urls.append(child.text.strip())

    return page_urls, sitemap_urls


def _fetch_and_parse_sitemap(sitemap_url):
    response = _get(sitemap_url)
    if not response:
        return [], []

    content = _decode_response_content(response)
    return _parse_sitemap_xml(content)


def get_sitemap_urls(domain, max_urls=500, include_homepage_fallback=True, max_sitemaps=30):
    domain = normalize_domain(domain)
    base_urls = _candidate_base_urls(domain)

    discovered_sitemaps = []
    for base_url in base_urls:
        discovered_sitemaps.extend(_extract_sitemaps_from_robots(base_url))
        discovered_sitemaps.extend(_common_sitemap_urls(base_url))

    discovered_sitemaps = list(dict.fromkeys(discovered_sitemaps))

    seen_sitemaps = set()
    queue = discovered_sitemaps[:]
    urls = []

    while queue and len(seen_sitemaps) < max_sitemaps and len(urls) < max_urls:
        sitemap_url = queue.pop(0)

        if sitemap_url in seen_sitemaps:
            continue

        seen_sitemaps.add(sitemap_url)

        page_urls, nested_sitemaps = _fetch_and_parse_sitemap(sitemap_url)
        urls.extend(page_urls)

        for nested in nested_sitemaps:
            if nested not in seen_sitemaps:
                queue.append(nested)

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

    if include_homepage_fallback:
        for base_url in base_urls:
            response = _get(base_url)
            if response:
                return [response.url], "homepage fallback"

    return [], "none"


def fetch_page(url):
    response = _get(url)

    if not response:
        return ""

    content_type = response.headers.get("content-type", "").lower()

    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        return ""

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return soup.get_text(" ", strip=True).lower()
    except Exception:
        return response.text.lower()


def _count_for_url(url, brands):
    content = fetch_page(url)
    return {brand: brand.lower() in content for brand in brands}


def count_brand_mentions(urls, brands):
    counts = {brand: 0 for brand in brands}

    if not urls:
        return [{"Brand": brand, "Mentions": 0} for brand in brands]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_count_for_url, url, brands) for url in urls]

        for future in as_completed(futures):
            try:
                result = future.result()
                for brand, found in result.items():
                    if found:
                        counts[brand] += 1
            except Exception:
                continue

    return [{"Brand": brand, "Mentions": count} for brand, count in counts.items()]


def estimate_traffic(domain):
    domain = normalize_domain(domain).replace("www.", "", 1)

    mock_traffic = {
        "ica.se": 12000000,
        "coop.se": 5800000,
        "willys.se": 7200000,
        "hemkop.se": 2200000,
        "citygross.se": 1800000,
        "amazon.com": 2400000000,
        "walmart.com": 450000000,
    }

    return mock_traffic.get(domain, random.randint(100000, 5000000))


def get_domain_data(domain, brands, max_urls=500):
    try:
        domain = normalize_domain(domain)
        urls, source = get_sitemap_urls(domain, max_urls=max_urls)
        traffic = estimate_traffic(domain)
        brand_results = count_brand_mentions(urls, brands) if urls else []

        enriched_results = []
        for row in brand_results:
            mentions = row["Mentions"]
            enriched_results.append(
                {
                    "Domain": domain,
                    "Brand": row["Brand"],
                    "Mentions": mentions,
                    "Traffic": traffic,
                    "URLs Scanned": len(urls),
                    "Presence Rate": mentions / len(urls) if urls else 0,
                }
            )

        return {
            "domain": domain,
            "urls": urls,
            "urls_found": len(urls),
            "url_source": source,
            "traffic": traffic,
            "results": enriched_results,
            "status": "ok",
        }

    except Exception as e:
        return {
            "domain": domain,
            "urls": [],
            "urls_found": 0,
            "url_source": "error",
            "traffic": 0,
            "results": [],
            "status": str(e),
        }
