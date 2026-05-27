# Brand Product Analyzer v7

Single-file Streamlit app.

## Improvements in this version

- Better brand matching for Pepsi, Red Bull, Coca-Cola, etc.
- Brand aliases:
  - Coca-Cola / Coca Cola / cocacola / coca
  - Red Bull / redbull / red-bull
  - Pepsi / Pepsi Max
- Looks at:
  - URL
  - title
  - H1/H2
  - meta description
  - Open Graph title/description
  - JSON-LD schema snippets
- Shows example matched product URLs
- Shows sample detected product URLs for debugging
- Uses Similarweb free endpoint when available
- Falls back to built-in demo traffic values if Similarweb fails

## Deploy

Upload these files to GitHub:

- app.py
- requirements.txt
- README.md
- .gitignore

Then set Streamlit main file path to:

```txt
app.py
```
