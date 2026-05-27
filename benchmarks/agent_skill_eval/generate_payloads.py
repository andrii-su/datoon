#!/usr/bin/env python3
"""Generate deterministic JSON payloads for agent skill evaluation."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD_DIR = ROOT / "payloads"
EXPECTED_PATH = ROOT / "expected_answers.json"

SCENARIO_SIZES = {
    "small": 5,
    "medium": 75,
    "large": 450,
}

REGIONS = ["north", "south", "east", "west"]
CATEGORIES = ["hardware", "software", "services", "training"]


def build_records(scenario: str, iteration: int, size: int) -> list[dict[str, object]]:
    """Build uniform records with deterministic totals and anomalies."""
    records: list[dict[str, object]] = []
    anomaly_mod = {"small": 4, "medium": 17, "large": 97}[scenario]

    for index in range(size):
        category = CATEGORIES[(index + iteration) % len(CATEGORIES)]
        region = REGIONS[(index * 2 + iteration) % len(REGIONS)]
        active = (index + iteration) % 5 != 0
        revenue_cents = 1200 + (index * 37) + (iteration * 111)
        units = 1 + ((index + iteration) % 9)
        is_anomaly = index % anomaly_mod == 0

        if is_anomaly:
            revenue_cents *= -1

        records.append(
            {
                "id": f"{scenario[:1]}-{iteration}-{index + 1:04d}",
                "region": region,
                "category": category,
                "active": active,
                "units": units,
                "revenue_cents": revenue_cents,
                "anomaly": is_anomaly,
            }
        )

    return records


def expected_for(payload: dict[str, object]) -> dict[str, object]:
    """Compute the exact answer agents should return."""
    records = payload["records"]
    assert isinstance(records, list)

    region_totals: dict[str, int] = {}
    category_totals: dict[str, int] = {}

    for record in records:
        assert isinstance(record, dict)
        region = str(record["region"])
        category = str(record["category"])
        revenue = int(record["revenue_cents"])
        region_totals[region] = region_totals.get(region, 0) + revenue
        category_totals[category] = category_totals.get(category, 0) + revenue

    top_region = sorted(region_totals.items(), key=lambda item: (-item[1], item[0]))[0][
        0
    ]
    top_category = sorted(
        category_totals.items(), key=lambda item: (-item[1], item[0])
    )[0][0]

    return {
        "scenario": payload["scenario"],
        "iteration": payload["iteration"],
        "record_count": len(records),
        "active_count": sum(
            1 for record in records if isinstance(record, dict) and record["active"]
        ),
        "total_revenue_cents": sum(
            int(record["revenue_cents"])
            for record in records
            if isinstance(record, dict)
        ),
        "top_region": top_region,
        "top_category": top_category,
        "anomaly_ids": [
            str(record["id"])
            for record in records
            if isinstance(record, dict) and record["anomaly"]
        ],
    }


def main() -> int:
    """Write payload and expected-answer files."""
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    expected: dict[str, dict[str, object]] = {}

    for iteration in range(1, 4):
        for scenario, size in SCENARIO_SIZES.items():
            payload = {
                "scenario": scenario,
                "iteration": iteration,
                "source": "datoon agent skill evaluation",
                "records": build_records(scenario, iteration, size),
            }
            name = f"{iteration}_{scenario}.json"
            path = PAYLOAD_DIR / name
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            expected[name] = expected_for(payload)

    EXPECTED_PATH.write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(expected)} payloads to {PAYLOAD_DIR}")
    print(f"wrote expected answers to {EXPECTED_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
