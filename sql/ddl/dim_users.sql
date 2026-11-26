CREATE TABLE IF NOT EXISTS energosbyt.dim_users (
    id UInt64,
    fio String, -- SCD 1: новое значение заменяет прежнее
    phone String, -- SCD 3: текущий телефон
    phone_prev String, -- SCD 3: предыдущий телефон
    created_at DateTime,
    updated_at DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY id;
