# Проверка SCD

После `make run` и `make setup` запустите [Postman-коллекцию](../api/energosbyt.postman_collection.json). Она меняет собственника, показание за 2026-10-01 и счётчик объекта `id = 1`. SQL ниже выполняется после коллекции через `docker compose exec clickhouse clickhouse-client` (или любой клиент ClickHouse). Для повторной проверки исходные данные восстанавливаются командой `make setup`.

### SCD 1 — смена фамилии

Коллекция вызывает `PATCH /users/1` с новым ФИО. Актуальная строка содержит только новое значение:

```sql
SELECT fio
FROM energosbyt.dim_users FINAL
WHERE id = 1;
-- Петрова Анна Сергеевна
```

### SCD 3 — две смены телефона

После двух `PATCH /users/1` остаются последний и предпоследний номера:

```sql
SELECT phone, phone_prev
FROM energosbyt.dim_users FINAL
WHERE id = 1;
-- +79222222222, +79111111111
```

### SCD 2 — тариф с 1 ноября

Запросы `GET /tariffs?date=2025-10-31` и `GET /tariffs?date=2025-11-01` возвращают разные цены. В таблице обе версии:

```sql
SELECT valid_from, valid_to, price_day_kwph, price_night_kwph
FROM energosbyt.dim_tariffs FINAL
WHERE id = 1
ORDER BY valid_from;
-- 2023-11-01 .. 2025-11-01: 500, 250
-- 2025-11-01 .. 2099-01-01: 620, 310
```

### Пересчёт старого счёта

Октябрьский счёт пересчитывается по тарифу, действовавшему на дату счёта. Его сохранённая сумма совпадает с расчётом по старой цене:

```sql
SELECT i.price, i.day_kw * t.price_day_kwph + i.night_kw * t.price_night_kwph AS recalculated
FROM energosbyt.fact_invoice AS i
CROSS JOIN
(
    SELECT price_day_kwph, price_night_kwph
    FROM energosbyt.dim_tariffs FINAL
    WHERE id = 1
      AND valid_from <= toDateTime('2025-10-31 14:00:00')
      AND valid_to > toDateTime('2025-10-31 14:00:00')
) AS t
WHERE i.realty_id = 1 AND i.created_at = toDateTime('2025-10-31 14:00:00');
-- price = recalculated
```

### Корректировка показания

Коллекция повторно передаёт показание за 2026-10-01. `FINAL` оставляет одну актуальную строку:

```sql
SELECT reading_date, day_kw, night_kw
FROM energosbyt.fact_meter_readings FINAL
WHERE realty_id = 1 AND reading_date = toDate('2026-10-01');
-- Одна строка: 2026-10-01, 1250, 300
```

### Замена счётчика

После `POST /realty/1/gauges` со счётчиком `2` старая установка аннулирована, активна только новая:

```sql
SELECT gauge_id, sign, version
FROM energosbyt.fact_gauge_bindings FINAL
WHERE realty_id = 1;
-- Одна строка: gauge_id = 2, sign = 1, version = 2
```

### Удаление ошибочной строки

Добавим копию октябрьского счёта с лишним нулём в сумме, затем удалим только эту строку:

```sql
INSERT INTO energosbyt.fact_invoice
    (realty_id, user_id, tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at)
SELECT realty_id, user_id, tariff_id, gauge_id, day_kw, night_kw,
       price * 10, deadline, created_at + INTERVAL 1 SECOND
FROM energosbyt.fact_invoice
WHERE realty_id = 1 AND created_at = toDateTime('2025-10-31 14:00:00');

SELECT price
FROM energosbyt.fact_invoice
WHERE realty_id = 1 AND created_at = toDateTime('2025-10-31 14:00:01');
-- Сумма в 10 раз больше исходной

ALTER TABLE energosbyt.fact_invoice DELETE
WHERE realty_id = 1 AND created_at = toDateTime('2025-10-31 14:00:01')
SETTINGS mutations_sync = 1;

SELECT count()
FROM energosbyt.fact_invoice
WHERE realty_id = 1 AND created_at = toDateTime('2025-10-31 14:00:01');
-- 0
```
