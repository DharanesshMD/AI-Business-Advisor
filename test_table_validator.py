
import json
from backend.agents.validator import get_validator
from langchain_core.messages import ToolMessage, AIMessage

def test_table_validation():
    validator = get_validator()
    
    # Tool output
    history = [
        ToolMessage(
            content=json.dumps({"symbol": "AAPL", "price": 150.25}),
            tool_call_id="1"
        )
    ]
    
    # Markdown Table Response
    table_resp = """
### 📊 Key Data & Findings
| Metric | Value | Source |
|--------|-------|--------|
| AAPL Price | $150.25 | Yahoo Finance |
| NVDA Price | $500.00 | Market Data |
"""
    # Note: NVDA won't be checked because it's not in tool history
    
    is_valid, err = validator.validate(table_resp, history)
    print(f"Table Test 1 (Exact): Passed={is_valid}")
    
    # 2. Table with error
    bad_table = table_resp.replace("150.25", "160.00")
    is_valid, err = validator.validate(bad_table, history)
    print(f"Table Test 2 (Mismatched): Passed={is_valid}")
    if not is_valid:
        print(f"Error Message: {err}")

if __name__ == "__main__":
    test_table_validation()
