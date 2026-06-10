#!/usr/bin/env python
"""Launch the Job Finder web app locally.

    python run.py            # serves http://127.0.0.1:8000
    python run.py --port 9000 --open
"""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Job Finder web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="open the browser automatically")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    args = parser.parse_args()

    url = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"
    print(f"\n  Job Finder running at  {url}\n  (press Ctrl+C to stop)\n")

    if args.open:
        def _open():
            time.sleep(1.2)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    import uvicorn
    uvicorn.run("jobfinder.web:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
