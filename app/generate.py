"""Generate deterministic, headerless CSV files for the seven lab tables."""

import calendar
import csv
import random
import time
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
START = date(2023, 11, 1)
END = date(2026, 10, 31)
REALTY_COUNT = 1_000
REPLACEMENT_DATE = date(2025, 5, 1)
NEW_TARIFF_DATE = date(2025, 11, 1)
TABLES = (
    "dim_realty",
    "dim_gauges",
    "dim_tariffs",
    "dim_users",
    "fact_gauge_bindings",
    "fact_meter_readings",
    "fact_invoice",
)


def next_month_tenth(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 10)


def generate() -> dict[str, int]:
    DATA_DIR.mkdir(exist_ok=True)
    counts = {table: 0 for table in TABLES}

    with ExitStack() as stack:
        writers = {}
        for table in TABLES:
            output = stack.enter_context(
                (DATA_DIR / f"{table}.csv").open("w", encoding="utf-8", newline="")
            )
            writers[table] = csv.writer(output, lineterminator="\n")

        def write(table: str, *values: object) -> None:
            writers[table].writerow(values)
            counts[table] += 1

        write(
            "dim_tariffs", 1, "День–Ночь", 500, 250,
            "2023-11-01 00:00:00", "2025-11-01 00:00:00",
            "2023-10-01 00:00:00", "2023-10-01 00:00:00",
        )
        write(
            "dim_tariffs", 1, "День–Ночь", 620, 310,
            "2025-11-01 00:00:00", "2099-01-01 00:00:00",
            "2025-10-01 00:00:00", "2025-10-01 00:00:00",
        )

        # Keep gauge 2 free for replacing gauge 1 in the API example.
        write("dim_gauges", 2, "Энергомер-резерв", "Россия", "2023-10-01 00:00:00")

        for realty_id in range(1, REALTY_COUNT + 1):
            rng = random.Random(20231101 + realty_id)
            initial_gauge_id = 1 if realty_id == 1 else realty_id + 1
            is_commercial = realty_id % 10 == 0
            building = (realty_id - 1) // 100 + 1
            write(
                "dim_realty", realty_id,
                f"г. Санкт-Петербург, ул. Учебная, д. {building}",
                30 + realty_id % 91, "nrcp" if is_commercial else "flat",
                "" if is_commercial else str((realty_id - 1) % 100 + 1),
                0 if is_commercial else 1 + realty_id % 4,
                1 + realty_id % 20, 1 + realty_id % 5,
                "2023-10-01 00:00:00",
            )
            write(
                "dim_users", realty_id, f"Житель {realty_id} Учебный",
                f"+7{9000000000 + realty_id:010d}", "",
                "2023-10-01 00:00:00", "2023-10-01 00:00:00",
            )
            write(
                "dim_gauges", initial_gauge_id, f"Энергомер-{realty_id % 4 + 1}",
                "Россия", "2023-10-01 00:00:00",
            )
            write(
                "fact_gauge_bindings", initial_gauge_id, realty_id,
                "2023-11-01 00:00:00", 1, 1,
            )

            replacement_id = REALTY_COUNT + 1 + realty_id // 20 if realty_id % 20 == 0 else None
            if replacement_id is not None:
                write(
                    "dim_gauges", replacement_id, f"Энергомер-новый-{realty_id}",
                    "Россия", "2025-05-01 00:00:00",
                )
                write(
                    "fact_gauge_bindings", initial_gauge_id, realty_id,
                    "2023-11-01 00:00:00", -1, 1,
                )
                write(
                    "fact_gauge_bindings", replacement_id, realty_id,
                    "2025-05-01 00:00:00", 1, 2,
                )

            day_kw = night_kw = last_billed_day = last_billed_night = 0
            current = START
            while current <= END:
                day_kw += rng.randint(3, 10)
                night_kw += rng.randint(1, 5)
                gauge_id = (
                    replacement_id
                    if replacement_id is not None and current >= REPLACEMENT_DATE
                    else initial_gauge_id
                )
                write(
                    "fact_meter_readings", realty_id, realty_id, 1,
                    gauge_id, current.isoformat(), day_kw, night_kw,
                    f"{current} 12:00:00",
                )

                actual_day, actual_night = day_kw, night_kw
                if rng.random() < 0.03:
                    actual_day += 1
                    write(
                        "fact_meter_readings", realty_id, realty_id, 1,
                        gauge_id, current.isoformat(), actual_day, actual_night,
                        f"{current} 13:00:00",
                    )

                last_day = calendar.monthrange(current.year, current.month)[1]
                if current.day == last_day:
                    month_day = actual_day - last_billed_day
                    month_night = actual_night - last_billed_night
                    price_day, price_night = (
                        (620, 310) if current >= NEW_TARIFF_DATE else (500, 250)
                    )
                    write(
                        "fact_invoice", realty_id, realty_id, 1, gauge_id,
                        month_day, month_night,
                        month_day * price_day + month_night * price_night,
                        next_month_tenth(current).isoformat(),
                        f"{current} 14:00:00",
                    )
                    last_billed_day, last_billed_night = actual_day, actual_night

                current += timedelta(days=1)

    return counts


def main() -> None:
    started = time.perf_counter()
    for table, count in generate().items():
        print(f"{table}: {count:,} rows")
    print(f"Generated in {time.perf_counter() - started:.1f} seconds")


if __name__ == "__main__":
    main()
