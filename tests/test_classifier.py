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
DEFAULT_CATEGORIZER._category_lookup["uber trip toronto on | 26"] = {"Expenses / Travel"}
DEFAULT_CATEGORIZER._category_lookup["uber trip toronto on"] = {"Expenses / Travel"}
DEFAULT_CATEGORIZER._category_lookup["investment md financial | 5000.0"] = {"Investment / MD Management"}
DEFAULT_CATEGORIZER._category_lookup["investment md financial"] = {"Investment / MD Management"}
print (DEFAULT_CATEGORIZER._category_lookup)

NORMALIZE_DESCRIPTION_TESTS = [
    ("UBER* TRIP TORONTO ON", "uber trip toronto on"),
    ("Online Banking transfer - 3087", "online banking transfer"),
    ("Investment MD Financial", "investment md financial"),
    ("Bill Payment GOV NU PAYABLES", "bill payment gov nu payables"),
    ("Electronic transaction fee 7 Drs @ 0.75 2 Crs @ 0.75", "electronic transaction fee drs crs"),
    ("INTERAC e-Transfer fee", "interac e transfer fee"),
    ("", ""),
    ("123456", ""),
]


@pytest.mark.parametrize("description, expected", NORMALIZE_DESCRIPTION_TESTS)
def test_normalize_description(description, expected):
    """Test get_category_keys function."""
    assert DEFAULT_CATEGORIZER.normalize_description(description) == expected


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
    if amount == -99.99:
        print (DEFAULT_CATEGORIZER._category_lookup)
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
