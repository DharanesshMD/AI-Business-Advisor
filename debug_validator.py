import re
from collections import Counter

def extract_claims(text: str):
    """
    Parses text to find claims about stock prices using a robust association logic.
    """
    # 1. Broadly normalize the text
    clean_text = re.sub(r'\*\*', '', text) # Remove bolding
    clean_text = re.sub(r'[^\x00-\x7F]+', ' ', clean_text) # Remove emojis/special chars
    
    print(f"DEBUG: Clean Text: {clean_text}")

    # 2. Extract every ticker mentioned (1-5 uppercase letters)
    # We ignore common false positive words
    potential_tickers = []
    ticker_matches = re.finditer(r'\b([A-Z]{1,5})\b', clean_text)
    skip_list = {'USD', 'GDP', 'CPI', 'FED', 'SEC', 'USA', 'UK', 'CEO', 'AI', 'INFO', 'THE', 'DATE', 'PRICE', 'AND', 'FOR', 'VAL'}
    
    for m in ticker_matches:
        ticker = m.group(1).upper()
        if ticker not in skip_list:
            potential_tickers.append({
                "symbol": ticker,
                "pos": m.start()
            })
            print(f"DEBUG: Found Ticker: {ticker} at {m.start()}")

    # 3. Extract every price mentioned ($123.45)
    potential_prices = []
    # Support $260.33, 260.33 USD, etc.
    price_matches = re.finditer(r'\$?\b(\d+[\.,]\d{1,2})\b', clean_text)
    for m in price_matches:
        try:
            val = float(m.group(1).replace(',', ''))
            potential_prices.append({
                "val": val,
                "pos": m.start()
            })
            print(f"DEBUG: Found Price: {val} at {m.start()}")
        except:
            continue

    if not potential_prices:
        print("DEBUG: No prices found")
        return []

    # 4. Association Logic
    claims = []
    seen_pairs = set()

    for price in potential_prices:
        best_ticker = None
        min_dist = float('inf')
        
        for ticker in potential_tickers:
            dist = price.get("pos") - ticker.get("pos")
            
            if 0 <= dist < 300: # Ticker is within 300 chars before the price
                if dist < min_dist:
                    min_dist = dist
                    best_ticker = ticker["symbol"]
            elif -50 < dist < 0:
                if abs(dist) < min_dist:
                    min_dist = abs(dist)
                    best_ticker = ticker["symbol"]

        if best_ticker:
            print(f"DEBUG: Paired {best_ticker} with {price['val']}")
            pair_id = f"{best_ticker}_{price['val']}"
            if pair_id not in seen_pairs:
                claims.append({"symbol": best_ticker, "price": price["val"]})
                seen_pairs.add(pair_id)

    if not claims and potential_tickers and potential_prices:
        ticker_counts = Counter(t["symbol"] for t in potential_tickers)
        main_ticker = ticker_counts.most_common(1)[0][0]
        print(f"DEBUG: Fallback to main ticker: {main_ticker}")
        for p in potential_prices:
            claims.append({"symbol": main_ticker, "price": p["val"]})

    return claims

test_text = """
CP Executive Summary
The current price of Apple Inc. (AAPL) is $260.33 USD as of January 8, 2026, at 1:25 PM UTC.
K Key Data & Findings
Metric	Value	Source
Stock Price	$260.33	Yahoo Finance
Currency	USD	Yahoo Finance
Timestamp	2026-01-08 13:25:39	Yahoo Finance
R Risks & Considerations
Market Volatility: Stock prices fluctuate based on market conditions.
Time Sensitivity: The price is current as of the timestamp and may change rapidly.
Action Items
Verify for Real-Time Use: If using this price for trading or financial decisions, confirm with your broker or platform for real-time accuracy.
Monitor Updates: Use a financial platform to track live updates if needed.
L Sources
Yahoo Finance (Free) - Real-time stock price data.
"""

print(f"RESULT: {extract_claims(test_text)}")
