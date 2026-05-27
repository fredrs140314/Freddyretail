import requests
from bs4 import BeautifulSoup
import random

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_sitemap_urls(domain):
    sitemap_url = f"https://{domain}/sitemap.xml"

    try:
        response = requests.get(sitemap_url, headers=HEADERS, timeout=10)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.content, "xml")

        urls = [loc.text for loc in soup.find_all("loc")]

        return urls[:100]

    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []


def fetch_page(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 200:
            return response.text.lower()

    except Exception as e:
        print(f"Error fetching page {url}: {e}")

    return ""


def count_brand_mentions(urls, brands):
    results = []

    for brand in brands:
        count = 0
        brand_lower = brand.lower()

        for url in urls:
            page_content = fetch_page(url)

            if brand_lower in page_content:
                count += 1

        results.append({
            "Brand": brand,
            "Mentions": count,
        })

    return results


def estimate_traffic(domain):
    mock_traffic = {
        "ica.se": 12000000,
        "amazon.com": 2400000000,
        "walmart.com": 450000000,
    }

    return mock_traffic.get(domain, random.randint(100000, 5000000))
