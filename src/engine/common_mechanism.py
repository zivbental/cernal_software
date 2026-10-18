"""Bounded local IBBIS Common Mechanism v2.1.0 adapter, JSON format 0.6.

The database is operator-provisioned, never fetched by a design job. A full file
inventory is verified before and after each run; no successful verdict cache or
partial/fast screening mode is provided. No real database is bundled here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.artifacts import sha256_file
from engine.errors import JobCancelled
from engine.safety import (
    AdapterStatus,
    Finding,
    FindingKind,
    LocalScreeningManifest,
    SafetyGate,
    ScreeningEvidence,
    SequenceSubmission,
)
from engine.sequences import to_dna

TOOL_VERSION = "2.1.0"
JSON_VERSION = "0.6"
POLICY_VERSION = "commec-resolved-findings-v2"
DATABASES = frozenset({"biorisk", "best_match", "low_concern", "control_lists"})
MAX_BATCH = 64
MAX_BATCH_BASES = 1_000_000
MAX_OUTPUT_BYTES = 16 * 1024 * 1024

# Pinned commec.config.result.ScreenStatus importance, excluding incomplete states.
_RESOLVED_ORDER = {"Pass": 0, "Warning (Cleared)": 1, "Flag (Cleared)": 2}
_UNRESOLVED = {"Flag", "Warning"}
_HIT_STEPS = {
    "Biorisk Search": "biorisk",
    "Protein Taxonomy Search": "protein_taxonomy",
    "Nucleotide Taxonomy Search": "nucleotide_taxonomy",
    "Low Concern Protein Search": "low_concern",
    "Low Concern RNA Search": "low_concern",
    "Low Concern DNA Search": "low_concern",
}


def _resolved_query(query: dict) -> bool:
    """Check native cleared-only consistency, without reimplementing search thresholds.

    Upstream aggregates each primary step from its hits, then low_concern from
    all steps. Clearing requires both an original hit and a low-concern hit.
    Conditional nucleotide Skip is permitted only without nucleotide hits.
    """
    status = query["status"]
    # Pinned check_low_concern._update_low_concern_data_for_query explicitly
    # excludes Biorisk Search from clearing. A cleared biorisk state is invalid.
    if status["biorisk"] != "Pass":
        return False
    grouped = {name: [] for name in set(_HIT_STEPS.values())}
    for hit in query["hits"]:
        recommendation = hit["recommendation"]
        step = _HIT_STEPS[recommendation["from_step"]]
        outcome = recommendation["status"]
        if outcome not in _RESOLVED_ORDER:
            return False
        if (
            not isinstance(hit["name"], str)
            or not hit["name"].strip()
            or not isinstance(hit["description"], str)
            or not isinstance(hit["annotations"], dict)
        ):
            return False
        region = hit["region"]
        if any(
            type(region[key]) is not int or not 1 <= region[key] <= query["length"]
            for key in ("query_start", "query_end")
        ):
            return False
        evalue = region["e_value"]
        if type(evalue) not in (int, float) or not math.isfinite(evalue) or evalue < 0:
            return False
        grouped[step].append(outcome)

    def worst(values):
        return max(["Pass", *values], key=_RESOLVED_ORDER.__getitem__)

    for step in ("biorisk", "protein_taxonomy", "nucleotide_taxonomy"):
        if step == "nucleotide_taxonomy" and status[step] == "Skip" and not grouped[step]:
            continue
        if status[step] != worst(grouped[step]):
            return False
    primary = [v for step, values in grouped.items() if step != "low_concern" for v in values]
    aggregate = worst(primary + grouped["low_concern"])
    if status["screen_status"] != aggregate:
        return False
    if aggregate == "Pass":
        return status["low_concern"] in {"Pass", "Skip"} and not (
            status["low_concern"] == "Skip" and grouped["low_concern"]
        )
    # Native clearing concerns overlapping query regions. Do not accept an
    # unrelated low-concern hit as corroboration, or invent a new coverage cutoff.
    primary_hits = [
        hit
        for hit in query["hits"]
        if _HIT_STEPS[hit["recommendation"]["from_step"]] != "low_concern"
        and hit["recommendation"]["status"] != "Pass"
    ]
    low_hits = [
        hit
        for hit in query["hits"]
        if _HIT_STEPS[hit["recommendation"]["from_step"]] == "low_concern"
        and hit["recommendation"]["status"] != "Pass"
    ]
    for hit in primary_hits:
        start, end = sorted((hit["region"]["query_start"], hit["region"]["query_end"]))
        if not any(
            _RESOLVED_ORDER[support["recommendation"]["status"]]
            >= _RESOLVED_ORDER[hit["recommendation"]["status"]]
            and min(support["region"]["query_start"], support["region"]["query_end"]) <= end
            and max(support["region"]["query_start"], support["region"]["query_end"]) >= start
            for support in low_hits
        ):
            return False
    return (
        status["low_concern"] == aggregate
        and worst(primary) == aggregate
        and worst(grouped["low_concern"]) == aggregate
    )


def _object(pairs):
    """Duplicate JSON keys are ambiguous evidence, not last-value-wins."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_OUTPUT_BYTES:
        raise ValueError("oversized screening data")
    data = json.loads(path.read_text(), object_pairs_hook=_object)
    if not isinstance(data, dict):
        raise ValueError("screening data must be an object")
    return data


def inventory_digest(files: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class CommonMechanismAdapter:
    """Trusted operator configuration; never accepts job/user executable arguments.

    ``files`` enumerates EVERY regular file in an immutable database directory.
    Provision it offline after validating the installation. The manifest database
    digest is SHA-256 of the canonical path-to-content-digest inventory, not a
    checksum asserted by the external process. Revisions must match its JSON too.
    """

    manifest: LocalScreeningManifest
    executable: Path
    database: Path
    files: dict[str, str]
    revisions: dict[str, str]
    software_files: dict[str, str]
    timeout_seconds: int = 300
    threads: int = 4

    def _verify_installation(self) -> None:
        if (
            self.manifest.adapter_name != "ibbis-common-mechanism"
            or self.manifest.adapter_version != TOOL_VERSION
            or not self.manifest.is_valid_at(datetime.now(UTC))
            or not self.executable.is_absolute()
            or not self.executable.is_file()
            or not self.database.is_absolute()
            or not self.database.is_dir()
            or not isinstance(self.files, dict)
            or not self.files
            or set(self.revisions) != DATABASES
            or any(
                not isinstance(v, str) or not re.fullmatch(r"1\.\d+(?:\.\d+)?", v)
                for v in self.revisions.values()
            )
            or self.manifest.policy_version != POLICY_VERSION
            or not self.software_files
            or inventory_digest(self.software_files) != self.manifest.software_sha256
            or str(self.executable) not in self.software_files
            or type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= 3600
            or type(self.threads) is not int
            or not 1 <= self.threads <= 32
            or inventory_digest(self.files) != self.manifest.database_sha256
        ):
            raise ValueError("invalid or unavailable local screening installation")
        for name, digest in self.software_files.items():
            path = Path(name)
            if not path.is_absolute() or not path.is_file() or sha256_file(path) != digest:
                raise ValueError("screening software content changed")
        actual = set()
        for path in self.database.rglob("*"):
            if path.is_symlink():
                raise ValueError("database symlinks are not an immutable inventory")
            if path.is_file():
                name = path.relative_to(self.database).as_posix()
                actual.add(name)
                if self.files.get(name) != sha256_file(path):
                    raise ValueError("database content changed")
        if actual != set(self.files):
            raise ValueError("incomplete database inventory")

    def screen(self, submission: SequenceSubmission) -> ScreeningEvidence:
        return self.screen_many((submission,))[0]

    def screen_many(
        self, submissions: tuple[SequenceSubmission, ...], *, on_batch=None
    ) -> tuple[ScreeningEvidence, ...]:
        """Hold all results until the same inventory is verified around the entire run.

        This avoids rehashing the full database for every bounded subprocess batch.
        The deployment directory must be read-only/versioned during the run; do not
        update files in place. No verdict survives this call in a reusable cache.
        """
        if not submissions:
            return ()
        if any(
            s.validation_errors()
            or s.sequence != s.sequence.strip().upper()
            or not 41 <= len(s.sequence) <= 100_000
            for s in submissions
        ):
            return tuple(
                ScreeningEvidence(self.manifest, AdapterStatus.INCONCLUSIVE) for _ in submissions
            )
        try:
            self._verify_installation()
            results = []
            batch = []
            bases = 0
            for submission in submissions:
                if batch and (
                    len(batch) == MAX_BATCH or bases + len(submission.sequence) > MAX_BATCH_BASES
                ):
                    if on_batch is not None and on_batch() is False:
                        raise JobCancelled("Screening final sequences")
                    results.extend(self._screen_one_batch(tuple(batch)))
                    batch, bases = [], 0
                batch.append(submission)
                bases += len(submission.sequence)
            if batch:
                if on_batch is not None and on_batch() is False:
                    raise JobCancelled("Screening final sequences")
                results.extend(self._screen_one_batch(tuple(batch)))
            self._verify_installation()
            return tuple(results)
        except (OSError, ValueError, TypeError, AttributeError):
            return tuple(
                ScreeningEvidence(self.manifest, AdapterStatus.UNAVAILABLE) for _ in submissions
            )

    def _screen_one_batch(self, submissions: tuple[SequenceSubmission, ...]):
        """Internal process step. Only screen_many may return releasable evidence."""

        def held(status):
            return tuple(ScreeningEvidence(self.manifest, status) for _ in submissions)

        if not submissions:
            return ()
        if (
            len(submissions) > MAX_BATCH
            or sum(len(s.sequence) for s in submissions) > MAX_BATCH_BASES
            or any(
                s.validation_errors()
                or s.sequence != s.sequence.strip().upper()
                or not 41 <= len(s.sequence) <= 100_000
                for s in submissions
            )
        ):
            return held(AdapterStatus.INCONCLUSIVE)
        # POSIX process groups ensure a timed-out CLI cannot leave BLAST/HMM children
        # working on sensitive temporary inputs. Native Windows isn't enabled here.
        if os.name != "posix":
            return held(AdapterStatus.UNAVAILABLE)
        try:
            with TemporaryDirectory(prefix="cernal-screen-") as directory:
                root = Path(directory)
                fasta = root / "final.fasta"
                fasta.write_text(
                    "".join(
                        f">q{i:06d}\n{to_dna(s.sequence)}\n" for i, s in enumerate(submissions)
                    ),
                    encoding="ascii",
                )
                input_digest = sha256_file(fasta)
                process = subprocess.Popen(
                    [
                        str(self.executable),
                        "screen",
                        "-d",
                        str(self.database),
                        "--regions",
                        "all",
                        "-t",
                        str(self.threads),
                        "-o",
                        str(root / "result"),
                        str(fasta),
                    ],
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                try:
                    code = process.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    return held(AdapterStatus.TIMEOUT)
                finally:
                    # Clean the owned group even on interruption/nonzero exit; external
                    # search descendants must not survive temp-file cleanup. Never kill
                    # unrelated processes, and tolerate a group already fully exited.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
                if code != 0:
                    return held(AdapterStatus.FAILED)
                # The pinned tool writes the effective config, not merely requested flags.
                effective = (root / "input_result" / "result_config.yaml").read_text()
                for key in (
                    "skip_taxonomy_search",
                    "skip_nt_search",
                    "auto_update_databases",
                    "resume",
                ):
                    values = re.findall(rf"(?m)^{key}: ([^\n]+)$", effective)
                    if values not in (["false"], ["False"]):
                        return held(AdapterStatus.INCONCLUSIVE)
                data = read_json(root / "result.output.json")
                if (
                    data.get("query_info", {}).get("file") != str(fasta)
                    or sha256_file(fasta) != input_digest
                ):
                    return held(AdapterStatus.INCONCLUSIVE)
                return self.parse_result(data, submissions)
        except FileNotFoundError:
            return held(AdapterStatus.FAILED)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return held(AdapterStatus.FAILED)

    def parse_result(self, data: dict, submissions: tuple[SequenceSubmission, ...]):
        """Strictly validate the pinned native schema; never infer success from no hits."""

        def held(status):
            return tuple(ScreeningEvidence(self.manifest, status) for _ in submissions)

        try:
            info = data["commec_info"]
            queries = data["queries"]
            totals = data["query_info"]
            expected = {f"q{i:06d}" for i in range(len(submissions))}
            if (
                info["commec_version"] != TOOL_VERSION
                or info["json_output_version"] != JSON_VERSION
                or data["database_info"]["revisions"] != self.revisions
                or set(queries) != expected
                or type(totals["number_of_queries"]) is not int
                or totals["number_of_queries"] != len(submissions)
                or type(totals["total_query_length"]) is not int
                or totals["total_query_length"] != sum(len(s.sequence) for s in submissions)
            ):
                return held(AdapterStatus.INCONCLUSIVE)
            results = []
            for i, submission in enumerate(submissions):
                name = f"q{i:06d}"
                query = queries[name]
                if (
                    query["query"] != name
                    or type(query["length"]) is not int
                    or query["length"] != len(submission.sequence)
                    or not isinstance(query["hits"], list)
                ):
                    return held(AdapterStatus.INCONCLUSIVE)
                status = query["status"]
                aggregate = status["screen_status"]
                components = [status[key] for key in _HIT_STEPS.values()]
                hit_statuses = [hit["recommendation"]["status"] for hit in query["hits"]]
                known = set(_RESOLVED_ORDER) | _UNRESOLVED | {"Skip", "Error"}
                if any(value not in known for value in [aggregate, *components, *hit_statuses]):
                    return held(AdapterStatus.INCONCLUSIVE)
                native = json.dumps(query, sort_keys=True, separators=(",", ":"), allow_nan=False)
                if "Error" in [aggregate, *components, *hit_statuses]:
                    results.append(
                        ScreeningEvidence(
                            self.manifest,
                            AdapterStatus.FAILED
                            if aggregate == "Error"
                            else AdapterStatus.INCONCLUSIVE,
                            native_screening_json=native,
                        )
                    )
                elif aggregate in _UNRESOLVED:
                    results.append(
                        ScreeningEvidence(
                            self.manifest,
                            AdapterStatus.COMPLETE,
                            (
                                Finding(
                                    FindingKind.SCREENING_FLAG,
                                    "commec-review-required",
                                    "confirmed",
                                    f"local:commec:{POLICY_VERSION}:{aggregate}",
                                ),
                            ),
                            native_screening_json=native,
                        )
                    )
                elif _resolved_query(query):
                    results.append(
                        ScreeningEvidence(
                            self.manifest, AdapterStatus.COMPLETE, native_screening_json=native
                        )
                    )
                else:
                    results.append(
                        ScreeningEvidence(
                            self.manifest, AdapterStatus.INCONCLUSIVE, native_screening_json=native
                        )
                    )
            return tuple(results)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return held(AdapterStatus.INCONCLUSIVE)


def load_adapter(path: str) -> CommonMechanismAdapter:
    """Read an operator-only manifest selected by the worker environment."""
    config = read_json(Path(path))
    manifest = config["manifest"]
    return CommonMechanismAdapter(
        manifest=LocalScreeningManifest(
            adapter_name=manifest["adapter_name"],
            adapter_version=manifest["adapter_version"],
            database_id=manifest["database_id"],
            database_sha256=manifest["database_sha256"],
            validated_at=datetime.fromisoformat(manifest["validated_at"]),
            expires_at=datetime.fromisoformat(manifest["expires_at"]),
            policy_version=manifest["policy_version"],
            software_sha256=manifest["software_sha256"],
        ),
        executable=Path(config["executable"]),
        database=Path(config["database"]),
        files=config["files"],
        revisions=config["revisions"],
        software_files=config["software_files"],
        timeout_seconds=config.get("timeout_seconds", 300),
        threads=config.get("threads", 4),
    )


def screen_final_batch(
    submissions: tuple[SequenceSubmission, ...], adapter: CommonMechanismAdapter, *, on_batch=None
):
    """Policy evaluation binds each result to the original RNA/DNA bytes, not CLI IDs."""
    evidence = adapter.screen_many(submissions, on_batch=on_batch)
    now = datetime.now(UTC)
    return tuple(
        SafetyGate().evaluate(s, e, now=now) for s, e in zip(submissions, evidence, strict=True)
    )


def configured_final_screens(
    submissions: tuple[SequenceSubmission, ...], path: str, *, on_batch=None
):
    """Configuration failures produce auditable holds, never fallback clean screens."""
    try:
        adapter = load_adapter(path)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        now = datetime.now(UTC)
        manifest = LocalScreeningManifest(
            "unprovisioned-local-screening",
            "0",
            "unavailable",
            "0" * 64,
            now,
            now,
        )
        return tuple(
            SafetyGate().evaluate(
                s, ScreeningEvidence(manifest, AdapterStatus.UNAVAILABLE), now=now
            )
            for s in submissions
        )
    return screen_final_batch(submissions, adapter, on_batch=on_batch)
