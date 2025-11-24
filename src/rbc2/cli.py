"""Command-line interface for rbc-pdf-to-csv."""

from pathlib import Path

import click

from . import __version__
from .extractors import extract_to_csv
from .processors import normalize_csv
from .categorizer import add_categories, initialize_category_lookup


@click.group()
@click.version_option(version=__version__)
def main():
    """Convert bank statement PDFs to CSV files."""
    pass


@main.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output CSV file path (default: same as input with .csv extension)",
)
@click.option("-y", "--overwrite", is_flag=True, help="Overwrite existing CSV files")
def extract(pdf_path: Path, output: Path | None, overwrite: bool):
    """Extract transactions from a PDF to CSV format."""
    try:
        # check if the pdf_path is a directory
        files = [pdf_path]
        if pdf_path.is_dir():
            files = list(sorted(pdf_path.glob("*.pdf")))
            output = None
        for file in sorted(files):
            output_path = file.with_suffix(".csv") if output is None else output
            if output_path.exists() and not overwrite:
                click.echo(f"☑️ SKIPPED: {output_path}")
                continue
            csv_content = extract_to_csv(file)
            with open(output_path, "w") as f:
                f.write(csv_content)
            click.echo(f"✅ {output_path}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort() from e


@main.command()
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
@click.option("-C", "--categories", type=click.Path(exists=True, path_type=Path), help="Add categories to the CSV file")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output CSV file path (default: same as input with .processed.csv extension)",
)
@click.option("-y", "--overwrite", is_flag=True, help="Overwrite existing CSV files")
def process(file_path: Path, output: Path | None, categories: Path | None, overwrite: bool):
    """Normalize a CSV file to standard format."""
    # check if the pdf_path is a directory
    files = [file_path]
    if file_path.is_dir():
        pdf_files = list(file_path.glob("*.pdf"))
        files = list(file_path.glob("*.csv"))
        files = [file for file in files if not file.with_suffix(".processed.csv")]
        for pdf_file in pdf_files:
            # check if the file is in the list
            if pdf_file.with_suffix(".csv") not in files:
                files.append(pdf_file)
        # remove .pdf files where we have a .csv file in the array
        files = sorted(files)
        output = None
    for file in sorted(files):
        processed_path = file.with_suffix(".processed.csv") if output is None else output
        if processed_path.exists() and not overwrite:
            click.echo(f"☑️ SKIPPED: {processed_path}")
            continue

        # check if we need to convert the file to csv first
        if file.suffix == ".csv":
            csv_content = open(file).read()
        else:
            csv_content = extract_to_csv(file)

        normalized_csv = normalize_csv(file, csv_content)

        with open(processed_path, "w") as f:
            f.write(normalized_csv)

        if categories:
            initialize_category_lookup(categories)
            categorized_csv = add_categories(normalized_csv)
            categorized_path = file.with_suffix(".categorized.csv")
            with open(categorized_path, "w") as f:
                f.write(categorized_csv)
        click.echo(f"✅ {processed_path}")


if __name__ == "__main__":
    main()
