import finnhub
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def test_finnhub():
    api_key = os.getenv("FINNHUB_API_KEY")
    print(f"Testing Finnhub with key: {api_key[:5]}...{api_key[-5:]}")
    
    finnhub_client = finnhub.Client(api_key=api_key)
    
    try:
        # Test basic profile fetch (usually always works if key is valid)
        profile = finnhub_client.company_profile2(symbol='AAPL')
        print(f"Company Profile (AAPL): {profile.get('name')}")
        
        # Test quote (real-time price)
        quote = finnhub_client.quote('AAPL')
        print(f"Current Price (AAPL): {quote.get('c')}")
        
        # Test candles (historical data) - this is what failed in the logs
        end_time = int(datetime.now().timestamp())
        start_time = int((datetime.now() - timedelta(days=30)).timestamp())
        
        try:
            res = finnhub_client.stock_candles('AAPL', 'D', start_time, end_time)
            print(f"Candles status: {res.get('s')}")
        except Exception as candle_error:
            print(f"Candle error specifically: {candle_error}")
            
    except Exception as e:
        print(f"Finnhub Test Failed: {e}")

if __name__ == "__main__":
    test_finnhub()
