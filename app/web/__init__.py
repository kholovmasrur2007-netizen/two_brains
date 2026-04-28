"""Web UI for the two_brains pipeline.

A small FastAPI app that exposes the same orchestrator the CLI uses
behind a REST + WebSocket surface, plus a single-file HTML UI that
visualises every brain phase live.

Entry point:

    python -m app.web                # serve on http://127.0.0.1:8000
    python -m app.web --port 9000    # alternative port
"""
