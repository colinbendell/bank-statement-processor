"""Command-line interface for rbc-pdf-to-csv."""

import csv
from pathlib import Path

import click
import pandas as pd

from . import __version__
from .account_metadata import extract_statement_metadata
from .classifier import Classifier
from .extractors import extract_to_csv
from .processors import normalize_csv


@click.group()
@click.version_option(version=__version__)
def cli():
    """RBC PDF to CSV converter and statement processor."""
    pass


@cli.command(name="convert")
@click.argument("files", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option(
    "-C",
    "--categories",
    type=click.Path(exists=True, path_type=Path),
    help="Use the categories training file to categorize the CSV file",
)
@click.option(
    "--output",
    "-o",
    type=str,
    help="Output CSV file path (default: same as input with .csv extension)",
)
@click.option("--artifacts", is_flag=True, help="Save the artifacts of the process")
@click.option("-y", "--overwrite", is_flag=True, help="Overwrite existing CSV files")
@click.option("--dry-run", is_flag=True, help="Dry run the process and don't write any files")
@click.option(
    "--use-llm",
    is_flag=True,
    help="Use LLM to infer categories for uncategorized transactions (requires ANTHROPIC_API_KEY env var)",
)
def convert(
    files: Path,
    output: Path | None,
    categories: Path | None,
    artifacts: bool,
    overwrite: bool,
    dry_run: bool,
    use_llm: bool,
):
    """Convert PDF statements to normalized CSV format."""
    # check if the pdf_path is a directory
    working_files = {file_path for file_path in files if not file_path.is_dir()}
    for dir_path in (file_path for file_path in files if file_path.is_dir()):
        csv_files = set(dir_path.glob("**/*.extracted.csv"))
        working_files.update(csv_files)

        # Only add PDFs that don't have a corresponding extracted.csv file
        pdf_files = dir_path.glob("**/*.pdf")
        working_files.update(f for f in pdf_files if f.with_suffix(".extracted.csv") not in csv_files)
    if len(working_files) > 1 and output is not None and output != "-" and not output.startswith("/dev/null"):
        output = None

    if categories:
        classifier = Classifier(categories)

    include_header = True
    for file in sorted(working_files):
        output_path = (
            Path(str(file).replace(".extracted.csv", ".csv")).with_suffix(".csv")
            if output is None and output != "-"
            else output
        )
        if output_path != "-" and Path(output_path).exists() and not overwrite:
            click.echo(f"☑️ SKIPPED: {output_path}")
            continue

        # check if we need to convert the file to csv first
        if str(file).endswith(".extracted.csv"):
            output_df = pd.read_csv(file)
        else:
            output_df = extract_to_csv(file)
            if artifacts:
                with open(output_path.with_suffix(".extracted.csv"), "w") as f:
                    output_df.to_csv(f, index=False, quoting=csv.QUOTE_MINIMAL)
        if output_df is None:
            click.echo(f"❌ {file} - No transactions found")
            continue

        output_df = normalize_csv(output_df)

        if artifacts:
            with open(output_path.with_suffix(".processed.csv"), "w") as f:
                output_df.to_csv(f, index=False, quoting=csv.QUOTE_MINIMAL)

        if classifier:
            output_df = classifier.categorize_transactions(output_df, use_llm=use_llm)
            if artifacts:
                with open(output_path.with_suffix(".categorized.csv"), "w") as f:
                    output_df.to_csv(f, index=False, quoting=csv.QUOTE_MINIMAL)

        if not dry_run and output_path != "-":
            with open(output_path, "w") as f:
                output_df.to_csv(f, index=False, quoting=csv.QUOTE_MINIMAL)
            click.echo(f"✅ {output_path}")
        if output_path == "-":
            click.echo(f"✅ {file}", err=True)
            print(output_df.to_csv(index=False, quoting=csv.QUOTE_MINIMAL, header=include_header))
            include_header = False


@cli.command(name="accounts")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def accounts(path: Path):
    """Extract account metadata from PDF statements.

    Analyzes PDF bank statements to extract account numbers, account types
    (personal/business), and account classifications (visa/chequing/savings).

    PATH can be a single PDF file or a directory containing PDFs.
    If a directory is provided, all PDFs will be processed recursively.
    """
    # Collect PDF files
    if path.is_file():
        pdf_files = [path]
    else:
        pdf_files = sorted(path.rglob("*.pdf"))

    if not pdf_files:
        click.echo(f"No PDF files found in {path}", err=True)
        return

    click.echo(f"Processing {len(pdf_files)} PDF files...")

    # Extract account information
    results = extract_statement_metadata(pdf_files)

    for result in results:
        filestem = Path(result["file"]).stem
        click.echo(f"🔍 {filestem} - {result['account_type']}/{result['account_class']}/{result['account_number']}")


@cli.command(name="main")
@click.pass_context
def main_compat(ctx):
    """Legacy main command (deprecated - use 'convert' instead)."""
    click.echo("Warning: 'main' command is deprecated. Use 'convert' instead.", err=True)
    ctx.invoke(convert)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
