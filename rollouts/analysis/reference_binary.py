"""Identify a pinned ELF executable retained with its section table removed."""
from functools import lru_cache
from hashlib import file_digest, sha256
from pathlib import Path
from struct import unpack_from


@lru_cache(maxsize=None)
def sectionless_reference(path):
    """Return the byte count and digest for this observed ELF64 packaging form."""
    with path.open("rb") as source:
        header = source.read(64)
        if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01":
            return None
        offset = unpack_from("<Q", header, 32)[0]
        entry_size, count = unpack_from("<HH", header, 54)
        if entry_size != 56 or not 0 < count < 65535:
            return None
        source.seek(offset)
        end = offset + entry_size * count
        for _ in range(count):
            record = source.read(entry_size)
            if len(record) != entry_size:
                return None
            start = unpack_from("<Q", record, 8)[0]
            size = unpack_from("<Q", record, 32)[0]
            if size:
                end = max(end, start + size)
        if not 64 <= end < unpack_from("<Q", header, 40)[0] or end > path.stat().st_size:
            return None
        # Only the section-table offset, entry size, count and name index changed.
        digest = sha256(header[:40] + bytes(8) + header[48:58] + bytes(6))
        source.seek(64)
        remaining = end - 64
        while remaining:
            block = source.read(min(remaining, 1024 * 1024))
            if not block:
                return None
            digest.update(block)
            remaining -= len(block)
        return end, digest.hexdigest()


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Compare a terminal binary against its pinned ProgramBench reference.")
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    with args.candidate.open("rb") as candidate, args.reference.open("rb") as reference:
        result = (args.candidate.stat().st_size, file_digest(candidate, "sha256").hexdigest())
        original = (args.reference.stat().st_size, file_digest(reference, "sha256").hexdigest())
    if result == original:
        print("Byte-identical supplied executable")
    elif result == sectionless_reference(args.reference):
        print("Supplied executable with section-table metadata removed")
    else:
        print("No match for either checked form")
