# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python CLI tool that converts bank statement PDFs to CSV files with automatic normalization. It supports multiple statement types (Visa credit cards, chequing, and savings accounts) and uses pattern matching to extract transactions from PDF text.

## Development Commands

### Environment Setup
This project uses `uv` for dependency management. All commands should be prefixed with `uv run`:

```bash
# Install dependencies
uv sync --dev

# Install the CLI tool for development
uv pip install -e .
```

### Running the CLI
```bash
# Extract PDF to raw CSV
uv run rbc-pdf-to-csv extract path/to/statement.pdf

# Normalize an extracted CSV
uv run rbc-pdf-to-csv process path/to/statement.csv

# Extract and normalize in one step
uv run rbc-pdf-to-csv convert path/to/statement.pdf

# Batch process all PDFs in a directory
uv run rbc-pdf-to-csv batch path/to/directory/
```

### Testing
```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/rbc2 --cov-report=html

# Run specific test file
uv run pytest tests/test_regression.py -v

# Run a single test
uv run pytest tests/test_regression.py::test_name -v
```

### Code Quality
```bash
# Check code style and quality
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/

# Format code
uv run ruff format src/ tests/
```

## Architecture

### Three-Stage Processing Pipeline

1. **Detection** ([extractors.py:198-221](src/rbc2/extractors.py#L198-L221))
   - `detect_statement_type()` analyzes PDF text to identify statement type
   - Returns 'visa', 'chequing', or 'savings' based on keywords

2. **Extraction** ([extractors.py](src/rbc2/extractors.py))
   - Uses statement-specific extractors that inherit from `StatementExtractor`
   - `VisaStatementExtractor`: Parses transaction/posting dates, descriptions, amounts
   - `ChequingSavingsStatementExtractor`: Parses dates, descriptions, withdrawals/deposits/balances
   - Each extractor handles date parsing with year rollover logic

3. **Normalization** ([processors.py](src/rbc2/processors.py))
   - Converts all statement formats to unified schema: Date, File, Description, Amount
   - Handles sign conventions: positive = deposits/credits, negative = withdrawals/debits
   - **Important**: Visa amounts are inverted (payments become positive, charges become negative)

### Date Parsing Logic

The extractors handle abbreviated date formats (e.g., "NOV17", "21Mar") and must infer the year from the statement period. The critical logic in [extractors.py:19-51](src/rbc2/extractors.py#L19-L51) handles:
- Year rollover detection (when month < current_month and current_month >= 11)
- Multiple date format patterns (MMMDD and DDMMM)
- Statement period extraction from first page text

### Regex Patterns

Transaction parsing relies on regex patterns that match specific statement layouts:
- **Visa** [extractors.py:95-98](src/rbc2/extractors.py#L95-L98): Matches "MMMDD MMMDD Description $Amount"
- **Chequing/Savings** [extractors.py:163-166](src/rbc2/extractors.py#L163-L166): Matches "DDMmm Description Amount1 [Amount2]"

When modifying patterns, test against all samples in `samples/` directory.

### Test Structure

The `samples/` directory contains test fixtures in triplets:
- `.pdf` - Original statement
- `.csv` - Raw extracted format
- `.processed.csv` - Normalized format

The regression test suite ([tests/test_regression.py](tests/test_regression.py)) automatically discovers and tests all samples.

## Common Development Tasks

### Adding Support for New Statement Variations

1. Add sample files to `samples/` directory (PDF, CSV, processed.csv)
2. Run tests to identify failures: `uv run pytest tests/test_regression.py -v`
3. Update regex patterns in the appropriate extractor class
4. Adjust date parsing logic if needed for new date formats
5. Test against all existing samples to avoid regressions

### Debugging Extraction Issues

1. Check PDF text extraction quality: `pdfplumber` may produce inconsistent spacing
2. Verify regex pattern matches using test data
3. Check year rollover logic for statements spanning December/January
4. Validate that the statement period extraction works for the new format

### Modifying Normalization Logic

The normalization step in [processors.py](src/rbc2/processors.py) must preserve the sign convention:
- Deposits/Credits → Positive amounts
- Withdrawals/Debits → Negative amounts
- Visa statements require sign inversion ([processors.py:52](src/rbc2/processors.py#L52))

## Code Style

- Python 3.12+ with modern type hints (`Path | None`, `list[dict[str, Any]]`)
- Line length: 120 characters
- Ruff for linting and formatting
- Use pandas for CSV operations in processors, csv module for extractors
- PDF conversion can be complicated, use the best pdf library for each kind of pdf statement

## Common patterns found in Canadian Banking pdfs

- Spelling can be a mix of British and American
- Use common terms. Prefer Withdrawals and Deposits. For example interpret "Cheques" or "Debits" as "Withdrawals
- some lines might not have a date. When this happens use the date from the row prior. For example, the first two rows should be interpretted as 20 Sep

| Date   | Description     | Cheques & Debits | Deposits & Credits | Balance  |
| ====== | =============== | ================ | ================== | ======== |
| 20 Sep | Online transfer | 2,000.00         |                    |          |
|        | Misc Payment    | 374.00           |                    | 922.29   |
| 27 Sep | Payment         |                  | 735.00             | 1,657.29 |

- Ignore lines such as 'opening balance' and 'closing balance'
- The dates are presented in chronological order. If the statement goes from December 2023 and the first transaction date is January, you can assume that this is January 2024 which is after December 2023
- Spaces should be preserved in the Description even though the pdf blocks might not make the spaces obvious. For example: "Online Banking payment - 6271 OTTAWA-TAX" not "OnlineBankingpayment-6271OTTAWA-TAX"
- Multiple spaces (`  `) can safely be re-interpreted as a single space (` `)
- Format all dates in ISO8601. For example 2025-11-12 for date segments
