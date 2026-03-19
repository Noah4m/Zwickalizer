# Zwickalizer

Minimal chat app built with:

- `frontend`: React UI
- `backend`: FastAPI proxy
- `agent`: FastAPI Gemini wrapper

Current flow:

1. Frontend sends a chat request to `backend`
2. Backend forwards it to `agent`
3. Agent calls Gemini and returns a plain text answer

Run with:

```bash
docker compose up --build
```

Required environment variable:

```bash
GEMINI_API_KEY=your-gemini-api-key
```


## MongoDB Connect
```bash
docker network connect zwickalizer_matai-net txp-database
```
