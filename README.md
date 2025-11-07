# MCP server and client (Python)

This repository contains examples for running an MCP server and client using the Model Context Protocol Python SDK and integrating with Google GenAI (Gemini).

## Quick start

1. Clone this repo
2. Install uv if you haven't already

```bash
# Mac/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

3. Rename the example environment file to `.env` and add your Gemini API key (can obtain it from Google AI Studio):

```bash
GEMINI_API_KEY=your_api_key_here
```

4. Install Python dependencies:

```bash
uv sync
```

5. Run the server and client with `uv run` (examples below assume scripts in `src/`):

Run the server:

```bash
uv run src/server.py
```

Run the client:

```bash
uv run src/client.py
```

If you want to see the MCP Inspector wrapper, then:

```bash
npx @modelcontextprotocol/inspector

uv run mcp dev src/server.py
```