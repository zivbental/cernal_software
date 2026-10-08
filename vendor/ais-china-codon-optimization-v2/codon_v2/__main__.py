import argparse
import json
from pathlib import Path

from .pipeline import optimize
from .references import ReferenceStore
from .report import export
from .sequence import InputError


def main():
    parser = argparse.ArgumentParser(description="Codon Optimization Tool V2")
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve", help="Start the local browser interface")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("run", help="Run a saved request and export all results")
    run.add_argument("--request", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    commands.add_parser("hosts", help="Show installed, checked reference capabilities")
    args = parser.parse_args()
    if args.command == "serve":
        from .server import serve
        serve(args.host, args.port)
    elif args.command == "hosts":
        print(json.dumps([r.metadata() for r in ReferenceStore().hosts.values()], indent=2))
    else:
        try:
            result = optimize(json.loads(args.request.read_text(encoding="utf-8-sig")))
        except (InputError, ValueError, OSError) as exc:
            parser.exit(2, f"Invalid request: {exc}\n")
        args.output.mkdir(parents=True, exist_ok=True)
        for suffix in ("json", "csv", "fasta"):
            data, _ = export(result, suffix)
            (args.output / ("results." + suffix)).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": result["status"], "candidates": len(result["candidates"]), "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
