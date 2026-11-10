"""Measurement frame reader. Calibration records are keyed by numeric type ID."""
from decimal import Decimal


TYPE_RECORDS = {}


def decode(frame_hex):
    frame = bytes.fromhex(frame_hex)
    if len(frame) != 9:
        raise ValueError("A measurement frame is nine bytes long")
    type_id = int.from_bytes(frame[:2], "big")
    record = TYPE_RECORDS[type_id]
    raw = int.from_bytes(frame[4:8], record["byte_order"], signed=record["signed"])
    reading = raw * Decimal(record["scale"]) + Decimal(record["offset"])
    return {
        "type_id": type_id,
        "sequence": int.from_bytes(frame[2:4], "big"),
        "reading": format(reading, ".2f"),
        "unit": record["unit"],
        "status": record["states"][str(frame[8])],
    }
