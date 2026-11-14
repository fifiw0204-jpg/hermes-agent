"""A managed run whose submitter exited is not a crashed card.

Regression: card ``t_722fec79`` (the 2200 W LLC report) was booked ``crashed`` twice while
its admitted session kept calling the model. The dispatcher's spawned submitter exits by
design once the owner admits the turn — ``tasks.worker_pid`` names that submitter, not the
attempt — so the attempt continues inside the owner after the pid is gone. The crash sweep
read the pid as the attempt's liveness, and because ``owner_reclaim_paused`` is False
whenever the owner process is still alive (an unsettled admission is not a dead owner), the
"a live lease means the owner is still working" rule never applied: the card was re-queued,
ran again, and was auto-blocked after two crashes while its session kept working.

These tests pin the missing fence: while the owner still holds an admitted, unsettled attempt
under a live lease, a dead submitter pid must not book the card crashed. A settled admission,
an expired lease and a dead owner keep the platform's existing behaviour.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import psutil
import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_db_dispatch as kbd
from hermes_cli.kanban_owner_recovery import managed_attempt_in_flight
from hermes_cli.process_identity import process_birth

NOW = int(time.time())
HOST = kb._claimer_id().split(":", 1)[0]


def _absent_pid(base: int = 3_500_000) -> int:
    """A pid that provably does not exist on this host, so a fixture can never hit a process."""
    pid = base
    while psutil.pid_exists(pid):
        pid += 1
    return pid


class _Board:
    """A scratch board plus the scratch admission ledger an owner receipt points at."""

    def __init__(self, root: Path):
        self.path = root / "kanban.db"
        kbc.init_db(self.path)
        self.conn = kbc.connect(self.path)
        self.ledger = root / "state.db"
        with sqlite3.connect(self.ledger) as store:
            store.execute(
                "CREATE TABLE session_admissions "
                "(target_session_id TEXT, request_id TEXT, status TEXT, outcome TEXT)"
            )

    def close(self) -> None:
        self.conn.close()

    def managed_attempt(
        self,
        tid: str = "t_managed",
        *,
        owner_alive: bool,
        admission_status: str,
        claim_live: bool,
        worker_pid: int | None = None,
        worker_bound: bool = False,
    ) -> int:
        """A ``running`` card whose submitter is gone but whose owner still holds the attempt."""
        worker_pid = _absent_pid() if worker_pid is None else worker_pid
        owner_pid = os.getpid() if owner_alive else _absent_pid(base=3_600_000)
        lock = f"{HOST}:{owner_pid}"
        expires = NOW + 600 if claim_live else NOW - 600
        started = NOW - 120
        fingerprint = kbd._process_fingerprint(os.getpid())
        run_id = self.conn.execute(
            "INSERT INTO task_runs (task_id, profile, status, claim_lock, claim_expires, "
            "worker_pid, started_at) VALUES (?, 'default', 'running', ?, ?, ?, ?)",
            (tid, lock, expires, worker_pid, started),
        ).lastrowid
        run = int(run_id)
        self.conn.execute(
            "INSERT INTO tasks (id, title, assignee, status, created_at, claim_lock, claim_expires, "
            "worker_pid, worker_started_at, last_heartbeat_at, current_run_id, started_at, priority) "
            "VALUES (?, ?, 'default', 'running', ?, ?, ?, ?, ?, ?, ?, ?, 5)",
            (tid, tid, NOW - 86400, lock, expires, worker_pid, fingerprint, None, run, started),
        )
        self.event(tid, run, "claimed", {"source_status": "ready"}, started)
        self.event(tid, run, "spawned", {"pid": worker_pid, "started_at": fingerprint}, started)
        payload = {
            "db": str(self.ledger),
            "session_id": "sess-1",
            "pid": owner_pid,
            "request_id": f'kanban:["default","{tid}",1]',
        }
        if owner_alive:
            payload["birth"] = process_birth(psutil.Process(os.getpid()))
        self.event(tid, run, "owner_admitted", payload, started + 30)
        if worker_bound:
            self.event(
                tid, run, "worker_bound",
                {"pid": worker_pid, "claim_lock": lock, "started_at": fingerprint},
                started + 60,
            )
        with sqlite3.connect(self.ledger) as store:
            store.execute(
                "INSERT INTO session_admissions VALUES ('sess-1', ?, ?, ?)",
                (payload["request_id"], admission_status, None),
            )
        self.conn.commit()
        return run

    def event(self, tid: str, run: int, kind: str, payload: dict, ts: int) -> None:
        self.conn.execute(
            "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)", (tid, run, kind, json.dumps(payload), ts))

    def state(self, tid: str) -> dict:
        return dict(self.conn.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone())


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_CRASH_GRACE_SECONDS", "0")
    scratch = _Board(tmp_path)
    yield scratch
    scratch.close()


def test_a_dead_submitter_does_not_crash_an_admitted_attempt(board):
    """The regression: the card was booked crashed while its admitted session kept working."""
    board.managed_attempt("t_managed", owner_alive=True, admission_status="started", claim_live=True)
    assert managed_attempt_in_flight(board.conn, "t_managed") is True
    assert kbd.detect_crashed_workers(board.conn) == []
    assert board.state("t_managed")["status"] == "running"


def test_an_expired_lease_still_books_the_card_crashed(board):
    """The fence holds a live lease only — an expired one is the platform's reclaim path."""
    board.managed_attempt("t_managed", owner_alive=True, admission_status="started", claim_live=False)
    assert managed_attempt_in_flight(board.conn, "t_managed") is False
    assert kbd.detect_crashed_workers(board.conn) == ["t_managed"]
    assert board.state("t_managed")["status"] != "running"


def test_a_settled_admission_is_not_an_attempt_in_flight(board):
    """The owner settled the attempt, so nothing can still be executing it."""
    board.managed_attempt("t_managed", owner_alive=True, admission_status="terminal", claim_live=True)
    assert managed_attempt_in_flight(board.conn, "t_managed") is False


def test_a_dead_owner_is_not_an_attempt_in_flight(board):
    """A dead owner cannot be holding anything."""
    board.managed_attempt("t_managed", owner_alive=False, admission_status="started", claim_live=True)
    assert managed_attempt_in_flight(board.conn, "t_managed") is False
