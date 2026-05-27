import requests
from bs4 import BeautifulSoup
import random

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def normalize_domain(domain):
    domain = domain.replace("https://", "")
    domain = domain.replace("http://", "")
    domain = domain.strip("/")
    return domain


def get_possible_sitemaps(domain):

    domain = normalize_domain(domain)

    return [
        f"https://{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
        f"https://{domain}/robots.txt",
    ]


def extract_urls_from_xml(xml_content):

    soup = BeautifulSoup(xml_content, "xml")

    urls = [loc.text for loc in soup.find_all("loc")]

    return urls


def get_sitemap_urls(domain):

    sitemap_urls = get_possible_sitemaps(domain)

    for sitemap in sitemap_urls:

        try:
            response = requests.get(
                sitemap,
                headers=HEADERS,
                timeout=15,
            )

            if response.status_code == 200:

                # robots.txt support
                if "robots.txt" in sitemap:

                    lines = response.text.splitlines()

                    for line in lines:
                        if "sitemap:" in line.lower():
                            sitemap_url = line.split(": ", 1)[1]

                            sitemap_response = requests.get(
                                sitemap_url,
                                headers=HEADERS,
                                timeout=15,
                            )

                            if sitemap_response.status_code == 200:
                                urls = extract_urls_from_xml(
                                    sitemap_response.content
                                )

                                if urls:
                                    return urls[:200]

                else:

                    urls = extract_urls_from_xml(response.content)

                    if urls:
                        return urls[:200]

        except Exception as e:
            print(f"Error with sitemap {sitemap}: {e}")

    return []


def fetch_page(url):

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=10,
        )

        if response.status_code == 200:
            return response.text.lower()

    except Exception as e:
        print(f"Error fetching {url}: {e}")

    return ""


def count_brand_mentions(urls, brands):

    mention_count = 0

    for url in urls:

        content = fetch_page(url)

        for brand in brands:

            if brand.lower() in content:
                mention_count += 1
                break

    return mention_count


def estimate_traffic(domain):

    domain = normalize_domain(domain)

    mock_data = {
        "ica.se": 22000,
        "coop.se": 12000,
        "willys.se": 5000,
        "lidl.se": 23000,
        "wolt.com": 10000,
        "foodora.se": 4500,
    }

    return mock_data.get(
        domain,
        random.randint(2000, 25000)
    )


def get_domain_data(domain, brands):

    clean_domain = normalize_domain(domain)

    urls = get_sitemap_urls(clean_domain)

    mentions = count_brand_mentions(urls, brands)

    traffic = estimate_traffic(clean_domain)

    return {
        "Domain": clean_domain,
        "Brand Mentions": mentions,
        "Estimated Traffic": traffic,
        "URLs Scanned": len(urls),
    }
