# Brand Product Page Analyzer

A Streamlit MVP for comparing brand product-page presence across retailer domains.

## What it does

- Accepts multiple retailer domains
- Accepts multiple brands
- Discovers URLs from sitemaps and robots.txt
- Filters likely product pages
- Counts product pages connected to each brand
- Calculates assortment share
- Estimates brand opportunity based on traffic and product-page presence
- Creates an executive "Search Intelligence" graph similar to retail media/SEO decks

## Files

```txt
brand-product-analyzer/
├── app.py
├── backend.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Install

```bash
pip install -r requirements.txt
```

## Run locally

```bash
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Create a GitHub repo
2. Upload all files from this folder
3. Go to Streamlit Community Cloud
4. Connect the GitHub repo
5. Set main file path to:

```txt
app.py
```

6. Deploy

## Notes

Traffic values are currently mocked in `backend.py`.

Replace `estimate_traffic()` later with an API such as:

- Similarweb
- SEMrush
- Ahrefs
- Sistrix

Product-page detection is heuristic-based. It uses:

- URL patterns
- sitemap URLs
- title/H1/meta matching
- brand-token matching

For production use, add:

- retailer-specific URL rules
- canonical extraction
- structured data extraction
- ecommerce API integrations
- duplicate product handling
- brand alias mapping
