from __future__ import annotations

import hashlib
import json
import re
import signal
import ssl
import shutil
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from civic_data import __version__


class HttpClient(Protocol):
    def get_bytes(self, url: str) -> tuple[bytes, dict[str, str]]:
        ...

    def get_json(self, url: str) -> dict[str, Any]:
        ...


class UrlLibHttpClient:
    def __init__(
        self,
        timeout_seconds: int = 20,
        max_bytes: int = 100 * 1024 * 1024,
        allow_insecure_ssl: bool = False,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.allow_insecure_ssl = allow_insecure_ssl

    def get_bytes(self, url: str) -> tuple[bytes, dict[str, str]]:
        request = urllib.request.Request(url, headers={"User-Agent": "civic-data/0.1"})
        context = ssl._create_unverified_context() if self.allow_insecure_ssl else None
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds, context=context
            ) as response:
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_bytes = int(content_length)
                    except ValueError:
                        declared_bytes = 0
                    if declared_bytes > self.max_bytes:
                        raise RuntimeError(
                            f"Response from {url} declared content-length={content_length}, "
                            f"exceeding max_bytes={self.max_bytes}"
                        )
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise RuntimeError(
                        f"Response from {url} exceeded max_bytes={self.max_bytes}"
                    )
                headers = {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"URL error while fetching {url}: {exc.reason}") from exc
        return body, headers

    def get_json(self, url: str) -> dict[str, Any]:
        body, _headers = self.get_bytes(url)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid JSON response from {url}: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"JSON response from {url} must be an object")
        return data


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    status: str
    run_dir: Path
    errors: list[str]


def fetch_all_sources(
    sources: list[dict[str, Any]],
    raw_root: Path,
    registry_hash_value: str,
    http_client: HttpClient | None = None,
    timestamp: str | None = None,
    progress_callback: Any | None = None,
    source_timeout_seconds: int | None = None,
    resume: bool = False,
    resource_retries: int = 0,
    retry_delay_seconds: float = 1,
    max_resources: int | None = None,
) -> list[FetchResult]:
    client = http_client or UrlLibHttpClient()
    run_timestamp = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    results = []
    for source in sources:
        if source.get("enabled") is False:
            continue
        result = fetch_source(
            source,
            raw_root=raw_root,
            registry_hash_value=registry_hash_value,
            http_client=client,
            timestamp=run_timestamp,
            source_timeout_seconds=source_timeout_seconds,
            resume=resume,
            resource_retries=resource_retries,
            retry_delay_seconds=retry_delay_seconds,
            max_resources=max_resources,
        )
        results.append(result)
        if progress_callback:
            progress_callback(result)
    return results


def fetch_source(
    source: dict[str, Any],
    raw_root: Path,
    registry_hash_value: str,
    http_client: HttpClient | None = None,
    timestamp: str | None = None,
    source_timeout_seconds: int | None = None,
    resume: bool = False,
    resume_from: Path | None = None,
    resource_retries: int = 0,
    retry_delay_seconds: float = 1,
    max_resources: int | None = None,
) -> FetchResult:
    client = http_client or UrlLibHttpClient()
    source_id = _required_string(source, "id")
    url = _required_string(source, "url")
    access_method = _required_string(source, "access_method")
    run_timestamp = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    previous_run = resume_from or (_latest_run_dir(raw_root / source_id) if resume else None)
    run_dir = raw_root / source_id / run_timestamp
    original_dir = run_dir / "original"
    metadata_dir = run_dir / "metadata"
    original_dir.mkdir(parents=True, exist_ok=False)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, Any]] = []
    errors: list[str] = []
    source_metadata: dict[str, Any] = {}
    ckan_records: list[dict[str, Any]] = []

    try:
        with _source_timeout(source_timeout_seconds, source_id):
            if access_method == "opencity_ckan":
                package = _fetch_ckan_package(url, client)
                source_metadata["ckan_package_name"] = package.get("result", {}).get("name")
                package_bytes = json.dumps(package, indent=2, sort_keys=True).encode("utf-8")
                files.append(
                    _write_file(original_dir / "ckan_package.json", package_bytes, "application/json")
                )
                resources = package.get("result", {}).get("resources", [])
                if not isinstance(resources, list):
                    raise RuntimeError("CKAN package result.resources must be a list")
                active_resources = [
                    resource
                    for resource in resources
                    if isinstance(resource, dict) and resource.get("state") in (None, "active")
                ]
                if max_resources is not None:
                    active_resources = active_resources[:max_resources]
                resume_state = _load_resume_state(previous_run) if previous_run else {}
                for resource in active_resources:
                    record, file_record = _fetch_ckan_resource(
                        resource=resource,
                        original_dir=original_dir,
                        run_dir=run_dir,
                        client=client,
                        resume_state=resume_state,
                        resource_retries=resource_retries,
                        retry_delay_seconds=retry_delay_seconds,
                    )
                    ckan_records.append(record)
                    if file_record:
                        files.append(file_record)
            elif access_method in {"direct_file", "official_html", "external_reference", "github"}:
                body, headers = client.get_bytes(url)
                filename = _url_filename(url, access_method, headers.get("content-type", ""))
                files.append(_write_file(original_dir / filename, body, headers.get("content-type", "")))
                _write_json(metadata_dir / "http_headers.json", headers)
            elif access_method == "official_portal_scrape_later":
                body, headers = client.get_bytes(url)
                files.append(_write_file(metadata_dir / "portal_snapshot.html", body, headers.get("content-type", "")))
                _write_json(metadata_dir / "http_headers.json", headers)
            elif access_method == "manual_review":
                source_metadata["manual_review"] = True
            else:
                raise RuntimeError(f"Unsupported access method: {access_method}")
    except Exception as exc:  # noqa: BLE001 - failure manifests must capture all source failures.
        errors.append(str(exc))

    if ckan_records:
        resource_errors = [
            f"{record['resource_id']}: {record['error']}"
            for record in ckan_records
            if record.get("status") == "failed" and record.get("error")
        ]
        errors.extend(resource_errors)
    status = _source_status(files, errors, ckan_records)
    manifest = {
        "manifest_version": 2,
        "source_id": source_id,
        "fetched_at": run_timestamp,
        "fetcher_version": __version__,
        "registry_version_hash": registry_hash_value,
        "status": status,
        "files": [_relative_file_record(run_dir, item) for item in files],
        "errors": errors,
        "source_metadata": source_metadata,
    }
    if ckan_records:
        manifest["ckan_resources"] = _ckan_resource_summary(ckan_records)
    _write_manifest(
        run_dir,
        manifest,
    )
    _write_checksums(run_dir, files)
    (run_dir / "fetch.log").write_text("\n".join(errors) + ("\n" if errors else ""))
    return FetchResult(source_id=source_id, status=status, run_dir=run_dir, errors=errors)


def _fetch_ckan_package(dataset_url: str, client: HttpClient) -> dict[str, Any]:
    dataset_id = dataset_url.rstrip("/").split("/")[-1]
    if not dataset_id:
        raise RuntimeError(f"Could not determine CKAN dataset id from {dataset_url}")
    api_url = f"https://data.opencity.in/api/3/action/package_show?id={dataset_id}"
    package = client.get_json(api_url)
    if package.get("success") is not True:
        raise RuntimeError(f"CKAN package_show failed for {dataset_id}")
    return package


def _fetch_ckan_resource(
    resource: dict[str, Any],
    original_dir: Path,
    run_dir: Path,
    client: HttpClient,
    resume_state: dict[str, dict[str, Any]],
    resource_retries: int,
    retry_delay_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    resource_id = str(resource.get("id") or resource.get("name") or resource.get("url") or "")
    resource_url = resource.get("url")
    filename = _resource_filename(resource, {})
    record: dict[str, Any] = {
        "resource_id": resource_id,
        "name": str(resource.get("name") or ""),
        "url": resource_url if isinstance(resource_url, str) else "",
        "format": str(resource.get("format") or ""),
        "state": str(resource.get("state") or "active"),
        "filename": filename,
        "status": "pending",
        "attempts": 0,
        "path": "",
        "sha256": "",
        "bytes": 0,
        "content_type": "",
        "error": None,
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "reused_from": None,
    }

    if not isinstance(resource_url, str) or not resource_url:
        record["status"] = "failed"
        record["error"] = "CKAN resource missing non-empty url"
        record["completed_at"] = datetime.now(UTC).isoformat()
        return record, None

    reused = _reuse_resource(resource_id, filename, resume_state, original_dir, run_dir)
    if reused:
        file_record, previous_path = reused
        record.update(
            {
                "status": "reused",
                "path": _relative_file_record(run_dir, file_record)["path"],
                "sha256": file_record["sha256"],
                "bytes": file_record["bytes"],
                "content_type": file_record.get("content_type", ""),
                "completed_at": datetime.now(UTC).isoformat(),
                "reused_from": str(previous_path),
            }
        )
        return record, file_record

    last_error = ""
    for attempt in range(1, resource_retries + 2):
        record["attempts"] = attempt
        try:
            body, headers = client.get_bytes(resource_url)
            filename = _resource_filename(resource, headers)
            file_record = _write_file(
                original_dir / filename, body, headers.get("content-type", "")
            )
            relative_file = _relative_file_record(run_dir, file_record)
            record.update(
                {
                    "filename": filename,
                    "status": "success",
                    "path": relative_file["path"],
                    "sha256": file_record["sha256"],
                    "bytes": file_record["bytes"],
                    "content_type": file_record.get("content_type", ""),
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            return record, file_record
        except Exception as exc:  # noqa: BLE001 - per-resource ledger must capture all failures.
            last_error = str(exc)
            if attempt <= resource_retries:
                time.sleep(retry_delay_seconds)

    record["status"] = "failed"
    record["error"] = last_error
    record["completed_at"] = datetime.now(UTC).isoformat()
    return record, None


def _reuse_resource(
    resource_id: str,
    filename: str,
    resume_state: dict[str, dict[str, Any]],
    original_dir: Path,
    run_dir: Path,
) -> tuple[dict[str, Any], Path] | None:
    previous = resume_state.get(resource_id) or resume_state.get(Path(filename).stem)
    if not previous:
        return None
    previous_path = Path(str(previous.get("absolute_path", "")))
    previous_sha = previous.get("sha256")
    if not previous_path.exists() or not isinstance(previous_sha, str):
        return None
    data = previous_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != previous_sha:
        return None
    target = original_dir / filename
    if target.exists():
        target = original_dir / f"{Path(filename).stem}-{digest[:8]}{Path(filename).suffix}"
    shutil.copy2(previous_path, target)
    file_record = {
        "path": str(target),
        "sha256": digest,
        "bytes": len(data),
        "content_type": str(previous.get("content_type", "")),
    }
    return file_record, previous_path


def _load_resume_state(previous_run: Path | None) -> dict[str, dict[str, Any]]:
    if previous_run is None:
        return {}
    manifest_path = previous_run / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return {}

    state: dict[str, dict[str, Any]] = {}
    resource_records = manifest.get("ckan_resources", {}).get("records", [])
    if isinstance(resource_records, list):
        for record in resource_records:
            if not isinstance(record, dict) or record.get("status") not in {"success", "reused"}:
                continue
            path = previous_run / str(record.get("path", ""))
            entry = {
                "absolute_path": str(path),
                "sha256": record.get("sha256"),
                "content_type": record.get("content_type", ""),
            }
            if record.get("resource_id"):
                state[str(record["resource_id"])] = entry
            if record.get("filename"):
                state[Path(str(record["filename"])).stem] = entry

    files = manifest.get("files", [])
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path", ""))
            if path_value.endswith("ckan_package.json"):
                continue
            path = previous_run / path_value
            entry = {
                "absolute_path": str(path),
                "sha256": item.get("sha256"),
                "content_type": item.get("content_type", ""),
            }
            state[Path(path_value).stem] = entry
    return state


def _latest_run_dir(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    dirs = [path for path in source_dir.iterdir() if path.is_dir()]
    return sorted(dirs)[-1] if dirs else None


def _ckan_resource_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = sum(1 for record in records if record.get("status") in {"success", "reused"})
    failed = sum(1 for record in records if record.get("status") == "failed")
    skipped = sum(1 for record in records if record.get("status") == "skipped")
    pending = sum(1 for record in records if record.get("status") == "pending")
    return {
        "total": len(records),
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "pending": pending,
        "records": records,
    }


def _source_status(
    files: list[dict[str, Any]], errors: list[str], ckan_records: list[dict[str, Any]]
) -> str:
    if ckan_records:
        completed = sum(
            1 for record in ckan_records if record.get("status") in {"success", "reused"}
        )
        if completed == len(ckan_records) and not errors:
            return "success"
        if completed > 0:
            return "partial"
        return "failed"
    return "success" if files and not errors else "partial" if files else "failed"


def _resource_filename(resource: dict[str, Any], headers: dict[str, str]) -> str:
    resource_id = str(resource.get("id") or resource.get("name") or "resource")
    fmt = str(resource.get("format") or "").lower()
    if not fmt:
        fmt = _extension_from_content_type(headers.get("content-type", "")) or "bin"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", resource_id).strip("-")
    return f"{safe}.{fmt}"


def _url_filename(url: str, access_method: str, content_type: str) -> str:
    candidate = url.rstrip("/").split("/")[-1]
    if "." not in candidate:
        extension = _extension_from_content_type(content_type) or ("html" if "html" in access_method else "bin")
        candidate = f"snapshot.{extension}"
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", candidate).strip("-") or "snapshot.bin"


def _extension_from_content_type(content_type: str) -> str:
    content_type = content_type.lower()
    if "csv" in content_type:
        return "csv"
    if "json" in content_type:
        return "json"
    if "html" in content_type:
        return "html"
    if "pdf" in content_type:
        return "pdf"
    if "kml" in content_type:
        return "kml"
    return ""


def _write_file(path: Path, body: bytes, content_type: str) -> dict[str, Any]:
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    return {
        "path": str(path),
        "sha256": digest,
        "bytes": len(body),
        "content_type": content_type,
    }


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    _write_json(run_dir / "manifest.json", manifest)


def _write_checksums(run_dir: Path, files: list[dict[str, Any]]) -> None:
    lines = []
    for item in files:
        path = Path(str(item["path"]))
        lines.append(f"{item['sha256']}  {path.relative_to(run_dir)}")
    (run_dir / "checksums.sha256").write_text("\n".join(lines) + ("\n" if lines else ""))


def _relative_file_record(run_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    record = dict(item)
    record["path"] = str(Path(str(item["path"])).relative_to(run_dir))
    return record


def _required_string(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"source.{key} must be a non-empty string")
    return value


@contextmanager
def _source_timeout(seconds: int | None, source_id: str):
    if not seconds:
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)

    def _handle_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"Source {source_id} exceeded source_timeout_seconds={seconds}")

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
