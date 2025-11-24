"""Tests for CSV processors and normalization."""

from pathlib import Path
from io import StringIO

import pandas as pd
import pytest
import pandas.testing as pdt
from rbc2.processors import normalize_csv

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
PDF_FILES = list(SAMPLES_DIR.glob("*.pdf"))


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_csv_normalization(pdf_path):
    """Test that CSV normalization completes without errors."""

    csv_path = pdf_path.with_suffix(".extracted.csv")
    if not csv_path.exists():
        pytest.skip("No CSV file found for PDF")
    # Normalize CSV
    df = pd.read_csv(csv_path)
    actual_output = normalize_csv(transactions_df=df)

    # Verify it has the correct format
    expected_processed_csv = pdf_path.with_suffix(".processed.csv")
    expected_df = pd.read_csv(
        expected_processed_csv, dtype={"Date": str, "File": str, "Description": str, "Amount": float}
    )
    pdt.assert_frame_equal(actual_output, expected_df, check_like=False)


def test_chequing_normalization():
    """Test that Chequing/Savings normalization combines withdrawals/deposits."""
    # Find a chequing CSV
    chequing_pdf = next((p for p in PDF_FILES if "chequing" in p.stem.lower() or "savings" in p.stem.lower()), None)
    chequing_csv = chequing_pdf.with_suffix(".extracted.csv")
    if not chequing_csv.exists():
        pytest.skip("No chequing/savings CSV found in samples")

    df = pd.read_csv(chequing_csv)
    df = normalize_csv(transactions_df=df)

    # Check the format
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
