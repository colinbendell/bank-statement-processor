"""Transaction categorization logic."""

import csv
import re
from pathlib import Path
from typing import Any
from io import StringIO
import pandas as pd


# Singleton cache for category dictionary
_category_lookup: dict[str, str] = {}


def get_category_keys(description: str, amount: float) -> list[str]:
    """Normalize a transaction description by removing non-alpha characters and converting to lowercase.

    Args:
        description: Raw transaction description

    Returns:
        Normalized description string (lowercase, alpha characters only)
    """
    # Remove non-alpha characters (keeping spaces temporarily)
    normalized_description = re.sub(r"[^a-zA-Z]", "", description).lower()
    int_amount = int(abs(amount))
    key_with_amount = f"{normalized_description}|{int_amount}"
    key_without_amount = normalized_description
    return [key_with_amount, key_without_amount]


def initialize_category_lookup(categories_csv_path: Path) -> dict[str, str]:
    """Build category dictionary from categories CSV file (singleton pattern).

    This function uses a cache to ensure the category dictionary is only built once
    per unique categories CSV path. Subsequent calls with the same path will return
    the cached dictionary.

    The function creates a hashmap that maps normalized descriptions (with and without
    amounts) to categories. Conflicting mappings (same key, different categories) are
    excluded from the dictionary.

    Args:
        categories_csv_path: Path to the categories.csv file

    Returns:
        Dict mapping normalized key to category string
    """
    # Convert to absolute path for consistent cache keys
    # Temporary storage to track conflicts
    temp_map: dict[str, set[str]] = {}

    with open(categories_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            description = row["Description"]
            amount_str = row["Amount"].replace(",", "")
            category = row["Category"]

            # Parse amount
            try:
                amount = float(amount_str)
            except (ValueError, AttributeError):
                print(amount_str)
                continue

            # Normalize description
            category_keys = get_category_keys(description, amount)

            # Track both keys in temporary map
            for key in category_keys:
                if key not in temp_map:
                    temp_map[key] = set()
                temp_map[key].add(category)

    _category_lookup.clear()
    # Build final maps based on conflicts
    for key, categories in temp_map.items():
        if len(categories) == 1:
            # No conflict - add to primary map
            _category_lookup[key] = list(categories)[0]

    # Cache the result
    return _category_lookup


def categorize_transaction(description: str, amount: float) -> str:
    """Categorize a single transaction based on description and amount.

    Lookup order:
    1. Try normalized_description + rounded_amount
    2. Try normalized_description only
    3. Return empty string if no match

    Args:
        description: Transaction description
        amount: Transaction amount

    Returns:
        Category string if found, empty string otherwise
    """
    category_keys = get_category_keys(description, amount)

    for key in category_keys:
        if key in _category_lookup:
            return _category_lookup[key]
    return None


def add_categories(
    csv_content: str,
) -> str:
    """Add category column to normalized CSV content.

    Args:
        csv_content: CSV content string (Date, File, Description, Amount format)

    Returns:
        CSV content string with Category column added
    """

    # Read CSV content
    df = pd.read_csv(StringIO(csv_content))

    # Add Category column
    df["Category"] = df.apply(lambda row: categorize_transaction(row["Description"], row["Amount"]), axis=1)

    # Return as CSV
    return df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL)
