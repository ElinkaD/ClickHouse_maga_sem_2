"""JSON HTTP router for the lab service."""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import handlers
from .clickhouse import ClickHouse
from .config import setting


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.dispatch("GET")

    def do_POST(self) -> None:
        self.dispatch("POST")

    def do_PATCH(self) -> None:
        self.dispatch("PATCH")

    def reply(self, status: int, value: dict | None = None) -> None:
        body = b"" if value is None else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if value is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1_000_000:
                raise ValueError
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, json.JSONDecodeError):
            raise ValueError("invalid JSON body") from None

    def dispatch(self, method: str) -> None:
        url = urlsplit(self.path)
        path = url.path
        params = parse_qs(url.query, keep_blank_values=True)
        if method == "GET" and path == "/ping":
            self.reply(200)
            return

        try:
            db = ClickHouse()
            body = self.read_json() if method in ("POST", "PATCH") else None
            user = re.fullmatch(r"/users/(\d+)", path)
            realty = re.fullmatch(r"/realty/(\d+)", path)
            reading = re.fullmatch(r"/realty/(\d+)/readings", path)
            invoice = re.fullmatch(r"/realty/(\d+)/invoices", path)
            gauge = re.fullmatch(r"/realty/(\d+)/gauges", path)

            if user and method == "GET":
                result = handlers.get_user(db, int(user[1]))
            elif user and method == "PATCH":
                result = handlers.patch_user(db, int(user[1]), body)
            elif realty and method == "GET":
                result = handlers.get_realty(db, int(realty[1]))
            elif reading and method == "POST":
                result = handlers.post_reading(db, int(reading[1]), body)
            elif reading and method == "GET":
                result = handlers.get_readings(db, int(reading[1]), params)
            elif invoice and method == "GET":
                result = handlers.get_invoices(db, int(invoice[1]), params)
            elif path == "/tariffs" and method == "GET":
                result = handlers.get_tariff(db, params)
            elif gauge and method == "POST":
                result = handlers.post_gauge(db, int(gauge[1]), body)
            else:
                result = (404, {"message": "Not found"})
            self.reply(*result)
        except ValueError as exc:
            self.reply(400, {"message": str(exc)})
        except NotImplementedError:
            self.reply(501, {"message": "Not implemented"})
        except (OSError, RuntimeError) as exc:
            self.log_error("Backend error: %s", exc)
            self.reply(500, {"message": "Internal server error"})


def main() -> None:
    port = int(setting("APP_PORT"))
    server = ThreadingHTTPServer(("0.0.0.0", port), RequestHandler)
    print(f"Energosbyt API listening on {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
