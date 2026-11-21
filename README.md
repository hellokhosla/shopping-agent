# Team 12 — Retail Shopping Agent

Maven "Building Agentic AI Applications" capstone. The CALPAK demo storefront
connects its shopping assistant to the backend LangGraph search-and-compare
workflow and the configured PostgreSQL catalog.

## Architecture

The storefront submits a message to `app.py`. The backend graph extracts
search criteria with OpenAI, searches the configured database, and generates
a comparison from the returned products. The storefront displays verified
picks, matching variant prices and explicitly labeled near misses.

The static storefront product tiles are sample catalog snapshots; chat results
come from the selected database. This integration is CALPAK-specific; the
backend also supports Nordstrom through its CLI. Vector ranking is not enabled
by the storefront.

## Running locally

1. Install Git, Python 3.11+ and Docker Desktop. Start Docker Desktop.
2. Clone the repository, or pull the latest code in an existing checkout.
   Run all subsequent commands from the repository root:

   ```shell
   git clone https://github.com/hellokhosla/shopping-agent.git
   cd shopping-agent
   ```

3. Set up PostgreSQL and load the catalog using the
   [local PostgreSQL setup guide](backend/local_postgresql_database_setup.md).
   The backend defaults to the local database; `backend/database_target.json`
   can instead select `neon`. The first setup also starts a resumable embedding
   backfill which can take hours; chat uses exact and lexical search, not vectors.
4. Create and activate a Python environment, then install app and backend
   dependencies. On Windows PowerShell:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   On macOS:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

5. Create `backend/.env` in this checkout and set `OPENAI_API_KEY=your_key`.
   The file is git-ignored; never commit or share the key. Shopper prompts and
   matching product details are sent to OpenAI, and calls may incur charges.
6. With the environment activated, run:

   ```powershell
   python app.py
   ```

   Open the local URL printed by Gradio, normally <http://127.0.0.1:7860/>.
   Select **Ask the shopping assistant** and enter a CALPAK-related request.
   The app does not create a public sharing link. Stop it with Ctrl+C.

If chat reports a certificate verification error, check your organization's
approved proxy certificate and Python trust configuration with your network
administrator; do not disable TLS verification. If the database cannot connect,
check Docker Desktop and the connection settings in the local setup guide.

To run offline regression tests:

```powershell
python -m unittest tests.test_app
python -m unittest discover -s backend\tests -t .
```

## Code ownership

See [`OWNERS.md`](OWNERS.md) for the team breakdown. `app.py` is the integration
seam between the backend workflow and the frontend.
