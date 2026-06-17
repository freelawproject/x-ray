import json
import math
from dataclasses import dataclass
from importlib.metadata import version
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

DEFAULT_REPORT_PATH = (
    Path(__file__).resolve().parent / "benchmarks" / "report.html"
)
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class Stats:
    mean: float
    min: float
    max: float
    stddev: float
    rounds: int


@dataclass(frozen=True)
class ReportData:
    perf_data: dict[str, Any] | None
    perf_timeline: list[dict[str, Any]] | None
    accuracy_data: dict[str, Any] | None
    accuracy_timeline: list[dict[str, Any]] | None


def write_benchmark_report(
    benchmark_dir: Path = Path(".benchmarks"),
    report_path: Path = DEFAULT_REPORT_PATH,
) -> bool:
    report_data = load_benchmark_report_data(benchmark_dir)
    if report_data.perf_data is None and report_data.accuracy_data is None:
        return False

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_html(report_data))
    return True


def load_benchmark_report_data(benchmark_dir: Path) -> ReportData:
    benchmark_files = benchmark_json_files(benchmark_dir)
    if not benchmark_files:
        return ReportData(None, None, None, None)

    timeline = []
    accuracy_timeline = []
    latest_data = None
    latest_path = None

    for benchmark_file in benchmark_files:
        data = read_json(benchmark_file)
        if data is None:
            continue

        latest_data = data
        latest_path = benchmark_file
        benchmarks = data.get("benchmarks", [])
        timeline.append(
            {
                "timestamp": data.get("commit_info", {}).get("time", ""),
                "commit_id": data.get("commit_info", {}).get("id", "")[:8],
                "benchmarks": [
                    {
                        "name": benchmark["name"],
                        "stats": Stats(
                            mean=stats["mean"],
                            min=stats["min"],
                            max=stats["max"],
                            stddev=stats["stddev"],
                            rounds=stats["rounds"],
                        ),
                    }
                    for benchmark in benchmarks
                    if (stats := complete_stats(benchmark)) is not None
                ],
            }
        )

        accuracy_benchmarks = [
            benchmark
            for benchmark in benchmarks
            if benchmark.get("extra_info")
        ]
        if accuracy_benchmarks:
            accuracy_timeline.append(
                {
                    "timestamp": data.get("commit_info", {}).get("time", ""),
                    "commit_id": data.get("commit_info", {}).get("id", "")[:8],
                    "by_category": accuracy_by_category(accuracy_benchmarks),
                }
            )

    if latest_data is None or latest_path is None:
        return ReportData(None, None, None, None)

    perf_timeline = timeline or None
    latest = timeline[-1] if timeline else {"timestamp": "", "benchmarks": []}
    commit_info = latest_path.name.split("_")
    perf_data = {
        "xray_version": version("x-ray"),
        "commit_info": {
            "id": commit_info[1] if len(commit_info) > 1 else "",
            "timestamp": latest["timestamp"],
        },
        "benchmarks": latest["benchmarks"],
    }

    accuracy_benchmarks = [
        benchmark
        for benchmark in latest_data.get("benchmarks", [])
        if benchmark.get("extra_info")
    ]
    accuracy_data = (
        {"benchmarks": accuracy_benchmarks} if accuracy_benchmarks else None
    )

    return ReportData(
        perf_data=perf_data,
        perf_timeline=perf_timeline,
        accuracy_data=accuracy_data,
        accuracy_timeline=accuracy_timeline or None,
    )


def benchmark_json_files(benchmark_dir: Path) -> list[Path]:
    if not benchmark_dir.exists():
        return []
    return sorted(
        benchmark_dir.glob("*/*.json"),
        key=lambda path: path.stat().st_mtime,
    )


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def complete_stats(benchmark: dict[str, Any]) -> dict[str, Any] | None:
    stats = benchmark.get("stats")
    if not isinstance(stats, dict) or "name" not in benchmark:
        return None
    required = ("mean", "min", "max", "stddev", "rounds")
    return stats if all(key in stats for key in required) else None


def accuracy_by_category(
    accuracy_benchmarks: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    by_category = {}
    for benchmark in accuracy_benchmarks:
        extra = benchmark.get("extra_info", {})
        category = extra.get("category", "unknown")
        if category not in by_category:
            by_category[category] = {"count": 0, "matches": 0}
        by_category[category]["count"] += 1
        if extra.get("accuracy_match"):
            by_category[category]["matches"] += 1
    return by_category


def bar_color(ratio: float) -> str:
    r = int(74 + ratio * (252 - 74))
    g = int(222 + ratio * (165 - 222))
    b = int(128 + ratio * (165 - 128))
    return f"#{r:02x}{g:02x}{b:02x}"


def benchmark_name(benchmark: dict[str, Any]) -> str:
    name = benchmark["name"]
    return name.split("[")[-1].rstrip("]") if "[" in name else name


def log_scale_position(
    val: float, log_min: float, log_span: float, width: float = 540
) -> float:
    if val is None or val <= 0:
        return 0.0
    return (math.log10(val) - log_min) / log_span * width


def render_html(report_data: ReportData) -> str:
    perf_data = report_data.perf_data
    perf_timeline = report_data.perf_timeline
    accuracy_data = report_data.accuracy_data
    accuracy_timeline = report_data.accuracy_timeline

    xray_ver = (perf_data or {}).get("xray_version", version("x-ray"))
    commit = (perf_data or {}).get("commit_info", {})
    commit_id = commit.get("id", "")[:8]
    commit_msg = commit.get("message", "")
    meta = f"x-ray {xray_ver}"
    if commit_id:
        meta += f" &mdash; <code>{commit_id}</code>"
    if commit_msg:
        meta += f" {commit_msg}"

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    env.filters["bar_color"] = bar_color
    env.filters["log_scale_position"] = log_scale_position
    env.filters["max"] = max
    env.filters["min"] = min
    env.globals["log_scale_position"] = log_scale_position  # type: ignore
    env.globals["max"] = max  # type: ignore

    context = {
        "meta": meta,
        "perf_data": perf_data,
        "perf_timeline": perf_timeline,
        "accuracy_data": accuracy_data,
        "accuracy_timeline": accuracy_timeline,
        "by_duration": [],
        "accuracy_by_category": {},
        "accuracy_by_file": {},
    }

    if perf_data and perf_data.get("benchmarks"):
        context.update(prep_perf_context(perf_data, perf_timeline))

    if accuracy_data:
        context.update(prep_accuracy_context(accuracy_data))

    return env.get_template("report.html").render(context)


def prep_perf_context(
    perf_data: dict[str, Any], perf_timeline: list[dict[str, Any]] | None
) -> dict[str, Any]:
    by_duration = sorted(
        perf_data["benchmarks"], key=lambda benchmark: benchmark["stats"].mean
    )
    if not by_duration:
        return {"by_duration": []}

    n = len(by_duration)

    prev_lookup: dict[str, float] = {}
    if perf_timeline and len(perf_timeline) > 1:
        prev = perf_timeline[-2]
        for benchmark in prev["benchmarks"]:
            prev_lookup[benchmark_name(benchmark)] = round(
                benchmark["stats"].mean * 1000, 3
            )
    has_prev = bool(prev_lookup)

    mins_ms = [
        round(benchmark["stats"].min * 1000, 3) for benchmark in by_duration
    ]
    maxes_ms = [
        round(benchmark["stats"].max * 1000, 3) for benchmark in by_duration
    ]
    g_min = min(mins_ms)
    g_max = max(maxes_ms)
    log_min = math.log10(max(g_min, 0.001))
    log_max = math.log10(g_max)
    log_span = log_max - log_min or 1

    return {
        "by_duration": by_duration,
        "prev_lookup": prev_lookup,
        "log_min": log_min,
        "log_span": log_span,
        "chart_height": max(380, n * 22 + 80),
        "has_prev": has_prev,
        "n": n,
        "timeline": perf_timeline,
    }


def prep_accuracy_context(accuracy_data: dict[str, Any]) -> dict[str, Any]:
    by_category: dict[str, dict[str, int | float]] = {}
    by_file = {}

    for benchmark in accuracy_data.get("benchmarks", []):
        extra = benchmark.get("extra_info", {})
        category = extra.get("category", "unknown")
        filename = benchmark_name(benchmark)

        if category not in by_category:
            by_category[category] = {
                "count": 0,
                "matches": 0,
                "expected_total": 0,
                "actual_total": 0,
            }

        by_category[category]["count"] += 1
        if extra.get("accuracy_match"):
            by_category[category]["matches"] += 1
        by_category[category]["expected_total"] += extra.get(
            "expected_detections", 0
        )
        by_category[category]["actual_total"] += extra.get(
            "actual_detections", 0
        )

        by_file[filename] = {
            "category": category,
            "expected": extra.get("expected_detections", 0),
            "actual": extra.get("actual_detections", 0),
            "match": extra.get("accuracy_match", False),
        }

    for category in by_category:
        summary = by_category[category]
        summary["accuracy"] = (
            summary["matches"] / summary["count"] * 100
            if summary["count"] > 0
            else 0
        )

    return {
        "accuracy_by_category": by_category,
        "accuracy_by_file": by_file,
    }
