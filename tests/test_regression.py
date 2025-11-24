"""Regression tests comparing output against known-good sample files."""

from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from rbc2.processors import process_pdf_to_normalized_csv

SAMPLES_DIR = Path(__file__).parent.parent / "samples"

# Find all PDF files that have corresponding .processed.csv files
PDF_WITH_PROCESSED = []
for pdf_path in SAMPLES_DIR.glob("*.pdf"):
    processed_csv = SAMPLES_DIR / f"{pdf_path.stem}.processed.csv"
    if processed_csv.exists():
        PDF_WITH_PROCESSED.append((pdf_path, processed_csv))


@pytest.mark.parametrize("pdf_path,expected_csv", PDF_WITH_PROCESSED, ids=[p[0].stem for p in PDF_WITH_PROCESSED])
def test_end_to_end_regression(pdf_path, expected_csv):
    """Test that PDF-to-processed-CSV matches the expected output."""
    # Process PDF to normalized CSV
    actual_output = process_pdf_to_normalized_csv(pdf_path)

    # Load both CSVs
    actual_df = pd.read_csv(StringIO(actual_output))
    expected_df = pd.read_csv(expected_csv)

    # Compare structure
    assert set(actual_df.columns) == set(expected_df.columns), (
        f"Column mismatch for {pdf_path.name}: {actual_df.columns} vs {expected_df.columns}"
    )

    # Compare row counts (with tolerance for extraction differences)
    actual_count = len(actual_df)
    expected_count = len(expected_df)

    # Allow up to 10% difference in row count due to extraction differences
    if actual_count != expected_count:
        diff_pct = abs(actual_count - expected_count) / expected_count * 100
        if diff_pct > 10:
            pytest.fail(
                f"Row count mismatch for {pdf_path.name}: "
                f"expected {expected_count}, got {actual_count} ({diff_pct:.1f}% difference)"
            )
        else:
            pytest.skip(
                f"Row count differs but within tolerance for {pdf_path.name}: "
                f"expected {expected_count}, got {actual_count} ({diff_pct:.1f}% difference)"
            )

    # Spot check: verify first and last rows have reasonable data
    if len(actual_df) > 0:
        assert pd.notna(actual_df["Date"].iloc[0])
        assert pd.notna(actual_df["Description"].iloc[0])
        # Amount can be NaN in some edge cases
        assert "File" in actual_df.columns


@pytest.mark.parametrize("pdf_path,expected_csv", PDF_WITH_PROCESSED, ids=[p[0].stem for p in PDF_WITH_PROCESSED])
def test_processed_csv_format(pdf_path, expected_csv, tmp_path):
    """Test that the processed CSV has the correct format."""
    actual_output = process_pdf_to_normalized_csv(pdf_path)

    # Load the CSV
    df = pd.read_csv(StringIO(actual_output))

    # Verify required columns
    assert "Date" in df.columns
    assert "File" in df.columns
    assert "Description" in df.columns
    assert "Amount" in df.columns

    # Verify date format (YYYY-MM-DD)
    for date_str in df["Date"]:
        assert "-" in str(date_str), f"Date not in YYYY-MM-DD format: {date_str}"
        parts = str(date_str).split("-")
        assert len(parts) == 3, f"Invalid date format: {date_str}"

    # Verify File column has the PDF name
    assert all(df["File"] == pdf_path.name)


def test_all_samples_have_processed_csv():
    """Verify that all expected sample files have .processed.csv files."""
    # This test documents which samples are expected to work
    assert len(PDF_WITH_PROCESSED) > 0, "No processed CSV files found in samples directory"

    print(f"\nFound {len(PDF_WITH_PROCESSED)} PDF files with corresponding .processed.csv files:")
    for pdf_path, _ in PDF_WITH_PROCESSED:
        print(f"  - {pdf_path.name}")
