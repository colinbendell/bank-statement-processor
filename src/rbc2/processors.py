"""CSV normalization and post-processing logic."""

import csv
from io import StringIO
from pathlib import Path
from re import S
import pandas as pd
from .extractors import extract_to_csv
from datetime import datetime
import re


def iso8601_date(d: str) -> str:
    """Convert various date formats to YYYY-MM-DD format.

    Args:
        d: Date string in various formats

    Returns:
        Date string in YYYY-MM-DD format

    Raises:
        ValueError: If date format is not supported
    """
    try:
        return datetime.strptime(d, "%Y/%m/%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        return datetime.strptime(d, "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass
    raise ValueError(f"unsupported date format: {d}")


def clean_date_column(df: pd.DataFrame, column: str) -> None:
    """Clean and standardize date column in DataFrame.

    Args:
        df: DataFrame containing the date column
        column: Name of the date column to clean
    """
    d = pd.to_datetime(df[column], format="%Y/%m/%d", errors="coerce").min()
    if pd.isna(d):
        raise RuntimeError(f"no valid dates in column {column}")

    for i in range(len(df)):
        cur = df.loc[i, column]
        if pd.isna(cur):
            df.loc[i, column] = d
            continue
        try:
            d = iso8601_date(cur)
        except ValueError:
            pass
        df.loc[i, column] = d


def sanitize_description(description: str) -> str:
    """Sanitize transaction description by removing newlines.

    Args:
        description: Raw description string

    Returns:
        Sanitized description string
    """
    return re.sub(r"\n+", " ", description)


def normalize_csv(input_path: Path, csv_content: str = None) -> str:
    """
    Normalize a CSV file to a standard format.

    The normalized format has columns: Date, File, Description, Amount
    - Date format is YYYY-MM-DD
    - File is the source PDF filename
    - Description is the transaction description
    - Amount is positive for deposits/credits, negative for withdrawals/debits

    Args:
        input_path: Path to the input CSV file
        output_path: Optional output path for the processed CSV file

    Returns:
        Path to the processed CSV file
    """
    if csv_content is None:
        df = pd.read_csv(input_path)
    else:
        df = pd.read_csv(StringIO(csv_content))

    # Determine the source PDF filename
    if "File" not in df.columns:
        df["File"] = input_path.with_suffix(".pdf").name

    if "Transaction Date" in df.columns:
        # clean_date_column(df, "Transaction Date")
        df["Date"] = df["Transaction Date"].apply(iso8601_date)
    else:
        # clean_date_column(df, "Date")
        df["Date"] = df["Date"].apply(iso8601_date)
    if "Amount" not in df.columns:
        if "Withdrawals" not in df.columns:
            df["Withdrawals"] = 0.0
        if "Deposits" not in df.columns:
            df["Deposits"] = 0.0
        df["Withdrawals"] = df["Withdrawals"].astype(float)
        df["Deposits"] = df["Deposits"].astype(float)
        df.fillna(value={"Withdrawals": 0.0, "Deposits": 0.0}, inplace=True)
        df["Description"] = df["Description"].apply(sanitize_description)
        df["Amount"] = (df["Withdrawals"] * -1.0) + df["Deposits"]

    # Filter out rows that include "Opening or Closing Balance" in the description
    df = df[~df["Description"].str.contains("opening balance", na=False, case=False)]
    df = df[~df["Description"].str.contains("Closing balance", na=False, case=False)]

    df = df[["Date", "File", "Description", "Amount"]]
    normalized_df = df
    # return df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL)

    # # Normalize based on the format
    # if "Transaction Date" in df.columns:
    #     # Visa format
    #     normalized_rows = []
    #     for _, row in df.iterrows():
    #         # Use Transaction Date as the main date
    #         date = row["Transaction Date"].replace("/", "-")
    #         description = row["Description"]
    #         amount = float(row["Amount"])

    #         # For Visa: payments are negative in original, charges are positive
    #         # In normalized format: credits should be positive, debits negative
    #         # So we invert the sign
    #         normalized_amount = -amount

    #         normalized_rows.append(
    #             {"Date": date, "File": source_filename, "Description": description, "Amount": normalized_amount}
    #         )

    #     normalized_df = pd.DataFrame(normalized_rows)

    # elif "Withdrawals" in df.columns or "Deposits" in df.columns:
    #     # Chequing/Savings format
    #     normalized_rows = []
    #     for _, row in df.iterrows():
    #         date = row["Date"].replace("/", "-")
    #         description = row["Description"]

    #         # Determine amount: deposits are positive, withdrawals are negative
    #         withdrawal = row.get("Withdrawals", "")
    #         Deposits = row.get("Deposits", "")

    #         if Deposits and str(Deposits).strip():
    #             amount = float(str(Deposits).replace(",", ""))
    #         elif withdrawal and str(withdrawal).strip():
    #             amount = -float(str(withdrawal).replace(",", ""))
    #         else:
    #             continue  # Skip rows with no amount

    #         normalized_rows.append(
    #             {"Date": date, "File": source_filename, "Description": description, "Amount": amount}
    #         )

    #     normalized_df = pd.DataFrame(normalized_rows)

    # else:
    #     raise ValueError(f"Unknown CSV format in {input_path}")

    return normalized_df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL)


def process_pdf_to_normalized_csv(pdf_path: Path, output_path: Path = None) -> Path:
    """
    Extract PDF to CSV and then normalize it in one step.

    Args:
        pdf_path: Path to the PDF file
        output_path: Optional output path for the normalized CSV file

    Returns:
        Path to the normalized CSV file
    """

    # First extract to CSV
    extracted_csv = extract_to_csv(pdf_path)

    return normalize_csv(pdf_path, extracted_csv)
