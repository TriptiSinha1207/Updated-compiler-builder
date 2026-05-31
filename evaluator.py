from __future__ import annotations
import json
import time
from typing import Dict, List
from .engine import PipelineEngine


class EvaluationEngine:
    def __init__(self, prompts: List[Dict[str, str]]):
        self.prompts = prompts

    def evaluate(self) -> Dict[str, object]:
        metrics = {
            "total": len(self.prompts),
            "success": 0,
            "failures": 0,
            "retry_count": 0,
            "latencies_ms": [],
            "failure_types": {},
            "results": [],
        }
        for item in self.prompts:
            prompt = item["prompt"]
            start = time.time()
            result = self.run_prompt(prompt)
            latency_ms = int((time.time() - start) * 1000)
            metrics["latencies_ms"].append(latency_ms)
            metrics["results"].append({"id": item.get("id"), "prompt": prompt, **result, "latency_ms": latency_ms})
            if result["success"]:
                metrics["success"] += 1
            else:
                metrics["failures"] += 1
                failure = result.get("failed_stage") or "unknown"
                metrics["failure_types"][failure] = metrics["failure_types"].get(failure, 0) + 1
            metrics["retry_count"] += result.get("retry_count", 0)

        metrics["average_latency_ms"] = int(sum(metrics["latencies_ms"]) / len(metrics["latencies_ms"])) if metrics["latencies_ms"] else 0
        metrics["retry_rate"] = metrics["retry_count"] / metrics["total"] if metrics["total"] else 0
        return metrics

    def run_prompt(self, prompt: str) -> Dict[str, object]:
        result = PipelineEngine.run(prompt)
        if result.get("success"):
            return {
                "success": True,
                "failed_stage": None,
                "retry_count": len(result.get("repairs", [])),
                "estimated_cost": result.get("job", {}).get("total_cost", 0),
                "integrations": result.get("intent", {}).get("integrations_requested", []),
            }

        failure_stage = result.get("stage") or "validation"
        repair_count = len(result.get("repairs", [])) if isinstance(result.get("repairs"), list) else 0
        return {
            "success": False,
            "failed_stage": failure_stage,
            "retry_count": repair_count,
            "estimated_cost": result.get("job", {}).get("total_cost", 0),
            "integrations": result.get("intent", {}).get("integrations_requested", []),
            "errors": result.get("errors") or result.get("detail") or [],
        }

    @classmethod
    def load_prompts(cls, path: str) -> List[Dict[str, str]]:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
