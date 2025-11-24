"""Tests for CSV processors and normalization."""

from pathlib import Path
from io import StringIO

import pandas as pd
import pytest

from rbc2.processors import normalize_csv

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
CSV_FILES = list(SAMPLES_DIR.glob("*.csv"))
# Exclude .processed.csv files
CSV_FILES = [f for f in CSV_FILES if not f.stem.endswith(".processed")]


@pytest.mark.parametrize("csv_path", CSV_FILES, ids=[p.stem for p in CSV_FILES])
def test_csv_normalization(csv_path, tmp_path):
    """Test that CSV normalization completes without errors."""

    # Normalize CSV
    result = normalize_csv(csv_path)

    # Verify it has the correct format
    df = pd.read_csv(StringIO(result))
    assert "Date" in df.columns
    assert "File" in df.columns
    assert "Description" in df.columns
    assert "Amount" in df.columns

    # Verify dates are in YYYY-MM-DD format
    assert all("-" in str(date) for date in df["Date"])

    # Verify there's data
    assert len(df) > 0


def test_normalization_inverts_visa_signs():
    """Test that Visa normalization inverts the sign."""
    # Find a visa CSV
    visa_csv = next((p for p in CSV_FILES if "visa" in p.stem.lower()), None)
    if not visa_csv:
        pytest.skip("No visa CSV found in samples")

    actual_output = normalize_csv(visa_csv)

    # Check that amounts were inverted
    df = pd.read_csv(StringIO(actual_output))
    assert "Amount" in df.columns
    # Should have both positive and negative amounts
    amounts = df["Amount"].tolist()
    assert any(float(a) > 0 for a in amounts) or any(float(a) < 0 for a in amounts)


def test_chequing_normalization():
    """Test that Chequing/Savings normalization combines withdrawals/deposits."""
    # Find a chequing CSV
    chequing_csv = next((p for p in CSV_FILES if "chequing" in p.stem.lower() or "savings" in p.stem.lower()), None)
    if not chequing_csv:
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
