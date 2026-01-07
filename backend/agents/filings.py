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
        Analyze filings to extract risks, sector, and supplier dependencies.
        Stores enriched data in Neo4j Knowledge Graph.
        """
        # 1. Get Text
        text = await self.search_filings(symbol)
        
        if not text:
            return {"error": "Could not retrieve filing text."}
            
        # 2. LLM Extraction - Enhanced prompt for richer data
        prompt = f"""
        Extract key information for {symbol} from the following 10-K text excerpts.
        Focus on risks, business sector, and key suppliers/dependencies.
        
        Text:
        {text[:4000]}...
        
        Return JSON with this exact structure:
        {{
            "company_name": "Full company name",
            "sector": "Industry sector (e.g., Technology, Healthcare, Consumer Goods)",
            "risks": [
                {{ "category": "Supply Chain", "description": "Brief description" }},
                {{ "category": "Regulation", "description": "Brief description" }},
                {{ "category": "Market", "description": "Brief description" }}
            ],
            "suppliers": [
                "Key supplier or dependency name (company or resource)"
            ],
            "macro_factors": [
                "Key macro-economic factor affecting the business (e.g., Interest Rates, Currency, Oil Prices)"
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
            sector = result.get("sector", "")
            company_name = result.get("company_name", "")
            suppliers = result.get("suppliers", [])
            macro_factors = result.get("macro_factors", [])
            
            # 3. Store enriched data in Neo4j
            if self.driver:
                await self._store_enriched_data(
                    symbol, company_name, sector, risks, suppliers, macro_factors
                )
                
            return {
                "symbol": symbol,
                "company_name": company_name,
                "sector": sector,
                "risks": risks,
                "suppliers": suppliers,
                "macro_factors": macro_factors,
                "stored_in_graph": bool(self.driver)
            }
            
        except Exception as e:
            logger.error(f"Risk extraction error: {e}")
            return {"error": str(e)}

    async def _store_enriched_data(self, symbol: str, company_name: str, 
                                    sector: str, risks: list, 
                                    suppliers: list, macro_factors: list):
        """Write enriched company data to Neo4j Knowledge Graph."""
        
        # Main query: Create company, sector, and risk relationships
        main_query = """
        MERGE (c:Company {ticker: $symbol})
        SET c.name = $company_name
        WITH c
        
        // Create sector relationship
        FOREACH (s IN CASE WHEN $sector <> '' THEN [$sector] ELSE [] END |
            MERGE (sec:Sector {name: s})
            MERGE (c)-[:IN_SECTOR]->(sec)
        )
        
        WITH c
        UNWIND $risks as r
        MERGE (k:RiskCategory {name: r.category})
        MERGE (c)-[:FACES_RISK {description: r.description}]->(k)
        """
        
        # Supplier query
        supplier_query = """
        MATCH (c:Company {ticker: $symbol})
        UNWIND $suppliers as sup
        MERGE (s:Supplier {name: sup})
        MERGE (c)-[:DEPENDS_ON]->(s)
        """
        
        # Macro factors query - link to sector
        macro_query = """
        MATCH (sec:Sector {name: $sector})
        UNWIND $factors as f
        MERGE (m:MacroFactor {name: f})
        MERGE (sec)-[:SENSITIVE_TO]->(m)
        """
        
        try:
            with self.driver.session() as session:
                # Store main data
                def write_main(tx):
                    tx.run(main_query, symbol=symbol, company_name=company_name,
                           sector=sector, risks=risks)
                await asyncio.to_thread(session.execute_write, write_main)
                
                # Store suppliers
                if suppliers:
                    def write_suppliers(tx):
                        tx.run(supplier_query, symbol=symbol, suppliers=suppliers)
                    await asyncio.to_thread(session.execute_write, write_suppliers)
                
                # Store macro factors
                if sector and macro_factors:
                    def write_macro(tx):
                        tx.run(macro_query, sector=sector, factors=macro_factors)
                    await asyncio.to_thread(session.execute_write, write_macro)
                
            logger.info(f"Stored enriched data for {symbol}: {len(risks)} risks, "
                       f"sector={sector}, {len(suppliers)} suppliers, "
                       f"{len(macro_factors)} macro factors")
        except Exception as e:
            logger.error(f"Neo4j write error: {e}")

    async def _store_risks(self, symbol: str, risks: list):
        """Legacy method - kept for backwards compatibility."""
        await self._store_enriched_data(symbol, "", "", risks, [], [])

_filings_agent = None
def get_filings_agent():
    global _filings_agent
    if _filings_agent is None:
        _filings_agent = FilingsAgent()
    return _filings_agent

