from __future__ import annotations
import json
import os
import sqlite3
from typing import Any, Dict, List
from flask import Flask, jsonify, request, render_template, redirect, url_for, Response, stream_with_context
from .schemas import AppConfig, Endpoint
from .intent import IntentExtractor
from .design import DesignGenerator
from .validator import ConfigValidator
from .engine import PipelineEngine

_SQL_TYPE_MAP = {
    "integer": "INTEGER",
    "string": "TEXT",
    "boolean": "INTEGER",
    "float": "REAL",
    "text": "TEXT",
}

class ConfigRuntime:
    def __init__(self, config: AppConfig, db_path: str = ":memory:"):
        self.config = config
        self.db_path = db_path
        base_dir = os.path.dirname(os.path.dirname(__file__))
        self.app = Flask(
            self.config.metadata.app_name,
            template_folder=os.path.join(base_dir, "templates"),
            static_folder=os.path.join(base_dir, "static"),
        )
        self.app.config["TEMPLATES_AUTO_RELOAD"] = True
        self.conn = None
        self._create_database()
        self._register_routes()

    def _create_database(self) -> None:
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = self.conn.cursor()
        for table in self.config.db.tables:
            columns_sql = []
            for column in table.columns:
                col_type = _SQL_TYPE_MAP.get(column.type, "TEXT")
                null_clause = "NOT NULL" if column.required else ""
                columns_sql.append(f"{column.name} {col_type} {null_clause}".strip())
            columns_sql.append(f"PRIMARY KEY ({table.primary_key})")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {table.name} ({', '.join(columns_sql)})")
        self.conn.commit()

    def _register_routes(self) -> None:
        self.frontend_prefix = "/app"

        @self.app.route("/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok", "app": self.config.metadata.app_name})

        @self.app.route("/config", methods=["GET"])
        def config_view():
            return jsonify(json.loads(self.config.model_dump_json()))

        @self.app.route("/generate", methods=["POST"])
        def generate_app():
            payload = request.get_json(silent=True) or {}
            prompt = (payload.get("prompt") or "").strip()
            if not prompt:
                return jsonify({"success": False, "error": "Prompt is required."}), 400
            # Use pipeline engine to produce a strict AppSpec and validation metadata
            result = PipelineEngine.run(prompt)
            if not result.get("success"):
                return jsonify({"success": False, "detail": result}), 200
            return jsonify(result)

        @self.app.route("/stream-generate", methods=["GET"])
        def stream_generate():
            prompt = (request.args.get("prompt") or "").strip()
            if not prompt:
                return ("Prompt is required."), 400

            def event_stream():
                for evt in PipelineEngine.stream_generate(prompt):
                    yield f"data: {json.dumps(evt)}\n\n"

            return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

        @self.app.route("/job-status", methods=["GET"])
        def job_status():
            return jsonify(PipelineEngine.latest_job_status())

        for endpoint in self.config.api.endpoints:
            self._register_endpoint(endpoint)

        self._register_frontend_routes()

    def _register_frontend_routes(self) -> None:
        @self.app.route("/", methods=["GET"])
        def root():
            pages = [
                {
                    "name": page.name,
                    "route": f"{self.frontend_prefix}" if page.path == "/" else f"{self.frontend_prefix}{page.path}",
                }
                for page in self.config.ui.pages
            ]
            return render_template(
                "index.html",
                app_name=self.config.metadata.app_name,
                description=self.config.metadata.description,
                pages=pages,
            )

        for page in self.config.ui.pages:
            route = f"{self.frontend_prefix}" if page.path == "/" else f"{self.frontend_prefix}{page.path}"
            endpoint_name = f"page_{route.replace('/', '_')}_{page.name.replace(' ', '_')}"
            self.app.add_url_rule(route, endpoint_name, self._make_page_handler(page), methods=["GET"])

    def _make_page_handler(self, page):
        def handler():
            return render_template("page.html", page=page, config=self.config)
        return handler

    def _register_endpoint(self, endpoint: Endpoint) -> None:
        path = endpoint.path
        method = endpoint.method
        if method == "GET":
            self.app.add_url_rule(path, endpoint.name, self._make_get_handler(endpoint), methods=["GET"])
        elif method == "POST":
            self.app.add_url_rule(path, endpoint.name, self._make_post_handler(endpoint), methods=["POST"])
        elif method == "PUT":
            self.app.add_url_rule(path, endpoint.name, self._make_put_handler(endpoint), methods=["PUT"])
        else:
            self.app.add_url_rule(path, endpoint.name, self._make_generic_handler(endpoint), methods=[method])

    def _make_get_handler(self, endpoint: Endpoint):
        def handler(id: Any = None):
            cursor = self.conn.cursor()
            if "<id>" in endpoint.path:
                if id is None:
                    return jsonify({"error": "id required"}), 400
                table = endpoint.linked_entity or endpoint.path.strip("/").split("/")[0]
                cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (id,))
                row = cursor.fetchone()
                return jsonify({"item": row}) if row else jsonify({"error": "not found"}), 404
            table = endpoint.linked_entity or endpoint.path.strip("/").split("/")[0]
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            return jsonify({"items": rows})
        return handler

    def _make_post_handler(self, endpoint: Endpoint):
        def handler():
            payload = request.get_json(silent=True) or {}
            table = endpoint.linked_entity or endpoint.path.strip("/").split("/")[0]
            cursor = self.conn.cursor()
            fields = [field.name for field in (endpoint.request_schema.fields if endpoint.request_schema else []) if field.name != "id"]
            values = []
            placeholders = []
            for field in fields:
                value = payload.get(field)
                if value is not None:
                    values.append(value)
                    placeholders.append("?")
            if not values:
                values = [payload]
                placeholders = ["?"]
            sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            try:
                cursor.execute(sql, tuple(values))
            except sqlite3.OperationalError:
                return jsonify({"error": "invalid insert schema"}), 400
            self.conn.commit()
            item_id = cursor.lastrowid
            return jsonify({"id": item_id, "created": True})
        return handler

    def _make_put_handler(self, endpoint: Endpoint):
        def handler(id: Any = None):
            if id is None:
                return jsonify({"error": "id required"}), 400
            payload = request.get_json(silent=True) or {}
            table = endpoint.linked_entity or endpoint.path.strip("/").split("/")[0]
            updates = []
            values = []
            for key, value in payload.items():
                updates.append(f"{key} = ?")
                values.append(value)
            if not updates:
                return jsonify({"error": "no fields to update"}), 400
            values.append(id)
            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE id = ?", tuple(values))
            self.conn.commit()
            affected = cursor.rowcount
            return jsonify({"updated": affected})
        return handler

    def _make_generic_handler(self, endpoint: Endpoint):
        def handler(**kwargs):
            return jsonify({"message": f"Endpoint {endpoint.name} is configured."})
        return handler

    def simulate(self) -> Dict[str, Any]:
        client = self.app.test_client()
        results = {}
        health_resp = client.get("/health")
        results["health"] = health_resp.status_code == 200
        results["config"] = client.get("/config").status_code == 200
        for endpoint in self.config.api.endpoints:
            if endpoint.method == "GET":
                resp = client.get(endpoint.path.replace("<id>", "1"))
                results[f"GET {endpoint.path}"] = resp.status_code in (200, 404)
        return results

    def run(self, host: str = "127.0.0.1", port: int = 5000) -> None:
        self.app.run(host=host, port=port)
