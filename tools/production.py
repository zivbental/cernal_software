"""Explicit production preparation for one Linux VM; never controls services."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "REPLACE_WITH_A_RANDOM_SECRET"
sys.path.insert(0, str(ROOT / "src"))

from config.runtime import ensure_runtime_directories, reject_symlink_path  # noqa: E402


def domain_name(value):
    value = value.lower()
    if (
        len(value) > 253
        or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value
        )
        or any(len(label) > 63 for label in value.split("."))
    ):
        raise ValueError("Domain must be a DNS hostname without scheme, port, path or wildcard")
    return value


def deployment_path(value):
    # Restrict to paths whose meaning is identical in dotenv, systemd and Caddy.
    value = str(value)
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", value) or ".." in Path(value).parts:
        raise ValueError(
            "Deployment paths must be absolute POSIX paths without spaces or metacharacters"
        )
    return value.rstrip("/")


def read_config(path):
    reject_symlink_path(path)
    values = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in values:
            raise ValueError(f"Invalid or duplicate configuration key at line {number}")
        tokens = shlex.split(value, comments=False)
        if len(tokens) != 1 or any(c in tokens[0] for c in "\n\r\x00"):
            raise ValueError(f"Configuration value at line {number} must be one literal value")
        values[key] = tokens[0]
    return values


def upload_limits(dataset_mb):
    if not 1 <= dataset_mb <= 1024:
        raise ValueError("MAX_DATASET_MB must be between 1 and 1024 MiB")
    return dataset_mb * 1024 * 1024, (dataset_mb + 2) * 1024 * 1024


def write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        os.chmod(path, 0o600)
        stream.write(text)


def prepare(root, output, domain, user, group, dataset_mb):
    root = Path(deployment_path(root))
    output = Path(deployment_path(output))
    reject_symlink_path(root)
    reject_symlink_path(output)
    if not (root / "manage.py").is_file():
        raise ValueError("Deployment root must be a CERNAL checkout containing manage.py")
    domain = domain_name(domain)
    for value in (user, group):
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", value):
            raise ValueError("Service user/group must be simple Linux account names")
    _, body_bytes = upload_limits(dataset_mb)
    replacements = {
        "ROOT": str(root),
        "VAR": str(root / "var"),
        "ENV": str(output / "cernal.env"),
        "DOMAIN": domain,
        "USER": user,
        "GROUP": group,
        "DATASET_MB": str(dataset_mb),
        "BODY_BYTES": str(body_bytes),
    }
    rendered = {}
    for name in (
        "cernal.env.example",
        "Caddyfile",
        "cernal-web.service",
        "cernal-worker.service",
        "cernal-reconciler.service",
    ):
        text = (ROOT / "deploy" / name).read_text()
        for key, value in replacements.items():
            text = text.replace("@@" + key + "@@", value)
        if "@@" in text:
            raise ValueError(f"Unresolved deployment parameter in {name}")
        rendered["cernal.env" if name.endswith(".example") else name] = text
    # Check every conflict before writing anything. Never reset a secret on rerun.
    for name, text in rendered.items():
        destination = output / name
        reject_symlink_path(destination)
        if destination.is_symlink():
            raise ValueError(f"Configuration conflict: symlink {destination}")
        if destination.exists():
            if name == "cernal.env":
                actual, expected = (
                    read_config(destination),
                    dict(
                        line.split("=", 1)
                        for line in text.splitlines()
                        if line and not line.startswith("#")
                    ),
                )
                fixed = (
                    "DJANGO_SETTINGS_MODULE",
                    "ALLOWED_HOSTS",
                    "CSRF_TRUSTED_ORIGINS",
                    "CERNAL_VAR_DIR",
                    "DATABASE_URL",
                    "MEDIA_ROOT",
                    "MAX_DATASET_MB",
                )
                if any(actual.get(k) != expected[k] for k in fixed):
                    raise ValueError(
                        f"Configuration conflict: {destination}; preserve and review manually"
                    )
            elif destination.read_text() != text:
                raise ValueError(f"Template conflict: {destination}; preserve and review manually")
    ensure_runtime_directories(root / "var", root / "var/media", root / "var/staticfiles")
    for name, text in rendered.items():
        if not (output / name).exists():
            write_new(output / name, text)
    print(f"Prepared {output}. Existing files preserved. Supply SECRET_KEY before install.")


def environment(config):
    values = read_config(config)
    if values.get("DJANGO_SETTINGS_MODULE") != "config.settings.prod":
        raise ValueError("Configuration must select config.settings.prod")
    if len(values.get("SECRET_KEY", "")) < 50 or values["SECRET_KEY"] == PLACEHOLDER:
        raise ValueError(
            "Supply an operator-owned SECRET_KEY of at least 50 characters; no default is generated"
        )
    if values.get("REVIEWER_LOGIN_ENABLED", "False").lower() not in ("false", "0", "no"):
        raise ValueError("Production preparation requires reviewer login disabled")
    domain = domain_name(values.get("ALLOWED_HOSTS", ""))
    if values.get("CSRF_TRUSTED_ORIGINS") != "https://" + domain:
        raise ValueError("CSRF origin must match the HTTPS hostname")
    upload_limits(int(values.get("MAX_DATASET_MB", "100")))
    var = Path(deployment_path(values.get("CERNAL_VAR_DIR", "")))
    for path in (var, var / "cernal.db", var / "media", var / "logs", var / "logs/cernal.log"):
        reject_symlink_path(path)
    if values.get("DATABASE_URL") != f"sqlite:///{var}/cernal.db" or values.get(
        "MEDIA_ROOT"
    ) != str(var / "media"):
        raise ValueError("Supported preparation requires SQLite and media under CERNAL_VAR_DIR")
    result = dict(os.environ)
    result.update(values)
    # Override inherited variables and prevent Django's .env fallback from enabling login.
    result["REVIEWER_LOGIN_ENABLED"] = "False"
    return result


def run(command, root, env):
    try:
        result = subprocess.run(command, cwd=root, env=env, check=False)
    except OSError as exc:
        raise ValueError(
            f"Cannot run {command[0]}: {exc.strerror}; install the documented prerequisite"
        ) from exc
    if result.returncode:
        raise ValueError(
            f"Preparation step failed: {command[0]} {command[1]}; existing data/config preserved"
        )


def install(root, config, initialize=False, admin=False):
    reject_symlink_path(root)
    reject_symlink_path(root / ".venv")
    reject_symlink_path(root / ".venv/cernal-install-root")
    reject_symlink_path(root / ".env")
    env = environment(config)
    if root.resolve() != ROOT.resolve():
        raise ValueError("Run the entrypoint from the target checkout after relocation")
    if env["CERNAL_VAR_DIR"] != str(root / "var"):
        raise ValueError("Configuration belongs to another checkout; review relocation paths first")
    database = Path(env["CERNAL_VAR_DIR"]) / "cernal.db"
    ensure_runtime_directories(root / "var", root / "var/media", root / "var/staticfiles")
    if not database.exists() and not initialize:
        raise ValueError(
            "Database absent: choose --initialize-database for fresh setup, or restore separately"
        )
    if database.exists() and initialize:
        raise ValueError(
            "Database already exists; omit --initialize-database to preserve and migrate it"
        )
    if admin and not sys.stdin.isatty():
        raise ValueError("--create-admin requires an interactive terminal; no default credentials")
    marker = root / ".venv/cernal-install-root"
    if (root / ".venv").exists() and (not marker.exists() or marker.read_text() != str(root)):
        raise ValueError(
            "Unmanaged or relocated .venv: move it aside and rebuild with uv sync; "
            "never patch shebangs"
        )
    run(["uv", "sync", "--locked", "--extra", "dev"], root, env)
    marker.write_text(str(root))
    python = str(root / ".venv/bin/python")
    for command in (
        [python, "tools/install_data.py"],
        ["npm", "--prefix", "frontend", "ci"],
        ["npm", "--prefix", "frontend", "run", "build"],
        [python, "manage.py", "migrate", "--noinput"],
        [python, "manage.py", "collectstatic", "--noinput"],
        [python, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
    ):
        run(command, root, env)
    if admin:
        run([python, "manage.py", "createsuperuser"], root, env)
    print(
        "Preparation complete. Services, proxy, firewall and production acceptance "
        "are separate operator steps."
    )


def status(root, config):
    env = environment(config)
    python = str(root / ".venv/bin/python")
    checks = {}

    def probe(name, command):
        try:
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=180)
            checks[name] = "ok" if result.returncode == 0 else "unavailable"
        except (OSError, subprocess.TimeoutExpired):
            checks[name] = "unavailable"

    probe("data", [python, "tools/install_data.py", "--check"])
    # Migration check refuses missing schema; this never applies migrations.
    database = Path(env["CERNAL_VAR_DIR"]) / "cernal.db"
    if database.is_file():
        probe("database", [python, "manage.py", "migrate", "--check"])
    else:
        checks["database"] = "missing"
    for service in ("web", "worker", "reconciler"):
        probe(service + "_service", ["systemctl", "is-active", "--quiet", "cernal-" + service])
    for name, endpoint, expected in (("web", "health", "ok"), ("worker", "ready", "ready")):
        try:
            with urlopen(
                "https://" + env["ALLOWED_HOSTS"] + "/api/" + endpoint, timeout=10
            ) as response:
                payload = json.load(response)
                checks[name] = (
                    "ok"
                    if isinstance(payload, dict) and payload.get("status") == expected
                    else "unavailable"
                )
        except (OSError, ValueError):
            checks[name] = "unavailable"
    probe("screening_inventory", [python, "tools/production_screening_check.py"])
    checks["screening_note"] = (
        "Inventory verification only; per-sequence screening and approval remain required."
    )
    checks["reconciler_note"] = (
        "Service activity only; inspect journal and perform an acceptance run."
    )
    print(json.dumps(checks, indent=2))
    return 0 if all(v == "ok" for k, v in checks.items() if not k.endswith("_note")) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--domain", required=True)
    prepare_parser.add_argument("--root", type=Path, default=ROOT)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--user", default="cernal")
    prepare_parser.add_argument("--group", default="cernal")
    prepare_parser.add_argument("--dataset-mib", type=int, default=100)
    for action in ("install", "status"):
        child = sub.add_parser(action)
        child.add_argument("--config", type=Path, required=True)
        if action == "install":
            child.add_argument("--initialize-database", action="store_true")
            child.add_argument("--create-admin", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            prepare(args.root, args.output, args.domain, args.user, args.group, args.dataset_mib)
        elif args.action == "install":
            install(ROOT, args.config, args.initialize_database, args.create_admin)
        else:
            return status(ROOT, args.config)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Production preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
