"""
Response Validator Agent
Checks generated responses for factual consistency regarding stock prices and historical data.
"""

import json
import re
import logging
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple, Set
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
        # Regex for finding currency amounts: $123.45, 123, 123.45 USD, etc.
        self.price_pattern = re.compile(r'\$?\s*\b(\d+(?:[\.,]\d{1,2})?)\b')
        # Regex for finding tickers: (AAPL), AAPL, $AAPL
        self.ticker_pattern = re.compile(r'\b[A-Z]{1,5}\b')

    def extract_claims(self, text: str) -> List[Dict[str, Any]]:
        """
        Hardened extraction logic for stock prices, percentages, and dollar amounts.
        Supports stress test outputs, portfolio analysis, and general financial data.
        """
        # 1. Normalize and clean - keep percent signs, minus signs, and pipes for tables
        clean_text = re.sub(r'\*\*', '', text)
        # Keep: alphanumeric, whitespace, $, %, ., ,, -, (, ), |, tabs
        clean_text = re.sub(r'[^\w\s\$%\.,\-\(\)\|\t]+', ' ', clean_text)
        
        self.logger.debug(f"Validator: Normalized text sample: {clean_text[:150]}...")
        
        claims = []
        seen_pairs = set()
        
        # Skip list for common non-ticker words (comprehensive to avoid false positives)
        skip_list = {
            # Currency/Units
            'USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'INR',
            # Financial abbreviations
            'VAL', 'DATA', 'DATE', 'PRICE', 'VAR', 'PCT', 'BPS', 'ETF', 'IPO', 'CEO', 'CFO', 'COO',
            'SEC', 'FED', 'RATE', 'HIKE', 'CUT', 'YOY', 'QOQ', 'MOM', 'ROI', 'ROE', 'ROA', 
            'EPS', 'PE', 'PB', 'PS', 'NAV', 'AUM', 'TBD', 'NA', 'NR',
            # Time-related
            'UTC', 'IST', 'GMT', 'EST', 'PST', 'CST', 'MST', 'TIME', 'WEEK', 'DAY', 'YEAR',
            # Common English words that look like tickers
            'THE', 'AND', 'FOR', 'NOT', 'BUT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR',
            'OUT', 'ARE', 'HAS', 'HIS', 'HOW', 'ITS', 'LET', 'MAY', 'NEW', 'NOW', 'OLD', 'SEE',
            'WAY', 'WHO', 'BOY', 'DID', 'GET', 'HIM', 'MAN', 'OWN', 'SAY', 'SHE', 'TOO', 'USE',
            # Report/Document words
            'NOTE', 'RISK', 'ITEM', 'KEY', 'TOTAL', 'SOURCE', 'VALUE', 'IMPACT', 'LOSS', 
            'METRIC', 'SUMMARY', 'FINDINGS', 'SCENARIO', 'URGENT', 'WITHIN', 'ACTION',
            # Partial word fragments that regex might catch
            'AT', 'T', 'S', 'IS', 'IT', 'AS', 'BE', 'BY', 'DO', 'GO', 'IF', 'IN', 'NO', 
            'OF', 'ON', 'OR', 'SO', 'TO', 'UP', 'US', 'WE', 'AN', 'AM', 'MY', 'HE', 'ME',
            # Common abbreviated fragments from business text
            'EXEC', 'EXECU', 'VERIF', 'MONIT', 'MANAG', 'ANALY', 'REPOR', 'INVES', 'MARKE',
            'FINAN', 'TRADI', 'PROJE', 'REVIE', 'UPDAT', 'CREAT', 'TRACK', 'CHECK', 'ALERT',
            # Other common abbreviations
            'AI', 'ML', 'API', 'UI', 'UX', 'QA', 'IT', 'HR', 'PR', 'VP', 'SVP', 'EVP',
            # Verification related
            'VERIFY', 'VALID', 'PASS', 'FAIL', 'TRUE', 'FALSE', 'YES', 'OK'
        }
        
        # Minimum price threshold to filter out list numbers (1., 2., etc.)
        MIN_STOCK_PRICE = 5.0

        def add_claim(claim_type: str, key: str, value: float, unit: str = ""):
            """Add a claim with deduplication."""
            key = key.upper()
            if key in skip_list:
                return
            pair = f"{claim_type}_{key}_{value}"
            if pair not in seen_pairs:
                claims.append({
                    "type": claim_type,  # "price", "percent", "dollar"
                    "key": key,          # Ticker or metric name
                    "value": value,
                    "unit": unit
                })
                seen_pairs.add(pair)
                self.logger.debug(f"Validator: Found {claim_type} claim: {key} = {value}{unit}")

        # ============ STRATEGY 1: Ticker + Price Patterns ============
        # Matches: TSLA ... $431.41, AAPL at $150.25, (NVDA) $500
        ticker_price_pattern = re.compile(
            r'\(?([A-Z]{2,5})\)?[^$\d]{0,50}\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)',
            re.IGNORECASE
        )
        for m in ticker_price_pattern.finditer(clean_text):
            try:
                ticker = m.group(1).upper()
                price = float(m.group(2).replace(',', ''))
                if ticker not in skip_list and price >= MIN_STOCK_PRICE:
                    add_claim("price", ticker, price, "$")
            except: continue

        # ============ STRATEGY 2: Ticker + Percentage Impact ============
        # Matches: AAPL Impact -5.0%, NVDA: +3.2%
        ticker_pct_pattern = re.compile(
            r'\b([A-Z]{2,5})\b[^%\d]{0,30}([+-]?\d+(?:\.\d+)?)\s*%',
            re.IGNORECASE
        )
        for m in ticker_pct_pattern.finditer(clean_text):
            try:
                ticker = m.group(1).upper()
                pct_value = float(m.group(2))
                if ticker not in skip_list:
                    add_claim("percent", ticker, pct_value, "%")
            except: continue
        
        # ============ STRATEGY 3: Ticker + Dollar Loss/Gain ============
        # Matches: AAPL ($500 loss), MSFT -$1,500
        ticker_dollar_pattern = re.compile(
            r'\b([A-Z]{2,5})\b[^\$]{0,20}\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:loss|gain)?',
            re.IGNORECASE
        )
        for m in ticker_dollar_pattern.finditer(clean_text):
            try:
                ticker = m.group(1).upper()
                dollar_value = float(m.group(2).replace(',', ''))
                if ticker not in skip_list and dollar_value >= MIN_STOCK_PRICE:
                    add_claim("dollar", ticker, dollar_value, "$")
            except: continue

        # ============ STRATEGY 4: Table Row Parsing ============
        # Handle markdown/text tables like: | AAPL | $150.25 | or AAPL\t$150.25
        lines = clean_text.split('\n')
        for line in lines:
            # Skip header/separator lines
            if '---' in line or not line.strip():
                continue
            
            # Split by pipe or tab
            cells = re.split(r'[\|\t]+', line)
            cells = [c.strip() for c in cells if c.strip()]
            
            if len(cells) >= 2:
                # Look for ticker in first few cells
                ticker = None
                for cell in cells[:2]:
                    ticker_match = re.search(r'\b([A-Z]{2,5})\b', cell)
                    if ticker_match and ticker_match.group(1).upper() not in skip_list:
                        ticker = ticker_match.group(1).upper()
                        break
                
                if ticker:
                    # Look for values in remaining cells
                    for cell in cells:
                        # Dollar amount
                        dollar_match = re.search(r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)', cell)
                        if dollar_match:
                            try:
                                value = float(dollar_match.group(1).replace(',', ''))
                                add_claim("dollar", ticker, value, "$")
                            except: pass
                        
                        # Percentage
                        pct_match = re.search(r'([+-]?\d+(?:\.\d+)?)\s*%', cell)
                        if pct_match:
                            try:
                                value = float(pct_match.group(1))
                                add_claim("percent", ticker, value, "%")
                            except: pass

        # ============ STRATEGY 5: Named Metrics ============
        # Matches: Total Portfolio Impact -5.0%, Worst-Case VaR $2,250
        named_metrics = [
            (r'Total\s+Portfolio\s+(?:Impact|Loss)[^\d]*([+-]?\d+(?:\.\d+)?)\s*%', "PORTFOLIO_IMPACT", "percent"),
            (r'Total\s+Portfolio\s+(?:Impact|Loss)[^\$]*\$\s*(\d{1,3}(?:,\d{3})*)', "PORTFOLIO_LOSS", "dollar"),
            (r'Worst[- ]?Case\s+(?:VaR|Loss)[^\$]*\$\s*(\d{1,3}(?:,\d{3})*)', "WORST_CASE_VAR", "dollar"),
            (r'Equity\s+Market\s+Impact[^\d]*([+-]?\d+(?:\.\d+)?)\s*%', "EQUITY_IMPACT", "percent"),
            (r'Volatility\s+Spike[^\d]*\+?(\d+(?:\.\d+)?)\s*%', "VOL_SPIKE", "percent"),
        ]
        for pattern, key, claim_type in named_metrics:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1).replace(',', ''))
                    unit = "%" if claim_type == "percent" else "$"
                    add_claim(claim_type, key, value, unit)
                except: continue

        self.logger.debug(f"Validator: Extracted {len(claims)} total claims.")
        return claims

    def get_ground_truth(self, messages: List[Any]) -> Dict[str, Dict[str, float]]:
        """
        Scans history for ToolMessages and extracts 'ground truth' data.
        Returns a nested dict: { key: { "price": X, "percent": Y, "dollar": Z } }
        """
        ground_truth = {}
        
        def add_truth(key: str, claim_type: str, value: float):
            """Add a ground truth value."""
            key = key.upper()
            if key not in ground_truth:
                ground_truth[key] = {}
            ground_truth[key][claim_type] = value
        
        for msg in messages:
            if isinstance(msg, ToolMessage):
                content = msg.content
                try:
                    data = json.loads(content)
                    
                    if not isinstance(data, dict):
                        continue
                    
                    # ====== Stock Price Format ======
                    symbol = data.get("symbol")
                    price = data.get("price")
                    if symbol and price:
                        add_truth(symbol, "price", float(price))
                    
                    # ====== Portfolio Analysis Format ======
                    if "portfolio_analysis" in data or "holdings" in data:
                        for holding in data.get("holdings", []):
                            s = holding.get("symbol")
                            p = holding.get("current_price")
                            if s and p:
                                add_truth(s, "price", float(p))
                    
                    # ====== Stress Test Format ======
                    # Parse holdings_analysis from stress tests
                    for item in data.get("holdings_analysis", []):
                        symbol = item.get("symbol", "").upper()
                        if not symbol:
                            continue
                        
                        # Expected impact: "+5.1%" or "-3.0%"
                        impact_str = item.get("expected_impact", "")
                        if impact_str:
                            match = re.search(r'([+-]?\d+(?:\.\d+)?)', impact_str)
                            if match:
                                add_truth(symbol, "percent", float(match.group(1)))
                        
                        # Expected P&L: "$-500" or "$+1,000"
                        pnl_str = item.get("expected_pnl", "")
                        if pnl_str:
                            match = re.search(r'\$\s*([+-]?\d{1,3}(?:,\d{3})*)', pnl_str)
                            if match:
                                val = float(match.group(1).replace(',', '').replace('+', ''))
                                add_truth(symbol, "dollar", abs(val))
                    
                    # Parse portfolio_summary
                    summary = data.get("portfolio_summary", {})
                    if summary:
                        # Total portfolio impact %
                        impact_str = summary.get("expected_portfolio_impact", "")
                        if impact_str:
                            match = re.search(r'([+-]?\d+(?:\.\d+)?)', impact_str)
                            if match:
                                add_truth("PORTFOLIO_IMPACT", "percent", float(match.group(1)))
                        
                        # Total portfolio P&L
                        pnl_str = summary.get("expected_portfolio_pnl", "")
                        if pnl_str:
                            match = re.search(r'\$\s*([+-]?\d{1,3}(?:,\d{3})*)', pnl_str)
                            if match:
                                val = float(match.group(1).replace(',', '').replace('+', ''))
                                add_truth("PORTFOLIO_LOSS", "dollar", abs(val))
                        
                        # Worst case VaR
                        var_str = summary.get("var_adjusted_pnl", "")
                        if var_str:
                            match = re.search(r'\$\s*([+-]?\d{1,3}(?:,\d{3})*)', var_str)
                            if match:
                                val = float(match.group(1).replace(',', '').replace('+', ''))
                                add_truth("WORST_CASE_VAR", "dollar", abs(val))
                    
                    # Parse macro_impacts
                    macro = data.get("macro_impacts", {})
                    if macro:
                        # Equity market impact
                        impact_str = macro.get("equity_market_impact", "")
                        if impact_str:
                            match = re.search(r'([+-]?\d+(?:\.\d+)?)', impact_str)
                            if match:
                                add_truth("EQUITY_IMPACT", "percent", float(match.group(1)))
                        
                        # Volatility spike
                        vol_str = macro.get("volatility_spike", "")
                        if vol_str:
                            match = re.search(r'\+?(\d+(?:\.\d+)?)', vol_str)
                            if match:
                                add_truth("VOL_SPIKE", "percent", float(match.group(1)))
                                    
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        
        return ground_truth

    def validate(self, response_content: str, message_history: List[Any]) -> Tuple[bool, Optional[str]]:
        """
        Main validation entry point.
        Returns (is_valid, error_message)
        """
        self.logger.graph_step("validator", "start", "Validating financial data consistency")
        
        claims = self.extract_claims(response_content)
        if not claims:
            self.logger.debug("No data claims found in response to validate.")
            return True, None
            
        truth = self.get_ground_truth(message_history)
        if not truth:
            self.logger.debug("No tool data (ground truth) found in history to validate against.")
            return True, None
            
        discrepancies = []
        for claim in claims:
            key = claim["key"]
            claim_type = claim["type"]
            claimed_value = claim["value"]
            unit = claim["unit"]
            
            if key in truth and claim_type in truth[key]:
                actual_value = truth[key][claim_type]
                
                # Calculate difference - allow 1% tolerance for rounding
                if actual_value != 0:
                    diff_pct = abs(claimed_value - actual_value) / abs(actual_value)
                else:
                    diff_pct = 0 if claimed_value == 0 else 1
                
                if diff_pct > 0.01:  # 1% threshold
                    discrepancies.append(
                        f"- **{key}** ({claim_type}): You stated {unit}{claimed_value}, but tool data shows {unit}{actual_value}."
                    )
                    self.logger.tool_call_error("validator", f"Mismatch for {key}: AI={claimed_value}, Tool={actual_value}")

        if discrepancies:
            error_msg = (
                "DATA INCONSISTENCY DETECTED:\n"
                "I found discrepancies between your response and the actual tool data results:\n"
                + "\n".join(discrepancies) + "\n\n"
                "Please RE-CHECK the tool outputs in the conversation history and provide a corrected response "
                "with the exact figures from the tools. Do not hallucinate or estimate values if real data is available."
            )
            return False, error_msg

        self.logger.graph_step("validator", "end", "Validation successful (all data matched)")
        return True, None

    def validate_structured(self, response_content: str, message_history: List[Any]) -> Dict[str, Any]:
        """
        Validates AI response and returns a structured report with detailed analysis.
        """
        self.logger.graph_step("validaator", "start", "Generating structured validation report")
        
        # Gather detailed analysis info
        message_length = len(response_content) if response_content else 0
        word_count = len(response_content.split()) if response_content else 0
        
        # Count tool messages in history
        tool_message_count = sum(1 for msg in message_history if isinstance(msg, ToolMessage))
        ai_message_count = sum(1 for msg in message_history if isinstance(msg, AIMessage))
        human_message_count = sum(1 for msg in message_history if isinstance(msg, HumanMessage))
        
        claims = self.extract_claims(response_content)
        truth = self.get_ground_truth(message_history)
        
        # Build detailed analysis section
        analysis_details = {
            "message_stats": {
                "character_count": message_length,
                "word_count": word_count,
                "has_content": message_length > 0
            },
            "history_stats": {
                "total_messages": len(message_history),
                "tool_messages": tool_message_count,
                "ai_messages": ai_message_count,
                "human_messages": human_message_count
            },
            "extraction_patterns_checked": [
                "Ticker + Price patterns (e.g., 'AAPL $150.25')",
                "Ticker + Percentage patterns (e.g., 'NVDA +3.2%')",
                "Ticker + Dollar Loss/Gain patterns (e.g., 'MSFT -$1,500')",
                "Markdown/Text table rows",
                "Named metrics (Portfolio Impact, VaR, etc.)"
            ],
            "ground_truth_sources": list(truth.keys()) if truth else [],
            "claims_extracted": len(claims),
            "claim_details": [
                {
                    "key": c["key"], 
                    "type": c["type"], 
                    "value": c["value"], 
                    "unit": c["unit"]
                } for c in claims
            ] if claims else []
        }
        
        report = {
            "is_valid": True,
            "total_claims": len(claims),
            "verified_claims": 0,
            "failed_claims": 0,
            "unverified_claims": 0,
            "checks": [],
            "analysis": analysis_details,
            "summary": ""
        }
        
        # Build detailed summary based on what we found
        if not response_content or message_length == 0:
            report["summary"] = (
                f"📭 **Empty Message Received**\n\n"
                f"The message content was empty (0 characters). There is nothing to validate.\n\n"
                f"**Session Context:**\n"
                f"• Conversation history: {len(message_history)} messages\n"
                f"• Tool outputs available: {tool_message_count}\n"
                f"• Ground truth data for: {', '.join(truth.keys()) if truth else 'None'}"
            )
            return report
        
        if not claims:
            # Build detailed explanation of what we looked for
            report["summary"] = (
                f"🔍 **Validation Complete - No Financial Data Claims Found**\n\n"
                f"**Message Analyzed:**\n"
                f"• Length: {message_length} characters, {word_count} words\n\n"
                f"**Patterns Searched:**\n"
                f"• Stock ticker + price (e.g., 'AAPL $150.25', 'TSLA at $400')\n"
                f"• Ticker + percentage impact (e.g., 'NVDA +3.2%', 'MSFT Impact -5%')\n"
                f"• Ticker + dollar amounts (e.g., 'AAPL $500 loss')\n"
                f"• Table data with tickers and values\n"
                f"• Named portfolio metrics (Total Impact, VaR, etc.)\n\n"
                f"**Session Context:**\n"
                f"• Conversation history: {len(message_history)} messages\n"
                f"• Tool outputs available: {tool_message_count}\n"
                f"• Ground truth symbols: {', '.join(truth.keys()) if truth else 'None'}\n\n"
                f"**Conclusion:** This message appears to be conversational/descriptive text without specific "
                f"numerical financial claims that require validation against tool data."
            )
            return report

        if not truth:
            report["summary"] = (
                f"⚠️ **Claims Found, But No Reference Data Available**\n\n"
                f"**Extracted Claims ({len(claims)}):**\n" +
                "\n".join([f"• {c['key']}: {c['unit']}{c['value']} ({c['type']})" for c in claims[:10]]) +
                (f"\n• ... and {len(claims) - 10} more" if len(claims) > 10 else "") +
                f"\n\n**Issue:** No tool outputs (API calls, searches) were found in the session history "
                f"to verify these claims against.\n\n"
                f"**Session Context:**\n"
                f"• Conversation history: {len(message_history)} messages\n"
                f"• Tool messages: {tool_message_count}\n\n"
                f"**Recommendation:** Use tool functions (like validate_stock_price, portfolio analysis) "
                f"to fetch real data before making claims."
            )
            for claim in claims:
                report["unverified_claims"] += 1
                report["checks"].append({
                    "key": claim["key"],
                    "type": claim["type"],
                    "claimed": claim["value"],
                    "unit": claim["unit"],
                    "actual": None,
                    "status": "unverified",
                    "reason": "No tool data available for comparison"
                })
            return report

        # We have both claims and ground truth - do the validation
        discrepancies_count = 0
        for claim in claims:
            key = claim["key"]
            claim_type = claim["type"]
            claimed_value = claim["value"]
            unit = claim["unit"]
            
            check_item = {
                "key": key,
                "type": claim_type,
                "claimed": claimed_value,
                "unit": unit,
                "actual": None,
                "status": "unknown",
                "diff_pct": 0
            }
            
            if key in truth and claim_type in truth[key]:
                actual_value = truth[key][claim_type]
                check_item["actual"] = actual_value
                
                # Calculate difference
                if actual_value != 0:
                    diff_pct = abs(claimed_value - actual_value) / abs(actual_value)
                else:
                    diff_pct = 0 if claimed_value == 0 else 1
                    
                check_item["diff_pct"] = round(diff_pct * 100, 2)
                
                if diff_pct <= 0.01:
                    check_item["status"] = "passed"
                    report["verified_claims"] += 1
                else:
                    check_item["status"] = "failed"
                    report["failed_claims"] += 1
                    discrepancies_count += 1
            else:
                check_item["status"] = "unverified"
                check_item["reason"] = f"No {claim_type} data for '{key}' in tool results"
                report["unverified_claims"] += 1
            
            report["checks"].append(check_item)

        # Build final summary
        if discrepancies_count > 0:
            report["is_valid"] = False
            failed_items = [c for c in report["checks"] if c["status"] == "failed"]
            report["summary"] = (
                f"❌ **Validation Failed - Data Inconsistencies Detected**\n\n"
                f"**Results:**\n"
                f"• ✅ Verified: {report['verified_claims']}\n"
                f"• ❌ Failed: {report['failed_claims']}\n"
                f"• ⚠️ Unverified: {report['unverified_claims']}\n\n"
                f"**Discrepancies Found:**\n" +
                "\n".join([
                    f"• **{c['key']}**: Claimed {c['unit']}{c['claimed']}, "
                    f"Actual {c['unit']}{c['actual']} (diff: {c['diff_pct']}%)"
                    for c in failed_items[:5]
                ]) +
                (f"\n• ... and {len(failed_items) - 5} more" if len(failed_items) > 5 else "") +
                f"\n\n**Action Required:** Re-check tool outputs and correct the response."
            )
        elif report["verified_claims"] > 0:
            report["is_valid"] = True
            verified_items = [c for c in report["checks"] if c["status"] == "passed"]
            report["summary"] = (
                f"✅ **Validation Passed - All Data Verified**\n\n"
                f"**Results:**\n"
                f"• ✅ Verified: {report['verified_claims']}\n"
                f"• ⚠️ Unverified: {report['unverified_claims']}\n\n"
                f"**Verified Claims:**\n" +
                "\n".join([
                    f"• **{c['key']}**: {c['unit']}{c['claimed']} ✓ (matches source)"
                    for c in verified_items[:5]
                ]) +
                (f"\n• ... and {len(verified_items) - 5} more" if len(verified_items) > 5 else "") +
                f"\n\n**Conclusion:** All extracted financial data matches the tool output sources."
            )
        else:
            report["summary"] = (
                f"⚠️ **Validation Inconclusive**\n\n"
                f"**Extracted Claims ({len(claims)}):**\n" +
                "\n".join([f"• {c['key']}: {c['unit']}{c['value']} ({c['type']})" for c in claims[:5]]) +
                (f"\n• ... and {len(claims) - 5} more" if len(claims) > 5 else "") +
                f"\n\n**Available Ground Truth:**\n" +
                "\n".join([f"• {k}: {list(v.keys())}" for k, v in list(truth.items())[:5]]) +
                f"\n\n**Issue:** The claims found don't match the data types available in tool outputs. "
                f"For example, a price claim requires price data from a stock lookup tool."
            )

        self.logger.graph_step("validator", "end", f"Structured validation complete: {report['verified_claims']} passed, {report['failed_claims']} failed, {report['unverified_claims']} unverified")
        return report

def get_validator() -> ResponseValidator:
    """Singleton pattern for the validator."""
    return ResponseValidator()
