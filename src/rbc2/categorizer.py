"""Transaction categorization logic."""

import csv
import os
import re
from pathlib import Path
from typing import Any
from io import StringIO
import pandas as pd
from anthropic import Anthropic
from dotenv import load_dotenv


# Singleton cache for category dictionary
_category_lookup: dict[str, str] = {}

# Load environment variables from .env file
load_dotenv()


def get_category_keys(description: str, amount: float) -> list[str]:
    """Normalize a transaction description by removing non-alpha characters and converting to lowercase.

    Args:
        description: Raw transaction description

    Returns:
        Normalized description string (lowercase, alpha characters only)
    """
    # Remove non-alpha characters (keeping spaces temporarily)
    normalized_description = re.sub(r"\*[0-9]*(?:[A-Z]+[0-9]+){2,}[A-Z0-9]+\b", "", description)
    normalized_description = re.sub(r"\b[0-9]*[A-Z]+[0-9]+[A-Z0-9]+$", "", normalized_description)
    normalized_description = re.sub(r"[^a-zA-Z]", "", normalized_description).lower()
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


def infer_categories_batch_with_llm(
    transactions: list[tuple[int, str, float]], existing_categories: dict[str, str]
) -> dict[int, str]:
    """Use an LLM to infer categories for multiple transactions in a single batch request.

    Args:
        transactions: List of tuples (index, description, amount) for uncategorized transactions
        existing_categories: Dictionary mapping descriptions to categories

    Returns:
        Dictionary mapping transaction index to inferred category string
    """
    # Check if API key is available
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not transactions:
        return {}
    print(f"Inferring categories for {len(transactions)} transactions")
    # Sample existing categories for context (limit to 20 unique categories)
    category_examples = []
    seen_categories = set()
    for _, category in list(existing_categories.items())[:100]:
        if category not in seen_categories:
            category_examples.append(f"- {category}")
            seen_categories.add(category)
            if len(category_examples) >= 20:
                break

    # Build transaction list for prompt
    transaction_lines = []
    for idx, description, amount in transactions:
        transaction_lines.append(f"{idx}. Description: {description} | Amount: ${amount:.2f}")

    # Build prompt with all transactions
    prompt = f"""Based on the following existing transaction categories, suggest the most appropriate category for each transaction below.

Existing categories in use:
{chr(10).join(category_examples)}

Transactions to categorize:
{chr(10).join(transaction_lines)}

For each transaction, respond with the transaction number followed by a colon and the category. Each response should be on a separate line. The category should follow the same hierarchical format (e.g., "Expenses / Travel", "Revenue / Ontario", "Investment / MD Management").
If the category is alow probability match format the response with "MAYBE: <category>". If you are uncertain or if no existing categories fit well, suggest a new category in the format "MAYBE: <category>".

Example response format:
0: Expenses / Travel
1: Revenue / Ontario
2: Investment / MD Management
3: MAYBE: Expenses / Travel
4: MAYBE: Revenue / Ireland

Response:"""

    try:
        client = Anthropic(api_key=api_key)

        message = client.messages.create(
            max_tokens=1024,
            model="claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse the response
        result = {}
        if message.content and len(message.content) > 0:
            response_text = message.content[0].text.strip()
            for line in response_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    try:
                        idx = int(parts[0].strip())
                        category = parts[1].strip()
                        if category:
                            result[idx] = category
                    except (ValueError, IndexError):
                        continue

        return result

    except Exception as e:
        print(f"Warning: LLM categorization failed: {e}")
        return {}


def categorize_transaction(description: str, amount: float) -> str | None:
    """Categorize a single transaction based on description and amount.

    Lookup order:
    1. Try normalized_description + rounded_amount
    2. Try normalized_description only
    3. Return None if no match

    Args:
        description: Transaction description
        amount: Transaction amount

    Returns:
        Category string if found, None otherwise
    """
    category_keys = get_category_keys(description, amount)

    for key in category_keys:
        if key in _category_lookup:
            return _category_lookup[key]

    return None


def add_categories(
    csv_content: str,
    use_llm: bool = False,
) -> str:
    """Add category column to normalized CSV content.

    Args:
        csv_content: CSV content string (Date, File, Description, Amount format)
        use_llm: Whether to use LLM for missing categories (requires ANTHROPIC_API_KEY env var)

    Returns:
        CSV content string with Category column added
    """

    # Read CSV content
    df = pd.read_csv(StringIO(csv_content))

    # First pass: categorize using existing lookup
    df["Category"] = df.apply(lambda row: categorize_transaction(row["Description"], row["Amount"]), axis=1)

    # Second pass: if use_llm is enabled, batch process missing categories
    if use_llm:
        # Find rows with missing categories
        uncategorized_rows = []
        for idx, row in df.iterrows():
            if pd.isna(row["Category"]) or row["Category"] is None:
                uncategorized_rows.append((idx, row["Description"], row["Amount"]))

        # Batch process with LLM if there are uncategorized transactions
        if uncategorized_rows:
            llm_categories = infer_categories_batch_with_llm(uncategorized_rows, _category_lookup)

            # Apply LLM-inferred categories back to dataframe
            for idx, category in llm_categories.items():
                df.at[idx, "Category"] = category

    # Return as CSV
    return df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL)
