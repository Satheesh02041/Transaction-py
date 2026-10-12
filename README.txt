1. REQUIREMENTS AND DEPENDENCIES

- Minimum Python Version: Python 3.7 or higher.
- Third-Party Packages: None.
- Standard Library: Python's built-in standard library is sufficient (using argparse, csv, json, re, sys, unicodedata, collections, datetime, decimal, and pathlib). No external packages or installation commands are required.


2. HOW TO RUN

1. Ensure that solution.py and input.csv are located in the same directory.
2. Open Command Prompt or PowerShell in that directory.
3. Run the script using the following command:
   python solution.py
   (On Windows systems where the Python launcher is used, you can also run: py solution.py)
4. Optional command-line arguments supported by the code:
   --input <path>            Path to input CSV file (default: input.csv)
   --cleaned <path>          Path to cleaned CSV output (default: cleaned.csv)
   --report <path>           Path to report JSON output (default: report.json)
   --day-first               Parse DD/MM/YYYY before MM/DD/YYYY (default: True)
   --reject-ambiguous        Reject ambiguous dates where day and month are both 12 or less (default: False)
5. Upon successful execution, the program creates two files in the working directory: cleaned.csv and report.json.


3. HOW THE PROGRAM WORKS

- Ingestion: Reads transaction records from input.csv using csv.DictReader with utf-8-sig encoding to handle byte order marks.
- Field Standardization:
  * Customer Names: Strips accents via unicodedata, rearranges "LAST, First" into "First Last", removes stray punctuation, collapses repeated whitespace, converts to title case, and generates a lowercase matching key. Blank names are flagged as MISSING_NAME.
  * Dates: Converts valid dates to ISO format (YYYY-MM-DD) via datetime.strptime. Unambiguous year-first dates and day-first formats (DD/MM/YYYY) are parsed; impossible dates (such as 2026-15-08) and unparseable values are flagged as INVALID_DATE with an empty clean date.
  * Amounts: Parses currency values into Decimal objects with two decimal places, removing currency symbols, handling accounting parentheses for negative values, and resolving regional comma and dot separators. Zero amounts are flagged as ZERO_AMOUNT, and negative amounts are flagged as NEGATIVE_AMOUNT unless the status is refund.
  * Statuses: Normalizes status values to lowercase and maps synonyms to canonical business statuses (paid, pending, cancelled, refund). Unrecognized statuses are mapped to unknown and flagged as UNKNOWN_STATUS.
- Duplicate Detection: Keeps the first occurrence of each transaction ID and flags later occurrences as DUPLICATE_ID. Identifies near-duplicate transactions matching customer key, clean date, clean amount, clean status, and order ID under differing transaction IDs, flagging later rows with NEAR_DUPLICATE.
- Validation: Every record is retained and assigned an is_valid status ("true" or "false") along with semicolon-separated issue codes.
- Outputs:
  * cleaned.csv preserves all original input rows in order, adding normalized fields, row validity flags, and explanations of any data quality issues.
  * report.json contains reconciled record counts, duplicate tallies, issue frequency counts, and total revenue, refund, and net revenue figures.
