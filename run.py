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

from jobfinder.config import settings


_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Job Finder web app.")
    # Defaults come from config (env-overridable): JOBFINDER_HOST / JOBFINDER_PORT.
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--open", action="store_true", help="open the browser automatically")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    parser.add_argument("--allow-lan", action="store_true",
                        help="permit serving beyond loopback (exposes your data on the network)")
    args = parser.parse_args()

    allow_lan = args.allow_lan or settings.allow_lan

    # Guard rail: binding a non-loopback host exposes every stored CV and cover
    # letter to the local network. Require an explicit opt-in; otherwise fall back
    # to loopback so the app still starts, but safely.
    if args.host not in _LOOPBACK and not allow_lan:
        print(f"\n  ! Refusing to bind {args.host} without --allow-lan — that would expose your\n"
              f"    CVs and cover letters on the network. Falling back to 127.0.0.1.\n"
              f"    Re-run with --allow-lan (or set JOBFINDER_ALLOW_LAN=1) on a trusted network.\n")
        args.host = "127.0.0.1"
    elif args.host not in _LOOPBACK and allow_lan:
        print(f"\n  ! LAN serving ENABLED — Job Finder will bind {args.host}:{args.port} with no login.\n"
              f"    Only do this on a network you trust. To reach it from another device, add the\n"
              f"    address you'll use to JOBFINDER_ALLOWED_HOSTS (e.g. your LAN IP or hostname);\n"
              f"    other Hosts are rejected as a DNS-rebinding defense.\n")

    url = f"http://{args.host if args.host not in ('0.0.0.0', '::') else '127.0.0.1'}:{args.port}"
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
