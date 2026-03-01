# Yevrah Terminal

Terminal-based legal research tool using CourtListener API with dual search strategy (keyword + semantic).

## Overview

Yevrah takes natural language queries and executes parallel keyword (BM25) and semantic (vector) searches against CourtListener's database of millions of court opinions. An LLM interprets queries to extract search parameters, formulate optimized queries, and map jurisdictions. Results are reranked using Cohere and displayed with source tags. Users can select any result for full opinion analysis.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.8+ |
| LLM Provider | Groq (groq/compound model) |
| Legal Database | CourtListener API |
| Reranking | Cohere rerank-v4.0-fast |
| Terminal UI | Rich library |
| Entry Point | main.py |
| License | BSD License |

## Commands

```bash
# Setup
git clone https://github.com/legaltextai/yevrah_terminal.git
cd yevrah_terminal
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment (create .env file)
# Add: GROQ_API_KEY, COURTLISTENER_API_KEY, COHERE_API_KEY (optional)

# Run
python main.py

# Terminal Commands
exit, quit, q        # Exit application
new, reset           # Start new search session
help                 # Show help information
jurisdictions        # List all available court codes
1-10                 # Analyze full opinion for result #1-10
```

## Architecture

### Query Flow

```
User Input (natural language)
    ↓
Groq LLM (groq/compound)
    ├─ Extracts: semantic query, keyword query, jurisdiction, dates
    ├─ Handles Boolean operators (AND, OR, NOT, &, %)
    └─ Calls: execute_search_case_law tool
         ↓
CourtListener API (parallel execution)
    ├─ Keyword Search (20 results) → Top 5 by BM25
    └─ Semantic Search (20 results) → Cohere rerank → Top 5
         ↓
Display: 10 results with source tags (KEYWORD/SEMANTIC)
    ↓
User selects result # → Fetch full opinion → LLM analysis
```

### Module Breakdown

| File | Purpose |
|------|---------|
| `main.py` | Entry point, main conversation loop |
| `llm_client.py` | Groq API client, system prompts, tool calling |
| `tools.py` | Tool definitions, dual search logic, jurisdiction mapping, date parsing |
| `courtlistener.py` | CourtListener API client (keyword & semantic search) |
| `reranker.py` | Cohere rerank integration for semantic results |
| `formatter.py` | Terminal UI formatting with Rich library |
| `jurisdictions.py` | Court code reference (200+ courts) |

### Search Strategy

**Keyword Search (BM25):**
- Boolean operators and exact term matching
- Returns 20 results from CourtListener
- Shows top 5 by BM25 relevance score
- No reranking - trusts CourtListener's scoring

**Semantic Search (Vector):**
- Natural language and concept matching
- Returns 20 results from CourtListener's vector index
- Reranks all 20 results using Cohere rerank-v4.0-fast (if API key available)
- Shows top 5 after reranking
- Falls back to CourtListener's order if no Cohere key

### Jurisdiction Mapping Examples

| Natural Language | Court Codes |
|------------------|-------------|
| "California" | `cal calctapp ca9 cand cacd casd caed` |
| "California state" | `cal calctapp` |
| "Ninth Circuit" | `ca9` |
| "Supreme Court" | `scotus` |
| "Florida" | `fla flactapp ca11 flsd flmd flnd` |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROQ_API_KEY` | Yes | Query interpretation and opinion analysis with Groq LLM |
| `COURTLISTENER_API_KEY` | Yes | Access to CourtListener's search API (get from https://www.courtlistener.com/api/rest-info/) |
| `COHERE_API_KEY` | No | Semantic result reranking with Cohere rerank-v4.0-fast (get from https://cohere.com/) |

## Note

For company-wide development standards, see the main CLAUDE.md at /home/vncuser/Desktop/CLAUDE.md.

---

For company-wide development standards, see the main CLAUDE.md at `~/Desktop/CLAUDE.md`.

For centralized business, legal, marketing, and product documentation, see the [Adjudica Documentation Hub](~/Desktop/adjudica-documentation/CLAUDE.md) and the [Quick Index](~/Desktop/adjudica-documentation/ADJUDICA_INDEX.md).

---

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
