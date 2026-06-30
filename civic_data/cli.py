from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from civic_data.dossier import create_dossier
from civic_data.demo_report import generate_hiring_demo_report
from civic_data.fetch import UrlLibHttpClient, fetch_all_sources
from civic_data.geo_boundary import build_boundary_geojson
from civic_data.model_matrix import run_packet_rag_matrix
from civic_data.normalize import normalize_channels, normalize_grievances, normalize_wards, normalize_works_payments
from civic_data.packet import build_evidence_packet
from civic_data.packet_builder import dumps_packet, render_packet_markdown
from civic_data.packet_eval import run_packet_eval
from civic_data.packet_explainer import explain_packet
from civic_data.packet_rag_eval import run_packet_rag_eval
from civic_data.profile import profile_archives
from civic_data.rag import ask_rag, build_rag_index
from civic_data.registry import load_sources, registry_hash, validate_registry
from civic_data.retrieval_eval import run_retrieval_eval
from civic_data.site import DEFAULT_PLACES, build_site_data, parse_place_arg
from civic_data.trace_inspector import inspect_trace, list_traces, render_trace_markdown
from civic_data.truth import write_place_truth
from civic_data.warehouse import export_wave1_for_postgres, load_wave1_with_psql


DEFAULT_REGISTRY = Path("registry/sources.yaml")
DEFAULT_SCHEMA = Path("registry/source_schema.json")
DEFAULT_RAW_ROOT = Path("data/raw")
DEFAULT_EXPORT_ROOT = Path("data/exports")
DEFAULT_WAREHOUSE_ROOT = Path("data/normalized")
DEFAULT_WAREHOUSE_EXPORT_ROOT = Path("data/warehouse")
DEFAULT_WEB_DATA_ROOT = Path("web/src/data/generated")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "registry" and args.registry_command == "validate":
            return _registry_validate(args)
        if args.command == "sources" and args.sources_command == "fetch":
            return _sources_fetch(args)
        if args.command == "sources" and args.sources_command == "status":
            return _sources_status(args)
        if args.command == "sources" and args.sources_command == "profile":
            return _sources_profile(args)
        if args.command == "normalize" and args.normalize_command == "wards":
            return _normalize_wards(args)
        if args.command == "normalize" and args.normalize_command == "grievances":
            return _normalize_grievances(args)
        if args.command == "normalize" and args.normalize_command == "works-payments":
            return _normalize_works_payments(args)
        if args.command == "normalize" and args.normalize_command == "channels":
            return _normalize_channels(args)
        if args.command == "places" and args.places_command == "truth":
            return _places_truth(args)
        if args.command == "rag" and args.rag_command == "ask":
            return _rag_ask(args)
        if args.command == "rag" and args.rag_command == "index":
            return _rag_index(args)
        if args.command == "rag" and args.rag_command == "explain-packet":
            return _rag_explain_packet(args)
        if args.command == "packets" and args.packets_command == "build":
            return _packets_build(args)
        if args.command == "packets" and args.packets_command == "explain":
            return _packets_explain(args)
        if args.command == "geo" and args.geo_command == "build-boundaries":
            return _geo_build_boundaries(args)
        if args.command == "traces" and args.traces_command == "list":
            return _traces_list(args)
        if args.command == "traces" and args.traces_command == "inspect":
            return _traces_inspect(args)
        if args.command == "retrieval" and args.retrieval_command == "build":
            return _retrieval_build(args)
        if args.command == "eval" and args.eval_command == "rag":
            return _eval_rag(args)
        if args.command == "eval" and args.eval_command == "packets":
            return _eval_packets(args)
        if args.command == "eval" and args.eval_command == "packet-rag":
            return _eval_packet_rag(args)
        if args.command == "eval" and args.eval_command == "packet-rag-matrix":
            return _eval_packet_rag_matrix(args)
        if args.command == "eval" and args.eval_command == "retrieval":
            return _eval_retrieval(args)
        if args.command == "warehouse" and args.warehouse_command == "export":
            return _warehouse_export(args)
        if args.command == "warehouse" and args.warehouse_command == "load":
            return _warehouse_load(args)
        if args.command == "dossiers" and args.dossiers_command == "create":
            return _dossiers_create(args)
        if args.command == "demo" and args.demo_command == "report":
            return _demo_report(args)
        if args.command == "site" and args.site_command == "build":
            return _site_build(args)
    except Exception as exc:  # noqa: BLE001 - command-line boundary should report cleanly.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="civic-data")
    subparsers = parser.add_subparsers(dest="command")

    registry = subparsers.add_parser("registry")
    registry_sub = registry.add_subparsers(dest="registry_command")
    validate = registry_sub.add_parser("validate")
    validate.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    validate.add_argument("--schema", default=str(DEFAULT_SCHEMA))

    sources = subparsers.add_parser("sources")
    sources_sub = sources.add_subparsers(dest="sources_command")

    fetch = sources_sub.add_parser("fetch")
    fetch.add_argument("--all", action="store_true")
    fetch.add_argument("--source")
    fetch.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    fetch.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    fetch.add_argument("--timeout", type=int, default=20)
    fetch.add_argument("--max-bytes", type=int, default=100 * 1024 * 1024)
    fetch.add_argument("--source-timeout", type=int, default=120)
    fetch.add_argument("--resume", action="store_true")
    fetch.add_argument("--resume-from")
    fetch.add_argument("--resource-retries", type=int, default=0)
    fetch.add_argument("--retry-delay", type=float, default=1)
    fetch.add_argument("--max-resources", type=int)
    fetch.add_argument("--allow-partial", action="store_true")
    fetch.add_argument("--skip-successful", action="store_true")
    fetch.add_argument("--skip-archived", action="store_true")
    fetch.add_argument("--insecure-ssl", action="store_true")

    status = sources_sub.add_parser("status")
    status.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    status.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))

    profile = sources_sub.add_parser("profile")
    profile.add_argument("--all", action="store_true")
    profile.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    profile.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    profile.add_argument("--export-root", default=str(DEFAULT_EXPORT_ROOT))

    normalize = subparsers.add_parser("normalize")
    normalize_sub = normalize.add_subparsers(dest="normalize_command")
    normalize_wards_parser = normalize_sub.add_parser("wards")
    normalize_wards_parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    normalize_wards_parser.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    normalize_grievances_parser = normalize_sub.add_parser("grievances")
    normalize_grievances_parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    normalize_grievances_parser.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    normalize_works_parser = normalize_sub.add_parser("works-payments")
    normalize_works_parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    normalize_works_parser.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    normalize_channels_parser = normalize_sub.add_parser("channels")
    normalize_channels_parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    normalize_channels_parser.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))

    places = subparsers.add_parser("places")
    places_sub = places.add_subparsers(dest="places_command")
    truth = places_sub.add_parser("truth")
    truth.add_argument("--q", required=True)
    truth.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    truth.add_argument("--output")
    truth.add_argument("--year-from", type=int)
    truth.add_argument("--year-to", type=int)
    truth.add_argument("--lens-label")

    rag = subparsers.add_parser("rag")
    rag_sub = rag.add_subparsers(dest="rag_command")
    rag_ask = rag_sub.add_parser("ask")
    rag_ask.add_argument("--q", required=True)
    rag_ask.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    rag_ask.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    rag_ask.add_argument("--index")
    rag_index = rag_sub.add_parser("index")
    rag_index.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    rag_index.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    rag_index.add_argument("--output")
    rag_explain = rag_sub.add_parser("explain-packet")
    rag_explain.add_argument("--packet", required=True)
    rag_explain.add_argument("--q")
    rag_explain.add_argument("--mode", choices=("deterministic", "llm"))

    packets = subparsers.add_parser("packets")
    packets_sub = packets.add_subparsers(dest="packets_command")
    packets_build = packets_sub.add_parser("build")
    packets_build.add_argument("--q", required=True)
    packets_build.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    packets_build.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    packets_build.add_argument("--index")
    packets_build.add_argument("--lat", type=float)
    packets_build.add_argument("--lng", type=float)
    packets_build.add_argument("--locality-aliases", default="data/config/locality_aliases.json")
    packets_build.add_argument("--boundary-path", default="data/geo/ward_boundaries.geojson")
    packets_build.add_argument("--format", choices=("json", "md"), default="json")
    packets_build.add_argument("--output")
    packets_explain = packets_sub.add_parser("explain")
    packets_explain.add_argument("--packet", required=True)
    packets_explain.add_argument("--q")
    packets_explain.add_argument("--mode", choices=("deterministic", "llm"))

    geo = subparsers.add_parser("geo")
    geo_sub = geo.add_subparsers(dest="geo_command")
    geo_build = geo_sub.add_parser("build-boundaries")
    geo_build.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    geo_build.add_argument("--output", default="data/geo/ward_boundaries.geojson")

    traces = subparsers.add_parser("traces")
    traces_sub = traces.add_subparsers(dest="traces_command")
    traces_list = traces_sub.add_parser("list")
    traces_list.add_argument("--trace-path", default=".context/traces/packets.jsonl")
    traces_list.add_argument("--limit", type=int, default=10)
    traces_inspect = traces_sub.add_parser("inspect")
    traces_inspect.add_argument("--trace-id", required=True)
    traces_inspect.add_argument("--trace-path", default=".context/traces/packets.jsonl")
    traces_inspect.add_argument("--format", choices=("json", "md"), default="md")

    retrieval = subparsers.add_parser("retrieval")
    retrieval_sub = retrieval.add_subparsers(dest="retrieval_command")
    retrieval_build = retrieval_sub.add_parser("build")
    retrieval_build.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    retrieval_build.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    retrieval_build.add_argument("--output-root", default="data/retrieval")

    eval_parser = subparsers.add_parser("eval")
    eval_sub = eval_parser.add_subparsers(dest="eval_command")
    eval_rag = eval_sub.add_parser("rag")
    eval_rag.add_argument("--suite", required=True)
    eval_rag.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    eval_rag.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    eval_rag.add_argument("--index")
    eval_packets = eval_sub.add_parser("packets")
    eval_packets.add_argument("--suite", required=True)
    eval_packets.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    eval_packets.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    eval_packets.add_argument("--index")
    eval_packets.add_argument("--report", action="store_true")
    eval_packets.add_argument("--output")
    eval_packet_rag = eval_sub.add_parser("packet-rag")
    eval_packet_rag.add_argument("--suite", required=True)
    eval_packet_rag.add_argument("--mode", choices=("deterministic", "llm"), default="deterministic")
    eval_packet_rag.add_argument("--output")
    eval_packet_rag_matrix = eval_sub.add_parser("packet-rag-matrix")
    eval_packet_rag_matrix.add_argument("--suite", required=True)
    eval_packet_rag_matrix.add_argument("--providers", default="deterministic,anthropic,openai")
    eval_packet_rag_matrix.add_argument("--output", default="data/eval_runs/model_matrix_latest")
    eval_retrieval = eval_sub.add_parser("retrieval")
    eval_retrieval.add_argument("--suite", required=True)
    eval_retrieval.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    eval_retrieval.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    eval_retrieval.add_argument("--retrieval-mode", default="packet_lexical", choices=("packet_lexical", "packet_embedding"))

    warehouse = subparsers.add_parser("warehouse")
    warehouse_sub = warehouse.add_subparsers(dest="warehouse_command")
    export = warehouse_sub.add_parser("export")
    export.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    export.add_argument("--export-root", default=str(DEFAULT_WAREHOUSE_EXPORT_ROOT))
    load = warehouse_sub.add_parser("load")
    load.add_argument("--database-url", required=True)
    load.add_argument("--export-root", default=str(DEFAULT_WAREHOUSE_EXPORT_ROOT))

    dossiers = subparsers.add_parser("dossiers")
    dossiers_sub = dossiers.add_subparsers(dest="dossiers_command")
    create = dossiers_sub.add_parser("create")
    create.add_argument("--place", required=True)
    create.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    create.add_argument("--output", required=True)

    demo = subparsers.add_parser("demo")
    demo_sub = demo.add_subparsers(dest="demo_command")
    demo_report = demo_sub.add_parser("report")
    demo_report.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    demo_report.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    demo_report.add_argument("--output", default="data/eval_runs/hiring_demo_report.md")

    site = subparsers.add_parser("site")
    site_sub = site.add_subparsers(dest="site_command")
    build = site_sub.add_parser("build")
    build.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    build.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    build.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    build.add_argument("--warehouse-root", default=str(DEFAULT_WAREHOUSE_ROOT))
    build.add_argument("--web-data-root", default=str(DEFAULT_WEB_DATA_ROOT))
    build.add_argument("--dossier-root", default=str(DEFAULT_EXPORT_ROOT))
    build.add_argument(
        "--place",
        action="append",
        help="Place to generate as Name:slug. May be repeated. Defaults to pilot places.",
    )
    return parser


def _registry_validate(args: argparse.Namespace) -> int:
    sources = load_sources(Path(args.registry))
    errors = validate_registry(sources, Path(args.schema))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"registry valid: {len(sources)} sources")
    return 0


def _sources_fetch(args: argparse.Namespace) -> int:
    if not args.all and not args.source:
        raise ValueError("Use --all or --source <source_id>")
    sources = load_sources(Path(args.registry))
    if args.source:
        sources = [source for source in sources if source.get("id") == args.source]
        if not sources:
            raise ValueError(f"Unknown source id: {args.source}")
    if args.skip_successful:
        raw_root = Path(args.raw_root)
        sources = [
            source
            for source in sources
            if _latest_status(raw_root / str(source["id"])) != "success"
        ]
    if args.skip_archived:
        raw_root = Path(args.raw_root)
        sources = [
            source
            for source in sources
            if _latest_status(raw_root / str(source["id"])) in {"not_fetched", "incomplete", "partial"}
        ]
    resume_from = Path(args.resume_from) if args.resume_from else None
    if resume_from:
        if len(sources) != 1:
            raise ValueError("--resume-from requires exactly one --source")
        # fetch_all_sources does not accept a source-specific resume directory; use fetch_source
        # directly for the explicit resume-from path.
        from civic_data.fetch import fetch_source

        result = fetch_source(
            sources[0],
            raw_root=Path(args.raw_root),
            registry_hash_value=registry_hash(Path(args.registry)),
            http_client=UrlLibHttpClient(
                timeout_seconds=args.timeout,
                max_bytes=args.max_bytes,
                allow_insecure_ssl=args.insecure_ssl,
            ),
            source_timeout_seconds=args.source_timeout,
            resume_from=resume_from,
            resource_retries=args.resource_retries,
            retry_delay_seconds=args.retry_delay,
            max_resources=args.max_resources,
        )
        print(f"{result.source_id}: {result.status}", flush=True)
        results = [result]
    else:
        results = fetch_all_sources(
            sources,
            raw_root=Path(args.raw_root),
            registry_hash_value=registry_hash(Path(args.registry)),
            http_client=UrlLibHttpClient(
                timeout_seconds=args.timeout,
                max_bytes=args.max_bytes,
                allow_insecure_ssl=args.insecure_ssl,
            ),
            source_timeout_seconds=args.source_timeout,
            resume=args.resume,
            resource_retries=args.resource_retries,
            retry_delay_seconds=args.retry_delay,
            max_resources=args.max_resources,
            progress_callback=lambda result: print(
                f"{result.source_id}: {result.status}", flush=True
            ),
        )
    success_statuses = {"success", "partial"} if args.allow_partial else {"success"}
    return 0 if all(result.status in success_statuses for result in results) else 1


def _sources_status(args: argparse.Namespace) -> int:
    sources = load_sources(Path(args.registry))
    raw_root = Path(args.raw_root)
    rows = []
    for source in sources:
        source_id = str(source["id"])
        source_dir = raw_root / source_id
        latest = _latest_run(source_dir)
        status = _manifest_status(latest) if latest else "not_fetched"
        latest = _latest_run(source_dir)
        counts = _manifest_resource_counts(latest)
        rows.append((source_id, status, counts))
    for source_id, status, counts in rows:
        print(
            f"{source_id},{status},{counts['expected_resource_count']},"
            f"{counts['fetched_resource_count']},{counts['failed_resource_count']},"
            f"{counts['pending_resource_count']}"
        )
    return 0


def _sources_profile(args: argparse.Namespace) -> int:
    if not args.all:
        raise ValueError("Use --all")
    sources = load_sources(Path(args.registry))
    rows = profile_archives(
        sources=sources,
        raw_root=Path(args.raw_root),
        export_root=Path(args.export_root),
    )
    print(f"profiled {len(rows)} sources")
    return 0


def _normalize_wards(args: argparse.Namespace) -> int:
    counts = normalize_wards(
        raw_root=Path(args.raw_root),
        warehouse_root=Path(args.warehouse_root),
    )
    print(
        f"normalized wards: {counts['wards']} wards, "
        f"{counts['old_new_ward_mappings']} mappings, {counts['rejected']} rejected"
    )
    return 0


def _normalize_grievances(args: argparse.Namespace) -> int:
    counts = normalize_grievances(
        raw_root=Path(args.raw_root),
        warehouse_root=Path(args.warehouse_root),
    )
    print(
        f"normalized grievances: {counts['complaints']} complaints, "
        f"{counts['issue_categories']} categories, {counts['rejected']} rejected"
    )
    return 0


def _normalize_works_payments(args: argparse.Namespace) -> int:
    counts = normalize_works_payments(
        raw_root=Path(args.raw_root),
        warehouse_root=Path(args.warehouse_root),
    )
    print(
        f"normalized works/payments: {counts['works']} works, "
        f"{counts['payments']} payments, {counts['rejected']} rejected"
    )
    return 0


def _normalize_channels(args: argparse.Namespace) -> int:
    counts = normalize_channels(
        raw_root=Path(args.raw_root),
        warehouse_root=Path(args.warehouse_root),
    )
    print(
        f"normalized channels: {counts['agencies']} agencies, "
        f"{counts['complaint_channels']} complaint channels, "
        f"{counts['contact_channels']} contact channels, "
        f"{counts['issue_categories']} issue categories, {counts['rejected']} rejected"
    )
    return 0


def _places_truth(args: argparse.Namespace) -> int:
    write_place_truth(
        query=str(args.q),
        warehouse_root=Path(args.warehouse_root),
        output_path=Path(args.output) if args.output else None,
        year_from=args.year_from,
        year_to=args.year_to,
        lens_label=args.lens_label,
    )
    return 0


def _rag_ask(args: argparse.Namespace) -> int:
    payload = ask_rag(
        query=str(args.q),
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        index_path=Path(args.index) if args.index else None,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _rag_index(args: argparse.Namespace) -> int:
    payload = build_rag_index(
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _rag_explain_packet(args: argparse.Namespace) -> int:
    packet = json.loads(Path(args.packet).read_text())
    payload = explain_packet(packet, question=args.q, mode=args.mode)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _packets_explain(args: argparse.Namespace) -> int:
    packet = json.loads(Path(args.packet).read_text())
    payload = explain_packet(packet, question=args.q, mode=args.mode)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _packets_build(args: argparse.Namespace) -> int:
    payload = build_evidence_packet(
        query=str(args.q),
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        index_path=Path(args.index) if args.index else None,
        lat=args.lat,
        lng=args.lng,
        locality_alias_path=Path(args.locality_aliases) if args.locality_aliases else None,
        boundary_path=Path(args.boundary_path) if args.boundary_path else None,
    )
    text = render_packet_markdown(payload) if args.format == "md" else dumps_packet(payload)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)
    return 0


def _geo_build_boundaries(args: argparse.Namespace) -> int:
    payload = build_boundary_geojson(Path(args.raw_root), Path(args.output))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "feature_count": len(payload.get("features", [])),
                "source_file": payload.get("metadata", {}).get("source_file"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _traces_list(args: argparse.Namespace) -> int:
    print(json.dumps(list_traces(Path(args.trace_path), limit=int(args.limit)), indent=2, sort_keys=True))
    return 0


def _traces_inspect(args: argparse.Namespace) -> int:
    event = inspect_trace(str(args.trace_id), Path(args.trace_path))
    if args.format == "json":
        print(json.dumps(event, indent=2, sort_keys=True))
    else:
        print(render_trace_markdown(event), end="")
    return 0


def _retrieval_build(args: argparse.Namespace) -> int:
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    index_path = output_root / "rag_index.json"
    payload = build_rag_index(
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        output_path=index_path,
    )
    manifest = {
        "retrieval_snapshot_id": f"rag-index:{payload['built_at']}",
        "index_path": str(index_path),
        "chunk_count": payload["chunk_count"],
        "schema_version": payload["schema_version"],
        "built_at": payload["built_at"],
        "backend": "bucketed-json-fallback",
        "note": "Temporary fallback until Postgres/PostGIS/pgvector retrieval is loaded.",
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _eval_rag(args: argparse.Namespace) -> int:
    suite_path = Path(args.suite)
    cases = _read_eval_cases(suite_path)
    results = []
    passed = 0
    for case in cases:
        answer = ask_rag(
            query=str(case["query"]),
            warehouse_root=Path(args.warehouse_root),
            raw_root=Path(args.raw_root),
            index_path=Path(args.index) if args.index else None,
        )
        failures = _eval_case_failures(case, answer)
        status = "passed" if not failures else "failed"
        if status == "passed":
            passed += 1
        results.append({"id": case.get("id"), "status": status, "failures": failures})
    payload = {
        "suite": str(suite_path),
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "results": results,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["failed"] == 0 else 1


def _eval_packets(args: argparse.Namespace) -> int:
    payload = run_packet_eval(
        Path(args.suite),
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        index_path=Path(args.index) if args.index else None,
    )
    if args.report and args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["failed"] == 0 else 1


def _eval_packet_rag(args: argparse.Namespace) -> int:
    payload = run_packet_rag_eval(Path(args.suite), mode=str(args.mode))
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["failed"] == 0 else 1


def _eval_packet_rag_matrix(args: argparse.Namespace) -> int:
    payload = run_packet_rag_matrix(
        Path(args.suite),
        [item.strip() for item in str(args.providers).split(",")],
        Path(args.output),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["summary"]["failed"] == 0 else 1


def _eval_retrieval(args: argparse.Namespace) -> int:
    payload = run_retrieval_eval(
        Path(args.suite),
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        retrieval_mode=str(args.retrieval_mode),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["failed"] == 0 else 1


def _read_eval_cases(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing eval suite: {path}")
    cases = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not item.get("query"):
            raise ValueError(f"Invalid eval case at {path}:{line_number}")
        cases.append(item)
    return cases


def _eval_case_failures(case: dict[str, object], answer: dict[str, object]) -> list[str]:
    failures = []
    expected_place = case.get("expected_place")
    if expected_place and answer.get("normalized_place") != expected_place:
        failures.append(f"expected_place={expected_place}, got={answer.get('normalized_place')}")
    expected_issue = case.get("expected_issue")
    if expected_issue and answer.get("normalized_issue") != expected_issue:
        failures.append(f"expected_issue={expected_issue}, got={answer.get('normalized_issue')}")
    claim_types = {claim.get("claim_type") for claim in answer.get("claims", []) if isinstance(claim, dict)}
    for required in case.get("required_claim_types") or []:
        if required not in claim_types:
            failures.append(f"missing_claim_type={required}")
    for claim in answer.get("claims", []):
        if isinstance(claim, dict) and not claim.get("citation_ids"):
            failures.append(f"uncited_claim={claim.get('claim_type')}")
    return failures


def _warehouse_export(args: argparse.Namespace) -> int:
    manifest = export_wave1_for_postgres(
        warehouse_root=Path(args.warehouse_root),
        export_root=Path(args.export_root),
    )
    table_counts = ", ".join(
        f"{name}={details['rows']}" for name, details in manifest["tables"].items()
    )
    print(f"exported warehouse load artifacts: {table_counts}")
    return 0


def _warehouse_load(args: argparse.Namespace) -> int:
    load_wave1_with_psql(
        database_url=str(args.database_url),
        export_root=Path(args.export_root),
    )
    print("loaded warehouse wave1 via psql")
    return 0


def _dossiers_create(args: argparse.Namespace) -> int:
    create_dossier(
        place=str(args.place),
        warehouse_root=Path(args.warehouse_root),
        output_path=Path(args.output),
    )
    print(f"created dossier: {args.output}")
    return 0


def _demo_report(args: argparse.Namespace) -> int:
    payload = generate_hiring_demo_report(
        warehouse_root=Path(args.warehouse_root),
        raw_root=Path(args.raw_root),
        output_path=Path(args.output),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _site_build(args: argparse.Namespace) -> int:
    places = [parse_place_arg(value) for value in args.place] if args.place else DEFAULT_PLACES
    result = build_site_data(
        registry_path=Path(args.registry),
        schema_path=Path(args.schema),
        raw_root=Path(args.raw_root),
        warehouse_root=Path(args.warehouse_root),
        web_data_root=Path(args.web_data_root),
        dossier_root=Path(args.dossier_root),
        places=places,
    )
    print(
        f"built site data: {result.truth_payloads} truth payloads, "
        f"{result.source_count} sources, {len(result.known_gaps)} known gaps"
    )
    return 0


def _latest_run(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    dirs = [path for path in source_dir.iterdir() if path.is_dir()]
    return sorted(dirs)[-1] if dirs else None


def _latest_status(source_dir: Path) -> str:
    latest = _latest_run(source_dir)
    return _manifest_status(latest) if latest else "not_fetched"


def _manifest_status(run_dir: Path | None) -> str:
    if not run_dir:
        return "not_fetched"
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return "incomplete"
    manifest = json.loads(manifest_path.read_text())
    return str(manifest.get("status", "unknown"))


def _manifest_resource_counts(run_dir: Path | None) -> dict[str, int]:
    empty = {
        "expected_resource_count": 0,
        "fetched_resource_count": 0,
        "failed_resource_count": 0,
        "pending_resource_count": 0,
    }
    if not run_dir:
        return empty
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return empty
    manifest = json.loads(manifest_path.read_text())
    summary = manifest.get("ckan_resources")
    if not isinstance(summary, dict):
        return _infer_v1_ckan_resource_counts(manifest, run_dir)
    return {
        "expected_resource_count": int(summary.get("total", 0) or 0),
        "fetched_resource_count": int(summary.get("completed", 0) or 0),
        "failed_resource_count": int(summary.get("failed", 0) or 0),
        "pending_resource_count": int(summary.get("pending", 0) or 0),
    }


def _infer_v1_ckan_resource_counts(
    manifest: dict[str, object], run_dir: Path
) -> dict[str, int]:
    package_path = run_dir / "original" / "ckan_package.json"
    if not package_path.exists():
        return {
            "expected_resource_count": 0,
            "fetched_resource_count": 0,
            "failed_resource_count": 0,
            "pending_resource_count": 0,
        }
    try:
        package = json.loads(package_path.read_text())
    except json.JSONDecodeError:
        return {
            "expected_resource_count": 0,
            "fetched_resource_count": 0,
            "failed_resource_count": 0,
            "pending_resource_count": 0,
        }
    resources = package.get("result", {}).get("resources", [])
    if not isinstance(resources, list):
        return {
            "expected_resource_count": 0,
            "fetched_resource_count": 0,
            "failed_resource_count": 0,
            "pending_resource_count": 0,
        }
    expected_ids = {
        str(resource.get("id"))
        for resource in resources
        if isinstance(resource, dict)
        and resource.get("state") in (None, "active")
        and resource.get("id")
    }
    fetched_ids = set()
    files = manifest.get("files", [])
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict):
                stem = Path(str(item.get("path", ""))).stem
                if stem in expected_ids:
                    fetched_ids.add(stem)
    expected = len(expected_ids)
    fetched = len(fetched_ids)
    failed = 0 if manifest.get("status") == "success" else max(expected - fetched, 0)
    return {
        "expected_resource_count": expected,
        "fetched_resource_count": fetched if fetched else (expected if manifest.get("status") == "success" else 0),
        "failed_resource_count": failed,
        "pending_resource_count": max(expected - fetched - failed, 0),
    }


if __name__ == "__main__":
    raise SystemExit(main())
