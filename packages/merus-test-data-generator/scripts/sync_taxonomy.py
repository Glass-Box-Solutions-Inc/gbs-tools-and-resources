#!/usr/bin/env python3
"""
Re-extract taxonomy from Adjudica-classifier TypeScript sources.

Reads types.ts, subtypes.ts, and mapping.ts from the classifier and prints
Python enum/dict code to stdout. Pipe to data/taxonomy.py after review.

Usage:
    python scripts/sync_taxonomy.py                          # Print to stdout
    python scripts/sync_taxonomy.py --check                  # Check for drift
    python scripts/sync_taxonomy.py --classifier-path /path  # Custom path

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Default location relative to monorepo layout
DEFAULT_CLASSIFIER_PATH = Path.home() / "Desktop" / "Adjudica-classifier"


def extract_const_object(ts_content: str, const_name: str) -> list[str]:
    """Extract keys from a TypeScript const object declaration."""
    pattern = rf"export\s+const\s+{const_name}\s*=\s*\{{(.*?)\}}\s*as\s+const"
    match = re.search(pattern, ts_content, re.DOTALL)
    if not match:
        pattern = rf"export\s+const\s+{const_name}.*?\{{(.*?)\}}"
        match = re.search(pattern, ts_content, re.DOTALL)
    if not match:
        return []
    body = match.group(1)
    keys = re.findall(r"^\s*(\w+)\s*:", body, re.MULTILINE)
    return keys


def extract_label_object(ts_content: str, const_name: str) -> dict[str, str]:
    """Extract key: "label" pairs from a TypeScript Record const."""
    pattern = rf"export\s+const\s+{const_name}.*?\{{(.*?)\}}\s*;"
    match = re.search(pattern, ts_content, re.DOTALL)
    if not match:
        return {}
    body = match.group(1)
    pairs = re.findall(r'(\w+)\s*:\s*"([^"]*)"', body)
    return dict(pairs)


def extract_mapping(ts_content: str) -> dict[str, list[str]]:
    """Extract DOCUMENT_TYPE_TO_SUBTYPES mapping from mapping.ts."""
    result: dict[str, list[str]] = {}
    # Find each type block
    blocks = re.findall(
        r'(\w+)\s*:\s*\[(.*?)\]', ts_content, re.DOTALL
    )
    for type_name, block_body in blocks:
        subtypes = re.findall(r'"(\w+)"', block_body)
        if subtypes:
            result[type_name] = subtypes
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync taxonomy from classifier TS")
    parser.add_argument(
        "--classifier-path", type=Path, default=DEFAULT_CLASSIFIER_PATH,
        help="Path to Adjudica-classifier repo",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check for drift between classifier and local taxonomy (exit 1 if drifted)",
    )
    args = parser.parse_args()

    taxonomy_dir = args.classifier_path / "src" / "taxonomy"
    if not taxonomy_dir.exists():
        print(f"ERROR: Classifier taxonomy dir not found: {taxonomy_dir}", file=sys.stderr)
        sys.exit(1)

    types_ts = (taxonomy_dir / "types.ts").read_text()
    subtypes_ts = (taxonomy_dir / "subtypes.ts").read_text()
    mapping_ts = (taxonomy_dir / "mapping.ts").read_text()

    # Extract
    type_keys = extract_const_object(types_ts, "DOCUMENT_TYPES")
    type_labels = extract_label_object(types_ts, "DOCUMENT_TYPE_LABELS")
    subtype_keys = extract_const_object(subtypes_ts, "DOCUMENT_SUBTYPES")
    subtype_labels = extract_label_object(subtypes_ts, "DOCUMENT_SUBTYPE_LABELS")
    mapping = extract_mapping(mapping_ts)

    if args.check:
        # Compare with current taxonomy.py
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data.taxonomy import (
            DOCUMENT_SUBTYPE_LABELS as current_labels,
            DOCUMENT_TYPE_TO_SUBTYPES as current_mapping,
            DocumentSubtype,
            DocumentType,
        )

        current_types = set(t.value for t in DocumentType)
        current_subtypes = set(s.value for s in DocumentSubtype)
        ts_types = set(type_keys)
        ts_subtypes = set(subtype_keys)

        added_types = ts_types - current_types
        removed_types = current_types - ts_types
        added_subtypes = ts_subtypes - current_subtypes
        removed_subtypes = current_subtypes - ts_subtypes

        drifted = bool(added_types or removed_types or added_subtypes or removed_subtypes)

        if drifted:
            print("TAXONOMY DRIFT DETECTED:")
            if added_types:
                print(f"  Added types: {sorted(added_types)}")
            if removed_types:
                print(f"  Removed types: {sorted(removed_types)}")
            if added_subtypes:
                print(f"  Added subtypes ({len(added_subtypes)}): {sorted(added_subtypes)[:10]}...")
            if removed_subtypes:
                print(f"  Removed subtypes ({len(removed_subtypes)}): {sorted(removed_subtypes)[:10]}...")
            sys.exit(1)
        else:
            print(f"OK: taxonomy in sync ({len(current_types)} types, {len(current_subtypes)} subtypes)")
            sys.exit(0)

    # Print summary
    print(f"Extracted from {taxonomy_dir}:", file=sys.stderr)
    print(f"  Types: {len(type_keys)}", file=sys.stderr)
    print(f"  Subtypes: {len(subtype_keys)}", file=sys.stderr)
    print(f"  Labels: {len(subtype_labels)}", file=sys.stderr)
    print(f"  Mapping entries: {sum(len(v) for v in mapping.values())}", file=sys.stderr)

    # Print Python code to stdout
    print("# --- Types ---")
    for k in type_keys:
        label = type_labels.get(k, k)
        print(f'    {k} = "{k}"  # {label}')

    print("\n# --- Subtypes ---")
    for k in subtype_keys:
        print(f'    {k} = "{k}"')

    print(f"\n# Total: {len(subtype_keys)} subtypes across {len(type_keys)} types")


if __name__ == "__main__":
    main()
