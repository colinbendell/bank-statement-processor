"""Regression tests comparing output against known-good sample files."""

from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from rbc2.processors import normalize_csv
from rbc2.extractors import extract_to_csv
from rbc2.categorizer import add_categories, initialize_category_lookup, _category_lookup

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
PDF_FILES = list(SAMPLES_DIR.glob("*.pdf"))
PERSONAL_CATEGORIES_PATH = SAMPLES_DIR / "_categories_personal.csv"
BUSINESS_CATEGORIES_PATH = SAMPLES_DIR / "_categories_business.csv"
PERSONAL_CATEGORY_LOOKUP = initialize_category_lookup(PERSONAL_CATEGORIES_PATH).copy()
BUSINESS_CATEGORY_LOOKUP = initialize_category_lookup(BUSINESS_CATEGORIES_PATH).copy()
_category_lookup.clear()


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_end_to_end_regression(pdf_path):
    """Test that PDF-to-processed-CSV matches the expected output."""
    # Process PDF to normalized CSV
    expected_csv = pdf_path.with_suffix(".csv")
    processed_output = extract_to_csv(pdf_path)

    # Load both CSVs
    actual_df = pd.read_csv(StringIO(processed_output))
    expected_df = pd.read_csv(expected_csv)

    # Compare structure
    assert set(actual_df.columns) == set(expected_df.columns)
    assert actual_df.equals(expected_df)

    processed_csv = pdf_path.with_suffix(".processed.csv")

    normalized_output = normalize_csv(pdf_path, processed_output)
    # Load both CSVs
    actual_df = pd.read_csv(StringIO(normalized_output))
    expected_df = pd.read_csv(processed_csv)

    # Compare structure
    assert set(actual_df.columns) == set(expected_df.columns)
    for row in actual_df.itertuples():
        assert row.Date == expected_df.loc[row.Index, "Date"]
        assert row.File == expected_df.loc[row.Index, "File"]
        assert row.Description == expected_df.loc[row.Index, "Description"]
        assert row.Amount == expected_df.loc[row.Index, "Amount"]
    assert actual_df.equals(expected_df)

    categorized_csv = pdf_path.with_suffix(".categorized.csv")
    if "personal" in pdf_path.stem:
        _category_lookup.clear()
        _category_lookup.update(**PERSONAL_CATEGORY_LOOKUP)
    else:
        _category_lookup.clear()
        _category_lookup.update(**BUSINESS_CATEGORY_LOOKUP)
    categorized_output = add_categories(normalized_output)
    actual_df = pd.read_csv(StringIO(categorized_output))
    expected_df = pd.read_csv(categorized_csv)

    # Compare structure
    assert set(actual_df.columns) == set(expected_df.columns)
    for row in actual_df.itertuples():
        assert row.Date == expected_df.loc[row.Index, "Date"]
        assert row.File == expected_df.loc[row.Index, "File"]
        assert row.Description == expected_df.loc[row.Index, "Description"]
        assert row.Amount == expected_df.loc[row.Index, "Amount"]
        if pd.isna(expected_df.loc[row.Index, "Category"]):
            assert pd.isna(row.Category)
        else:
            assert row.Category == expected_df.loc[row.Index, "Category"]
    # assert actual_df.equals(expected_df)
