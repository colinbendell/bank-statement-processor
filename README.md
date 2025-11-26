# bank-statement

A Python CLI tool to convert bank statement PDFs to CSV files with automatic normalization. This is primarily been tested with RBC statements

## Features

- **Multiple Statement Types**: Supports Visa credit cards, chequing accounts, and savings accounts
- **Automatic Detection**: Automatically detects the statement type from PDF content
- **Normalization**: Post-processes extracted data to a standard format
- **Regression Testing**: Built-in test harness using sample files
- **Modern Python**: Built with Python 3.12+, `uv` for package management, and latest best practices

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management. Install it first:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install the project:

```bash
# Clone the repository
git clone <repository-url>
cd bank_statement_processor

# Install dependencies
uv sync --dev

# Install the CLI tool
uv pip install -e .
```

## Usage

The tool provides several commands:

### Extract PDF to CSV

Extract transactions from a PDF to CSV format:

```bash
uv run rbc-pdf-to-csv extract path/to/statement.pdf
# Output: path/to/statement.csv

# Specify output path
uv run rbc-pdf-to-csv extract path/to/statement.pdf -o output.csv
```

### Normalize CSV

Normalize a CSV file to standard format:

```bash
uv run rbc-pdf-to-csv process path/to/statement.csv
# Output: path/to/statement.processed.csv

# Specify output path
uv run rbc-pdf-to-csv process path/to/statement.csv -o normalized.csv
```

### Convert (Extract + Normalize)

Extract and normalize in one step:

```bash
uv run rbc-pdf-to-csv convert path/to/statement.pdf
# Output: path/to/statement.processed.csv

# Keep intermediate CSV file
uv run rbc-pdf-to-csv convert path/to/statement.pdf --keep-intermediate
```

### Batch Processing

Process all PDFs in a directory:

```bash
uv run rbc-pdf-to-csv batch path/to/directory/
```

## Output Format

### Raw CSV Format (after extraction)

**Visa Statements:**
- Transaction Date, Posting Date, Description, Amount

**Chequing/Savings Statements:**
- Date, Description, Withdrawals, Deposits, Balance

### Normalized CSV Format (after processing)

All statement types are normalized to:
- **Date**: YYYY-MM-DD format
- **File**: Source PDF filename
- **Description**: Transaction description
- **Amount**: Positive for deposits/credits, negative for withdrawals/debits

## Testing

The project includes a comprehensive test suite using pytest:

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/bank_statement_processor --cov-report=html

# Run only regression tests
uv run pytest tests/test_regression.py -v
```

### Adding New Test Samples

To add new test cases:

1. Add PDF files to the `samples/` directory
2. Add corresponding `.csv` files (raw extracted format)
3. Add corresponding `.processed.csv` files (normalized format)

The test harness will automatically discover and test new samples.

## Development

### Code Quality

The project uses [ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check code quality
uv run ruff check src/ tests/

# Fix auto-fixable issues
uv run ruff check --fix src/ tests/

# Format code
uv run ruff format src/ tests/
```

### Project Structure

```
bank_statement_processor/
├── src/bank_statement_processor/
│   ├── __init__.py
│   ├── cli.py          # Click-based CLI interface
│   ├── extractors.py   # PDF extraction logic
│   └── processors.py   # CSV normalization logic
├── tests/
│   ├── test_extractors.py   # Extraction tests
│   ├── test_processors.py   # Normalization tests
│   └── test_regression.py   # End-to-end regression tests
├── samples/            # Test PDF and CSV files
├── pyproject.toml     # Project configuration
└── README.md
```

## How It Works

### 1. Statement Type Detection

The tool analyzes the PDF content to detect whether it's a:
- Visa credit card statement
- Chequing account statement
- Savings account statement

### 2. Extraction

Based on the detected type, the appropriate extractor parses the PDF text:
- Extracts transaction dates (handling various date formats)
- Parses descriptions and amounts
- Handles multi-page statements
- Manages year rollovers in abbreviated dates

### 3. Normalization

The processor standardizes the extracted data:
- Converts dates to YYYY-MM-DD format
- Combines Withdrawals/Deposits into a single Amount column
- Inverts signs for Visa (payments → positive, charges → negative)
- Adds source filename for tracking
- Removes quotes and normalizes formatting

## Known Limitations

- PDF text extraction quality varies by PDF generator
- Some edge cases may not be handled (see test failures)
- Multi-line descriptions may be truncated
- Spacing in extracted text may differ from original

## Contributing

1. Add your test case to `samples/`
2. Run tests to identify issues: `uv run pytest -v`
3. Improve extraction logic in `src/bank_statement_processor/extractors.py`
4. Ensure tests pass: `uv run pytest`
5. Check code quality: `uv run ruff check src/`

## License

[Add your license here]

## Author

Colin Bendell <colin@bendell.ca>
