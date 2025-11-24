"""Extract account metadata from RBC statement PDFs.

This module provides functionality to extract account numbers, account types
(personal/business), and account classifications (visa/chequing/savings) from
RBC bank statement PDFs.
"""

import re
from pathlib import Path
from typing import Any

import pymupdf

ACCOUNT_NUMBER_PATTERN = re.compile(r"(?:Your\s+)?Account\s+(?:Number|No)[\s:.]+(\d[\d\s\-]+)", re.IGNORECASE)
CARD_NUMBER_PATTERN = re.compile(r"(\d\d\d\d\s+(?:[0-9*]{4}\s+){2}\d\d\d\d)", re.IGNORECASE)
CARD_ENDING_PATTERN = re.compile(r"(?:Card\s+ending|ending\s+in)[\s:]+(\d{4})", re.IGNORECASE)


def _extract_account_number(pdf_pages: list[str]) -> list[str]:
    """Extract account number from PDF text using multiple patterns.

    Args:
        all_text: Raw text from PDF (preserves spacing)

    Returns:
        Extracted account number or 'NOT_FOUND'
    """

    results = set()
    for page in pdf_pages:
        # Pattern 1: "Account Number: XXXXX" or "Your account number: XXXXX"
        account_match = ACCOUNT_NUMBER_PATTERN.findall(page)
        if len(account_match) > 0:
            for card in account_match:
                # Clean up the account number - remove all spaces and keep dashes
                results.add(card.replace(" ", ""))
            continue

        # Pattern 2: Visa card numbers like "4516 07** **** 9998"
        # Must search in all_text (not clean_text) to preserve spacing pattern
        card_match = CARD_NUMBER_PATTERN.findall(page)
        if len(card_match) > 0:
            for card in card_match:
                if "*" in card:
                    results.add(card.strip())
            continue

        # Pattern 3: Generic card ending pattern
        card_match = CARD_ENDING_PATTERN.findall(page)
        for card in card_match:
            results.add(f"****{card}")

    if len(results) == 0:
        results.add("NOT_FOUND")
    return results


PERSONAL_PATTERN = re.compile(r"\bpersonal\b", re.IGNORECASE)
BUSINESS_PATTERN = re.compile(r"\b(business|commercial)\b", re.IGNORECASE)


def _extract_account_use(pdf_pages: list[str]) -> str:
    """Determine if account is personal or business.

    Args:
        all_text: Raw text from PDF
        pdf_path: Path to the PDF file (used as fallback)

    Returns:
        'PERSONAL', 'BUSINESS', or 'UNKNOWN'
    """
    # Only check the first 800 chars to avoid footer/disclaimer text
    # (footer often contains "Royal Trust Corporation" which has "corp" in it)
    for page in pdf_pages:
        header = page[:400]
        # Check for personal first (more specific)
        if PERSONAL_PATTERN.search(header):
            return "PERSONAL"

        # Then check for business indicators
        if BUSINESS_PATTERN.search(header):
            return "BUSINESS"

    return "PERSONAL"


def _extract_account_type(pdf_pages: str) -> str:
    """Determine account classification (visa/chequing/savings).

    Args:
        all_text: Raw text from PDF

    Returns:
        'VISA', 'CHEQUING', 'SAVINGS', or 'UNKNOWN'
    """
    for page in pdf_pages:
        header = page[:300]

        if re.search(r"visa|master card|credit card|cardholder agreement", header, re.IGNORECASE):
            return "VISA"

        # Check for savings account
        if re.search(r"savings?\s*account", header, re.IGNORECASE):
            return "SAVINGS"

        # Check for chequing - look for "chequing account" or "banking account"
        if re.search(r"(?:chequing|banking)\s*account", header, re.IGNORECASE):
            return "CHEQUING"

        # Fallback to broader patterns
        if re.search(r"chequs|debits", page, re.IGNORECASE):
            return "CHEQUING"

    return "UNKNOWN"


def extract_statement_metadata(pdf_paths: list[Path]) -> list[dict[str, str]]:
    """Extract account number, type, and classification from a PDF statement.

    Args:
        pdf_paths: List of paths to PDF files

    Returns:
        Dictionary with the following keys:
        - file: Full path to the PDF file
        - account_number: Extracted account number or 'NOT_FOUND'
        - account_use: 'PERSONAL', 'BUSINESS', or 'UNKNOWN'
        - account_type: 'VISA', 'CHEQUING', 'SAVINGS', or 'UNKNOWN'

    Examples:
        >>> from pathlib import Path
        >>> pdfs = [Path('statement1.pdf'), Path('statement2.pdf')]
        >>> results = extract_statement_metadata(pdfs)
        >>> len(results)
        2
        >>> print(results[0]['account_number'])
        '01592-5076500'
        >>> print(results[0]['account_use'])
        'PERSONAL'
        >>> print(results[0]['account_type'])
        'CHEQUING'

    """
    results = []
    for pdf_path in pdf_paths:
        with pymupdf.open(pdf_path) as pdf:
            all_text = []
            for pdf_page in pdf:
                all_text.append(" ".join(pdf_page.get_text().split()))

            account_use = _extract_account_use(all_text)
            account_type = _extract_account_type(all_text)
            account_numbers = _extract_account_number(all_text)

            for account_number in account_numbers:
                results.append(
                    {
                        "account_number": account_number,
                        "account_use": account_use,
                        "account_type": account_type,
                        "file": pdf_path,
                    }
                )

    return results
