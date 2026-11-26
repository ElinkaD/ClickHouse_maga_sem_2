"""HTTP endpoints for the Energosbyt lab."""

import re
from datetime import date, datetime, timedelta

from .clickhouse import ClickHouse


NOT_FOUND = (404, {"message": "Not found"})


def _invalid(name: str, kind: str = "field") -> tuple[int, dict]:
    return 400, {"message": f'invalid "{name}" {kind}'}


def _uint(value: object, bits: int = 64, *, positive: bool = True) -> bool:
    return (
        type(value) is int
        and (value > 0 if positive else value >= 0)
        and value < 2**bits
    )


def _date(value: object) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _exists(db: ClickHouse, table: str, object_id: int) -> bool:
    if table not in {"dim_realty", "dim_gauges", "dim_users", "dim_tariffs"}:
        raise ValueError("invalid table")
    final = " FINAL" if table in {"dim_users", "dim_tariffs"} else ""
    return bool(
        db.rows(
            f"SELECT id FROM energosbyt.{table}{final} WHERE id = {{id:UInt64}} LIMIT 1",
            {"id": object_id},
        )
    )


def _later_than(previous: str) -> str:
    """Produce a DateTime version strictly newer than a stored one."""
    now = datetime.now().replace(microsecond=0)
    old = datetime.fromisoformat(previous)
    return max(now, old + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")


def get_user(db: ClickHouse, user_id: int) -> tuple[int, dict | None]:
    rows = db.rows(
        """SELECT id, fio, phone, phone_prev
           FROM energosbyt.dim_users FINAL
           WHERE id = {id:UInt64}
           LIMIT 1""",
        {"id": user_id},
    )
    if not rows:
        return 404, {"message": "Not found"}
    return 200, rows[0]


def patch_user(db: ClickHouse, user_id: int, body: dict) -> tuple[int, dict | None]:
    if not any(key in body for key in ("fio", "phone")):
        return _invalid("fio")
    for field in ("fio", "phone"):
        if field in body and (not isinstance(body[field], str) or not body[field].strip()):
            return _invalid(field)

    rows = db.rows(
        """SELECT id, fio, phone, phone_prev, created_at, updated_at
           FROM energosbyt.dim_users FINAL
           WHERE id = {id:UInt64} LIMIT 1""",
        {"id": user_id},
    )
    if not rows:
        return NOT_FOUND
    old = rows[0]
    new_fio = body.get("fio", old["fio"])
    new_phone = body.get("phone", old["phone"])
    new_phone_prev = old["phone"] if new_phone != old["phone"] else old["phone_prev"]
    db.execute(
        """INSERT INTO energosbyt.dim_users
           (id, fio, phone, phone_prev, created_at, updated_at)
           SELECT {id:UInt64}, {fio:String}, {phone:String}, {phone_prev:String},
                  {created_at:DateTime}, {updated_at:DateTime}""",
        {
            "id": user_id,
            "fio": new_fio,
            "phone": new_phone,
            "phone_prev": new_phone_prev,
            "created_at": old["created_at"],
            "updated_at": _later_than(old["updated_at"]),
        },
    )
    return 204, None


def get_realty(db: ClickHouse, realty_id: int) -> tuple[int, dict | None]:
    rows = db.rows(
        """SELECT id, address, square, type, number, rooms, floor, porch
           FROM energosbyt.dim_realty
           WHERE id = {id:UInt64}
           LIMIT 1""",
        {"id": realty_id},
    )
    if not rows:
        return 404, {"message": "Not found"}
    return 200, rows[0]


def post_reading(db: ClickHouse, realty_id: int, body: dict) -> tuple[int, dict | None]:
    reading_date = _date(body.get("reading_date"))
    if reading_date is None:
        return _invalid("reading_date")
    for field in ("user_id", "gauge_id", "tariff_id"):
        if not _uint(body.get(field)):
            return _invalid(field)
    for field in ("day_kw", "night_kw"):
        if not _uint(body.get(field), 32, positive=False):
            return _invalid(field)

    if not all(
        _exists(db, table, object_id)
        for table, object_id in (
            ("dim_realty", realty_id),
            ("dim_users", body["user_id"]),
            ("dim_gauges", body["gauge_id"]),
            ("dim_tariffs", body["tariff_id"]),
        )
    ):
        return NOT_FOUND

    previous = db.rows(
        """SELECT created_at FROM energosbyt.fact_meter_readings FINAL
           WHERE realty_id = {realty_id:UInt64}
             AND reading_date = {reading_date:Date} LIMIT 1""",
        {"realty_id": realty_id, "reading_date": reading_date.isoformat()},
    )
    created_at = (
        _later_than(previous[0]["created_at"])
        if previous else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.execute(
        """INSERT INTO energosbyt.fact_meter_readings
           (realty_id, user_id, tariff_id, gauge_id, reading_date,
            day_kw, night_kw, created_at)
           SELECT {realty_id:UInt64}, {user_id:UInt64}, {tariff_id:UInt64},
                  {gauge_id:UInt64}, {reading_date:Date}, {day_kw:UInt32},
                  {night_kw:UInt32}, {created_at:DateTime}""",
        {
            "realty_id": realty_id,
            "user_id": body["user_id"],
            "tariff_id": body["tariff_id"],
            "gauge_id": body["gauge_id"],
            "reading_date": reading_date.isoformat(),
            "day_kw": body["day_kw"],
            "night_kw": body["night_kw"],
            "created_at": created_at,
        },
    )
    return 201, None


def get_readings(
    db: ClickHouse, realty_id: int, params: dict[str, list[str]]
) -> tuple[int, dict | None]:
    dates = {}
    for field in ("date_from", "date_to"):
        dates[field] = _date(params.get(field, [None])[0])
        if dates[field] is None:
            return _invalid(field, "parameter")
    if dates["date_from"] > dates["date_to"]:
        return _invalid("date_from", "parameter")
    if not _exists(db, "dim_realty", realty_id):
        return NOT_FOUND

    rows = db.rows(
        """SELECT reading_date, user_id, tariff_id, gauge_id, day_kw, night_kw
           FROM energosbyt.fact_meter_readings FINAL
           WHERE realty_id = {realty_id:UInt64}
             AND reading_date >= {date_from:Date}
             AND reading_date <= {date_to:Date}
           ORDER BY reading_date""",
        {
            "realty_id": realty_id,
            "date_from": dates["date_from"].isoformat(),
            "date_to": dates["date_to"].isoformat(),
        },
    )
    return 200, {"readings": rows, "count": len(rows)}


def get_invoices(
    db: ClickHouse, realty_id: int, params: dict[str, list[str]]
) -> tuple[int, dict | None]:
    pagination = {}
    for field, default in (("limit", "10"), ("offset", "0")):
        value = params.get(field, [default])[0]
        if (
            not isinstance(value, str) or len(value) > 20
            or not value.isascii() or not value.isdecimal()
        ):
            return _invalid(field, "parameter")
        pagination[field] = int(value)
        if pagination[field] >= 2**64:
            return _invalid(field, "parameter")
    if not _exists(db, "dim_realty", realty_id):
        return NOT_FOUND

    count = db.rows(
        """SELECT count() AS count FROM energosbyt.fact_invoice
           WHERE realty_id = {realty_id:UInt64}""",
        {"realty_id": realty_id},
    )[0]["count"]
    rows = db.rows(
        """SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at
           FROM energosbyt.fact_invoice
           WHERE realty_id = {realty_id:UInt64}
           ORDER BY created_at DESC
           LIMIT {limit:UInt64} OFFSET {offset:UInt64}""",
        {"realty_id": realty_id, **pagination},
    )
    return 200, {"invoices": rows, "count": int(count)}


def get_tariff(db: ClickHouse, params: dict[str, list[str]]) -> tuple[int, dict | None]:
    selected_date = _date(params.get("date", [None])[0])
    if selected_date is None:
        return _invalid("date", "parameter")
    rows = db.rows(
        """SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to
           FROM energosbyt.dim_tariffs FINAL
           WHERE valid_from <= toDateTime({day:Date})
             AND toDateTime({day:Date}) < valid_to
           ORDER BY valid_from DESC
           LIMIT 1""",
        {"day": selected_date.isoformat()},
    )
    if not rows:
        return NOT_FOUND
    return 200, rows[0]


def post_gauge(db: ClickHouse, realty_id: int, body: dict) -> tuple[int, dict | None]:
    gauge_id = body.get("gauge_id")
    if not _uint(gauge_id):
        return _invalid("gauge_id")
    if not _exists(db, "dim_realty", realty_id) or not _exists(db, "dim_gauges", gauge_id):
        return NOT_FOUND

    active = db.rows(
        """SELECT gauge_id, created_at, version
           FROM energosbyt.fact_gauge_bindings FINAL
           WHERE realty_id = {realty_id:UInt64} AND sign = 1
           ORDER BY version DESC LIMIT 1""",
        {"realty_id": realty_id},
    )
    if active:
        old = active[0]
        db.execute(
            """INSERT INTO energosbyt.fact_gauge_bindings
               (gauge_id, realty_id, created_at, sign, version)
               SELECT {old_gauge_id:UInt64}, {realty_id:UInt64},
                      {old_created_at:DateTime}, toInt8(-1), {old_version:UInt64}
               UNION ALL
               SELECT {new_gauge_id:UInt64}, {realty_id:UInt64},
                      now(), toInt8(1), {new_version:UInt64}""",
            {
                "old_gauge_id": int(old["gauge_id"]),
                "old_created_at": old["created_at"],
                "old_version": int(old["version"]),
                "new_gauge_id": gauge_id,
                "new_version": int(old["version"]) + 1,
                "realty_id": realty_id,
            },
        )
    else:
        db.execute(
            """INSERT INTO energosbyt.fact_gauge_bindings
               (gauge_id, realty_id, created_at, sign, version)
               SELECT {gauge_id:UInt64}, {realty_id:UInt64}, now(), toInt8(1),
                      toUInt64(1)""",
            {"gauge_id": gauge_id, "realty_id": realty_id},
        )
    return 201, None
