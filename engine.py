from __future__ import annotations
import json
import threading
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

from .gateway import MultiProviderGateway
from .intent import IntentExtractor
from .data_schema_generator import DataSchemaGenerator
from .appspec_generator import AppSpecGenerator
from .schemas import AppSpec
from .spec_validator import SpecValidator
from .job_store import JobStore


class PipelineEngine:
    """Orchestrates the multi-stage pipeline: Intent → Schema → AppSpec → Validation."""

    last_job: Dict[str, Any] | None = None
    gateway = MultiProviderGateway()
    _job_lock = threading.Lock()

    @classmethod
    def run(cls, prompt: str) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "prompt": prompt,
            "started_at": time.time(),
            "stages": [],
            "total_cost": 0.0,
            "success": False,
        }

        intent_result = cls.gateway.run_stage("intent_extraction", {"prompt": prompt})
        job["stages"].append(intent_result)
        if not intent_result.get("success"):
            cls.last_job = {**job, "finished_at": time.time()}
            return {"success": False, "stage": "intent_extraction", "detail": intent_result, "job": cls.last_job}

        intent = IntentExtractor.parse(prompt)
        if intent.needs_clarification:
            clarification_payload = {
                "success": False,
                "stage": "intent_extraction",
                "clarification": intent.clarification_questions,
                "assumptions": intent.assumptions,
            }
            cls.last_job = {**job, "finished_at": time.time(), "stages": job["stages"]}
            return clarification_payload

        schema_result = cls.gateway.run_stage("schema_generation", {"intent": intent.model_dump(mode="json")})
        job["stages"].append(schema_result)

        data_schema = DataSchemaGenerator.generate(intent)
        schema_validator = SpecValidator()
        schema_validation = schema_validator.validate_data_schema(data_schema)
        if not schema_validation.valid:
            job["stages"].append({"stage": "schema_generation", "status": "validation_failed", "errors": schema_validation.errors})
            cls.last_job = {**job, "finished_at": time.time()}
            return {"success": False, "stage": "schema_generation", "errors": schema_validation.errors, "job": cls.last_job}

        appspec_result = cls.gateway.run_stage("appspec_generation", {"data_schema": data_schema.model_dump(mode="json")})
        job["stages"].append(appspec_result)

        app_spec = AppSpecGenerator.generate(data_schema, intent)

        validation_result = SpecValidator().validate_appspec(app_spec)
        validation_stage = {
            "stage": "validation",
            "status": "completed",
            "valid": validation_result.valid,
            "errors": validation_result.errors,
            "repairs": validation_result.repairs,
            "repair_logs": [log.model_dump(mode="json") for log in validation_result.repair_logs],
        }
        job["stages"].append(validation_stage)

        job["total_cost"] = sum(float(stage.get("cost", 0)) for stage in job["stages"] if isinstance(stage.get("cost"), (int, float)))
        job["finished_at"] = time.time()
        job["success"] = validation_result.valid
        cls.last_job = job

        return {
            "success": validation_result.valid,
            "intent": intent.model_dump(mode="json"),
            "app_spec": app_spec.model_dump(mode="json"),
            "errors": validation_result.errors,
            "repairs": validation_result.repairs,
            "repair_logs": [log.model_dump(mode="json") for log in validation_result.repair_logs],
            "job": {
                "id": job_id,
                "total_cost": job["total_cost"],
                "stages": job["stages"],
                "success": job["success"],
            },
        }

    @classmethod
    def start_job(cls, prompt: str) -> str:
        job_id = JobStore.create(prompt)
        thread = threading.Thread(target=cls._run_job, args=(job_id, prompt), daemon=True)
        thread.start()
        return job_id

    @classmethod
    def stream_generate(cls, prompt: str):
        """Generator that yields stage events for SSE streaming in the runtime."""
        yield {"stage": "job", "status": "started", "timestamp": time.time(), "message": "streaming generation started"}
        try:
            intent_start = time.time()
            yield {"stage": "intent_extraction", "status": "started", "timestamp": time.time()}
            intent_result = cls.gateway.run_stage("intent_extraction", {"prompt": prompt})
            yield {"stage": "intent_extraction", "status": "completed", "timestamp": time.time(), "latency": time.time() - intent_start, **(intent_result or {})}

            if not intent_result.get("success"):
                yield {"stage": "intent_extraction", "status": "failed", "timestamp": time.time(), "detail": intent_result}
                return

            intent = IntentExtractor.parse(prompt)
            if intent.needs_clarification:
                yield {"stage": "intent_extraction", "status": "clarify", "timestamp": time.time(), "clarification": intent.clarification_questions, "assumptions": intent.assumptions}
                return

            schema_start = time.time()
            yield {"stage": "schema_generation", "status": "started", "timestamp": time.time()}
            schema_result = cls.gateway.run_stage("schema_generation", {"intent": intent.model_dump(mode="json")})
            yield {"stage": "schema_generation", "status": "completed", "timestamp": time.time(), "latency": time.time() - schema_start, **(schema_result or {})}

            data_schema = DataSchemaGenerator.generate(intent)
            schema_validation = SpecValidator().validate_data_schema(data_schema)
            if not schema_validation.valid:
                yield {"stage": "schema_generation", "status": "failed", "timestamp": time.time(), "errors": schema_validation.errors}
                return

            appspec_start = time.time()
            yield {"stage": "appspec_generation", "status": "started", "timestamp": time.time()}
            appspec_result = cls.gateway.run_stage("appspec_generation", {"data_schema": data_schema.model_dump(mode="json")})
            yield {"stage": "appspec_generation", "status": "completed", "timestamp": time.time(), "latency": time.time() - appspec_start, **(appspec_result or {})}

            validation_start = time.time()
            app_spec = AppSpecGenerator.generate(data_schema, intent)
            validation_result = SpecValidator().validate_appspec(app_spec)
            yield {"stage": "validation", "status": "completed", "timestamp": time.time(), "latency": time.time() - validation_start, "valid": validation_result.valid, "errors": validation_result.errors, "repairs": validation_result.repairs}

            total_cost = 0.0
            final_payload = {
                "stage": "finalize",
                "status": "completed",
                "timestamp": time.time(),
                "success": validation_result.valid,
                "intent": intent.model_dump(mode="json"),
                "config": app_spec.model_dump(mode="json"),
                "errors": validation_result.errors,
                "repairs": validation_result.repairs,
                "total_cost": total_cost,
            }
            yield final_payload
        except Exception as exc:
            yield {"stage": "error", "status": "failed", "timestamp": time.time(), "error": str(exc)}

    @classmethod
    def _run_job(cls, job_id: str, prompt: str) -> None:
        JobStore.append_event(job_id, {
            "stage": "job",
            "status": "started",
            "timestamp": time.time(),
            "message": "Job started.",
        })

        try:
            intent_start = time.time()
            JobStore.append_event(job_id, {"stage": "intent_extraction", "status": "started", "timestamp": time.time()})
            intent_result = cls.gateway.run_stage("intent_extraction", {"prompt": prompt})
            JobStore.append_event(job_id, {
                "stage": "intent_extraction",
                "status": "completed",
                "timestamp": time.time(),
                "latency": time.time() - intent_start,
                **intent_result,
            })

            if not intent_result.get("success"):
                JobStore.update_job(job_id, status="failed", finished_at=time.time(), errors=["Intent extraction failed"])
                JobStore.append_event(job_id, {"stage": "intent_extraction", "status": "failed", "timestamp": time.time(), "detail": intent_result})
                return

            intent = IntentExtractor.parse(prompt)
            if intent.needs_clarification:
                JobStore.update_job(job_id, status="failed", finished_at=time.time(), errors=["Clarification required"])
                JobStore.append_event(job_id, {
                    "stage": "intent_extraction",
                    "status": "clarify",
                    "timestamp": time.time(),
                    "clarification": intent.clarification_questions,
                    "assumptions": intent.assumptions,
                })
                return

            schema_start = time.time()
            JobStore.append_event(job_id, {"stage": "schema_generation", "status": "started", "timestamp": time.time()})
            schema_result = cls.gateway.run_stage("schema_generation", {"intent": intent.model_dump(mode="json")})
            JobStore.append_event(job_id, {
                "stage": "schema_generation",
                "status": "completed",
                "timestamp": time.time(),
                "latency": time.time() - schema_start,
                **schema_result,
            })

            data_schema = DataSchemaGenerator.generate(intent)
            schema_validation = SpecValidator().validate_data_schema(data_schema)
            if not schema_validation.valid:
                JobStore.update_job(job_id, status="failed", finished_at=time.time(), errors=schema_validation.errors)
                JobStore.append_event(job_id, {"stage": "schema_generation", "status": "failed", "timestamp": time.time(), "errors": schema_validation.errors})
                return

            appspec_start = time.time()
            JobStore.append_event(job_id, {"stage": "appspec_generation", "status": "started", "timestamp": time.time()})
            appspec_result = cls.gateway.run_stage("appspec_generation", {"data_schema": data_schema.model_dump(mode="json")})
            JobStore.append_event(job_id, {
                "stage": "appspec_generation",
                "status": "completed",
                "timestamp": time.time(),
                "latency": time.time() - appspec_start,
                **appspec_result,
            })

            validation_start = time.time()
            app_spec = AppSpecGenerator.generate(data_schema, intent)
            validation_result = SpecValidator().validate_appspec(app_spec)
            JobStore.append_event(job_id, {
                "stage": "validation",
                "status": "completed",
                "timestamp": time.time(),
                "latency": time.time() - validation_start,
                "valid": validation_result.valid,
                "errors": validation_result.errors,
                "repairs": validation_result.repairs,
            })

            total_cost = sum(float(stage.get("cost", 0)) for stage in [intent_result, schema_result, appspec_result] if isinstance(stage.get("cost"), (int, float)))
            final_payload = {
                "stage": "generation_complete",
                "status": "completed",
                "timestamp": time.time(),
                "success": validation_result.valid,
                "intent": intent.model_dump(mode="json"),
                "app_spec": app_spec.model_dump(mode="json"),
                "errors": validation_result.errors,
                "repairs": validation_result.repairs,
                "total_cost": total_cost,
            }
            JobStore.update_job(job_id, status="completed", finished_at=time.time(), result=final_payload, errors=validation_result.errors, repairs=validation_result.repairs, cost=total_cost)
            JobStore.append_event(job_id, final_payload)
        except Exception as exc:
            JobStore.update_job(job_id, status="failed", finished_at=time.time(), errors=[str(exc)])
            JobStore.append_event(job_id, {"stage": "job", "status": "failed", "timestamp": time.time(), "error": str(exc)})

    @classmethod
    def get_job(cls, job_id: str) -> Dict[str, Any]:
        return JobStore.get(job_id) or {}

    @classmethod
    def repair_stage(cls, job_id: str, stage: str, error_hint: Optional[str] = None) -> Dict[str, Any]:
        job = JobStore.get(job_id)
        if not job:
            return {"success": False, "reason": "Job not found."}
        result = job.get("result") or {}
        if stage == "validation":
            app_spec_payload = result.get("app_spec")
            if not app_spec_payload:
                return {"success": False, "reason": "No AppSpec available to repair."}
            app_spec = AppSpec.parse_obj(app_spec_payload)
            validation = SpecValidator().validate_appspec(app_spec)
            repair_response = {
                "stage": "validation",
                "errors": validation.errors,
                "repairs": validation.repairs,
                "repair_logs": [log.model_dump(mode="json") for log in validation.repair_logs],
            }
            JobStore.append_event(job_id, {"stage": "repair", "status": "completed", "timestamp": time.time(), "stage_repaired": stage, "hint": error_hint, **repair_response})
            return repair_response

        return {"success": False, "reason": f"Repair supported only for validation stage, not '{stage}'."}

    @classmethod
    def latest_job_status(cls) -> Dict[str, Any]:
        return cls.last_job or {}
