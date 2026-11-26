CREATE TABLE IF NOT EXISTS energosbyt.dim_tariffs (
    id UInt64,
    name String,
    price_day_kwph UInt32, -- Копейки за кВт·ч
    price_night_kwph UInt32, -- Копейки за кВт·ч
    valid_from DateTime,
    valid_to DateTime, -- 2099-01-01 00:00:00 для открытой версии
    created_at DateTime,
    updated_at DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (id, valid_from);
