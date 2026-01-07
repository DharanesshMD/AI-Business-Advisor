
import json
from backend.agents.validator import get_validator
from langchain_core.messages import ToolMessage, AIMessage

def test_validator():
    validator = get_validator()
    
    # Setup history with some tool data
    history = [
        ToolMessage(
            content=json.dumps({"symbol": "AAPL", "price": 150.25, "currency": "USD"}),
            tool_call_id="1"
        ),
        ToolMessage(
            content=json.dumps({
                "portfolio_analysis": True, 
                "holdings": [{"symbol": "NVDA", "current_price": 500.0}]
            }),
            tool_call_id="2"
        )
    ]
    
    # 1. Correct response
    valid_resp = "AAPL is at $150.25 and NVDA is trading near $500.00."
    is_valid, err = validator.validate(valid_resp, history)
    print(f"Test 1 (Valid): Passed={is_valid}, Error={err}")
    
    # 2. Hallucinated AAPL price
    invalid_resp = "AAPL is currently at $180.00 while NVDA is fine at $500."
    is_valid, err = validator.validate(invalid_resp, history)
    print(f"Test 2 (Invalid AAPL): Passed={is_valid}")
    if not is_valid:
        print(f"Error Message: {err}")

    # 3. No prices to check
    neutral_resp = "Hello, how can I help you today?"
    is_valid, err = validator.validate(neutral_resp, history)
    print(f"Test 3 (Neutral): Passed={is_valid}")

if __name__ == "__main__":
    test_validator()
