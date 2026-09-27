# ContextAI 🤖

ContextAI is an intelligent personal AI assistant architecture built with modular components for context-aware conversation, intent classification, memory persistence, and multi-step agent orchestration.

---

## 🛠 Tech Stack

- **Backend API**: [FastAPI](https://fastapi.tiangolo.com/) (REST endpoints & routing)
- **Frontend UI**: [Streamlit](https://streamlit.io/) (Interactive dashboard & chat)
- **Agent Orchestration**: [LangGraph](https://github.com/langchain-ai/langgraph) (Stateful multi-actor agent flows)
- **LLM Abstraction**: [LiteLLM](https://github.com/BerriAI/litellm) (Unified interface across LLM providers)
- **Structured Persistence**: SQLite (Local structured memory & user metadata)
- **Vector Memory**: [ChromaDB](https://www.trychroma.com/) (Embeddings & semantic document retrieval)
- **Intent Classification**: scikit-learn (TF-IDF vectorizer + Logistic Regression)
- **Testing**: [pytest](https://pytest.org/)

---

## 📁 Project Structure

```text
ContextAI/
├── .env.example                # Sample environment configuration template
├── .gitignore                  # Git ignore rules for Python, SQLite, Chroma, and caches
├── README.md                   # Project overview and setup instructions
├── requirements.txt            # Minimal project dependencies
├── data/                       # Local runtime data (SQLite databases, vector stores)
│   └── .gitkeep
├── src/                        # Main source code
│   ├── backend/                # FastAPI backend application
│   │   ├── agent/              # LangGraph workflow definitions and agent state schemas
│   │   │   ├── graph.py
│   │   │   └── state.py
│   │   ├── api/                # FastAPI route controllers and API schemas
│   │   │   └── routes.py
│   │   ├── classifier/         # TF-IDF + Logistic Regression intent classifier
│   │   │   └── intent_classifier.py
│   │   ├── core/               # Configuration settings and shared utilities
│   │   │   └── config.py
│   │   ├── llm/                # LiteLLM provider client wrapper
│   │   │   └── client.py
│   │   ├── memory/             # Persistent storage (SQLite manager & ChromaDB store)
│   │   │   ├── sql_db.py
│   │   │   └── vector_store.py
│   │   └── main.py             # FastAPI entrypoint application
│   └── frontend/               # Streamlit UI application
│       └── app.py              # Streamlit entrypoint
└── tests/                      # Unit and integration test suite
    ├── test_agent.py           # Tests for agent state and graph compilation
    ├── test_api.py             # Tests for API endpoints and contracts
    └── test_classifier.py      # Tests for intent classification
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ installed

### 2. Set Up Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```
Update `.env` with your preferred LLM API keys and configuration parameters.

### 5. Running the Services

#### Run FastAPI Backend:
```bash
uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API docs will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

#### Run Streamlit Frontend:
```bash
streamlit run src/frontend/app.py
```
Frontend interface will be available at [http://localhost:8501](http://localhost:8501).

### 6. Running Tests

```bash
pytest
```
