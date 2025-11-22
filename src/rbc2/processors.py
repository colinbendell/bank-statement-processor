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
    # if d is a Timestamp, format it as YYYY-MM-DD
    if isinstance(d, pd.Timestamp):
        return d.strftime("%Y-%m-%d")
    if re.match(r"^\d{4}/\d{2}/\d{2}$", d):
        return datetime.strptime(d, "%Y/%m/%d").strftime("%Y-%m-%d")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    if re.match(r"^\d{2}-\d{2}-\d{4}$", d):
        return datetime.strptime(d, "%d-%m-%Y").strftime("%Y-%m-%d")
    try:
        return datetime.strptime(d, "%B %d, %Y").strftime("%Y-%m-%d")
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


def normalize_csv(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize a CSV file to a standard format.

    The normalized format has columns: Date, File, Description, Amount, Category
    - Date format is YYYY-MM-DD
    - File is the source PDF filename
    - Description is the transaction description
    - Amount is positive for deposits/credits, negative for withdrawals/debits

    Args:
        input_path: Path to the input CSV file
        csv_content: Optional CSV content string (if None, reads from input_path)

    Returns:
        Normalized CSV content as string
    """
    df = transactions_df

    if df.empty:
        return df

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
    # normalized_csv = df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL)

    return df
