"""
Knowledge Graph Agent for ARIA.
Enables graph-based reasoning to discover hidden risk correlations,
supplier dependencies, and macro sensitivities using Neo4j.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any

from neo4j import GraphDatabase

from backend.config import get_settings

logger = logging.getLogger("advisor.knowledge_graph")


class KnowledgeGraphAgent:
    """
    Agent responsible for Knowledge Graph queries and graph-based reasoning.
    Uses Neo4j to store and traverse company relationships, risks, and dependencies.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.driver = None
        
        # Initialize Neo4j connection
        if self.settings.NEO4J_URI:
            try:
                self.driver = GraphDatabase.driver(
                    self.settings.NEO4J_URI,
                    auth=(self.settings.NEO4J_USER, self.settings.NEO4J_PASSWORD)
                )
                self._verify_connectivity()
            except Exception as e:
                logger.error(f"Neo4j connection failed: {e}")
    
    def _verify_connectivity(self):
        """Verify Neo4j connection is active."""
        if self.driver:
            try:
                self.driver.verify_connectivity()
                logger.info("Connected to Neo4j Knowledge Graph.")
            except Exception as e:
                logger.error(f"Neo4j connectivity check failed: {e}")
    
    def close(self):
        """Close the Neo4j driver."""
        if self.driver:
            self.driver.close()
    
    async def setup_schema(self):
        """Create indexes and constraints for the Knowledge Graph."""
        queries = [
            "CREATE CONSTRAINT company_ticker IF NOT EXISTS FOR (c:Company) REQUIRE c.ticker IS UNIQUE",
            "CREATE CONSTRAINT sector_name IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT risk_name IF NOT EXISTS FOR (r:RiskCategory) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT macro_name IF NOT EXISTS FOR (m:MacroFactor) REQUIRE m.name IS UNIQUE",
            "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
        ]
        
        if not self.driver:
            logger.warning("No Neo4j connection - skipping schema setup")
            return
        
        def _run_queries(tx):
            for q in queries:
                try:
                    tx.run(q)
                except Exception as e:
                    logger.debug(f"Schema query note: {e}")
        
        try:
            with self.driver.session() as session:
                await asyncio.to_thread(session.execute_write, _run_queries)
            logger.info("Knowledge Graph schema initialized.")
        except Exception as e:
            logger.error(f"Schema setup error: {e}")
    
    async def discover_related_risks(self, symbol: str) -> Dict[str, Any]:
        """
        Traverse the Knowledge Graph to find connected risks.
        
        This discovers:
        - Direct risks the company faces
        - Risks inherited from its sector
        - Macro factors affecting its sector
        - Supplier dependencies and their risks
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dictionary containing discovered relationships and risks
        """
        symbol = symbol.upper()
        
        if not self.driver:
            return {
                "symbol": symbol,
                "error": "Knowledge Graph not available (Neo4j not connected)",
                "direct_risks": [],
                "sector_context": None,
                "supplier_risks": [],
                "macro_sensitivities": []
            }
        
        query = """
        MATCH (c:Company {ticker: $symbol})
        OPTIONAL MATCH (c)-[:FACES_RISK]->(r:RiskCategory)
        OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector)
        OPTIONAL MATCH (s)-[:SENSITIVE_TO]->(m:MacroFactor)
        OPTIONAL MATCH (c)-[:DEPENDS_ON]->(sup:Supplier)
        OPTIONAL MATCH (sup)-[:FACES_RISK]->(sr:RiskCategory)
        RETURN c.ticker as ticker,
               c.name as company_name,
               s.name as sector,
               collect(DISTINCT r.name) as direct_risks,
               collect(DISTINCT m.name) as macro_factors,
               collect(DISTINCT {supplier: sup.name, risks: collect(DISTINCT sr.name)}) as supplier_data
        """
        
        def _execute(tx):
            result = tx.run(query, symbol=symbol)
            return result.single()
        
        try:
            with self.driver.session() as session:
                record = await asyncio.to_thread(session.execute_read, _execute)
            
            if not record or not record["ticker"]:
                return {
                    "symbol": symbol,
                    "message": f"No data found in Knowledge Graph for {symbol}. Use the filings search tool first to populate the graph.",
                    "direct_risks": [],
                    "sector_context": None,
                    "supplier_risks": [],
                    "macro_sensitivities": []
                }
            
            # Process supplier data
            supplier_risks = []
            for sup in record["supplier_data"]:
                if sup.get("supplier"):
                    supplier_risks.append({
                        "supplier": sup["supplier"],
                        "risks": sup.get("risks", [])
                    })
            
            return {
                "symbol": symbol,
                "company_name": record["company_name"],
                "sector_context": {
                    "sector": record["sector"],
                    "macro_factors": record["macro_factors"]
                } if record["sector"] else None,
                "direct_risks": record["direct_risks"],
                "supplier_risks": supplier_risks,
                "macro_sensitivities": record["macro_factors"],
                "insight": self._generate_insight(
                    record["direct_risks"],
                    record["sector"],
                    record["macro_factors"],
                    supplier_risks
                )
            }
            
        except Exception as e:
            logger.error(f"Knowledge Graph query error: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "direct_risks": [],
                "sector_context": None,
                "supplier_risks": [],
                "macro_sensitivities": []
            }
    
    def _generate_insight(self, direct_risks: List, sector: str, 
                          macro_factors: List, supplier_risks: List) -> str:
        """Generate a human-readable insight from graph data."""
        insights = []
        
        if direct_risks:
            insights.append(f"Direct risk exposure: {', '.join(direct_risks[:3])}")
        
        if sector and macro_factors:
            factors = ', '.join(macro_factors[:3])
            insights.append(f"As a {sector} company, sensitive to: {factors}")
        
        if supplier_risks:
            risky_suppliers = [s["supplier"] for s in supplier_risks if s.get("risks")]
            if risky_suppliers:
                insights.append(f"Supply chain exposure via: {', '.join(risky_suppliers[:2])}")
        
        return " | ".join(insights) if insights else "No significant correlations discovered."
    
    async def get_company_context(self, symbol: str) -> Dict[str, Any]:
        """
        Get all stored knowledge about a company.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Complete context from Knowledge Graph
        """
        symbol = symbol.upper()
        
        if not self.driver:
            return {"error": "Knowledge Graph not available"}
        
        query = """
        MATCH (c:Company {ticker: $symbol})
        OPTIONAL MATCH (c)-[fr:FACES_RISK]->(r:RiskCategory)
        OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector)
        OPTIONAL MATCH (c)-[:DEPENDS_ON]->(sup:Supplier)
        RETURN c {.*, 
            risks: collect(DISTINCT {category: r.name, description: fr.description}),
            sector: s.name,
            suppliers: collect(DISTINCT sup.name)
        } as company
        """
        
        def _execute(tx):
            result = tx.run(query, symbol=symbol)
            return result.single()
        
        try:
            with self.driver.session() as session:
                record = await asyncio.to_thread(session.execute_read, _execute)
            
            if not record:
                return {"symbol": symbol, "message": "No data found in Knowledge Graph"}
            
            return record["company"]
            
        except Exception as e:
            logger.error(f"Company context query error: {e}")
            return {"error": str(e)}
    
    async def store_company_sector(self, symbol: str, sector: str, name: str = None):
        """
        Store or update a company's sector in the Knowledge Graph.
        
        Args:
            symbol: Stock ticker
            sector: Industry sector name
            name: Optional company name
        """
        if not self.driver:
            return
        
        query = """
        MERGE (c:Company {ticker: $symbol})
        SET c.name = COALESCE($name, c.name)
        MERGE (s:Sector {name: $sector})
        MERGE (c)-[:IN_SECTOR]->(s)
        """
        
        def _execute(tx):
            tx.run(query, symbol=symbol.upper(), sector=sector, name=name)
        
        try:
            with self.driver.session() as session:
                await asyncio.to_thread(session.execute_write, _execute)
            logger.info(f"Stored sector relationship: {symbol} -> {sector}")
        except Exception as e:
            logger.error(f"Store sector error: {e}")
    
    async def store_macro_sensitivity(self, sector: str, factor: str, factor_type: str = "economic"):
        """
        Link a sector to a macro factor.
        
        Args:
            sector: Industry sector name
            factor: Macro factor name (e.g., "Interest Rates", "Oil Prices")
            factor_type: Type of factor (economic, commodity, regulatory)
        """
        if not self.driver:
            return
        
        query = """
        MERGE (s:Sector {name: $sector})
        MERGE (m:MacroFactor {name: $factor})
        SET m.type = $factor_type
        MERGE (s)-[:SENSITIVE_TO]->(m)
        """
        
        def _execute(tx):
            tx.run(query, sector=sector, factor=factor, factor_type=factor_type)
        
        try:
            with self.driver.session() as session:
                await asyncio.to_thread(session.execute_write, _execute)
            logger.info(f"Stored macro sensitivity: {sector} -> {factor}")
        except Exception as e:
            logger.error(f"Store macro sensitivity error: {e}")


# Singleton instance
_kg_agent = None

def get_knowledge_graph_agent() -> KnowledgeGraphAgent:
    """Get singleton Knowledge Graph agent instance."""
    global _kg_agent
    if _kg_agent is None:
        _kg_agent = KnowledgeGraphAgent()
    return _kg_agent
