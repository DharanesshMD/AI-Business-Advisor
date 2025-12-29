# AI Business Advisor

An AI-powered business advisory chatbot built with **NVIDIA Llama 3.1 Nemotron 70B**, featuring real-time web search, location-aware regulations, and a sophisticated business consultant persona.

![AI Business Advisor](https://img.shields.io/badge/NVIDIA-Nemotron%2070B-76b900?style=for-the-badge&logo=nvidia)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge)

## ✨ Features

- **🤖 ARIA Persona** - Senior Business Consultant with 20+ years of experience
- **🔍 Real-time Web Search** - Powered by Perplexity (Sonar) for current market data
- **📍 Location-Aware** - Advice tailored to local regulations and markets
- **⚡ Streaming Responses** - Real-time token streaming via WebSocket
- **🎨 Modern UI** - Premium dark theme with glassmorphism design
- **🐳 Docker Ready** - Containerized for easy deployment

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [NVIDIA API Key](https://build.nvidia.com) - For Nemotron 70B model
- [Perplexity API Key](https://docs.perplexity.ai) - For web search

### Installation

1. **Clone and navigate to the directory:**
   ```bash
   cd AI-Business-Advisor
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   copy .env.example .env
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

## 🐳 Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or build manually
docker build -t ai-business-advisor .
docker run -p 8000:8000 --env-file .env ai-business-advisor
```

## 📁 Project Structure

```
AI-Business-Advisor/
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI app with WebSocket
│   ├── config.py            # Environment configuration
│   └── agents/
│       ├── advisor.py       # ARIA persona & system prompt
│       ├── tools.py         # Perplexity search tools
│       └── graph.py         # LangGraph orchestration
├── frontend/
│   ├── index.html           # Chat interface
│   ├── styles.css           # Premium dark theme
│   └── app.js               # WebSocket client
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🔧 API Reference

### WebSocket: `/ws/chat`

Connect for streaming chat responses.

**Send Message:**
```json
{
  "type": "message",
  "content": "How do I register a startup in India?",
  "location": "India"
}
```

**Receive Events:**
- `token` - Streaming response tokens
- `tool_status` - Web search status
- `done` - Response complete
- `error` - Error message

### REST: `POST /api/chat`

Non-streaming chat endpoint.

```json
{
  "message": "What licenses do I need for a restaurant?",
  "location": "United States",
  "session_id": "optional-session-id"
}
```

### Health Check: `GET /health`

```json
{
  "status": "healthy",
  "version": "1.0.0-mvp",
  "model": "nvidia/llama-3.1-nemotron-70b-instruct"
}
```

## 🎯 Example Queries

- *"How do I register a tech startup in Bangalore, India?"*
- *"What are the GST requirements for an e-commerce business?"*
- *"Compare LLC vs Corporation for a consulting firm in the US"*
- *"What licenses do I need to start a food delivery app in Singapore?"*
- *"Explain the funding stages for a startup"*

## 🔒 Security Considerations

- API keys are stored in environment variables
- Non-root Docker user for container security
- CORS configured for frontend access
- Input sanitization in frontend

## 📈 Scaling to SaaS

To scale this MVP to a full SaaS product:

1. **Add Database** - PostgreSQL for user data, conversations
2. **Add Caching** - Redis for session management
3. **Add Auth** - JWT-based authentication
4. **Add Multi-tenancy** - Organization & user management
5. **Add Analytics** - Usage tracking & billing

## 📝 License

MIT License - See LICENSE file for details.

---

Built with ❤️ using NVIDIA NIM and LangGraph
