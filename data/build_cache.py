#!/usr/bin/env python3
"""Build the optional SpatialAgent SQLite context cache.

The input is a MapEval-Textual-style JSONL file with a `context` field.
The output database contains four tables used by local database operators:
places, travel_times, routes, and nearby_places.
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.context_parser import ContextParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_CLASSES = {"routing", "trip", "poi", "nearby"}


def parse_nearby_entries(nearby_text: str) -> Dict[str, str]:
    """Parse numbered nearby entries and return them keyed by place name."""
    entries: Dict[str, str] = {}
    pattern = r"(\d+)\.\s*<b>([^<]+)</b>(.*?)(?=\d+\.\s*<b>|$)"
    for match in re.finditer(pattern, nearby_text, re.DOTALL):
        name = match.group(2).strip()
        details = match.group(3).strip()
        entry = f"<b>{name}</b>\n{details}" if details else f"<b>{name}</b>"
        if name not in entries or len(entry) > len(entries[name]):
            entries[name] = entry
    return entries


def merge_nearby_texts(text_a: str, text_b: str) -> str:
    """Merge nearby lists by place name, keeping the longer entry text."""
    entries_a = parse_nearby_entries(text_a)
    entries_b = parse_nearby_entries(text_b)
    merged: Dict[str, str] = {}
    for name in sorted(set(entries_a) | set(entries_b)):
        a = entries_a.get(name, "")
        b = entries_b.get(name, "")
        merged[name] = a if len(a) >= len(b) else b
    return "\n".join(f"{index}. {merged[name]}" for index, name in enumerate(sorted(merged), 1))


def extract_nearby_header(nearby_text: str) -> str:
    """Return the Nearby header line when present."""
    match = re.match(r"^(Nearby\s+[\w\s]+\s+of\s+.+?\s+are\s+\([^)]+\):)", nearby_text, re.IGNORECASE)
    return match.group(1) if match else ""


def create_schema(cursor: sqlite3.Cursor) -> None:
    """Create the cache schema if it does not already exist."""
    logger.info("Creating database schema")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_name TEXT NOT NULL UNIQUE,
            information TEXT,
            lat REAL,
            lng REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_places_name ON places(place_name)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS travel_times (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            mode TEXT NOT NULL,
            duration_distance TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(origin, destination, mode)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tt_origin ON travel_times(origin)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tt_dest ON travel_times(destination)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            mode TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(origin, destination, mode)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_routes_origin ON routes(origin)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_routes_dest ON routes(destination)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS nearby_places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_place TEXT NOT NULL,
            reference_info TEXT,
            category TEXT,
            radius_meters INTEGER,
            nearby_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(reference_place, category)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nearby_ref ON nearby_places(reference_place)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nearby_category ON nearby_places(reference_place, category)")
    logger.info("Schema ready")


class DedupLogger:
    """Collect deduplication decisions and write them to a sidecar log."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.entries = []

    def log(self, table: str, action: str, key: str, old_len: Optional[int] = None, new_len: Optional[int] = None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        detail = f" old_len={old_len} new_len={new_len}" if old_len is not None else ""
        self.entries.append(f"[{timestamp}] [{table}] {action}: {key}{detail}\n")

    def save(self) -> None:
        if not self.entries:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"# Deduplication log\n# Generated at: {datetime.now().isoformat()}\n\n")
            f.writelines(self.entries)
        logger.info("Deduplication log saved to %s", self.log_path)


def upsert_longer(
    cursor: sqlite3.Cursor,
    table: str,
    key_where: str,
    key_values: tuple,
    value_column: str,
    value: str,
    insert_sql: str,
    insert_values: tuple,
    update_sql: str,
    update_values: tuple,
    stats: Dict[str, int],
    stat_prefix: str,
    dedup: DedupLogger,
    key_label: str,
) -> None:
    """Insert a row, or update an existing row only when the new value is longer."""
    cursor.execute(f"SELECT {value_column} FROM {table} WHERE {key_where}", key_values)
    existing = cursor.fetchone()
    if existing:
        old_value = existing[0] or ""
        if len(value) > len(old_value):
            cursor.execute(update_sql, update_values)
            stats[f"{stat_prefix}_updated"] += 1
            dedup.log(table, "update", key_label, len(old_value), len(value))
        else:
            stats[f"{stat_prefix}_skipped"] += 1
            dedup.log(table, "skip", key_label, len(old_value), len(value))
    else:
        cursor.execute(insert_sql, insert_values)
        stats[f"{stat_prefix}_inserted"] += 1


def build_database(input_file: str, output_db: str) -> None:
    """Build the context cache database from a JSONL file."""
    input_path = Path(input_file)
    output_path = Path(output_db)
    dedup = DedupLogger(output_path.parent / "dedup_log.txt")

    if not input_path.exists():
        logger.error("Input file does not exist: %s", input_file)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(output_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    create_schema(cursor)

    stats = {
        "total_questions": 0,
        "routing_trip_count": 0,
        "poi_nearby_count": 0,
        "places_inserted": 0,
        "places_updated": 0,
        "places_skipped": 0,
        "coords_updated": 0,
        "travel_times_inserted": 0,
        "travel_times_updated": 0,
        "travel_times_skipped": 0,
        "routes_inserted": 0,
        "routes_updated": 0,
        "routes_skipped": 0,
        "nearby_inserted": 0,
        "nearby_updated": 0,
        "nearby_skipped": 0,
        "parse_errors": 0,
    }

    logger.info("Building cache from %s", input_file)
    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                context = item.get("context", "")
                classification = item.get("classification", "")
                if classification not in SUPPORTED_CLASSES or not context:
                    continue
                stats["total_questions"] += 1
                if classification in {"routing", "trip"}:
                    stats["routing_trip_count"] += 1
                else:
                    stats["poi_nearby_count"] += 1

                for place_name, information in ContextParser.parse_places(context).items():
                    upsert_longer(
                        cursor,
                        "places",
                        "place_name = ?",
                        (place_name,),
                        "information",
                        information,
                        "INSERT INTO places (place_name, information) VALUES (?, ?)",
                        (place_name, information),
                        "UPDATE places SET information = ? WHERE place_name = ?",
                        (information, place_name),
                        stats,
                        "places",
                        dedup,
                        f"place_name={place_name!r}",
                    )

                for (origin, dest, mode), duration_distance in ContextParser.parse_travel_times(context).items():
                    upsert_longer(
                        cursor,
                        "travel_times",
                        "origin = ? AND destination = ? AND mode = ?",
                        (origin, dest, mode),
                        "duration_distance",
                        duration_distance,
                        "INSERT INTO travel_times (origin, destination, mode, duration_distance) VALUES (?, ?, ?, ?)",
                        (origin, dest, mode, duration_distance),
                        "UPDATE travel_times SET duration_distance = ? WHERE origin = ? AND destination = ? AND mode = ?",
                        (duration_distance, origin, dest, mode),
                        stats,
                        "travel_times",
                        dedup,
                        f"{origin!r}->{dest!r}/{mode}",
                    )

                for (origin, dest, mode), summary in ContextParser.parse_routes(context).items():
                    upsert_longer(
                        cursor,
                        "routes",
                        "origin = ? AND destination = ? AND mode = ?",
                        (origin, dest, mode),
                        "summary",
                        summary,
                        "INSERT INTO routes (origin, destination, mode, summary) VALUES (?, ?, ?, ?)",
                        (origin, dest, mode, summary),
                        "UPDATE routes SET summary = ? WHERE origin = ? AND destination = ? AND mode = ?",
                        (summary, origin, dest, mode),
                        stats,
                        "routes",
                        dedup,
                        f"{origin!r}->{dest!r}/{mode}",
                    )

                if classification in {"poi", "nearby"}:
                    for place_name, (lat, lng) in ContextParser.parse_place_coordinates(context).items():
                        cursor.execute(
                            "INSERT OR IGNORE INTO places (place_name) VALUES (?)",
                            (place_name,),
                        )
                        cursor.execute(
                            "UPDATE places SET lat = ?, lng = ? WHERE place_name = ?",
                            (lat, lng, place_name),
                        )
                        stats["coords_updated"] += 1

                if classification == "nearby":
                    for group in ContextParser.parse_nearby_places(context):
                        ref_place = group.get("reference_place", "")
                        category = group.get("category", "")
                        nearby_text = group.get("nearby_text", "")
                        reference_info = group.get("reference_info", "")
                        radius = group.get("radius_meters")
                        cursor.execute(
                            "SELECT nearby_text FROM nearby_places WHERE reference_place = ? AND category = ?",
                            (ref_place, category),
                        )
                        existing = cursor.fetchone()
                        if existing:
                            merged = merge_nearby_texts(existing[0] or "", nearby_text)
                            if extract_nearby_header(merged) == "":
                                header = extract_nearby_header(nearby_text) or extract_nearby_header(existing[0] or "")
                                merged = f"{header}\n{merged}" if header else merged
                            cursor.execute(
                                "UPDATE nearby_places SET reference_info = ?, radius_meters = ?, nearby_text = ? WHERE reference_place = ? AND category = ?",
                                (reference_info, radius, merged, ref_place, category),
                            )
                            stats["nearby_updated"] += 1
                            dedup.log("nearby_places", "merge", f"{ref_place!r}/{category!r}")
                        else:
                            cursor.execute(
                                "INSERT INTO nearby_places (reference_place, reference_info, category, radius_meters, nearby_text) VALUES (?, ?, ?, ?, ?)",
                                (ref_place, reference_info, category, radius, nearby_text),
                            )
                            stats["nearby_inserted"] += 1
            except Exception as exc:
                stats["parse_errors"] += 1
                logger.warning("Failed to parse line %s: %s", line_num, exc)

    conn.commit()
    conn.close()
    dedup.save()

    logger.info("=" * 60)
    logger.info("Cache build complete")
    logger.info("Output database: %s", output_db)
    logger.info("Questions processed: %s", stats["total_questions"])
    logger.info("places: inserted=%s updated=%s skipped=%s coords_updated=%s", stats["places_inserted"], stats["places_updated"], stats["places_skipped"], stats["coords_updated"])
    logger.info("travel_times: inserted=%s updated=%s skipped=%s", stats["travel_times_inserted"], stats["travel_times_updated"], stats["travel_times_skipped"])
    logger.info("routes: inserted=%s updated=%s skipped=%s", stats["routes_inserted"], stats["routes_updated"], stats["routes_skipped"])
    logger.info("nearby_places: inserted=%s merged=%s", stats["nearby_inserted"], stats["nearby_updated"])
    if stats["parse_errors"]:
        logger.warning("Parse errors: %s", stats["parse_errors"])
    logger.info("=" * 60)
    verify_database(output_db)


def verify_database(db_path: str) -> None:
    """Print basic sanity checks for a generated cache database."""
    logger.info("Verifying database")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    counts = {}
    for table in ["places", "travel_times", "routes", "nearby_places"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM places WHERE lat IS NOT NULL")
    places_with_coords = cursor.fetchone()[0]

    logger.info("Final record counts:")
    logger.info("  places: %s (with coordinates: %s)", counts["places"], places_with_coords)
    logger.info("  travel_times: %s", counts["travel_times"])
    logger.info("  routes: %s", counts["routes"])
    logger.info("  nearby_places: %s", counts["nearby_places"])

    cursor.execute("SELECT place_name, lat, lng FROM places WHERE lat IS NOT NULL LIMIT 3")
    for place_name, lat, lng in cursor.fetchall():
        logger.info("  coordinate sample: %s -> (%s, %s)", place_name, lat, lng)

    cursor.execute("SELECT origin, destination, mode, duration_distance FROM travel_times LIMIT 3")
    for origin, dest, mode, duration_distance in cursor.fetchall():
        logger.info("  travel-time sample: %s -> %s (%s) - %s", origin, dest, mode, duration_distance)

    cursor.execute("SELECT reference_place, category, nearby_text FROM nearby_places LIMIT 2")
    for reference_place, category, nearby_text in cursor.fetchall():
        place_count = len(re.findall(r"\d+\.\s*<b>", nearby_text or ""))
        logger.info("  nearby sample: %s / %s -> %s places", reference_place, category, place_count)

    conn.close()

    issues = []
    if counts["places"] == 0:
        issues.append("places table is empty")
    if counts["travel_times"] == 0:
        issues.append("travel_times table is empty")
    if counts["routes"] == 0:
        issues.append("routes table is empty")
    if counts["nearby_places"] == 0:
        issues.append("nearby_places table is empty")

    if issues:
        logger.warning("Database verification warnings:")
        for issue in issues:
            logger.warning("  %s", issue)
    else:
        logger.info("Database verification passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a SpatialAgent SQLite context cache")
    parser.add_argument("--input", default="MapEval-Textual.jsonl", help="Input JSONL file")
    parser.add_argument("--output", default="data/context_cache.db", help="Output SQLite database path")
    args = parser.parse_args()
    build_database(args.input, args.output)


if __name__ == "__main__":
    main()
