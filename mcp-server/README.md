## MCP Servers

`mcp-server/` is now a container folder for multiple MCP-style services.

Current servers:

- `db/`: MongoDB-backed tools for querying and summarising material test data
- `plot/`: plotting tools that return structured chart payloads

Shared dependency files live in `requirements/`.

To add another tool family, copy the pattern:

1. Create a new folder under `mcp-server/` with its own `server.py` and `Dockerfile`.
2. Add a requirements file under `mcp-server/requirements/` if the server needs extra packages.
3. Register the service in `docker-compose.yml`.
4. Add the tool declaration and route mapping in `agent/agent.py`.
