CREATE TABLE IF NOT EXISTS energosbyt.fact_gauge_bindings (
    gauge_id UInt64,
    realty_id UInt64,
    created_at DateTime,
    sign Int8, -- 1: установка, -1: аннулирование
    version UInt64
) ENGINE = VersionedCollapsingMergeTree(sign, version)
ORDER BY (realty_id, gauge_id);
