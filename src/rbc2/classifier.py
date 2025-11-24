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


# Load environment variables from .env file
load_dotenv()


class Classifier:
    """Transaction categorizer that maps descriptions to categories using a lookup dictionary."""

    def __init__(self, categories_csv_path: Path | None = None):
        """Initialize the categorizer with a categories CSV file.

        Args:
            categories_csv_path: Path to the categories.csv file
        """
        self._category_lookup: dict[str, str] = {}
        if categories_csv_path is not None and categories_csv_path.exists():
            with open(categories_csv_path, "r", encoding="utf-8") as f:
                csv_content = f.read()
            self._initialize_category_lookup(StringIO(csv_content))

    SIMPLE_ID_PATTERN = re.compile(r"\*[0-9]*(?:[A-Z]+[0-9]+){2,}[A-Z0-9]+\b")
    LONGER_ID_PATTERN = re.compile(r"\b[0-9]*[A-Z]+[0-9]+[A-Z0-9]+$")
    NON_ALPHA_PATTERN = re.compile(r"[^a-z]", re.IGNORECASE)

    @staticmethod
    def _get_category_keys(description: str, amount: float) -> list[str]:
        """Normalize a transaction description by removing non-alpha characters and converting to lowercase.

        Args:
            description: Raw transaction description
            amount: Transaction amount

        Returns:
            List of normalized keys (with and without amount)
        """
        # Remove non-alpha characters (keeping spaces temporarily)
        normalized_description = Classifier.SIMPLE_ID_PATTERN.sub("", description)
        normalized_description = Classifier.LONGER_ID_PATTERN.sub("", normalized_description)
        normalized_description = Classifier.NON_ALPHA_PATTERN.sub("", normalized_description).lower()
        int_amount = int(abs(amount))
        key_with_amount = f"{normalized_description}|{int_amount}"
        key_without_amount = normalized_description
        return [key_with_amount, key_without_amount]

    def set_category(self, description: str, amount: float, category: str) -> None:
        """Add a category to the lookup dictionary.

        Args:
            description: Transaction description
            amount: Transaction amount
            category: Category string
        """
        category_keys = self._get_category_keys(description, amount)

        for key in category_keys:
            category_set = self._category_lookup.get(key, set())

            category_set.add(category)
            self._category_lookup[key] = category_set

    def get_category(self, description: str, amount: float) -> str | None:
        """Get the category for a given description and amount.

        Args:
            description: Transaction description
            amount: Transaction amount

        Returns:
            Category string if found, None otherwise
        """
        category_keys = self._get_category_keys(description, amount)
        for key in category_keys:
            category_set = self._category_lookup.get(key, set())
            if len(category_set) == 1:
                return list(category_set)[0]
        return None

    def _initialize_category_lookup(self, csv_content: StringIO) -> None:
        """Build category dictionary from categories CSV file.

        The function creates a hashmap that maps normalized descriptions (with and without
        amounts) to categories. Conflicting mappings (same key, different categories) are
        excluded from the dictionary.
        """
        # Temporary storage to track conflicts

        reader = csv.DictReader(csv_content)

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
            self.set_category(description, amount, category)

    def infer_categories_batch_with_llm(self, transactions: list[tuple[int, str, float]]) -> dict[int, str]:
        """Use an LLM to infer categories for multiple transactions in a single batch request.

        Args:
            transactions: List of tuples (index, description, amount) for uncategorized transactions

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
        for _, category in list(self._category_lookup.items())[:100]:
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
Use only the categories provided. If the category is alow probability match format the response with "<category> ??". If you are uncertain or if no existing categories fit well, suggest a new category in the format "<category> ??".

Example response format:
0: Expenses / Travel
1: Revenue / Ontario
2: Investment / MD Management
3: Expenses / Travel ??
4: Revenue / Ireland ??

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
                                print(
                                    f"Categorized transaction {transactions[idx][1]} {transactions[idx][2]} as {category}"
                                )

                        except (ValueError, IndexError):
                            continue

            return result

        except Exception as e:
            print(f"Warning: LLM categorization failed: {e}")
            return {}

    def categorize_transaction(self, description: str, amount: float) -> str | None:
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
        category_keys = self._get_category_keys(description, amount)

        for key in category_keys:
            if key in self._category_lookup:
                return self._category_lookup[key]

        return None

    def categorize_transactions(
        self,
        transactions_df: pd.DataFrame,
        use_llm: bool = False,
    ) -> pd.DataFrame:
        """Add category column to normalized CSV content.

        Args:
            csv_content: CSV content string (Date, File, Description, Amount format)
            use_llm: Whether to use LLM for missing categories (requires ANTHROPIC_API_KEY env var)

        Returns:
            CSV content string with Category column added
        """

        # First pass: categorize using existing lookup
        transactions_df["Category"] = transactions_df.apply(
            lambda row: self.get_category(row["Description"], row["Amount"]), axis=1
        )

        # Find rows with missing categories
        uncategorized_rows = []
        for idx, row in transactions_df.iterrows():
            if pd.isna(row["Category"]) or row["Category"] is None:
                uncategorized_rows.append((idx, row["Description"], row["Amount"]))
                print(f"??: {row['Description']} {row['Amount']}")

        # Batch process with LLM if there are uncategorized transactions
        if uncategorized_rows:
            # Second pass: if use_llm is enabled, batch process missing categories
            if use_llm:
                llm_categories = self.infer_categories_batch_with_llm(uncategorized_rows)

                # Apply LLM-inferred categories back to dataframe
                for idx, category in llm_categories.items():
                    transactions_df.at[idx, "Category"] = category

        # Return as CSV
        return transactions_df
