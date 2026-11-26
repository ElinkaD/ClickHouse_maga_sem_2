"""ClickHouse HTTP client shared by the loader and API handlers."""

import base64
import http.client
import json
from pathlib import Path
from urllib.parse import urlencode

from .config import setting


class ClickHouse:
    def __init__(self) -> None:
        self.host = setting("CLICKHOUSE_HOST")
        self.port = int(setting("CLICKHOUSE_HTTP_PORT"))
        self.database = setting("CLICKHOUSE_DATABASE")
        credentials = f'{setting("CLICKHOUSE_USER")}:{setting("CLICKHOUSE_PASSWORD")}'
        self.authorization = "Basic " + base64.b64encode(credentials.encode()).decode()

    def _path(
        self, sql: str, params: dict[str, object] | None = None,
        database: str | None = None,
    ) -> str:
        query: dict[str, object] = {
            "database": database or self.database,
            "query": sql,
            "output_format_json_quote_64bit_integers": 0,
        }
        if params:
            query.update({f"param_{key}": value for key, value in params.items()})
        return "/?" + urlencode(query)

    def _response(self, response: http.client.HTTPResponse) -> bytes:
        body = response.read()
        if response.status >= 400:
            raise RuntimeError(f"ClickHouse HTTP {response.status}: {body[:500].decode(errors='replace')}")
        return body

    def execute(
        self, sql: str, params: dict[str, object] | None = None,
        database: str | None = None,
    ) -> bytes:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=60)
        try:
            connection.request(
                "POST", self._path(sql, params, database),
                headers={"Authorization": self.authorization},
            )
            return self._response(connection.getresponse())
        finally:
            connection.close()

    def rows(self, sql: str, params: dict[str, object] | None = None) -> list[dict]:
        """Run a SELECT using ClickHouse {name:Type} query parameters."""
        payload = self.execute(sql.rstrip().rstrip(";") + " FORMAT JSONEachRow", params)
        return [json.loads(line) for line in payload.splitlines()]

    def insert_csv(self, table: str, csv_path: Path) -> None:
        """Stream a headerless CSV in one insert without loading it into Python RAM."""
        connection = http.client.HTTPConnection(self.host, self.port, timeout=300)
        try:
            connection.putrequest("POST", self._path(f"INSERT INTO {table} FORMAT CSV"))
            connection.putheader("Authorization", self.authorization)
            connection.putheader("Content-Type", "text/csv; charset=utf-8")
            connection.putheader("Content-Length", str(csv_path.stat().st_size))
            connection.endheaders()
            with csv_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    connection.send(chunk)
            self._response(connection.getresponse())
        finally:
            connection.close()
