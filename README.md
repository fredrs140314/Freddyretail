# Brand Domain Analyzer MVP v3 Patched

This version fixes the Streamlit Cloud error:

```python
ImportError: cannot import name 'get_domain_data' from 'backend'
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## What changed

- Added `get_domain_data()` to `backend.py`
- Updated `app.py` to use one clean backend function
- Supports several domains
- Better sitemap discovery
- Supports `robots.txt` sitemap declarations
- Tries www and non-www versions
- Adds grouped bar chart, heatmap and traffic-vs-brand bubble chart
