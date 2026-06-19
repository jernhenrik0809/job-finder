"""Opt-in local alerts: periodically re-run saved searches and raise in-app
notifications for new matches and follow-up reminders.

**Off by default.** No external delivery — purely an in-app inbox (see notifications.py).
Enable from the Settings page (persisted to ``alerts.json`` in the data dir) or via
``JOBFINDER_ALERTS=1``. The interval is clamped to a polite minimum so background sweeps
never hammer the job boards. For people who'd rather use the OS scheduler than keep the
app running, ``python -m jobfinder.alerts`` runs a single sweep and exits.
"""
from __future__ import annotations

import json
import os
import threading
import time

from .bench import bench_fit_for_job
from .config import settings
from .engine import SearchSettings
from .insights import compute_insights
from .notifications import bench_fit_notification, new_matches_notification, reminder_notification
from .saved_searches import register_run
from .sources import available_sources

_MIN_INTERVAL_HOURS = 6
_POLL_SECONDS = 300.0                              # how often the loop wakes to check if due
# Patchable for tests (never the real data dir).
_FILE = settings.data_dir / "alerts.json"


# --- preferences (enabled + interval) -------------------------------------

def _env_enabled() -> bool:
    return os.environ.get("JOBFINDER_ALERTS", "").strip().lower() in ("1", "true", "yes", "on")


def _env_interval() -> int:
    try:
        return max(_MIN_INTERVAL_HOURS, int(os.environ.get("JOBFINDER_ALERTS_INTERVAL_HOURS", "6")))
    except ValueError:
        return _MIN_INTERVAL_HOURS


def get_prefs() -> dict:
    """Resolved alert prefs: the local file (user toggle) wins over the env defaults."""
    enabled, interval = _env_enabled(), _env_interval()
    try:
        d = json.loads(_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            enabled = bool(d.get("enabled", enabled))
            interval = max(_MIN_INTERVAL_HOURS, int(d.get("interval_hours", interval)))
    except Exception:
        pass
    return {"enabled": enabled, "interval_hours": interval}


def set_prefs(enabled: bool | None = None, interval_hours: int | None = None) -> dict:
    cur = get_prefs()
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    if interval_hours is not None:
        cur["interval_hours"] = max(_MIN_INTERVAL_HOURS, int(interval_hours))
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(cur), encoding="utf-8")
    return cur


# --- the sweep (synchronous, testable) ------------------------------------

def _settings_for(s) -> SearchSettings:
    # mirror web._build_settings: keep only known sources, de-duped, order-preserving
    known = set(available_sources())
    chosen = list(dict.fromkeys(x for x in (s.sources or []) if x in known)) or list(settings.default_sources)
    return SearchSettings(
        keywords=s.keywords, location=s.location, sources=chosen,
        limit_per_source=max(1, min(s.limit_per_source, 50)),
        remote=s.remote, days=s.days, semantic=s.semantic, min_score=s.min_score,
        gigs_only=getattr(s, "gigs_only", False),
    )


def run_sweep(store, find_jobs, now: float | None = None) -> dict:
    """Re-run every saved search, raise a new-matches notification when a search surfaces
    ids it hasn't seen, and raise/refresh follow-up reminders from the pipeline. Resilient:
    one failing search or source never aborts the sweep."""
    now = now if now is not None else time.time()
    searches_run = new_matches = reminders = bench_fits = 0

    # The house's bench, loaded ONCE (short lock); bench-matching then runs OUTSIDE the lock
    # (bench.py is pure). Empty bench → the consulting overlay is simply skipped.
    bench = store.list_consultants()

    # Reminder dedupe over EVERY existing reminder (read and unread). A dismissed reminder is
    # deleted from the store, so it's absent here and re-creates legitimately; a kept reminder
    # is refreshed in place — otherwise a still-quiet application would spawn a fresh duplicate
    # every sweep once the user had read (but not dismissed) it.
    reminders_index = {n.dedupe: n for n in store.list_notifications()
                       if n.kind == "reminder" and n.dedupe}

    for s in store.list_saved_searches():
        profile = store.get_profile(s.cv_id) if s.cv_id else None
        if profile is None:
            continue
        try:
            result = find_jobs(profile, _settings_for(s))
        except Exception:
            continue
        searches_run += 1
        # diff + seen-set update happen atomically on the freshest row (no lost update vs a
        # concurrent /run or /seen request — see Store.update_saved_search).
        box = {"new": []}
        def _diff(sv, _ids=[j.id for j in result.jobs]):
            box["new"] = register_run(sv, _ids)
        updated = store.update_saved_search(s.id, _diff)
        if updated is None:                       # deleted mid-sweep
            continue
        new_ids = box["new"]
        if new_ids:
            idset = set(new_ids)
            new_jobs = [j.to_dict() for j in result.jobs if j.id in idset]
            store.save_notification(new_matches_notification(updated, new_jobs, now))
            new_matches += len(new_ids)

            # Consulting overlay: which NEW postings does the house's bench fit? (bid/no-bid
            # applied — only gigs with a qualifying consultant are surfaced.) Resilient: a
            # bench-match failure never aborts the sweep.
            if bench:
                fits = []
                for j in result.jobs:
                    if j.id not in idset:
                        continue
                    try:
                        top = bench_fit_for_job(j, bench)
                    except Exception:
                        continue
                    if top:
                        fits.append({"title": j.title, "url": j.url, "source": j.source,
                                     "consultants": [{"name": m.consultant.name, "score": m.score}
                                                     for m in top]})
                if fits:
                    try:                              # build+save inside the try too — a save error
                        note = bench_fit_notification(updated, fits, now)   # must not abort the sweep
                        store.save_notification(note)
                        bench_fits += note.count       # count what was actually recorded (capped)
                    except Exception:
                        pass

    try:
        nudges = compute_insights(store.list_applications(), now).get("nudges", [])
    except Exception:
        nudges = []
    for nudge in nudges:
        dk = f"reminder:{nudge.get('id', '')}"
        note = reminder_notification(nudge, now)
        existing = reminders_index.get(dk)
        if existing is not None:                  # refresh in place (and re-surface as unread)
            existing.body = note.body
            existing.created = now
            existing.read = False
            store.save_notification(existing)
        else:
            store.save_notification(note)
            reminders_index[dk] = note
            reminders += 1

    return {"searches_run": searches_run, "new_matches": new_matches,
            "reminders": reminders, "bench_fits": bench_fits, "ran_at": now}


# --- the background scheduler (opt-in) ------------------------------------

class AlertScheduler:
    """A daemon thread that runs the sweep on a clamped interval *only while enabled*.
    The thread is cheap to leave running: while alerts are disabled it just sleeps."""

    def __init__(self, store, find_jobs):
        self._store = store
        self._find = find_jobs
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()            # guards _thread (start/stop)
        self._sweep_lock = threading.Lock()      # serializes sweeps (scheduled vs run-now)
        self.last_run: float | None = None
        self.last_summary: dict | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="jobfinder-alerts", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t:
            # wait out an in-flight sweep (bounded, so shutdown can't hang); every store write
            # is its own atomic transaction, so a daemon exit can't tear a row regardless
            deadline = time.time() + 30
            while t.is_alive() and time.time() < deadline:
                t.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(_POLL_SECONDS):
            try:
                self._maybe_run()
            except Exception:
                pass

    def _maybe_run(self, now: float | None = None) -> None:
        prefs = get_prefs()
        if not prefs["enabled"]:
            return
        now = now if now is not None else time.time()
        due_after = prefs["interval_hours"] * 3600.0
        # hold the sweep lock across the due-check + sweep so a concurrent run_now can't let
        # two sweeps overlap or race the last_run gate
        with self._sweep_lock:
            if self.last_run is not None and (now - self.last_run) < due_after:
                return
            self.last_summary = run_sweep(self._store, self._find, now)
            self.last_run = now

    def run_now(self, now: float | None = None) -> dict:
        """Force an immediate sweep regardless of the interval (a user-clicked 'Check now')."""
        now = now if now is not None else time.time()
        with self._sweep_lock:
            self.last_summary = run_sweep(self._store, self._find, now)
            self.last_run = now
            return self.last_summary

    def status(self) -> dict:
        p = get_prefs()
        return {"enabled": p["enabled"], "interval_hours": p["interval_hours"],
                "last_run": self.last_run, "last_summary": self.last_summary}

    def paused(self):
        """Context manager: hold the sweep lock so no sweep can run inside the block (and any
        in-flight one finishes first). Used to make a Delete-all atomic against the sweep, so a
        mid-flight sweep can't resurrect just-deleted rows."""
        return self._sweep_lock


def _main() -> None:
    """`python -m jobfinder.alerts` — run one sweep and exit (for OS-scheduled cron/Task
    Scheduler use instead of keeping the app running)."""
    from .engine import find_jobs
    from .store import get_store
    store = get_store(settings)
    summary = run_sweep(store, find_jobs)
    print(f"Alerts sweep: {summary['searches_run']} saved search(es) run, "
          f"{summary['new_matches']} new match(es), {summary['reminders']} reminder(s).")
    store.close()


if __name__ == "__main__":
    _main()
