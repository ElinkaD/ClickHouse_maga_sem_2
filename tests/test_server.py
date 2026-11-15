"""HTTP status, JSON shape, and empty-body checks through the real router."""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import server


class FakeDB:
    def rows(self, sql, params):
        if "dim_users" in sql:
            return [{"id": 1, "fio": "Иванов", "phone": "111", "phone_prev": ""}]
        return []


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_client = server.ClickHouse
        server.ClickHouse = FakeDB
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.RequestHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        server.ClickHouse = cls.real_client

    def test_ping_has_empty_body(self):
        with urlopen(self.base + "/ping") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"")
            self.assertEqual(response.headers["Content-Length"], "0")

    def test_user_response_is_json(self):
        with urlopen(self.base + "/users/1") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response)["id"], 1)

    def test_invalid_request_is_json_error(self):
        request = Request(
            self.base + "/users/1", data=b"{}", method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)
        self.assertIn("message", json.load(error.exception))


if __name__ == "__main__":
    unittest.main()
