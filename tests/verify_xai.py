
import asyncio
import httpx
import json

async def verify_xai():
    url = "http://127.0.0.1:8000/api/chat"
    payload = {
        "message": "I want to start a company but I have no money. What should I do?", 
        "location": "India",
        "session_id": "test-xai-001"
    }
    
    print(f"Sending request to {url}...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = data.get("response", "")
            print("\n--- RESPONSE START ---")
            print(content)
            print("--- RESPONSE END ---\n")
            
            # Checks
            checks = {
                "Causal Explanation": "Causal Reasoning" in content or "Causal Explanation" in content,
                "Counterfactuals": "Counterfactual" in content or "If you" in content,
                "Ethical/Regulatory": "Compliance" in content or "Risk" in content,
                "Structure": "**Executive Summary**" in content
            }
            
            print("--- VERIFICATION RESULTS ---")
            all_pass = True
            for check, passed in checks.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"{check}: {status}")
                if not passed:
                    all_pass = False
            
            if all_pass:
                print("\nOverall: SUCCESS - XAI features detected.")
            else:
                print("\nOverall: PARTIAL/FAIL - Some XAI features missing.")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_xai())
