"""
Test for the search_domain_experts tool.
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.tools import search_domain_experts

def test_expert_search():
    """Test the expert search tool with a business topic."""
    print("Testing search_domain_experts tool...")
    
    result = search_domain_experts.invoke({
        "topic": "SaaS pricing strategy",
        "expertise_type": "founder",
        "max_results": 3
    })
    
    print("Result:")
    print(result)
    
    # Basic validation
    assert "error" not in result.lower() or "topic" in result
    assert "experts_found" in result or "case_studies" in result
    
    print("\n✅ Expert search test passed!")

if __name__ == "__main__":
    test_expert_search()
