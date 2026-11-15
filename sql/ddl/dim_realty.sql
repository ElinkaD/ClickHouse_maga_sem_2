CREATE TABLE IF NOT EXISTS energosbyt.dim_realty (
    id UInt64,
    address String,
    square UInt32, -- Площадь в м²
    type String, -- flat или nrcp
    number String, -- Пустая строка для нежилого помещения
    rooms UInt8,
    floor UInt8,
    porch UInt8,
    created_at DateTime
) ENGINE = MergeTree()
ORDER BY id;
