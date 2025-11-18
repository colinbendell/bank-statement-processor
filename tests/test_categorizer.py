"""Tests for the categorization module."""

from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from rbc2.categorizer import (
    get_category_keys,
    add_categories,
    categorize_transaction,
    initialize_category_lookup,
    _category_lookup,
)

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
CSV_FILES = list(SAMPLES_DIR.glob("*.processed.csv"))
PERSONAL_CATEGORIES_PATH = SAMPLES_DIR / "_categories_personal.csv"
BUSINESS_CATEGORIES_PATH = SAMPLES_DIR / "_categories_business.csv"

PERSONAL_CATEGORY_LOOKUP = initialize_category_lookup(PERSONAL_CATEGORIES_PATH).copy()
BUSINESS_CATEGORY_LOOKUP = initialize_category_lookup(BUSINESS_CATEGORIES_PATH).copy()
_category_lookup.clear()


class TestNormalizeDescription:
    """Tests for description normalization."""

    test_get_category_keys = [
        ("UBER* TRIP TORONTO ON", 26.97, ["ubertriptorontoon|26", "ubertriptorontoon"]),
        ("Online transfer sent - 3248", 2000.00, ["onlinetransfersent|2000", "onlinetransfersent"]),
        ("Investment MD Financial", 5000.00, ["investmentmdfinancial|5000", "investmentmdfinancial"]),
        ("Bill Payment GOV NU PAYABLES", 5.12, ["billpaymentgovnupayables|5", "billpaymentgovnupayables"]),
        ("", 0.00, ["|0", ""]),
        ("123456", 0.00, ["|0", ""]),
    ]

    @pytest.mark.parametrize("description, amount, expected", test_get_category_keys)
    def test_get_category_keys(self, description, amount, expected):
        """Test get_category_keys function."""
        assert get_category_keys(description, amount) == expected


class TestCategorizeTransaction:
    """Tests for transaction categorization."""

    def setup_class(self):
        """Setup class."""
        _category_lookup["ubertriptorontoon|26"] = "Expenses / Travel"
        _category_lookup["ubertriptorontoon"] = "Expenses / Travel"
        _category_lookup["investmentmdfinancial|5000.0"] = "Investment / MD Management"
        _category_lookup["investmentmdfinancial"] = "Investment / MD Management"

    test_categorize_transaction = [
        ("UBER* TRIP TORONTO ON", 26.97, "Expenses / Travel"),
        ("UBER* TRIP TORONTO ON", -99.99, "Expenses / Travel"),
        ("UNKNOWN TRANSACTION", -100.00, None),
        ("", -100.00, None),
        ("123456", 0.00, None),
    ]

    @pytest.mark.parametrize("description, amount, expected", test_categorize_transaction)
    def test_categorize_transaction(self, description, amount, expected):
        """Test categorize_transaction function."""
        assert categorize_transaction(description, amount) == expected


@pytest.mark.parametrize("csv_path", CSV_FILES, ids=[p.stem for p in CSV_FILES])
def test_add_categories_to_csv(csv_path):
    """Test that CSV normalization completes without errors."""

    if "personal" in csv_path.stem:
        _category_lookup.clear()
        _category_lookup.update(**PERSONAL_CATEGORY_LOOKUP)
    else:
        _category_lookup.clear()
        _category_lookup.update(**BUSINESS_CATEGORY_LOOKUP)

    # Normalize CSV
    result = add_categories(open(csv_path).read())

    # Verify it has the correct format
    df = pd.read_csv(StringIO(result))
    assert "Category" in df.columns
    assert df["Category"].notna().any()
