"""Tests for PDF extractors using sample files."""

import csv
from io import StringIO
from pathlib import Path

import pytest

from rbc2.extractors import detect_statement_type, extract_to_csv

# Get all PDF files in the samples directory
SAMPLES_DIR = Path(__file__).parent.parent / "samples"
PDF_FILES = list(SAMPLES_DIR.glob("*.pdf"))


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_pdf_extraction(pdf_path):
    """Test that PDF extraction completes without errors."""
    expected_output_path = pdf_path.with_suffix(".csv")
    with open(expected_output_path, "r") as f:
        expected_output = f.read()
    # Extract PDF to CSV
    actual_output = extract_to_csv(pdf_path)

    expected_csv = csv.DictReader(StringIO(expected_output))
    actual_csv = csv.DictReader(StringIO(actual_output))

    assert expected_csv.fieldnames == actual_csv.fieldnames
    for expected_row, actual_row in zip(expected_csv, actual_csv):
        assert expected_row == actual_row


@pytest.mark.parametrize("pdf_path", PDF_FILES, ids=[p.stem for p in PDF_FILES])
def test_statement_type_detection(pdf_path):
    """Test that statement type is correctly detected."""
    statement_type = detect_statement_type(pdf_path)
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

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        output_path = Path(f.name)

    try:
        reader = csv.DictReader(StringIO(extract_to_csv(visa_pdf)))
        # Check the format
        fieldnames = reader.fieldnames
        assert "Transaction Date" in fieldnames
        assert "Posting Date" in fieldnames
        assert "Description" in fieldnames
        assert "Amount" in fieldnames
    finally:
        output_path.unlink(missing_ok=True)


def test_chequing_extraction_format():
    """Test that Chequing/Savings extraction produces the correct format."""
    # Find a chequing or savings PDF
    chequing_pdf = next((p for p in PDF_FILES if "chequing" in p.stem.lower() or "savings" in p.stem.lower()), None)
    if not chequing_pdf:
        pytest.skip("No chequing/savings PDF found in samples")

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        output_path = Path(f.name)

    csv_content = extract_to_csv(chequing_pdf)

    # Check the format
    reader = csv.DictReader(StringIO(csv_content))
    fieldnames = reader.fieldnames
    assert "Date" in fieldnames
    assert "Description" in fieldnames
    # May have Withdrawals, Deposits, Balance columns
