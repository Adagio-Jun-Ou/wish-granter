# Wish-Granter

An AI-powered "omnipotent wish-granting machine": give it a wish in plain English and an LLM agent turns it into a multi-step plan, executes it, reflects, revises, and synthesizes a final result.

## How it works

- **Planning**: your wish is sent to an OpenAI-compatible chat endpoint (default model `glm-5.1`), which returns a JSON plan of concrete steps
- **7 capabilities** the planner can draw on:
  - `web_search` — DuckDuckGo search
  - `code_gen` — generate and run code
  - `file_io` — read/write files
  - `data_analysis` — analyze data
  - `web_scraper` — fetch and parse pages (BeautifulSoup)
  - `shell` — run shell commands
  - `knowledge` — query the LLM directly
- **Continuous thinking loop**: the engine iterates — execute a step, think, periodically reflect on progress with the LLM, and revise the plan when needed — then runs a final synthesis over everything it learned

## Entry points

- **CLI**: `wish-granter "I wish to ..."` (installed by `pip install -e .`)
- **Demo**: `python demo.py [wish]` — reads its API key from the `OHMYAPI_API_KEY` environment variable
- **Web dashboard**: `wish-granter --serve` — FastAPI app on port `8020` with a REST API (`/docs` for OpenAPI UI) and a live WebSocket event stream of the thinking log

## Install

```bash
pip install -e .
```

Dependencies: fastapi, uvicorn, pydantic, httpx, requests, beautifulsoup4, jinja2, python-multipart.

You need an OpenAI-compatible chat endpoint and API key:

```bash
# via flags
wish-granter --api-url https://api.example.com/v1/chat/completions \
             --api-key YOUR_KEY \
             --model glm-5.1 \
             "I wish to understand quantum computing"

# demo.py reads the key from the environment
export OHMYAPI_API_KEY=your-key
python demo.py
```

Other useful flags: `--max-iterations` (default 50), `--priority` (1–10), `--watch <wish-id>`, `--host` / `--port` for the web server.

## License

MIT — see [LICENSE](LICENSE).