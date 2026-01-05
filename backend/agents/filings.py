"""
Financial Filings Agent for ARIA.
Analyzes SEC filings (10-K, 10-Q) and builds a Knowledge Graph.
"""

import logging
import asyncio
import json
from datetime import datetime

from neo4j import GraphDatabase
from openai import OpenAI

from backend.config import get_settings
from backend.agents.graph import create_openai_client
from backend.agents.utils import get_tavily_client

logger = logging.getLogger("advisor.filings")

class FilingsAgent:
    """
    Agent responsible for analyzing financial documents and KG construction.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.llm_client = create_openai_client()
        
        # Initialize Neo4j
        self.driver = None
        if self.settings.NEO4J_URI:
            try:
                self.driver = GraphDatabase.driver(
                    self.settings.NEO4J_URI, 
                    auth=(self.settings.NEO4J_USER, self.settings.NEO4J_PASSWORD)
                )
                self.verify_connectivity()
            except Exception as e:
                logger.error(f"Neo4j connection failed: {e}")
                
    def verify_connectivity(self):
        if self.driver:
            try:
                self.driver.verify_connectivity()
                logger.info("Connected to Neo4j.")
            except Exception as e:
                logger.error(f"Neo4j connectivity check failed: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    async def search_filings(self, symbol: str, year: int = None) -> str:
        """Search for latest 10-K Risk Factors section using Tavily."""
        year = year or datetime.now().year - 1
        query = f"{symbol} 10-K {year} 'Risk Factors' section text"
        
        logger.info(f"Searching filings: {query}")
        tavily = get_tavily_client()
        
        try:
            res = await asyncio.to_thread(
                tavily.search,
                query=query,
                search_depth="advanced",
                max_results=3,
                include_raw_content=True
            )
            
            # Aggregate content
            content = "\n\n".join([r.get('content', '')[:2000] for r in res.get('results', [])])
            return content
            
        except Exception as e:
            logger.error(f"Filings search error: {e}")
            return ""

    async def analyze_risks(self, symbol: str) -> dict:
        """
        Analyze filings to extract risks and store in Neo4j.
        """
        # 1. Get Text
        text = await self.search_filings(symbol)
        
        if not text:
            return {"error": "Could not retrieve filing text."}
            
        # 2. LLM Extraction
        prompt = f"""
        Extract key risk factors for {symbol} from the following 10-K text excerpts.
        Focus on operational, regulatory, and market risks.
        
        Text:
        {text[:4000]}...
        
        Return JSON:
        {{
            "risks": [
                {{ "category": "Supply Chain", "description": "..." }},
                {{ "category": "Regulation", "description": "..." }}
            ]
        }}
        """
        
        try:
            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=self.settings.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            risks = result.get("risks", [])
            
            # 3. Store in Neo4j
            if self.driver and risks:
                await self._store_risks(symbol, risks)
                
            return {
                "symbol": symbol,
                "risks": risks,
                "stored_in_graph": bool(self.driver)
            }
            
        except Exception as e:
            logger.error(f"Risk extraction error: {e}")
            return {"error": str(e)}

    async def _store_risks(self, symbol: str, risks: list):
        """Write risks to Neo4j graph."""
        query = """
        MERGE (c:Company {ticker: $symbol})
        WITH c
        UNWIND $risks as r
        MERGE (k:RiskCategory {name: r.category})
        MERGE (c)-[:FACES_RISK {description: r.description}]->(k)
        """
        
        def write_tx(tx):
            tx.run(query, symbol=symbol, risks=risks)
            
        try:
            # Neo4j python driver is sync by default unless using async driver
            # We imported GraphDatabase which is sync. asyncio.to_thread it.
            with self.driver.session() as session:
                await asyncio.to_thread(session.write_transaction, write_tx)
            logger.info(f"Stored {len(risks)} risks for {symbol} in Neo4j")
        except Exception as e:
            logger.error(f"Neo4j write error: {e}")

_filings_agent = None
def get_filings_agent():
    global _filings_agent
    if _filings_agent is None:
        _filings_agent = FilingsAgent()
    return _filings_agent
