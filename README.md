# Zwickalizer

Minimal chat app built with:

- `frontend`: React UI
- `backend`: FastAPI proxy
- `agent`: FastAPI OpenAI wrapper

Current flow:

1. Frontend sends a chat request to `backend`
2. Backend forwards it to `agent`
3. Agent calls OpenAI and returns a plain text answer

Run with:

```bash
docker compose up --build
```

Required environment variable:

```bash
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4.1-mini
MONGO_URI=mongodb://host.docker.internal:27017
MONGO_DB=txp_clean
```

Compatibility note:
If your local `.env` already uses `OPEN_API_KEY`, the agent will still accept it.

MongoDB note:
By default, the agent container connects to MongoDB on your host via `host.docker.internal`.
If your database runs in another container, override `MONGO_URI` to that container hostname on the same Docker network.
