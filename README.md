# AI Business Advisor

An AI-powered business advisory platform built with **NVIDIA Llama 3.3 Nemotron Super 49B**, featuring real-time web search, portfolio analysis, fact-checking, and a sophisticated business consultant persona (ARIA).

![NVIDIA](https://img.shields.io/badge/NVIDIA-Nemotron%2049B-76b900?style=for-the-badge&logo=nvidia)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge)
![CI](https://img.shields.io/github/actions/workflow/status/anomalyco/AI-Business-Advisor/ci.yml?label=CI&style=for-the-badge)

## Features

- **ARIA Persona** - Senior Business Consultant with 20+ years of experience
- **Multi-provider Web Search** - Tavily, Perplexity (Sonar), or DuckDuckGo; auto-selection supported
- **Location-Aware Advice** - Regulations and market context tailored to user's country
- **Portfolio Analysis** - Monte Carlo VaR/CVaR stress testing with live or mock price data
- **Fact-Checking Pipeline** - Automated validation of AI responses against retrieved sources
- **Knowledge Graph** - Neo4j-backed entity relationship tracking across conversations
- **Streaming Responses** - Real-time token streaming via WebSocket with live thinking indicators
- **Durable History** - PostgreSQL-backed conversation persistence (in-memory fallback when unavailable)
- **Modern UI** - Premium dark theme with glassmorphism design
- **Docker Ready** - Containerized for easy deployment

## Quick Start

### Prerequisites

- Python 3.11+
- [NVIDIA API Key](https://build.nvidia.com) — for the Nemotron 49B model
- [Tavily API Key](https://tavily.com) — primary web search (free tier available)
- Optional: Perplexity, Finnhub, Neo4j, PostgreSQL keys/URIs for full feature set

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/anomalyco/AI-Business-Advisor.git
   cd AI-Business-Advisor
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/macOS
   # venv\Scripts\activate         # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

5. **Run the application:**
   ```bash
   python -m uvicorn backend.main:app --reload
   ```

6. **Open in browser:**
   ```
   http://localhost:8000
   ```

## Docker Deployment

```bash
# Build and run with Docker Compose (includes PostgreSQL + Neo4j)
docker-compose up --build

# Or build manually
docker build -t ai-business-advisor .
docker run -p 8000:8000 --env-file .env ai-business-advisor
```

## Project Structure

```
AI-Business-Advisor/
├── .github/
│   └── workflows/
│       └── ci.yml               # CI: unit tests (py3.11+3.12), lint, docker build
├── backend/
│   ├── main.py                  # FastAPI app entry point & lifespan
│   ├── config.py                # Pydantic-settings environment config
│   ├── models.py                # Strict Pydantic request/response validation
│   ├── state.py                 # Shared mutable state (connections, histories)
│   ├── db.py                    # PostgreSQL async persistence (asyncpg)
│   ├── logger.py                # Structured request/session logger
│   ├── routers/
│   │   ├── chat.py              # REST /api/chat + WebSocket /ws/chat
│   │   ├── portfolio.py         # REST /api/portfolio/analyze + WebSocket /ws/portfolio
│   │   └── validation.py        # REST /api/validate (fact-check endpoint)
│   └── agents/
│       ├── advisor.py           # ARIA persona & system prompt
│       ├── graph.py             # LangGraph orchestration (agent + tools + fact_check)
│       ├── tools.py             # Multi-provider search tools
│       ├── validator.py         # Response fact-checking & validation
│       ├── portfolio.py         # Monte Carlo stress-test engine
│       ├── stress_test.py       # VaR / CVaR calculations
│       ├── knowledge_graph.py   # Neo4j entity extraction & relationship tracking
│       ├── sentiment.py         # Market sentiment analysis
│       ├── filings.py           # SEC filings retrieval
│       └── utils.py             # Shared agent utilities
├── frontend/
│   ├── index.html               # Chat interface
│   ├── styles.css               # Premium dark theme with glassmorphism
│   └── app.js                   # WebSocket client + fact-check display
├── tests/
│   ├── conftest.py              # Shared pytest fixtures
│   ├── test_models.py           # 26 Pydantic validation unit tests
│   ├── test_chat_helpers.py     # 12 helper function unit tests
│   └── test_api.py              # 14 endpoint contract tests
├── pytest.ini                   # Pytest configuration
├── requirements.txt             # All dependencies pinned
├── Dockerfile
├── docker-compose.yml           # App + PostgreSQL + Neo4j + Redis
└── .env.example
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `NVIDIA_API_KEY` | Yes | NVIDIA NIM API key |
| `TAVILY_API_KEY` | Yes | Tavily web search key |
| `SONAR_API_KEY` | No | Perplexity Sonar key (for `search_provider=perplexity`) |
| `FINNHUB_API_KEY` | No | Finnhub key for live price data |
| `POSTGRES_URI` | No | PostgreSQL DSN — enables durable history |
| `NEO4J_URI` | No | Neo4j bolt URI — enables knowledge graph |
| `NEO4J_PASSWORD` | No | Neo4j password |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: `http://localhost:8000`) |
| `REQUIRE_AUTH` | No | Set to `True` to enable JWT authentication on endpoints (default: `False`) |
| `JWT_SECRET_KEY` | No | Secret key used to verify tokens |

## API Reference

### WebSocket: `/ws/chat`

Streaming chat with real-time thinking indicators.

**Send:**
```json
{
  "type": "message",
  "content": "How do I register a startup in India?",
  "location": "India",
  "search_provider": "tavily"
}
```
`search_provider` options: `tavily` | `perplexity` | `duckduckgo` | `auto`

**Receive events:**
| Type | Description |
|---|---|
| `system` | Connection confirmation + session ID |
| `thinking` | Live reasoning step (icon, label, message) |
| `thinking_done` | Thinking phase complete — response begins |
| `token` | Streaming response chunk |
| `tool_status` | Web search status (tool name, query) |
| `fact_check` | Validation report (claims, sources, verdict) |
| `done` | Response complete |
| `error` | Error message |

### REST: `POST /api/chat`

Non-streaming chat endpoint.

```json
{
  "message": "What licenses do I need for a restaurant?",
  "location": "United States",
  "session_id": "optional-uuid"
}
```

Constraints: `message` 1–4,000 chars, `location` max 100 chars.

### REST: `POST /api/portfolio/analyze`

```json
{
  "holdings": [
    {"symbol": "AAPL", "quantity": 10, "purchase_price": 150.0}
  ],
  "simulations": 1000,
  "days": 30
}
```

Constraints: 1–50 holdings, simulations 100–10,000, days 1–365.
Returns VaR, CVaR, stress-test scenarios. Includes `"warning"` key when using mock price data.

### REST: `POST /api/deal/analyze`

```json
{
  "target_symbol": "MSFT",
  "peer_symbols": ["AAPL", "GOOGL"],
  "acquirer_market_share": 20.0,
  "target_market_share": 10.0
}
```

Returns M&A Deal Intelligence report (DCF, Comparables, Precedent Transactions, HHI risk).
Includes `"warning"` key when live data is unavailable and mock metrics are used.

### REST: `POST /api/validate`

```json
{
  "session_id": "your-session-id",
  "content": "The claim to validate"
}
```

### Health Check: `GET /health`

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "model": "nvidia/llama-3.3-nemotron-super-49b-v1"
}
```

## Running Tests

```bash
# Unit tests only (no live API calls required)
python -m pytest tests/test_models.py tests/test_chat_helpers.py tests/test_api.py -v

# All tests (integration tests require live API keys in .env)
python -m pytest -v
```

## Example Queries

- *"How do I register a tech startup in Bangalore, India?"*
- *"What are the GST requirements for an e-commerce business?"*
- *"Compare LLC vs Corporation for a consulting firm in the US"*
- *"What licenses do I need to start a food delivery app in Singapore?"*
- *"Analyze my portfolio: 10 shares of AAPL at $150, 5 MSFT at $300"*

## Security & Hardening

- **Authentication**: Opt-in JWT bearer token validation on all endpoints
- **Rate Limiting**: `slowapi` limits API requests (default 10/min for chat, 5/min for compute)
- **Input Validation**: All request fields validated with strict Pydantic bounds
- **CORS**: Restricted to configured origins (no wildcard `*`)
- **Error Handling**: Responses never expose internal exception details
- **Environment**: API keys stored in environment variables only
- **Container**: Non-root Docker user for container security

## License

MIT License — see LICENSE file for details.

---

Built with NVIDIA NIM and LangGraph
