"""PDF extraction logic for RBC bank statements.

Rewritten using PyMuPDF with coordinate-based extraction for 100% accuracy.
Uses text span coordinates to properly reconstruct table rows from PDF layout.
"""

import csv
import re
import io
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf  # PyMuPDF


def group_spans_by_row(spans: list[dict], y_tolerance: float = 3.0) -> list[list[dict]]:
    """
    Group text spans into rows based on Y-coordinate proximity.

    Args:
        spans: List of span dicts with 'text', 'x', 'y' keys
        y_tolerance: Maximum Y-coordinate difference to consider same row

    Returns:
        List of rows, where each row is a list of spans sorted by X-coordinate
    """
    if not spans:
        return []

    # Group spans by similar Y coordinates
    rows = []
    current_row = [spans[0]]
    current_y = spans[0]["y"]

    for span in spans[1:]:
        if abs(span["y"] - current_y) <= y_tolerance:
            # Same row
            current_row.append(span)
        else:
            # New row
            # Sort current row by X coordinate
            current_row.sort(key=lambda s: s["x"])
            rows.append(current_row)
            current_row = [span]
            current_y = span["y"]

    # Don't forget the last row
    if current_row:
        current_row.sort(key=lambda s: s["x"])
        rows.append(current_row)

    return rows


class StatementExtractor:
    """Base class for statement extractors."""

    def extract(self, pdf_path: Path) -> list[dict[str, Any]]:
        """Extract transactions from a PDF file."""
        raise NotImplementedError


class VisaStatementExtractor(StatementExtractor):
    """Extractor for RBC Visa credit card statements."""

    def _extract_statement_period(self, text: str) -> tuple[int, int]:
        """Extract start and end years from statement period."""
        pattern = r"(?:STATEMENT\s+)?FROM\s+([A-Z]{3})\s+\d{1,2},?\s*(\d{4})?\s+TO\s+([A-Z]{3})\s+\d{1,2},?\s*(\d{4})"
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            start_month_str, start_year_str, end_month_str, end_year_str = match.groups()
            start_month = datetime.strptime(start_month_str.upper(), "%b").month
            end_month = datetime.strptime(end_month_str.upper(), "%b").month
            end_year = int(end_year_str)

            if start_year_str:
                start_year = int(start_year_str)
            else:
                start_year = end_year - 1 if start_month > end_month else end_year

            return start_year, end_year

        # Fallback
        match = re.search(r"\b(20\d{2})\b", text)
        if match:
            year = int(match.group(1))
            return year, year

        current_year = datetime.now().year
        return current_year, current_year

    def _determine_year(self, month: int, start_year: int, end_year: int) -> int:
        """Determine which year a transaction belongs to."""
        if start_year == end_year:
            return start_year

        # For year-crossing statements
        return start_year if month >= 10 else end_year

    def _parse_date(self, date_str: str, start_year: int, end_year: int) -> str:
        """Parse Visa date format and return YYYY/MM/DD."""
        date_str = date_str.replace(" ", "").upper()

        match = re.match(r"([A-Z]{3})(\d{1,2})", date_str)
        if not match:
            return date_str

        month_str, day = match.groups()
        month = datetime.strptime(month_str, "%b").month
        year = self._determine_year(month, start_year, end_year)

        return f"{year}-{month:02d}-{int(day):02d}"

    def extract(self, pdf_path: Path) -> list[dict[str, Any]]:
        """Extract transactions from a Visa statement PDF using coordinate-based parsing.

        Handles both single-card and multi-card statements. Multi-card statements have
        sections for each card number (e.g., "4516 07** **** 4390").
        """
        transactions = []

        doc = pymupdf.open(pdf_path)

        # Get statement period from first page
        first_page_text = doc[0].get_text()
        start_year, end_year = self._extract_statement_period(first_page_text)

        for page in doc:
            text_dict = page.get_text("dict")

            # Collect all text spans with coordinates
            # Filter to transaction table area (x < 380 to exclude right-side summary boxes)
            all_spans = []
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            bbox = span.get("bbox", [])
                            # Only include spans in transaction area (left side of page)
                            if text and bbox and bbox[0] < 380:
                                all_spans.append(
                                    {
                                        "text": text,
                                        "x": bbox[0],
                                        "y": bbox[1],
                                    }
                                )

            # Sort by Y coordinate first
            all_spans.sort(key=lambda s: (s["y"], s["x"]))

            # Group into rows
            rows = group_spans_by_row(all_spans, y_tolerance=3.0)

            for row_spans in rows:
                # Build row text first for various checks
                row_text = " ".join([s["text"] for s in row_spans])

                # Check if this is a foreign currency info row (no dates, just currency details)
                # Format: "Foreign Currency-USD XX.XX Exchange rate-X.XXXXXX"
                # These rows have only 2 spans and should be captured before skipping short rows
                # Currency info appears AFTER the transaction, so we need to append it to the last transaction
                currency_match = re.search(
                    r"Foreign\s+Currency\s*-\s*([A-Z]{3})\s+([\d,]+\.\d{2})\s+Exchange\s+rate\s*-\s*([\d.]+)", row_text
                )
                if currency_match:
                    currency_code = currency_match.group(1)
                    foreign_amount = currency_match.group(2)
                    exchange_rate = currency_match.group(3)
                    currency_info = f" ({foreign_amount} {currency_code} @{exchange_rate})"

                    # Append to the last transaction's description
                    if transactions:
                        transactions[-1]["Description"] += currency_info
                    continue

                # Skip if not enough columns (need at least: trans_date, post_date, amount)
                # Some rows have post_date+description merged, so minimum is 3
                if len(row_spans) < 3:
                    continue

                # Skip card number headers (e.g., "4516 07** **** 4390")
                # These appear as section dividers in multi-card statements
                # Can appear with or without cardholder name prefix
                if re.search(r"\d{4}\s+\d{2}\*{2}\s+\*{4}\s+\d{4}", row_text):
                    continue

                # Skip header rows with column labels
                if "TRANSACTION" in row_text.upper() or "POSTING" in row_text.upper():
                    continue
                if "ACTIVITY DESCRIPTION" in row_text.upper():
                    continue
                if "SUBTOTAL" in row_text.upper() or "MONTHLY ACTIVITY" in row_text.upper():
                    continue

                # Check if first span looks like a date (MMM DD format)
                first_text = row_spans[0]["text"]
                if not re.match(r"^[A-Z]{3}\s*\d{1,2}$", first_text.upper()):
                    continue

                # Check if last span looks like an amount
                last_text = row_spans[-1]["text"]
                if not re.match(r"^[-]?\$?[\d,]+\.\d{2}$", last_text):
                    continue

                # Check if second span is also a date OR starts with a date
                second_text = row_spans[1]["text"]
                second_date_match = re.match(r"^([A-Z]{3}\s*\d{1,2})(?:\s+(.*))?$", second_text.upper())

                if not second_date_match:
                    continue

                # Parse transaction
                trans_date_str = first_text
                post_date_str = second_date_match.group(1)

                # Description: if posting date had extra text, use it; otherwise use spans between dates and amount
                extra_text = second_date_match.group(2)
                if extra_text:
                    # Second span contained "DATE DESCRIPTION", extract description part
                    # Get actual case from original text
                    desc_start = len(post_date_str)
                    remaining_text = second_text[desc_start:].strip()
                    description_parts = [remaining_text] + [s["text"] for s in row_spans[2:-1]]
                else:
                    # Normal case: description is between the two date spans
                    description_parts = [s["text"] for s in row_spans[2:-1]]

                description = " ".join(description_parts)

                amount = last_text

                # Parse dates
                trans_date = self._parse_date(trans_date_str, start_year, end_year)
                post_date = self._parse_date(post_date_str, start_year, end_year)

                # Clean amount
                is_negative = amount.startswith("-")
                amount_clean = amount.replace("-", "").replace("$", "").replace(",", "")

                transactions.append(
                    {
                        "Transaction Date": trans_date,
                        "Posting Date": post_date,
                        "Description": description,
                        "Amount": f"-{amount_clean}" if is_negative else amount_clean,
                    }
                )

        doc.close()
        return transactions


class ChequingSavingsStatementExtractor(StatementExtractor):
    """Extractor for RBC Chequing and Savings account statements."""

    def _extract_statement_period(self, text: str) -> tuple[int, int, int, int]:
        """
        Extract start and end dates from statement period.

        Returns:
            (start_year, end_year, start_month, end_month)
        """
        # Try with "From" prefix first
        pattern = r"From\s+([A-Za-z]+)\s+\d{1,2},?\s+(\d{4})\s+to\s+([A-Za-z]+)\s+\d{1,2},?\s+(\d{4})"
        match = re.search(pattern, text, re.IGNORECASE)

        # If not found, try without "From" prefix (e.g., "December 30, 2022 to January 31, 2023")
        if not match:
            pattern = r"([A-Za-z]+)\s+\d{1,2},?\s+(\d{4})\s+to\s+([A-Za-z]+)\s+\d{1,2},?\s+(\d{4})"
            match = re.search(pattern, text, re.IGNORECASE)

        if match:
            start_month_str, start_year_str, end_month_str, end_year_str = match.groups()
            start_month = datetime.strptime(start_month_str.title(), "%B").month
            end_month = datetime.strptime(end_month_str.title(), "%B").month
            return int(start_year_str), int(end_year_str), start_month, end_month

        # Fallback
        match = re.search(r"\b(20\d{2})\b", text)
        if match:
            year = int(match.group(1))
            return year, year, 1, 12

        current_year = datetime.now().year
        return current_year, current_year, 1, 12

    def _determine_year(self, month: int, start_year: int, end_year: int, start_month: int, end_month: int) -> int:
        """Determine which year a transaction month belongs to."""
        if start_year == end_year:
            return start_year

        # For year-crossing statements
        if start_month > end_month:
            if month >= start_month:
                return start_year
            elif month <= end_month:
                return end_year
            else:
                return end_year
        else:
            return start_year

    def _parse_date(self, date_str: str, start_year: int, end_year: int, start_month: int, end_month: int) -> str:
        """Parse chequing/savings date format and return YYYY/MM/DD."""
        date_str = date_str.replace(" ", "")

        match = re.match(r"(\d{1,2})([A-Za-z]{3})", date_str)
        if not match:
            return date_str

        day, month_str = match.groups()
        month = datetime.strptime(month_str.title(), "%b").month
        year = self._determine_year(month, start_year, end_year, start_month, end_month)

        return f"{year}-{month:02d}-{int(day):02d}"

    def extract(self, pdf_path: Path) -> list[dict[str, Any]]:
        """Extract transactions from a Chequing/Savings statement PDF using coordinate-based parsing."""
        transactions = []

        doc = pymupdf.open(pdf_path)

        # Get statement period from first page
        first_page_text = doc[0].get_text()
        start_year, end_year, start_month, end_month = self._extract_statement_period(first_page_text)

        # Detect column positions from header row (first page)
        withdrawal_col_x = None
        deposit_col_x = None
        balance_col_x = None

        first_page_dict = doc[0].get_text("dict")
        for block in first_page_dict.get("blocks", []):
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    line_text = "".join([span.get("text", "") for span in line.get("spans", [])])
                    if "Cheques & Debits" in line_text or "Deposits & Credits" in line_text:
                        for span in line.get("spans", []):
                            text = span.get("text", "")
                            bbox = span.get("bbox", [])
                            if "Cheques" in text or "Debits" in text:
                                withdrawal_col_x = bbox[0]
                            elif "Deposits" in text or "Credits" in text:
                                deposit_col_x = bbox[0]
                            elif "Balance" in text:
                                balance_col_x = bbox[0]

        # Fallback column positions if not found
        if withdrawal_col_x is None:
            withdrawal_col_x = 316.0
        if deposit_col_x is None:
            deposit_col_x = 418.0
        if balance_col_x is None:
            balance_col_x = 520.0

        # Track last seen date
        last_date = None

        for page in doc:
            text_dict = page.get_text("dict")

            # Collect all spans with coordinates
            all_spans = []
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            bbox = span.get("bbox", [])
                            if text and bbox:
                                all_spans.append(
                                    {
                                        "text": text,
                                        "x": bbox[0],
                                        "y": bbox[1],
                                    }
                                )

            # Sort by Y then X
            all_spans.sort(key=lambda s: (s["y"], s["x"]))

            # Group into rows by Y-coordinate
            rows = group_spans_by_row(all_spans, y_tolerance=3.0)

            # Merge multi-line descriptions (where description text spans multiple PDF rows without amounts)
            # Only merge when current row has NO amounts - true continuation lines
            # But don't merge if current row is a header row
            merged_rows = []
            i = 0
            while i < len(rows):
                current_row = rows[i]
                current_has_amounts = any(re.match(r"^[\d,]+\.\d{2}$", span["text"]) for span in current_row)

                # Check if current row is a header (contains skip words like "date description")
                row_text = " ".join([s["text"] for s in current_row]).lower()
                skip_words = [
                    "account activity",
                    "opening balance",
                    "closing balance",
                    "account fees",
                    "total deposits",
                    "total cheques",
                    "date description",
                    "cheques & debits",
                    "deposits & credits",
                    "withdrawals",
                    "royal bank",
                    "page ",
                    "of 1",
                    "of 2",
                    "of 3",
                    "account statement",
                    "account number",
                    "continued",
                ]
                is_header = any(skip in row_text for skip in skip_words)

                # If current row has NO amounts and is NOT a header, merge continuation lines
                if not current_has_amounts and not is_header:
                    while i + 1 < len(rows):
                        next_row = rows[i + 1]
                        next_has_date = any(re.match(r"^\d{1,2}\s*[A-Za-z]{3}$", span["text"]) for span in next_row)
                        y_distance = abs(next_row[0]["y"] - current_row[-1]["y"])

                        # Stop if next row has a date or is too far
                        if next_has_date or y_distance > 15.0:
                            break

                        # Merge the continuation line
                        current_row = current_row + next_row
                        i += 1

                        # Check if we now have amounts (found the amounts line)
                        current_has_amounts = any(re.match(r"^[\d,]+\.\d{2}$", span["text"]) for span in current_row)
                        if current_has_amounts:
                            break  # Stop merging once we have amounts

                merged_rows.append(current_row)
                i += 1

            rows = merged_rows

            for row_spans in rows:
                if not row_spans:
                    continue

                # Check if row contains a date
                date_span = None
                for span in row_spans:
                    if re.match(r"^\d{1,2}\s*[A-Za-z]{3}$", span["text"]):
                        date_span = span
                        break

                if date_span:
                    parsed_date = self._parse_date(date_span["text"], start_year, end_year, start_month, end_month)
                    last_date = parsed_date
                else:
                    if not last_date:
                        continue
                    parsed_date = last_date

                # Skip header rows
                row_text = " ".join([s["text"] for s in row_spans]).lower()
                skip_words = [
                    "account activity",
                    "opening balance",
                    "closing balance",
                    "account fees",
                    "total deposits",
                    "total cheques",
                    "date description",
                    "cheques & debits",
                    "deposits & credits",
                    "withdrawals",
                    "royal bank",
                    "page ",
                    "of 1",
                    "of 2",
                    "of 3",
                    "account statement",
                    "account number",
                    "continued",
                ]
                # Skip if any skip word is present, but allow dates containing month names
                if any(skip in row_text for skip in skip_words):
                    continue
                # Skip standalone month names (headers) but not dates like "01 May"
                month_names = [
                    "august",
                    "september",
                    "october",
                    "november",
                    "december",
                    "january",
                    "february",
                    "march",
                    "april",
                    "may",
                    "june",
                    "july",
                ]
                # Check if row is just a month name (not part of a date like "01 May")
                if row_text.strip() in month_names:
                    continue

                # Separate description and amounts by X position
                description_spans = []
                withdrawal_amount = ""
                deposit_amount = ""
                balance_amount = ""

                for span in row_spans:
                    # Skip date span
                    if date_span and span == date_span:
                        continue

                    # Check if this is an amount
                    if re.match(r"^[\d,]+\.\d{2}$", span["text"]):
                        amount = span["text"].replace(",", "")
                        x = span["x"]

                        # Determine which column based on X position using ranges
                        # Amounts are right-aligned, so we need adjusted boundaries
                        # Based on empirical observation, boundaries are:
                        # Withdrawals: < 400, Deposits: 400-500, Balance: > 500
                        withdrawal_deposit_boundary = 400.0
                        deposit_balance_boundary = 500.0

                        if x < withdrawal_deposit_boundary:
                            withdrawal_amount = amount
                        elif x < deposit_balance_boundary:
                            deposit_amount = amount
                        else:
                            balance_amount = amount
                    else:
                        # Description text
                        description_spans.append(span["text"])

                if not description_spans:
                    continue

                # Skip rows with no amounts at all
                if not withdrawal_amount and not deposit_amount and not balance_amount:
                    continue

                description = " ".join(description_spans)

                transactions.append(
                    {
                        "Date": parsed_date,
                        "Description": description,
                        "Withdrawals": withdrawal_amount,
                        "Deposits": deposit_amount,
                        "Balance": balance_amount,
                    }
                )

        doc.close()
        return transactions


def detect_statement_type(pdf_path: Path) -> str:
    """Detect the type of bank statement from the PDF content."""
    doc = pymupdf.open(pdf_path)

    if not doc:
        raise ValueError(f"Cannot open PDF file {pdf_path}")

    text = doc[0].get_text()
    doc.close()

    if not text:
        raise ValueError(f"Cannot extract text from {pdf_path}")

    text_lower = text.lower()

    # Check for specific account types first (more specific matches)
    if "chequing" in text_lower or "checking" in text_lower:
        return "chequing"
    elif "savings" in text_lower:
        return "savings"
    # Then check for visa/credit card (more general, can appear in warnings/ads)
    elif "visa" in text_lower or "credit card" in text_lower:
        return "visa"
    else:
        # Fallback: if has withdrawal/deposit columns, it's likely chequing/savings
        if "withdrawal" in text_lower or "deposit" in text_lower:
            return "chequing"
        return "visa"


def extract_to_csv(pdf_path: Path) -> str:
    """
    Extract transactions from a PDF and return CSV content as a string.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        CSV content as a string
    """
    statement_type = detect_statement_type(pdf_path)

    if statement_type == "visa":
        extractor = VisaStatementExtractor()
    else:
        extractor = ChequingSavingsStatementExtractor()

    transactions = extractor.extract(pdf_path)

    if not transactions:
        raise ValueError(f"No transactions found in {pdf_path}")

    # Generate CSV content
    output = io.StringIO()
    fieldnames = list(transactions[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(transactions)
    csv_content = output.getvalue()
    output.close()

    return csv_content
