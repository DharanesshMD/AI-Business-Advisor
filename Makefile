# AI Business Advisor - Setup and Run

.PHONY: run setup clean help

help:
	@echo "AI Business Advisor - Multi-Service Local Run"
	@echo ""
	@echo "Usage:"
	@echo "  make run    - Set up environment and run both frontend and backend (Preferred)"
	@echo "  make setup  - Install dependencies and create virtual environment"
	@echo "  make clean  - Remove virtual environment and logs"
	@echo ""

run:
	@./run.sh

setup:
	@echo "📦 Setting up virtual environment..."
	@python3 -m venv venv
	@echo "🛠️  Installing dependencies..."
	@./venv/bin/pip install --upgrade pip setuptools wheel
	@./venv/bin/pip install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env; echo "⚠️ Created .env from .env.example. Please add your NVIDIA_API_KEY."; fi

clean:
	@rm -rf venv/ logs/ *.sqlite
	@echo "🧹 Cleaned virtual environment and temporary files."
