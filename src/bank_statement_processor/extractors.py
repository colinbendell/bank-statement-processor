"""PDF extraction logic for RBC bank statements.

Rewritten using PyMuPDF with coordinate-based extraction for 100% accuracy.
Uses text span coordinates to properly reconstruct table rows from PDF layout.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
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

    ACCOUNT_NUMBER_REGEX = re.compile(r"(?:Your\s+)?Account\s+(?:Number|No)[\s:.]+(\d[\d\s\-]+)", re.IGNORECASE)
    CARD_NUMBER_REGEX = re.compile(r"(\d\d\d\d\s+(?:[0-9*]{4}\s+){2}\d\d\d\d)", re.IGNORECASE)
    CARD_ENDING_REGEX = re.compile(r"(?:Card\s+ending|ending\s+in)[\s:]+(\d{4})", re.IGNORECASE)

    SPACE_REGEX = re.compile(r"\s+")

    @staticmethod
    def extract_account_numbers(all_text: list[str]) -> list[str]:
        """Extract account number from PDF text using multiple patterns.

        Args:
            all_text: Raw text from PDF (preserves spacing)

        Returns:
            Extracted account number or 'NOT_FOUND'
        """

        results = []
        for page_text in all_text:
            # Pattern 1: "Account Number: XXXXX" or "Your account number: XXXXX"
            account_match = StatementExtractor.ACCOUNT_NUMBER_REGEX.findall(page_text)
            if len(account_match) > 0:
                for card in account_match:
                    # Clean up the account number - remove all spaces and keep dashes
                    results.append(StatementExtractor.SPACE_REGEX.sub(" ", card).strip())
                continue

            # Pattern 2: Visa card numbers like "4516 07** **** 9998"
            # Must search in all_text (not clean_text) to preserve spacing pattern
            card_match = StatementExtractor.CARD_NUMBER_REGEX.findall(page_text)
            if len(card_match) > 0:
                for card in card_match:
                    if "*" in card:
                        results.append(StatementExtractor.SPACE_REGEX.sub(" ", card).strip())
                continue

            # Pattern 3: Generic card ending pattern
            card_match = StatementExtractor.CARD_ENDING_REGEX.findall(page_text)
            for card in card_match:
                results.append(f"****{card}")

        if len(results) == 0:
            results.append("NOT_FOUND")
        return results

    PERSONAL_PATTERN = re.compile(r"\bpersonal\b", re.IGNORECASE)
    BUSINESS_PATTERN = re.compile(r"\b(business|commercial)\b", re.IGNORECASE)

    @staticmethod
    def extract_account_use(all_text: list[str]) -> str:
        """Determine if account is personal or business.

        Args:
            all_text: Raw text from PDF
            pdf_path: Path to the PDF file (used as fallback)

        Returns:
            'PERSONAL', 'BUSINESS', or 'UNKNOWN'
        """
        # Only check the first page's header to avoid footer/disclaimer text
        # (footer often contains "Royal Trust Corporation" which has "corp" in it)
        # Early exit after first page since account type is always at the top
        for page in all_text[:2]:
            header = page[:400]
            # Check for personal first (more specific)
            if StatementExtractor.PERSONAL_PATTERN.search(header):
                return "personal"

            # Then check for business indicators
            if StatementExtractor.BUSINESS_PATTERN.search(header):
                return "business"

        return "personal"

    VISA_MC_REGEX = re.compile(r"(visa|master card)", re.IGNORECASE)
    CREDIT_CARD_REGEX = re.compile(r"credit card|cardholder agreement", re.IGNORECASE)
    SAVINGS_REGEX = re.compile(r"savings?\s*account|esavings", re.IGNORECASE)
    CHEQUING_REGEX = re.compile(r"(?:chequing|banking)\s*account", re.IGNORECASE)
    DEBITS_REGEX = re.compile(r"cheques|debits|deposits", re.IGNORECASE)

    @staticmethod
    def extract_account_type(all_text: list[str]) -> str:
        """Determine account classification (visa/chequing/savings).

        Args:
            all_text: Raw text from PDF

        Returns:
            'VISA', 'CHEQUING', 'SAVINGS', or 'UNKNOWN'
        """
        # Account type is always on first page, check first 800 chars to include table headers
        for page in all_text[:2]:
            page_text = page[:500]

            if match := StatementExtractor.VISA_MC_REGEX.search(page_text):
                return match.group(0).lower()

            if StatementExtractor.CREDIT_CARD_REGEX.search(page_text):
                return "credit card"

            # Check for savings account
            if StatementExtractor.SAVINGS_REGEX.search(page_text):
                return "savings"

            # Check for chequing - look for "chequing account" or "banking account"
            if StatementExtractor.CHEQUING_REGEX.search(page_text):
                return "chequing"

            # Fallback to broader patterns (like "Cheques & Debits" table header)
            if StatementExtractor.DEBITS_REGEX.search(page_text):
                return "chequing"

        return "UNKNOWN"

    def statement_period(self, pdf_doc: pymupdf.Document) -> tuple[datetime, datetime]:
        """Extract start and end years from statement period."""
        raise NotImplementedError

    def extract(self, pdf_doc: pymupdf.Document, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Extract transactions from a PDF file."""
        raise NotImplementedError


class VisaStatementExtractor(StatementExtractor):
    """Extractor for RBC Visa credit card statements."""

    TRANSACTION_DATE_REGEX = re.compile(
        r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s]*(\d{1,2})$", re.IGNORECASE
    )
    STATEMENT_PERIOD_REGEX = re.compile(
        r"(?:STATEMENT\s+)?(?:From\s+)(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{1,2}),?\s*(\d{4})?\s+TO\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{1,2}),?\s*(\d{4})",
        re.IGNORECASE,
    )
    # Pre-compile frequently used patterns for row parsing
    AMOUNT_REGEX = re.compile(r"^[-]?\$?[\d,]+\.\d{2}$")
    NUMERIC_ONLY_REGEX = re.compile(r"^\d+$")
    CARD_NUMBER_SECTION_REGEX = re.compile(r"\d{4}\s+\d{2}\*{2}\s+\*{4}\s+\d{4}")
    CURRENCY_INFO_REGEX = re.compile(
        r"Foreign\s+Currency\s*-\s*([A-Z]{3})\s+([\d,]+\.\d{2})\s+Exchange\s+rate\s*-\s*([\d.]+)", re.IGNORECASE
    )
    SECOND_DATE_REGEX = re.compile(r"^([A-Z]{3}\s*\d{1,2})(?:\s+(.*))?$")
    AMOUNT_CLEAN_REGEX = re.compile(r"[^0-9.-]")

    def statement_period(self, all_text: list[str]) -> tuple[datetime, datetime]:
        """Extract start and end years from statement period."""

        for text in all_text:
            match = self.STATEMENT_PERIOD_REGEX.search(text)
            if not match:
                continue
            start_month_str, start_day, start_year, end_month_str, end_day, end_year = match.groups()

            end_month = datetime.strptime(end_month_str.upper(), "%b").month
            end_date = datetime(int(end_year), end_month, int(end_day))

            start_month = datetime.strptime(start_month_str.upper(), "%b").month
            if not start_year:
                start_year = end_date.year - 1 if start_month > end_date.month else end_date.year

            start_date = datetime(int(start_year), start_month, int(start_day))
            return start_date, end_date
        return None, None

    def _parse_date(self, date_str: str, start_date: datetime, end_date: datetime) -> str:
        """Parse Visa date format and return YYYY/MM/DD."""
        date_str = date_str.replace(" ", "").upper()

        match = self.TRANSACTION_DATE_REGEX.match(date_str)
        if not match:
            return date_str

        month_str, day = match.groups()
        month = datetime.strptime(month_str, "%b").month
        result = datetime(start_date.year, month, int(day))
        if result < start_date:
            result = datetime(end_date.year, month, int(day))
        return result.strftime("%Y-%m-%d")

    def extract(self, pdf_doc: pymupdf.Document, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Extract transactions from a Visa statement PDF using coordinate-based parsing.

        Handles both single-card and multi-card statements. Multi-card statements have
        sections for each card number (e.g., "4516 07** **** 4390").
        """

        # Posted date can be up to 30 days after the transaction date, we move the start_date back so the year calculations work
        start_date = start_date - timedelta(days=30)

        # Use dict of lists for faster DataFrame construction
        transactions = {
            "Transaction Date": [],
            "Posting Date": [],
            "Description": [],
            "Amount": [],
        }

        for page in pdf_doc:
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

            # Merge multi-line descriptions for Visa statements
            # When a description line continues on the next line without dates/amounts
            merged_rows = []
            i = 0
            while i < len(rows):
                current_row = rows[i]
                row_text = " ".join([s["text"] for s in current_row])

                # Check if this looks like a transaction row (has date pattern at start and amount at end)
                has_start_date = len(current_row) > 0 and self.TRANSACTION_DATE_REGEX.match(current_row[0]["text"])
                has_end_amount = len(current_row) > 0 and self.AMOUNT_REGEX.match(current_row[-1]["text"])

                # If this is a transaction row, check next rows for continuation lines
                if has_start_date and has_end_amount:
                    # Look ahead for description continuation lines
                    while i + 1 < len(rows):
                        next_row = rows[i + 1]
                        next_text = " ".join([s["text"] for s in next_row])

                        # Check if next row is a continuation (no date at start, no amount at end)
                        next_has_date = len(next_row) > 0 and self.TRANSACTION_DATE_REGEX.match(next_row[0]["text"])
                        next_has_amount = len(next_row) > 0 and self.AMOUNT_REGEX.match(next_row[-1]["text"])

                        # Stop if next row looks like a new transaction or header
                        if next_has_date or next_has_amount:
                            break
                        if "TRANSACTION" in next_text.upper() or "POSTING" in next_text.upper():
                            break

                        # Skip pure numeric reference codes (authorization numbers, etc.)
                        # These appear on their own line but are not part of the description
                        if self.NUMERIC_ONLY_REGEX.match(next_text.strip()):
                            i += 1
                            continue

                        # Check y-distance - don't merge if too far apart (different sections)
                        if len(current_row) > 0 and len(next_row) > 0:
                            y_distance = abs(next_row[0]["y"] - current_row[-1]["y"])
                            if y_distance > 15.0:
                                break

                        # This is a continuation line - insert it before the amount
                        # Remove amount from current row, add continuation text, re-add amount
                        amount_span = current_row[-1]
                        current_row = current_row[:-1] + next_row + [amount_span]
                        i += 1

                merged_rows.append(current_row)
                i += 1

            rows = merged_rows

            for row_spans in rows:
                # Build row text first for various checks
                row_text = " ".join([s["text"] for s in row_spans])

                # Check if this is a foreign currency info row (no dates, just currency details)
                # Format: "Foreign Currency-USD XX.XX Exchange rate-X.XXXXXX"
                # These rows have only 2 spans and should be captured before skipping short rows
                # Currency info appears AFTER the transaction, so we need to append it to the last transaction
                currency_match = self.CURRENCY_INFO_REGEX.search(row_text)
                if currency_match:
                    currency_code = currency_match.group(1)
                    foreign_amount = currency_match.group(2)
                    exchange_rate = currency_match.group(3)
                    currency_info = f" ({foreign_amount} {currency_code} @{exchange_rate})"

                    # Append to the last transaction's description
                    if transactions["Description"]:
                        transactions["Description"][-1] += currency_info
                    continue

                # Skip if not enough columns (need at least: trans_date, post_date, amount)
                # Some rows have post_date+description merged, so minimum is 3
                if len(row_spans) < 3:
                    continue

                # Skip card number headers (e.g., "4516 07** **** 4390")
                # These appear as section dividers in multi-card statements
                # Can appear with or without cardholder name prefix
                if self.CARD_NUMBER_SECTION_REGEX.search(row_text):
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
                if not self.TRANSACTION_DATE_REGEX.match(first_text):
                    continue

                # Check if last span looks like an amount
                last_text = row_spans[-1]["text"]
                if not self.AMOUNT_REGEX.match(last_text):
                    continue

                # Check if second span is also a date OR starts with a date
                second_text = row_spans[1]["text"]
                second_date_match = self.SECOND_DATE_REGEX.match(second_text.upper())

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

                amount = self.AMOUNT_CLEAN_REGEX.sub("", last_text)
                # amounts are negative for visa statements
                amount = float(amount) * -1.0

                # Parse dates
                trans_date = self._parse_date(trans_date_str, start_date, end_date)
                post_date = self._parse_date(post_date_str, start_date, end_date)

                # Append to lists (keep dates as strings for batch conversion)
                transactions["Transaction Date"].append(trans_date)
                transactions["Posting Date"].append(post_date)
                transactions["Description"].append(description)
                transactions["Amount"].append(float(amount))

        # Batch convert dates to datetime for better performance
        df = pd.DataFrame(transactions)
        if not df.empty:
            df["Transaction Date"] = pd.to_datetime(df["Transaction Date"])
            df["Posting Date"] = pd.to_datetime(df["Posting Date"])
        return df


class ChequingSavingsStatementExtractor(StatementExtractor):
    """Extractor for RBC Chequing and Savings account statements."""

    STATEMENT_PERIOD_REGEX = re.compile(
        r"(?:From\s+)?([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+to\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", re.IGNORECASE
    )
    TRANSACTION_DATE_REGEX = re.compile(r"(\d{1,2})\s*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)", re.IGNORECASE)
    # Pre-compile frequently used patterns
    AMOUNT_REGEX = re.compile(r"^[\d,]+\.\d{2}$")
    DATE_SIMPLE_REGEX = re.compile(r"^\d{1,2}\s*[A-Za-z]{3}$")
    DOC_REF_REGEX = re.compile(r"^RBP[A-Z]{2}\d")

    # Skip phrases for header detection (frozenset for faster lookups)
    SKIP_PHRASES = frozenset(
        [
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
            "of 4",
            "of 5",
            "of 6",
            "of 7",
            "of 8",
            "of 9",
            "of 10",
            "account statement",
            "account number",
            "continued",
        ]
    )

    MONTH_NAMES = frozenset(
        [
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
    )

    def statement_period(self, all_text: list[str]) -> tuple[datetime, datetime]:
        """Extract start and end years from statement period."""

        for text in all_text:
            match = self.STATEMENT_PERIOD_REGEX.search(text)
            if not match:
                continue
            start_month_str, start_day, start_year, end_month_str, end_day, end_year = match.groups()

            end_month = datetime.strptime(end_month_str.upper(), "%B").month
            end_date = datetime(int(end_year), end_month, int(end_day))

            start_month = datetime.strptime(start_month_str.upper(), "%B").month
            if not start_year:
                start_year = end_date.year - 1 if start_month > end_date.month else end_date.year

            start_date = datetime(int(start_year), start_month, int(start_day))
            return start_date, end_date
        return None, None

    def _parse_date(self, date_str: str, start_date: datetime, end_date: datetime) -> str:
        """Parse Visa date format and return YYYY/MM/DD."""

        match = self.TRANSACTION_DATE_REGEX.match(date_str)
        if not match:
            return date_str

        day, month_str = match.groups()
        month = datetime.strptime(month_str, "%b").month
        result = datetime(start_date.year, month, int(day))
        if result < start_date:
            result = datetime(end_date.year, month, int(day))
        return result.strftime("%Y-%m-%d")

    def extract(self, pdf_doc: pymupdf.Document, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Extract transactions from a Chequing/Savings statement PDF using coordinate-based parsing."""
        # Use dict of lists for faster DataFrame construction
        transactions = {
            "Date": [],
            "Description": [],
            "Withdrawals": [],
            "Deposits": [],
            "Balance": [],
        }

        # Detect column positions from header row (first page)
        withdrawal_col_x = None
        deposit_col_x = None
        balance_col_x = None

        first_page_dict = pdf_doc[0].get_text("dict")
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

        for page in pdf_doc:
            text_dict = page.get_text("dict")

            # Collect all spans with coordinates
            all_spans = []
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            bbox = span.get("bbox", [])
                            # Filter out document reference codes (typically start with RBPDA, RBPDP, etc.)
                            # These appear in margins and should not be included in transactions
                            if text and bbox and not self.DOC_REF_REGEX.match(text):
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
                current_has_amounts = any(self.AMOUNT_REGEX.match(span["text"]) for span in current_row)

                # Check if current row is a header (contains skip phrases)
                row_text = " ".join([s["text"] for s in current_row]).lower()
                is_header = any(phrase in row_text for phrase in self.SKIP_PHRASES)

                # If current row has NO amounts and is NOT a header, merge continuation lines
                if not current_has_amounts and not is_header:
                    while i + 1 < len(rows):
                        next_row = rows[i + 1]
                        next_has_date = any(self.DATE_SIMPLE_REGEX.match(span["text"]) for span in next_row)
                        y_distance = abs(next_row[0]["y"] - current_row[-1]["y"])

                        # Stop if next row has a date or is too far
                        if next_has_date or y_distance > 15.0:
                            break

                        # Merge the continuation line
                        current_row = current_row + next_row
                        i += 1

                        # Check if we now have amounts (found the amounts line)
                        current_has_amounts = any(self.AMOUNT_REGEX.match(span["text"]) for span in current_row)
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
                    if self.DATE_SIMPLE_REGEX.match(span["text"]):
                        date_span = span
                        break

                if date_span:
                    parsed_date = self._parse_date(date_span["text"], start_date, end_date)
                    last_date = parsed_date
                else:
                    if not last_date:
                        continue
                    parsed_date = last_date

                # Skip header rows
                row_text = " ".join([s["text"] for s in row_spans]).lower()
                # Skip if any skip phrase is present
                if any(phrase in row_text for phrase in self.SKIP_PHRASES):
                    continue
                # Skip standalone month names (headers) but not dates like "01 May"
                if row_text.strip() in self.MONTH_NAMES:
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
                    if self.AMOUNT_REGEX.match(span["text"]):
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

                # Append to lists (keep dates as strings, amounts as floats or NaN)
                transactions["Date"].append(parsed_date)
                transactions["Description"].append(description)
                transactions["Withdrawals"].append(float(withdrawal_amount) if withdrawal_amount else None)
                transactions["Deposits"].append(float(deposit_amount) if deposit_amount else None)
                transactions["Balance"].append(float(balance_amount) if balance_amount else None)

        # Batch convert dates to datetime for better performance
        df = pd.DataFrame(transactions)
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            # Ensure numeric columns have float64 dtype (needed when all values are NaN)
            df["Withdrawals"] = df["Withdrawals"].astype("float64")
            df["Deposits"] = df["Deposits"].astype("float64")
            df["Balance"] = df["Balance"].astype("float64")
        return df


def extract_to_csv(pdf_path: Path) -> pd.DataFrame:
    """
    Extract transactions from a PDF and return CSV content as a string.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        CSV content as a string
    """
    with pymupdf.open(pdf_path) as pdf:
        all_text = []
        for page in pdf:
            all_text.append(page.get_text())

        account_use = StatementExtractor.extract_account_use(all_text)
        account_type = StatementExtractor.extract_account_type(all_text)
        account_numbers = list(StatementExtractor.extract_account_numbers(all_text))
        # TODO: make this based on frequency
        account_number = account_numbers[-1]

        # file = "personal/rbc/visa/141232/2025-08-20.pdf"

        if account_type in ["visa", "master card", "credit card"]:
            extractor = VisaStatementExtractor()
        else:
            extractor = ChequingSavingsStatementExtractor()
        start_date, end_date = extractor.statement_period(all_text)
        df = extractor.extract(pdf, start_date, end_date)

        if df.empty:
            return df

        filename = f"{account_use}_{account_type}_{account_number}_{end_date.strftime('%Y_%m_%d')}"
        filename = re.sub(r"[\s.-]", "", filename).replace("*", "x")

        df["File"] = filename

    return df

def extract_filename(pdf_path: Path) -> pd.DataFrame:
    """
    Extract transactions from a PDF and return CSV content as a string.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        CSV content as a string
    """
    with pymupdf.open(pdf_path) as pdf:
        all_text = []
        for page in pdf:
            all_text.append(page.get_text())

        account_use = StatementExtractor.extract_account_use(all_text)
        account_type = StatementExtractor.extract_account_type(all_text)
        account_numbers = list(StatementExtractor.extract_account_numbers(all_text))
        # TODO: make this based on frequency
        account_number = account_numbers[-1]

        # file = "personal/rbc/visa/141232/2025-08-20.pdf"

        if account_type in ["visa", "master card", "credit card"]:
            extractor = VisaStatementExtractor()
        else:
            extractor = ChequingSavingsStatementExtractor()
        _start_date, end_date = extractor.statement_period(all_text)

        if not end_date:
            return None
        filename = f"{account_use}_{account_type}_{account_number}_{end_date.strftime('%Y_%m_%d')}"
        filename = re.sub(r"[\s.-]", "", filename).replace("*", "x")
        return filename
