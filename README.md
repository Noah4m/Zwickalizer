# MAT\\AI

MAT\\AI is an AI-assisted analysis workspace for materials-testing data. It combines a chat-driven interface, a FastAPI backend, an OpenAI-powered agent, and custom MCP servers to help users explore MongoDB test records, inspect measurement curves, and review suspicious outliers.

The project was built around ZwickRoell-style test data, where metadata and value columns are stored separately and linked through UUID-heavy identifiers. MAT\\AI hides that complexity behind a conversational workflow and a visual analysis UI.

## What It Does

- Search stored tests by customer, material, test type, tester, machine, or date
- Retrieve and visualize measurement/value-column data for a specific test
- Compare corresponding curves across two tests
- Turn raw tool results into tables and plots in the frontend
- Surface likely outliers for manual review in a dedicated workbench

## Product Overview

The UI has two main workspaces:

- `Chat`: ask questions about stored test data and inspect the returned metadata and plots in the Analysis Vault
- `Outliers`: review a ranked queue of suspicious tests, inspect why they were flagged, and decide what action to take

This is not a generic chatbot bolted onto a dashboard. The language model is connected to structured tools that query the database and resolve the measurement series behind each test.

## Architecture

The application is split into three services plus local MCP servers:

- `frontend`: React + Vite application for chat, charts, tables, and outlier review
- `backend`: FastAPI API gateway that receives frontend requests and forwards them to the agent
- `agent`: FastAPI service that calls OpenAI, starts MCP servers, exposes tool definitions to the model, and returns structured results
- `mcp-server/db`: MCP server for test discovery and value-column lookup in MongoDB
- `mcp-server/outliers`: MCP server for outlier detection and review payload generation

End-to-end request flow:

1. The frontend sends a request to `backend`
2. The backend forwards the request to `agent`
3. The agent starts the MCP toolbox, lets the model choose tools when needed, and executes those tools
4. Tool results are summarized for the model and returned in a chart-friendly format to the frontend
5. The frontend renders the assistant answer together with tables or plots

## Repository Structure

```text
frontend/       React app and analysis UI
backend/        FastAPI proxy between UI and agent
agent/          LLM orchestration, MCP client, outlier API
mcp-server/     MCP servers for database access and outlier detection
background_information/  Hackathon brief and supporting assets
docker-compose.yml       Local multi-service setup
```

## How The Data Layer Works

The backing dataset uses two main MongoDB collections:

- `_tests`: test metadata and declared value columns
- `valuecolumns_migrated`: numeric measurement/value arrays

To reconstruct a plotted signal, the system joins:

- `_tests._id` to `valuecolumns_migrated.metadata.refId`
- a derived child identifier from `test.valueColumns` to `valuecolumns_migrated.metadata.childId`

This is why the MCP database server matters: it encapsulates the join logic, handles UUID-based mappings, filters the data, and returns resolved measurement series in a format the rest of the app can use.

## MCP Tools

The database MCP server currently exposes tools for:

- listing customers
- finding tests with filters
- resolving value columns for one test
- comparing corresponding value columns across two tests

The outlier MCP server exposes a tool for:

- generating a small ranked review queue of suspicious tests based on sampled records and robust scoring

## Setup

### Prerequisites

- Docker and Docker Compose
- Access to the MongoDB dataset
- An OpenAI API key

### Environment Variables

Create a `.env` file from `.env.example`:

```bash
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4.1-mini
MONGO_URI=mongodb://host.docker.internal:27017
MONGO_DB=txp_clean
```

Notes:

- `OPEN_API_KEY` is also accepted by the agent for compatibility with older local setups
- `MONGO_URI` defaults to a MongoDB instance running on the host machine and exposed to Docker through `host.docker.internal`

### Run The Stack

```bash
docker compose up --build
```

Then open:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health`
- Agent health: `http://localhost:8003/health`

## MongoDB Notes

The project expects the test dataset to be available in MongoDB. If your database is running on your host machine, the default `MONGO_URI` should work. If it is running in another container, point `MONGO_URI` to that container hostname on the same Docker network.

For faster joins between `_tests` and `valuecolumns_migrated`, create this index:

```javascript
use txp_clean

db.valuecolumns_migrated.createIndex(
  { "metadata.refId": 1, "metadata.childId": 1 },
  { name: "refId_childId_idx" }
)
```

## Development Notes

- The frontend derives tables and charts from structured tool results returned by the agent
- Large value-column arrays are sampled before plotting to keep responses manageable
- The agent preserves raw tool use for the frontend while sending compact summaries back into model context
- Test IDs in this dataset may require literal curly braces, for example `{D1CB87C7-D89F-4583-9DA8-5372DC59F25A}`

## Main Tech Stack

- React, TypeScript, Vite, Tailwind, Recharts
- FastAPI and `httpx`
- OpenAI Python SDK
- MongoDB with `pymongo`
- MCP servers over stdio
- Docker Compose for local orchestration

## Why This Project Exists

Materials-testing datasets are rich but hard to navigate. Engineers often need to combine metadata lookup, signal retrieval, curve comparison, and anomaly review across schemas that were not designed for conversational use. MAT\\AI turns that workflow into a single interface where users can ask questions in plain language and immediately inspect the underlying data visually.
