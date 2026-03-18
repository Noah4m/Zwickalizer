# MatAI — Material Testing AI Assistant

Chat with your test data using natural language.

## Stack

| Service      | Port | What it does |
|-------------|------|--------------|
| `db`        | 5432 | PostgreSQL — your test results |
| `mcp-server`| 8001 | Exposes DB as agent-callable tools |
| `stats-tool`| 8002 | scipy/statsmodels — real statistics |
| `agent`     | 8003 | Claude + LangGraph orchestrator |
| `backend`   | 8000 | FastAPI — bridges frontend ↔ agent |
| `frontend`  | 3000 | React chat UI |

## Quick start

```bash
# 1. Copy and fill in your API key
cp .env.example .env
# edit .env → set ANTHROPIC_API_KEY=sk-ant-...

# 2. Start everything
docker compose up --build

# 3. Open the UI
open http://localhost:3000
```

## Communication flow

```
User (browser :3000)
  └─→ backend :8000  /api/chat
        └─→ agent :8003  /chat
              ├─→ Anthropic API  (Claude, tool calling)
              ├─→ mcp-server :8001  /tools/*  (DB queries)
              └─→ stats-tool :8002  /stats/*  (scipy tests)
                    └─→ db :5432  (PostgreSQL)
```

## Try these queries

- *"What materials are in the database?"*
- *"Summarise tensile strength for Fancyplast 42"*
- *"Is tensile strength of Fancyplast 42 declining? Is it statistically significant?"*
- *"Compare Machine A vs Machine B for Fancyplast 42 tensile strength"*
- *"Does test temperature correlate with elongation for Fancyplast 42?"*

## Adding your real DB

Replace `db/init.sql` with your own schema, or point `DATABASE_URL` in
`docker-compose.yml` at your existing Postgres container on the same Docker
network.

## Adding more stats tools

Add a new `@app.post("/stats/your_test")` endpoint in `stats-tool/server.py`,
then add the corresponding tool definition in `agent/agent.py` under `TOOLS`.
Claude will start using it automatically when relevant.

## Folder structure

```
matai/
├── docker-compose.yml
├── .env.example
├── db/
│   └── init.sql
├── mcp-server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py          ← add DB tools here
├── stats-tool/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py          ← add stat tests here
├── agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── agent.py           ← tool definitions + agentic loop
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── index.css
        ├── App.jsx
        ├── Chat.jsx
        ├── Message.jsx    ← tool call audit trail UI
        └── Sidebar.jsx
```
