# Brand Domain Analyzer MVP v4 Safe

This version is designed to avoid common Streamlit Cloud crashes.

## Fixes

- Removed `lxml` dependency
- Removed Python 3.10-only syntax
- Added visible error output inside the app
- Added safer sitemap parsing with Python standard library
- Added multi-domain support
- Added grouped bar chart, heatmap, and traffic bubble chart

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Important

When deploying to Streamlit Cloud, replace all old files with these files:

- app.py
- backend.py
- requirements.txt

Then reboot/redeploy the app.
