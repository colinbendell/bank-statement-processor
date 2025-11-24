"""Tests for PDF extractors using sample files."""

from pathlib import Path
import pandas as pd
import pytest
import pymupdf
from rbc2.extractors import StatementExtractor, extract_to_csv

# Get all PDF files in the samples directory
SAMPLES_DIR = Path(__file__).parent.parent / "samples"
PDF_FILES = list(SAMPLES_DIR.glob("*.pdf"))


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_pdf_extraction(pdf_path):
    """Test that PDF extraction completes without errors."""
    expected_output_path = pdf_path.with_suffix(".extracted.csv")
    expected_df = pd.read_csv(expected_output_path)
    # Extract PDF to CSV
    actual_df = extract_to_csv(pdf_path)

    assert set(expected_df.columns) == set(actual_df.columns)
    for expected_row, actual_row in zip(expected_df, actual_df):
        assert expected_row == actual_row


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_statement_type_detection(pdf_path):
    """Test that statement type is correctly detected."""
    with pymupdf.open(pdf_path) as pdf:
        statement_type = StatementExtractor.extract_account_type(pdf)
        assert statement_type in ["visa", "chequing", "savings"]

        # Verify the detected type makes sense based on filename
        filename_lower = pdf_path.stem.lower()
        if "visa" in filename_lower:
            assert statement_type == "visa"
        elif "chequing" in filename_lower:
            assert statement_type == "chequing"
        elif "savings" in filename_lower:
            assert statement_type in ["savings", "chequing"]  # Both use same format


def test_visa_extraction_format():
    """Test that Visa extraction produces the correct format."""
    # Find a visa PDF
    visa_pdf = next((p for p in PDF_FILES if "visa" in p.stem.lower()), None)
    if not visa_pdf:
        pytest.skip("No visa PDF found in samples")

    df = extract_to_csv(visa_pdf)
    # Check the format
    assert "Transaction Date" in df.columns
    assert "Posting Date" in df.columns
    assert "Description" in df.columns
    assert "Amount" in df.columns


def test_chequing_extraction_format():
    """Test that Chequing/Savings extraction produces the correct format."""
    # Find a chequing or savings PDF
    chequing_pdf = next((p for p in PDF_FILES if "chequing" in p.stem.lower() or "savings" in p.stem.lower()), None)
    if not chequing_pdf:
        pytest.skip("No chequing/savings PDF found in samples")

    df = extract_to_csv(chequing_pdf)

    # Check the format
    assert "Date" in df.columns
    assert "Description" in df.columns
    assert "Withdrawals" in df.columns
    assert "Deposits" in df.columns
    assert "Balance" in df.columns
