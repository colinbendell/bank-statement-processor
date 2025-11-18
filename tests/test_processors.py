"""Tests for CSV processors and normalization."""

from pathlib import Path
from io import StringIO

import pandas as pd
import pytest

from rbc2.processors import normalize_csv

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
PDF_FILES = list(SAMPLES_DIR.glob("*.pdf"))


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_csv_normalization(pdf_path):
    """Test that CSV normalization completes without errors."""

    csv_path = pdf_path.with_suffix(".csv")
    if not csv_path.exists():
        pytest.skip("No CSV file found for PDF")
    # Normalize CSV
    actual_output = normalize_csv(csv_path)

    # Verify it has the correct format
    df = pd.read_csv(StringIO(actual_output))
    expected_processed_csv = pdf_path.with_suffix(".processed.csv")
    expected_df = pd.read_csv(expected_processed_csv)

    assert "Date" in df.columns
    assert "File" in df.columns
    assert "Description" in df.columns
    assert "Amount" in df.columns

    # Verify dates are in YYYY-MM-DD format
    assert all("-" in str(date) for date in df["Date"])

    # Verify there's data
    assert len(df) > 0

    assert set(df.columns) == set(expected_df.columns)
    assert df.equals(expected_df)


def test_chequing_normalization():
    """Test that Chequing/Savings normalization combines withdrawals/deposits."""
    # Find a chequing CSV
    chequing_pdf = next((p for p in PDF_FILES if "chequing" in p.stem.lower() or "savings" in p.stem.lower()), None)
    chequing_csv = chequing_pdf.with_suffix(".csv")
    if not chequing_csv.exists():
        pytest.skip("No chequing/savings CSV found in samples")

    actual_output = normalize_csv(chequing_csv)

    # Check the format
    df = pd.read_csv(StringIO(actual_output))
    assert "Date" in df.columns
    assert "Amount" in df.columns
    assert "Withdrawals" not in df.columns
    assert "Deposits" not in df.columns
    assert "Balance" not in df.columns

    # Should have both positive and negative amounts
    amounts = df["Amount"].tolist()
    has_positive = any(float(a) > 0 for a in amounts)
    has_negative = any(float(a) < 0 for a in amounts)
    assert has_positive or has_negative
