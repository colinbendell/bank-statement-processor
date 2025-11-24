"""Tests for the categorization module."""

from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from rbc2.classifier import Classifier

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
CSV_FILES = list(SAMPLES_DIR.glob("*.processed.csv"))
PERSONAL_CATEGORIES_PATH = SAMPLES_DIR / "_categories_personal.csv"
BUSINESS_CATEGORIES_PATH = SAMPLES_DIR / "_categories_business.csv"

BUSINESS_CATEGORIZER = Classifier(BUSINESS_CATEGORIES_PATH)
PERSONAL_CATEGORIZER = Classifier(PERSONAL_CATEGORIES_PATH)

DEFAULT_CATEGORIZER = Classifier()
DEFAULT_CATEGORIZER._category_lookup["ubertriptorontoon|26"] = {"Expenses / Travel"}
DEFAULT_CATEGORIZER._category_lookup["ubertriptorontoon"] = {"Expenses / Travel"}
DEFAULT_CATEGORIZER._category_lookup["investmentmdfinancial|5000.0"] = {"Investment / MD Management"}
DEFAULT_CATEGORIZER._category_lookup["investmentmdfinancial"] = {"Investment / MD Management"}


GET_CATEGORY_KEYS_TESTS = [
    ("UBER* TRIP TORONTO ON", 26.97, ["ubertriptorontoon|26", "ubertriptorontoon"]),
    ("Online transfer sent - 3248", 2000.00, ["onlinetransfersent|2000", "onlinetransfersent"]),
    ("Investment MD Financial", 5000.00, ["investmentmdfinancial|5000", "investmentmdfinancial"]),
    ("Bill Payment GOV NU PAYABLES", 5.12, ["billpaymentgovnupayables|5", "billpaymentgovnupayables"]),
    ("", 0.00, ["|0", ""]),
    ("123456", 0.00, ["|0", ""]),
]


@pytest.mark.parametrize("description, amount, expected", GET_CATEGORY_KEYS_TESTS)
def GET_CATEGORY_KEYS_TESTS(description, amount, expected):
    """Test get_category_keys function."""
    assert DEFAULT_CATEGORIZER._get_category_keys(description, amount) == expected


CATEGORIZE_TRANSACTION_TESTS = [
    ("UBER* TRIP TORONTO ON", 26.97, "Expenses / Travel"),
    ("UBER* TRIP TORONTO ON", -99.99, "Expenses / Travel"),
    ("UNKNOWN TRANSACTION", -100.00, None),
    ("", -100.00, None),
    ("123456", 0.00, None),
]


@pytest.mark.parametrize("description, amount, expected", CATEGORIZE_TRANSACTION_TESTS)
def test_categorize_transaction(description, amount, expected):
    """Test categorize_transaction function."""
    assert DEFAULT_CATEGORIZER.get_category(description, amount) == expected


@pytest.mark.parametrize("csv_path", CSV_FILES, ids=[p.stem for p in CSV_FILES])
def test_add_categories_to_csv(csv_path):
    """Test that CSV normalization completes without errors."""
    df = pd.read_csv(csv_path)

    if "personal" in csv_path.stem:
        df = PERSONAL_CATEGORIZER.categorize_transactions(df)
    else:
        df = BUSINESS_CATEGORIZER.categorize_transactions(df)

    assert "Category" in df.columns
    assert df["Category"].notna().any()
