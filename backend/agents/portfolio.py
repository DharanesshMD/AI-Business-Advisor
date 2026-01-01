"""
Portfolio Analysis Agent for ARIA.
Handles quantitative financial analysis, risk metrics, and market data integration.
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats
import finnhub
import redis.asyncio as redis

from backend.config import get_settings

logger = logging.getLogger("advisor.portfolio")

class PortfolioAgent:
    """
    Agent responsible for portfolio quantitative analysis and risk assessment.
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # Initialize Finnhub client
        if self.settings.FINNHUB_API_KEY:
            self.finnhub_client = finnhub.Client(api_key=self.settings.FINNHUB_API_KEY)
        else:
            logger.warning("FINNHUB_API_KEY not set. Market data will be mocked.")
            self.finnhub_client = None
            
        # Initialize Redis client
        self.redis = redis.from_url(self.settings.REDIS_URI, decode_responses=True)
        
    async def get_market_data(self, symbol: str, days: int = 252) -> pd.DataFrame:
        """
        Fetch historical market data for a symbol.
        Tries Redis cache first, then falls back to Finnhub.
        Default: 1 year of trading days (252).
        """
        symbol = symbol.upper()
        cache_key = f"market_data:{symbol}:{days}"
        
        # Try cache
        try:
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {symbol}")
                df_json = json.loads(cached_data)
                df = pd.DataFrame(df_json)
                df.index = pd.to_datetime(df.index)
                return df
        except Exception as e:
            logger.error(f"Redis error: {e}")
            
        # Fetch from API
        if not self.finnhub_client:
            return self._generate_mock_data(symbol, days)
            
        try:
            end_time = int(datetime.now().timestamp())
            start_time = int((datetime.now() - timedelta(days=days * 1.5)).timestamp()) # Buffer for weekends
            
            # Resolution 'D' = Daily
            res = await asyncio.to_thread(
                self.finnhub_client.stock_candles, 
                symbol, 'D', start_time, end_time
            )
            
            if res['s'] != 'ok':
                logger.error(f"Finnhub error for {symbol}: {res.get('s')}")
                return self._generate_mock_data(symbol, days)
                
            df = pd.DataFrame({
                'date': pd.to_datetime(res['t'], unit='s'),
                'open': res['o'],
                'high': res['h'],
                'low': res['l'],
                'close': res['c'],
                'volume': res['v']
            })
            df.set_index('date', inplace=True)
            
            # Cache result (expire in 1 hour)
            try:
                await self.redis.setex(
                    cache_key, 
                    3600, 
                    df.to_json(date_format='iso')
                )
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return self._generate_mock_data(symbol, days)

    def _generate_mock_data(self, symbol: str, days: int) -> pd.DataFrame:
        """Generate legitimate-looking mock data for testing/fallback."""
        logger.info(f"Generating mock data for {symbol}")
        dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
        
        # Deterministic random seed based on symbol for consistency
        seed = sum(ord(c) for c in symbol)
        np.random.seed(seed)
        
        # Random walk
        start_price = 100 + (seed % 100)
        returns = np.random.normal(0.001, 0.02, days) # Mean 0.1%, Std 2%
        price_path = start_price * (1 + returns).cumprod()
        
        df = pd.DataFrame({
            'open': price_path * (1 + np.random.normal(0, 0.005, days)),
            'high': price_path * (1 + abs(np.random.normal(0, 0.01, days))),
            'low': price_path * (1 - abs(np.random.normal(0, 0.01, days))),
            'close': price_path,
            'volume': np.random.randint(100000, 1000000, days)
        }, index=dates)
        return df

    def calculate_metrics(self, returns: pd.Series, risk_free_rate: float = 0.04) -> Dict[str, float]:
        """Calculate Sharpe and Sortino ratios."""
        if len(returns) < 2:
            return {
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "annualized_volatility": 0.0,
                "annualized_return": 0.0
            }
            
        # Annualized values
        mean_return = returns.mean() * 252
        std_dev = returns.std() * np.sqrt(252)
        
        # Sharpe Ratio
        sharpe = (mean_return - risk_free_rate) / std_dev if std_dev != 0 else 0
        
        # Sortino Ratio (downside risk only)
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252)
        sortino = (mean_return - risk_free_rate) / downside_std if downside_std != 0 else 0
        
        return {
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "annualized_volatility": round(std_dev, 4),
            "annualized_return": round(mean_return, 4)
        }

    def calculate_var(self, returns: pd.Series, confidence_level: float = 0.95) -> Dict[str, float]:
        """Calculate Value at Risk (VaR) and Conditional VaR (CVaR)."""
        if len(returns) < 2:
            return {"var": 0.0, "cvar": 0.0}
            
        # Parametric VaR (assuming normal distribution)
        mean = returns.mean()
        std = returns.std()
        var_parametric = abs(stats.norm.ppf(1 - confidence_level, mean, std))
        
        # Historical VaR
        var_historical = abs(np.percentile(returns, (1 - confidence_level) * 100))
        
        # CVaR (Expected Shortfall) - Average of losses exceeding VaR
        metrics_below_var = returns[returns <= -var_historical]
        cvar = abs(metrics_below_var.mean()) if len(metrics_below_var) > 0 else var_historical
        
        return {
            "var_95": round(var_historical, 4), # Returning historical as default
            "var_parametric": round(var_parametric, 4),
            "cvar_95": round(cvar, 4)
        }

    async def run_monte_carlo(self, 
                            mu: float, 
                            sigma: float, 
                            start_price: float, 
                            days: int = 30, 
                            simulations: int = 1000) -> Dict[str, Any]:
        """
        Run Monte Carlo simulations to project portfolio value.
        Uses Geometric Brownian Motion.
        """
        dt = 1/252
        
        # Run simulation in a separate thread to avoid blocking
        def _simulate():
            paths = np.zeros((days, simulations))
            paths[0] = start_price
            
            for t in range(1, days):
                # Z ~ N(0, 1)
                z = np.random.standard_normal(simulations)
                # S_t = S_{t-1} * exp((mu - 0.5*sigma^2)dt + sigma*sqrt(dt)*Z)
                drift = (mu - 0.5 * sigma**2) * dt
                diffusion = sigma * np.sqrt(dt) * z
                paths[t] = paths[t-1] * np.exp(drift + diffusion)
                
            return paths
            
        paths = await asyncio.to_thread(_simulate)
        
        # Calculate percentiles
        final_values = paths[-1]
        percentiles = {
            "p10": np.percentile(final_values, 10),
            "p50": np.percentile(final_values, 50),
            "p90": np.percentile(final_values, 90)
        }
        
        # Pick 5 random paths for visualization
        sample_paths = []
        for i in range(5):
            sample_paths.append(paths[:, i].tolist())
            
        return {
            "percentiles": percentiles,
            "sample_paths": sample_paths, # List of lists
            "days_projected": days
        }

    async def analyze_portfolio(self, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze a portfolio of assets.
        
        Args:
            holdings: List of dicts with 'symbol', 'quantity', 'purchase_price' (optional)
        """
        if not holdings:
            return {"error": "No holdings provided"}
            
        logger.info(f"Analyzing portfolio: {len(holdings)} positions")
        
        portfolio_df = pd.DataFrame()
        total_value = 0
        weights = {}
        
        # Fetch data for all assets
        tasks = [self.get_market_data(h['symbol']) for h in holdings]
        results = await asyncio.gather(*tasks)
        
        valid_holdings = []
        
        for i, df in enumerate(results):
            holding = holdings[i]
            if df.empty:
                logger.warning(f"No data for {holding['symbol']}")
                continue
                
            current_price = df['close'].iloc[-1]
            position_value = current_price * holding['quantity']
            total_value += position_value
            
            # Calculate daily returns for this asset
            df['returns'] = df['close'].pct_change()
            portfolio_df[holding['symbol']] = df['returns']
            
            valid_holdings.append({
                **holding,
                "current_price": current_price,
                "current_value": position_value,
                "profit_loss": (current_price - holding.get('purchase_price', current_price)) * holding['quantity'],
                "profit_loss_pct": (current_price / holding.get('purchase_price', current_price) - 1) if holding.get('purchase_price') else 0
            })
            
        if total_value == 0:
            return {"error": "Total portfolio value is zero"}
            
        # Calculate weights
        for h in valid_holdings:
            h['weight'] = h['current_value'] / total_value
            
        # Clean data
        portfolio_df.dropna(inplace=True)
        
        # Calculate portfolio returns (weighted sum of asset returns)
        # We need to rebalance daily to maintain weights? simple approx for now
        # Better: sum(asset_ret * weight)
        
        weighted_returns = pd.Series(0, index=portfolio_df.index)
        for h in valid_holdings:
            symbol = h['symbol']
            if symbol in portfolio_df.columns:
                weighted_returns += portfolio_df[symbol] * h['weight']
                
        # Run Analysis
        metrics = self.calculate_metrics(weighted_returns)
        risk = self.calculate_var(weighted_returns)
        
        # Monte Carlo on Portfolio
        sim = await self.run_monte_carlo(
            metrics['annualized_return'], 
            metrics['annualized_volatility'], 
            total_value
        )
        
        return {
            "summary": {
                "total_value": round(total_value, 2),
                "holdings_count": len(valid_holdings),
            },
            "metrics": metrics,
            "risk": risk,
            "projections": sim,
            "holdings": valid_holdings
        }

# Singleton instance
_portfolio_agent = None

def get_portfolio_agent():
    global _portfolio_agent
    if _portfolio_agent is None:
        _portfolio_agent = PortfolioAgent()
    return _portfolio_agent
