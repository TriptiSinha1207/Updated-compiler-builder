import argparse
import json
import os
import sys

# Ensure the local repo root is on sys.path so `import pipeline` works
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from pipeline.intent import IntentExtractor
from pipeline.design import DesignGenerator
from pipeline.validator import ConfigValidator
from pipeline.runtime import ConfigRuntime
from pipeline.evaluator import EvaluationEngine

DATASET_PATH = os.path.join(os.path.dirname(__file__), "data", "dataset.json")


def generate_config(prompt: str, output_path: str) -> None:
    intent = IntentExtractor.parse(prompt)
    if intent.needs_clarification:
        print("Clarification needed:", intent.clarification_questions)
        return
    config = DesignGenerator.create(intent)
    validation = ConfigValidator.validate(config)
    if validation.repairs:
        print("Repaired config:", validation.repairs)
    if not validation.valid:
        print("Validation failed:", validation.errors)
        return
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(config.model_dump_json(indent=2))
    print(f"Config generated to {output_path}")


def simulate_config(config_path: str) -> None:
    with open(config_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    config, error = ConfigValidator.parse_config(json.dumps(payload))
    if error:
        print("Config parse error:", error)
        return
    runtime = ConfigRuntime(config)
    results = runtime.simulate()
    print("Simulation results:", results)


def run_server(config_path: str, port: int = 5000, host: str = "127.0.0.1") -> None:
    with open(config_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    config, error = ConfigValidator.parse_config(json.dumps(payload))
    if error:
        print("Config parse error:", error)
        return
    runtime = ConfigRuntime(config)
    print(f"Running app on http://{host}:{port}")
    runtime.run(host=host, port=port)


def evaluate_dataset() -> None:
    prompts = EvaluationEngine.load_prompts(DATASET_PATH)
    engine = EvaluationEngine(prompts)
    metrics = engine.evaluate()
    print("Evaluation metrics:")
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Config-driven app generator")
    subparsers = parser.add_subparsers(dest="command")

    gen_parser = subparsers.add_parser("generate")
    gen_parser.add_argument("--prompt", required=True)
    gen_parser.add_argument("--output", default="app_config.json")

    sim_parser = subparsers.add_parser("simulate")
    sim_parser.add_argument("--config", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config", default=os.getenv("APP_CONFIG_PATH", "app_config.json"))
    run_parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "5000")))
    run_parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))

    eval_parser = subparsers.add_parser("evaluate")

    args = parser.parse_args()
    if args.command == "generate":
        generate_config(args.prompt, args.output)
    elif args.command == "simulate":
        simulate_config(args.config)
    elif args.command == "run":
        run_server(args.config, args.port, args.host)
    elif args.command == "evaluate":
        evaluate_dataset()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
