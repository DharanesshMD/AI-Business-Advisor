import re
from collections import Counter

def extract_claims(text: str):
    clean_text = re.sub(r'\*\*', '', text)
    # Don't remove non-ASCII yet, let's see what regex does
    
    potential_tickers = []
    ticker_matches = re.finditer(r'\b([A-Z]{1,5})\b', clean_text)
    skip_list = {'USD', 'GDP', 'CPI', 'FED', 'SEC', 'USA', 'UK', 'CEO', 'AI', 'INFO', 'THE', 'DATE', 'PRICE', 'AND', 'FOR', 'VAL', 'VALUE', 'DATA', 'ITEM', 'NOTE', 'RISK', 'TIME', 'UTC', 'IST', 'GMT'}
    
    for m in ticker_matches:
        symbol = m.group(1).upper()
        if symbol not in skip_list:
            potential_tickers.append({"symbol": symbol, "pos": m.start()})

    potential_prices = []
    # Test the current regex: \$?\b(\d+[\.,]\d{1,2})\b
    # Let's also try a safer one: \$?\s*(\d+[\.,]\d{1,2})\b
    price_matches = re.finditer(r'\$?\b(\d+[\.,]\d{1,2})\b', clean_text)
    
    for m in price_matches:
        try:
            val = float(m.group(1).replace(',', ''))
            potential_prices.append({"val": val, "pos": m.start()})
        except:
            continue

    return {"tickers": potential_tickers, "prices": potential_prices}

user_text = """
Tesla (TSLA) is currently trading at $431.41 USD (as of 2026-01-08 15:31 UTC) with a neutral sentiment based on recent news.
📊 Key Data & Findings
Metric	Value
Stock Price	$431.41
"""

print(extract_claims(user_text))
