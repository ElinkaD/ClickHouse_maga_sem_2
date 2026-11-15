"""Contract checks for handler decisions without a running ClickHouse server."""

import unittest

from app import handlers


class FakeDB:
    def __init__(self, callback):
        self.callback = callback
        self.executed = []

    def rows(self, sql, params):
        return self.callback(sql, params)

    def execute(self, sql, params):
        self.executed.append((sql, params))


class HandlerTests(unittest.TestCase):
    def test_get_user_uses_current_version(self):
        user = {"id": 1, "fio": "Иванов", "phone": "111", "phone_prev": ""}

        def query(sql, params):
            self.assertIn("dim_users FINAL", sql)
            self.assertEqual(params, {"id": 1})
            return [user]

        self.assertEqual(handlers.get_user(FakeDB(query), 1), (200, user))
        self.assertEqual(handlers.get_user(FakeDB(lambda *_: []), 1), handlers.NOT_FOUND)

    def test_patch_user_keeps_phone_history_and_original_creation(self):
        old = {
            "id": 1, "fio": "Иванов", "phone": "111", "phone_prev": "000",
            "created_at": "2023-10-01 00:00:00", "updated_at": "2026-01-01 00:00:00",
        }
        db = FakeDB(lambda *_: [old])
        self.assertEqual(handlers.patch_user(db, 1, {"phone": "222"}), (204, None))
        sql, values = db.executed[0]
        self.assertIn("INSERT INTO energosbyt.dim_users", sql)
        self.assertEqual(values["fio"], "Иванов")
        self.assertEqual(values["phone_prev"], "111")
        self.assertEqual(values["created_at"], old["created_at"])
        self.assertGreater(values["updated_at"], old["updated_at"])

    def test_patch_user_rejects_empty_body(self):
        db = FakeDB(lambda *_: self.fail("should not query"))
        self.assertEqual(handlers.patch_user(db, 1, {})[0], 400)

    def test_post_reading_creates_later_correction(self):
        def query(sql, _):
            if "fact_meter_readings" in sql:
                return [{"created_at": "2026-10-01 12:00:00"}]
            return [{"id": 1}]

        db = FakeDB(query)
        body = {
            "user_id": 1, "gauge_id": 1, "tariff_id": 1,
            "reading_date": "2026-10-01", "day_kw": 123, "night_kw": 45,
        }
        self.assertEqual(handlers.post_reading(db, 1, body), (201, None))
        self.assertGreater(db.executed[0][1]["created_at"], "2026-10-01 12:00:00")
        self.assertEqual(handlers.post_reading(db, 1, {"reading_date": "bad"})[0], 400)

    def test_reading_period_is_inclusive_and_count_matches(self):
        reading = {"reading_date": "2026-10-01", "day_kw": 123}

        def query(sql, params):
            if "dim_realty" in sql:
                return [{"id": 1}]
            self.assertIn("fact_meter_readings FINAL", sql)
            self.assertIn("reading_date <=", sql)
            self.assertEqual(params["date_to"], "2026-10-31")
            return [reading]

        result = handlers.get_readings(
            FakeDB(query), 1, {"date_from": ["2026-10-01"], "date_to": ["2026-10-31"]}
        )
        self.assertEqual(result, (200, {"readings": [reading], "count": 1}))

    def test_invoices_return_total_count_not_page_size(self):
        def query(sql, params):
            if "dim_realty" in sql:
                return [{"id": 1}]
            if "count()" in sql:
                return [{"count": 36}]
            self.assertEqual(params["limit"], 2)
            self.assertEqual(params["offset"], 5)
            return [{"price": 100}]

        result = handlers.get_invoices(FakeDB(query), 1, {"limit": ["2"], "offset": ["5"]})
        self.assertEqual(result, (200, {"invoices": [{"price": 100}], "count": 36}))
        self.assertEqual(handlers.get_invoices(FakeDB(query), 1, {"limit": ["-1"]})[0], 400)

    def test_tariff_uses_request_date(self):
        def query(sql, params):
            self.assertIn("dim_tariffs FINAL", sql)
            self.assertIn("< valid_to", sql)
            self.assertEqual(params, {"day": "2025-11-01"})
            return [{"id": 1, "price_day_kwph": 620}]

        self.assertEqual(handlers.get_tariff(FakeDB(query), {"date": ["2025-11-01"]})[0], 200)
        self.assertEqual(handlers.get_tariff(FakeDB(query), {"date": ["bad"]})[0], 400)

    def test_gauge_replacement_copies_cancelled_state(self):
        def query(sql, _):
            if "fact_gauge_bindings" in sql:
                return [{"gauge_id": 1, "created_at": "2023-11-01 00:00:00", "version": 1}]
            return [{"id": 1}]

        db = FakeDB(query)
        self.assertEqual(handlers.post_gauge(db, 1, {"gauge_id": 2}), (201, None))
        sql, values = db.executed[0]
        self.assertIn("toInt8(-1)", sql)
        self.assertEqual(values["old_gauge_id"], 1)
        self.assertEqual(values["old_created_at"], "2023-11-01 00:00:00")
        self.assertEqual(values["old_version"], 1)
        self.assertEqual(values["new_gauge_id"], 2)
        self.assertEqual(values["new_version"], 2)

    def test_first_gauge_installation_starts_at_version_one(self):
        db = FakeDB(lambda sql, _: [] if "fact_gauge_bindings" in sql else [{"id": 1}])
        self.assertEqual(handlers.post_gauge(db, 1, {"gauge_id": 2}), (201, None))
        self.assertIn("toUInt64(1)", db.executed[0][0])


if __name__ == "__main__":
    unittest.main()
