"""Hardware-free Robot Protocol v1 voice probe.

The probe performs OTA manifest and login HTTP checks first, then optionally
opens the Robot Protocol v1 WebSocket and sends a heartbeat plus one final text
utterance. It never prints the supplied device token.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROBOT_WS_PREFIX = "/api/v1/robot/ws/"
ROBOT_OTA_PREFIX = "/api/v1/robot/ota/manifest/"
LOGIN_PATH = "/api/v1/auth/login"
BODY_LIMIT = 700
PROBE_CURRENT_VERSION = "2026.09.10+0"
LOGIN_REACHABLE_STATUS_CODES = {400, 401, 403, 422, 429}


class ProbeError(RuntimeError):
    """Expected probe failure with a bounded user-facing message."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = normalize_base_url(args.base_url)
    result: dict[str, Any] = {
        "device_id": args.device_id,
        "ota_manifest": {},
        "login": {},
        "websocket": {},
    }

    try:
        result["ota_manifest"] = probe_ota_manifest(
            base_url=base_url,
            device_id=args.device_id,
            device_token=args.device_token,
            timeout_seconds=args.timeout_seconds,
            no_proxy=args.no_proxy,
        )
    except ProbeError as exc:
        result["ota_manifest"] = {"ok": False, "error": str(exc)}

    try:
        result["login"] = probe_login_path(
            base_url=base_url,
            timeout_seconds=args.timeout_seconds,
            no_proxy=args.no_proxy,
        )
    except ProbeError as exc:
        result["login"] = {"ok": False, "error": str(exc)}

    try:
        result["websocket"] = probe_websocket(
            base_url=base_url,
            device_id=args.device_id,
            device_token=args.device_token,
            session_id=args.session_id,
            utterance=args.utterance,
            timeout_seconds=args.timeout_seconds,
            max_ws_frames=args.max_ws_frames,
            no_proxy=args.no_proxy,
        )
    except ProbeError as exc:
        result["websocket"] = {"ok": False, "error": str(exc)}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if result["ota_manifest"].get("ok")
        and result["login"].get("ok")
        and result["websocket"].get("ok")
        else 1
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe robot OTA and voice WebSocket paths without robot hardware."
    )
    parser.add_argument("--base-url", required=True, help="Server base URL, for example http://host:32020")
    parser.add_argument("--device-id", required=True, help="Robot device id bound to the token")
    parser.add_argument("--device-token", required=True, help="Robot device token; never printed")
    parser.add_argument("--utterance", required=True, help="Final text utterance to send over WebSocket")
    parser.add_argument("--session-id", default="probe-session", help="Robot Protocol v1 session id")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP and WS timeout")
    parser.add_argument("--max-ws-frames", type=int, default=8, help="Maximum WS frames to read for final text")
    parser.add_argument(
        "--no-proxy",
        dest="no_proxy",
        action="store_true",
        default=True,
        help="Bypass environment proxies for production/debug robot endpoints; default on",
    )
    parser.add_argument(
        "--allow-proxy",
        dest="no_proxy",
        action="store_false",
        help="Allow configured environment proxies",
    )
    return parser.parse_args(argv)


def normalize_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ProbeError("--base-url must include http(s):// or ws(s):// and a host")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def probe_ota_manifest(
    *,
    base_url: str,
    device_id: str,
    device_token: str,
    timeout_seconds: float,
    no_proxy: bool,
) -> dict[str, Any]:
    query = urlencode({"current_version": PROBE_CURRENT_VERSION, "protocol_version": "1"})
    url = f"{http_base_url(base_url)}{ROBOT_OTA_PREFIX}{quote(device_id, safe='')}?{query}"
    request = Request(url, headers={"X-Robot-Device-Token": device_token})
    try:
        with open_http(request, timeout_seconds=timeout_seconds, no_proxy=no_proxy) as response:
            body = response.read(BODY_LIMIT + 1).decode("utf-8", errors="replace")
            payload = parse_json_body(body)
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "decision": payload.get("decision") if isinstance(payload, dict) else None,
                "body_preview": truncate(body),
            }
    except HTTPError as exc:
        body = exc.read(BODY_LIMIT + 1).decode("utf-8", errors="replace")
        raise ProbeError(f"OTA manifest HTTP {exc.code}: {truncate(body)}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ProbeError(f"OTA manifest request failed: {truncate(str(exc))}") from exc


def probe_login_path(
    *,
    base_url: str,
    timeout_seconds: float,
    no_proxy: bool,
) -> dict[str, Any]:
    request = Request(
        f"{http_base_url(base_url)}{LOGIN_PATH}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with open_http(request, timeout_seconds=timeout_seconds, no_proxy=no_proxy) as response:
            body = response.read(BODY_LIMIT + 1).decode("utf-8", errors="replace")
            return {
                "ok": 200 <= response.status < 500,
                "status": response.status,
                "body_preview": truncate(body),
            }
    except HTTPError as exc:
        body = exc.read(BODY_LIMIT + 1).decode("utf-8", errors="replace")
        return {
            "ok": exc.code in LOGIN_REACHABLE_STATUS_CODES,
            "status": exc.code,
            "body_preview": truncate(body),
        }
    except (TimeoutError, URLError, OSError) as exc:
        raise ProbeError(f"login request failed: {truncate(str(exc))}") from exc


def probe_websocket(
    *,
    base_url: str,
    device_id: str,
    device_token: str,
    session_id: str,
    utterance: str,
    timeout_seconds: float,
    max_ws_frames: int,
    no_proxy: bool,
) -> dict[str, Any]:
    try:
        from websocket import WebSocketTimeoutException, create_connection
    except ImportError as exc:
        raise ProbeError(
            "WebSocket probe skipped: install optional dependency websocket-client to test "
            "/api/v1/robot/ws/ without hardware."
        ) from exc

    url = f"{websocket_base_url(base_url)}{ROBOT_WS_PREFIX}{quote(device_id, safe='')}"
    socket_handle = None
    try:
        socket_handle = create_connection(
            url,
            header=[f"X-Robot-Device-Token: {device_token}"],
            timeout=timeout_seconds,
            **websocket_proxy_options(no_proxy),
        )
        sent_types = ["device.heartbeat", "speech.partial"]
        socket_handle.send(
            json.dumps(
                build_envelope(
                    message_type="device.heartbeat",
                    device_id=device_id,
                    session_id=session_id,
                    payload={"runtime_version": "probe"},
                ),
                ensure_ascii=False,
            )
        )
        socket_handle.send(
            json.dumps(
                build_envelope(
                    message_type="speech.partial",
                    device_id=device_id,
                    session_id=session_id,
                    payload={"text": utterance, "is_final": True},
                ),
                ensure_ascii=False,
            )
        )
        final_frame = receive_final_assistant_frame(socket_handle, max_ws_frames=max_ws_frames)
        return {"ok": True, "sent_types": sent_types, **final_frame}
    except WebSocketTimeoutException as exc:
        raise ProbeError("WebSocket timed out waiting for assistant.text.done") from exc
    except Exception as exc:
        raise ProbeError(f"WebSocket probe failed: {truncate(str(exc))}") from exc
    finally:
        if socket_handle is not None:
            socket_handle.close()


def receive_final_assistant_frame(socket_handle: Any, *, max_ws_frames: int) -> dict[str, Any]:
    ignored_types: list[str] = []
    for _frame_number in range(max_ws_frames):
        raw_response = socket_handle.recv()
        if isinstance(raw_response, bytes):
            raw_response = raw_response.decode("utf-8", errors="replace")
        payload = parse_json_body(str(raw_response))
        response_type = payload.get("type") if isinstance(payload, dict) else None
        if response_type == "assistant.text.done":
            response_payload = payload.get("payload") if isinstance(payload, dict) else None
            response_text = response_payload.get("text") if isinstance(response_payload, dict) else None
            return {
                "received_type": response_type,
                "received_text": response_text if isinstance(response_text, str) else None,
                "ignored_types": ignored_types,
            }
        if isinstance(response_type, str):
            ignored_types.append(response_type)
    raise ProbeError(
        "WebSocket did not receive assistant.text.done within "
        f"{max_ws_frames} frames; ignored_types={ignored_types}"
    )


def build_envelope(
    *,
    message_type: str,
    device_id: str,
    session_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "protocol_version": "1",
        "message_id": uuid4().hex,
        "session_id": session_id,
        "device_id": device_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "type": message_type,
        "payload": payload,
    }


def open_http(request: Request, *, timeout_seconds: float, no_proxy: bool) -> Any:
    opener = build_opener(ProxyHandler({})) if no_proxy else build_opener()
    return opener.open(request, timeout=timeout_seconds)


def websocket_proxy_options(no_proxy: bool) -> dict[str, object]:
    if not no_proxy:
        return {}
    return {
        "http_proxy_host": None,
        "http_proxy_port": None,
        "http_no_proxy": ["*"],
    }


def http_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    return urlunsplit((scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def websocket_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme, parsed.scheme)
    return urlunsplit((scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def parse_json_body(body: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def truncate(value: str) -> str:
    value = value.replace("\r", "\\r").replace("\n", "\\n")
    if len(value) <= BODY_LIMIT:
        return value
    return f"{value[:BODY_LIMIT]}..."


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from error
