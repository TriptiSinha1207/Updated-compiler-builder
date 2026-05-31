from __future__ import annotations
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


class JobNotFoundError(KeyError):
    pass


class JobStore:
    _jobs: Dict[str, Dict[str, Any]] = {}
    _events: Dict[str, List[Dict[str, Any]]] = {}
    _conditions: Dict[str, threading.Condition] = {}
    _lock = threading.Lock()

    @classmethod
    def create(cls, prompt: str) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        job = {
            "id": job_id,
            "prompt": prompt,
            "status": "pending",
            "started_at": now,
            "finished_at": None,
            "events": [],
            "result": None,
            "intent": None,
            "data_schema": None,
            "app_spec": None,
            "errors": [],
            "repairs": [],
            "cost": 0.0,
        }
        with cls._lock:
            cls._jobs[job_id] = job
            cls._events[job_id] = []
            cls._conditions[job_id] = threading.Condition()
        return job_id

    @classmethod
    def append_event(cls, job_id: str, event: Dict[str, Any]) -> None:
        with cls._lock:
            if job_id not in cls._events:
                raise JobNotFoundError(job_id)
            cls._events[job_id].append(event)
            cls._jobs[job_id]["events"] = cls._events[job_id]
            condition = cls._conditions[job_id]
        with condition:
            condition.notify_all()

    @classmethod
    def update_job(cls, job_id: str, **updates: Any) -> None:
        with cls._lock:
            if job_id not in cls._jobs:
                raise JobNotFoundError(job_id)
            cls._jobs[job_id].update(updates)

    @classmethod
    def get(cls, job_id: str) -> Optional[Dict[str, Any]]:
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def get_events(cls, job_id: str) -> List[Dict[str, Any]]:
        with cls._lock:
            return list(cls._events.get(job_id, []))

    @classmethod
    def stream_events(cls, job_id: str):
        with cls._lock:
            if job_id not in cls._events:
                raise JobNotFoundError(job_id)
            condition = cls._conditions[job_id]

        last_index = 0
        while True:
            with condition:
                events = list(cls._events[job_id])
                while last_index < len(events):
                    yield events[last_index]
                    last_index += 1
                job = cls._jobs[job_id]
                if job["status"] in ("completed", "failed"):
                    return
                condition.wait(timeout=0.5)
