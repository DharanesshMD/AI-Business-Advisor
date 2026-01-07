"""
Response Validator Agent
Checks generated responses for factual consistency regarding stock prices and historical data.
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage

from backend.logger import get_logger

logger = logging.getLogger(__name__)

class ResponseValidator:
    """
    Validates AI responses against tool outputs to prevent hallucinations in 
    stock prices, dates, and historical metrics.
    """
    
    def __init__(self):
        self.logger = get_logger()
        # Regex for finding currency amounts: $123.45, 123.45 USD, etc.
        self.price_pattern = re.compile(r'\$?\b(\d+[\.,]\d{1,2})\b')
        # Regex for finding tickers: (AAPL), AAPL, $AAPL
        self.ticker_pattern = re.compile(r'\b[A-Z]{1,5}\b')

    def extract_claims(self, text: str) -> List[Dict[str, Any]]:
        """
        Parses text to find claims about stock prices.
        Returns a list of {symbol, price, context}
        """
        claims = []
        # Support markdown tables and standard sentences
        # Matches: | AAPL | $150.00 | OR | AAPL Price | $150.00 |
        # This regex looks for a Ticker followed eventually by a Price
        table_row_pattern = re.compile(r'\|?\s*([A-Z]{1,5})(?:\s+[^|]*)?\s*\|?\s*[^|]*?\$?\s*(\d+[\.,]\d{1,2})\b', re.IGNORECASE)
        
        matches = table_row_pattern.findall(text)
        for ticker, price in matches:
            ticker = ticker.upper()
            if ticker in ['USD', 'GDP', 'CPI', 'FED', 'SEC', 'USA', 'UK', 'CEO', 'AI', 'ITEM', 'VALUE', 'INFO']:
                continue
            try:
                price_val = float(price.replace(',', ''))
                claims.append({
                    "symbol": ticker,
                    "price": price_val
                })
            except ValueError:
                continue
        
        # Also check standard sentence format if table pattern didn't yield much
        if not claims:
            lines = text.split('\n')
            for line in lines:
                tickers = self.ticker_pattern.findall(line)
                prices = self.price_pattern.findall(line)
                if tickers and prices:
                    for t in tickers:
                        if t in ['USD', 'GDP', 'CPI', 'FED', 'SEC']: continue
                        try:
                            price_val = float(prices[0].replace(',', ''))
                            claims.append({"symbol": t.upper(), "price": price_val})
                        except: pass
        
        return claims

    def get_ground_truth(self, messages: List[Any]) -> Dict[str, float]:
        """
        Scans history for ToolMessages and extracts 'ground truth' prices.
        """
        ground_truth = {}
        for msg in messages:
            if isinstance(msg, ToolMessage):
                content = msg.content
                try:
                    # Try to parse as JSON first (our tools mostly return JSON)
                    data = json.loads(content)
                    
                    # Handle validate_stock_price format
                    if isinstance(data, dict):
                        symbol = data.get("symbol")
                        price = data.get("price")
                        if symbol and price:
                            ground_truth[symbol.upper()] = float(price)
                        
                        # Handle portfolio analysis format
                        if "portfolio_analysis" in data:
                            for holding in data.get("holdings", []):
                                s = holding.get("symbol")
                                p = holding.get("current_price")
                                if s and p:
                                    ground_truth[s.upper()] = float(p)
                                    
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Fallback: simple regex on tool output if not JSON
                    pass
        return ground_truth

    def validate(self, response_content: str, message_history: List[Any]) -> Tuple[bool, Optional[str]]:
        """
        Main validation entry point.
        Returns (is_valid, error_message)
        """
        self.logger.graph_step("validator", "start", "Validating stock data consistency")
        
        claims = self.extract_claims(response_content)
        if not claims:
            self.logger.debug("No price claims found in response to validate.")
            return True, None
            
        truth = self.get_ground_truth(message_history)
        if not truth:
            self.logger.debug("No tool data (ground truth) found in history to validate against.")
            return True, None
            
        discrepancies = []
        for claim in claims:
            symbol = claim["symbol"]
            claimed_price = claim["price"]
            
            if symbol in truth:
                actual_price = truth[symbol]
                # Allow 0.5% variance for rounding or slight timing diffs
                diff_pct = abs(claimed_price - actual_price) / actual_price
                
                if diff_pct > 0.01: # 1% threshold for strict validation
                    discrepancies.append(
                        f"- **{symbol}**: You stated ${claimed_price}, but tool data shows ${actual_price}."
                    )
                    self.logger.tool_call_error("validator", f"Price mismatch for {symbol}: AI={claimed_price}, Tool={actual_price}")

        if discrepancies:
            error_msg = (
                "DATA INCONSISTENCY DETECTED:\n"
                "I found discrepancies between your response and the actual tool data results:\n"
                + "\n".join(discrepancies) + "\n\n"
                "Please RE-CHECK the tool outputs in the conversation history and provide a corrected response "
                "with the exact figures from the tools. Do not hallucinate or estimate prices if real data is available."
            )
            return False, error_msg

        self.logger.graph_step("validator", "end", "Validation successful (all prices matched)")
        return True, None

def get_validator() -> ResponseValidator:
    """Singleton pattern for the validator."""
    return ResponseValidator()
