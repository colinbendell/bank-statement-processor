"""Regression tests comparing output against known-good sample files."""

from io import StringIO
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest


from rbc2.processors import normalize_csv
from rbc2.extractors import extract_to_csv
from rbc2.classifier import Classifier

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
PDF_FILES = list(SAMPLES_DIR.glob("*.pdf"))
PERSONAL_CATEGORIES_PATH = SAMPLES_DIR / "_categories_personal.csv"
BUSINESS_CATEGORIES_PATH = SAMPLES_DIR / "_categories_business.csv"
PERSONAL_CLASSIFIER = Classifier(PERSONAL_CATEGORIES_PATH)
BUSINESS_CLASSIFIER = Classifier(BUSINESS_CATEGORIES_PATH)

ACCOUNT_DTYPES = {
    "Withdrawals": float,
    "Deposits": float,
    "Balance": float,
}
CC_DTYPES = {
    "Amount": float,
}


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_end_to_end_regression(pdf_path):
    """Test that PDF-to-processed-CSV matches the expected output."""
    # Process PDF to normalized CSV
    expected_csv = pdf_path.with_suffix(".extracted.csv")

    actual_df = extract_to_csv(pdf_path)

    dtypes = ACCOUNT_DTYPES
    parse_dates = ["Date"]
    if "Amount" in actual_df.columns:
        dtypes = CC_DTYPES
        parse_dates = ["Posting Date", "Transaction Date"]

    # Load both CSVs
    expected_df = pd.read_csv(expected_csv, dtype=dtypes, parse_dates=parse_dates)
    pdt.assert_frame_equal(actual_df, expected_df, check_like=False)

    processed_csv = pdf_path.with_suffix(".processed.csv")
    actual_df = normalize_csv(pdf_path, actual_df)

    expected_df = pd.read_csv(processed_csv)
    pdt.assert_frame_equal(actual_df, expected_df, check_like=False)

    categorized_csv = pdf_path.with_suffix(".categorized.csv")
    if "personal" in pdf_path.stem:
        actual_df = PERSONAL_CLASSIFIER.categorize_transactions(actual_df)
    else:
        actual_df = BUSINESS_CLASSIFIER.categorize_transactions(actual_df)
    expected_df = pd.read_csv(categorized_csv, dtype={"Category": str})
    expected_df["Category"] = expected_df["Category"].fillna("").astype(str)
    actual_df["Category"] = actual_df["Category"].fillna("").astype(str)

    pdt.assert_frame_equal(actual_df, expected_df, check_like=True)
