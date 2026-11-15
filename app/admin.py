"""Schema creation, CSV loading, and teardown for make targets."""

import argparse
import time
from .clickhouse import ClickHouse
from .config import ROOT
from .generate import TABLES


DDL_DIR = ROOT / "sql" / "ddl"
DATA_DIR = ROOT / "data"


def wait_for_clickhouse(client: ClickHouse) -> None:
    for attempt in range(60):
        try:
            client.execute("SELECT 1", database="default")
            return
        except (OSError, RuntimeError):
            if attempt == 59:
                raise RuntimeError("ClickHouse was not ready after 60 seconds")
            time.sleep(1)


def schema(client: ClickHouse) -> None:
    client.execute("CREATE DATABASE IF NOT EXISTS energosbyt", database="default")
    files = sorted(DDL_DIR.glob("*.sql"))
    if len(files) != len(TABLES):
        raise RuntimeError(f"Expected {len(TABLES)} DDL files, found {len(files)}")
    for path in files:
        client.execute(path.read_text(encoding="utf-8"))
        print(f"Created {path.stem}")


def load(client: ClickHouse) -> None:
    files = {table: DATA_DIR / f"{table}.csv" for table in TABLES}
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise RuntimeError("Missing CSV files: " + ", ".join(missing))

    # Reloading starts from empty tables, including ordinary MergeTree tables.
    for table in TABLES:
        client.execute(f"TRUNCATE TABLE energosbyt.{table}")
    for table, path in files.items():
        start = time.perf_counter()
        client.insert_csv(f"energosbyt.{table}", path)
        print(f"Loaded {table} in {time.perf_counter() - start:.1f} seconds")


def teardown(client: ClickHouse) -> None:
    client.execute("DROP DATABASE IF EXISTS energosbyt SYNC", database="default")
    client.execute("CREATE DATABASE energosbyt", database="default")
    print("Removed all lab tables and data; database energosbyt is empty")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("schema", "load", "teardown"))
    command = parser.parse_args().command
    client = ClickHouse()
    wait_for_clickhouse(client)
    {"schema": schema, "load": load, "teardown": teardown}[command](client)


if __name__ == "__main__":
    main()
