from __future__ import annotations
import time
from typing import Any, Dict

from flask import Flask, Response, jsonify, request, stream_with_context

from pipeline.engine import PipelineEngine
from pipeline.integration_registry import IntegrationRegistry
from pipeline.job_store import JobStore


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/api/generate", methods=["POST"])
    def create_job() -> Any:
        payload = request.get_json(silent=True) or {}
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"success": False, "error": "Prompt is required."}), 400

        job_id = PipelineEngine.start_job(prompt)
        return jsonify({"jobId": job_id}), 202

    @app.route("/api/generate/<job_id>/stream", methods=["GET"])
    def stream_job(job_id: str) -> Any:
        job = JobStore.get(job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found."}), 404

        def event_stream() -> Any:
            try:
                for event in JobStore.stream_events(job_id):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'stage': 'error', 'status': 'failed', 'error': str(exc)})}\n\n"

        return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

    @app.route("/api/generate/<job_id>", methods=["GET"])
    def get_job_status(job_id: str) -> Any:
        job = JobStore.get(job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found."}), 404
        return jsonify(job)

    @app.route("/api/integrations", methods=["GET"])
    def list_integrations() -> Any:
        integrations = [integration.model_dump(mode="json") for integration in IntegrationRegistry.list_all().values()]
        return jsonify({"integrations": integrations})

    @app.route("/api/generate/<job_id>/repair", methods=["POST"])
    def repair_job(job_id: str) -> Any:
        job = JobStore.get(job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found."}), 404

        payload = request.get_json(silent=True) or {}
        stage = payload.get("stage")
        error_hint = payload.get("errorHint")
        if not stage:
            return jsonify({"success": False, "error": "Stage is required for repair."}), 400

        repair_result = PipelineEngine.repair_stage(job_id, stage, error_hint)
        return jsonify(repair_result)

    @app.route("/", methods=["GET"])
    def index() -> Any:
        return jsonify({"status": "ok", "message": "AI signal generation server is running."})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
