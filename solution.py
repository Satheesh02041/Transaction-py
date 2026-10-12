import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
DAY_FIRST = True
REJECT_AMBIGUOUS = False
STATUS_SYNONYMS = {
    "paid": "paid",
    "completed": "paid",
    "success": "paid",
    "settled": "paid",
    "pending": "pending",
    "processing": "pending",
    "in progress": "pending",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "void": "cancelled",
    "refund": "refund",
    "refunded": "refund",
    "reversed": "refund",
}
def clean_name(raw_name):
    if not raw_name or not raw_name.strip():
        return "", "", ["MISSING_NAME"]
    name = unicodedata.normalize("NFKD", raw_name)
    name = "".join(c for c in name if not unicodedata.combining(c)).strip()
    if not name:
        return "", "", ["MISSING_NAME"]
    if "," in name:
        parts = name.split(",", 1)
        name = f"{parts[1].strip()} {parts[0].strip()}"
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return "", "", ["MISSING_NAME"]
    name_clean = name.title()
    customer_key = name_clean.lower()
    return name_clean, customer_key, []
def parse_date(raw_date, day_first=DAY_FIRST, reject_ambiguous=REJECT_AMBIGUOUS):
    if not raw_date or not raw_date.strip():
        return "", ["MISSING_DATE"]
    s = raw_date.strip()
    match_dmy = re.match(r"^(\d{1,2})([/-])(\d{1,2})[/-](\d{4})$", s)
    if match_dmy and reject_ambiguous:
        part1 = int(match_dmy.group(1))
        part2 = int(match_dmy.group(3))
        if part1 <= 12 and part2 <= 12:
            return "", ["AMBIGUOUS_DATE"]
    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", s):
        formats = ["%Y-%m-%d", "%Y/%m/%d"]
    elif day_first:
        formats = ["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y"]
    else:
        formats = ["%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d"), []
        except ValueError:
            continue
    return "", ["INVALID_DATE"]
def normalize_status(raw_status):
    if not raw_status or not raw_status.strip():
        return "", ["MISSING_STATUS"]
    cleaned = raw_status.strip().lower()
    if cleaned in STATUS_SYNONYMS:
        return STATUS_SYNONYMS[cleaned], []
    return "unknown", ["UNKNOWN_STATUS"]
def parse_amount(raw_amount, status_clean=""):
    if not raw_amount or not raw_amount.strip().strip("\"'"):
        return "", ["MISSING_AMOUNT"]
    s = raw_amount.strip().strip("\"'")
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    s = re.sub(r"[\$€£¥₹\s]", "", s)
    if not s:
        return "", ["INVALID_AMOUNT"]
    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    if not re.match(r"^[0-9.,]+$", s):
        return "", ["INVALID_AMOUNT"]
    if "." in s and "," in s:
        if s.rfind(".") > s.rfind(","):
            num_str = s.replace(",", "")
        else:
            num_str = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            num_str = parts[0] + "." + parts[1]
        elif all(len(p) == 3 for p in parts[1:]):
            num_str = "".join(parts)
        else:
            return "", ["INVALID_AMOUNT"]
    elif s.count(".") > 1:
        parts = s.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            num_str = "".join(parts)
        else:
            return "", ["INVALID_AMOUNT"]
    else:
        num_str = s
    try:
        val = Decimal(num_str)
    except InvalidOperation:
        return "", ["INVALID_AMOUNT"]
    if is_negative:
        val = -val
    issues = []
    if val == Decimal("0"):
        issues.append("ZERO_AMOUNT")
    elif val < Decimal("0") and status_clean != "refund":
        issues.append("NEGATIVE_AMOUNT")
    return f"{val:.2f}", issues
def process_rows(raw_rows, day_first=DAY_FIRST, reject_ambiguous=REJECT_AMBIGUOUS):
    processed = []
    for r in raw_rows:
        raw_customer = r.get("customer_name", "")
        raw_amount = r.get("amount", "")
        raw_date = r.get("transaction_date", "")
        raw_status = r.get("status", "")
        name_clean, customer_key, name_issues = clean_name(raw_customer)
        date_clean, date_issues = parse_date(
            raw_date, day_first=day_first, reject_ambiguous=reject_ambiguous
        )
        status_clean, status_issues = normalize_status(raw_status)
        amount_clean, amount_issues = parse_amount(raw_amount, status_clean=status_clean)
        processed.append(
            {
                "transaction_id": r.get("transaction_id", "").strip(),
                "customer_name_original": raw_customer,
                "customer_name_clean": name_clean,
                "customer_key": customer_key,
                "amount_original": raw_amount,
                "amount_clean": amount_clean,
                "transaction_date_original": raw_date,
                "date_clean": date_clean,
                "status_original": raw_status,
                "status_clean": status_clean,
                "order_id": r.get("order_id", "").strip(),
                "issues": name_issues + date_issues + status_issues + amount_issues,
            }
        )
    return processed
def find_duplicates(rows):
    seen_ids = set()
    seen_transactions = {}
    for row in rows:
        tx_id = row["transaction_id"]
        if tx_id:
            if tx_id in seen_ids:
                row["issues"].append("DUPLICATE_ID")
            else:
                seen_ids.add(tx_id)
        can_compare = bool(
            row["date_clean"]
            and row["amount_clean"]
            and row["customer_key"]
            and row["status_clean"]
        )
        if can_compare:
            key = (
                row["customer_key"],
                row["date_clean"],
                row["amount_clean"],
                row["status_clean"],
                row["order_id"],
            )
            if key in seen_transactions:
                first_tx_id = seen_transactions[key]
                if first_tx_id != tx_id:
                    row["issues"].append(f"NEAR_DUPLICATE(of {first_tx_id})")
            else:
                seen_transactions[key] = tx_id

        row["is_valid"] = "true" if len(row["issues"]) == 0 else "false"
    return rows
def build_report(rows):
    input_rows = len(rows)
    valid_rows = sum(1 for r in rows if r["is_valid"] == "true")
    invalid_rows = sum(1 for r in rows if r["is_valid"] == "false")
    dup_id_rows = sum(1 for r in rows if "DUPLICATE_ID" in r["issues"])
    near_dup_rows = sum(1 for r in rows if any(i.startswith("NEAR_DUPLICATE") for i in r["issues"]))
    total_dup_rows = sum(
        1
        for r in rows
        if "DUPLICATE_ID" in r["issues"]
        or any(i.startswith("NEAR_DUPLICATE") for i in r["issues"])
    )
    issue_counter = Counter()
    for r in rows:
        for issue in r["issues"]:
            base_code = issue.split("(")[0]
            issue_counter[base_code] += 1
    total_revenue = sum(
        Decimal(r["amount_clean"])
        for r in rows
        if r["is_valid"] == "true" and r["status_clean"] == "paid"
    )
    total_refunds = sum(
        abs(Decimal(r["amount_clean"]))
        for r in rows
        if r["is_valid"] == "true" and r["status_clean"] == "refund"
    )
    net_revenue = total_revenue - total_refunds
    return {
        "input_rows": input_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "duplicates": {
            "duplicate_transaction_id_rows": dup_id_rows,
            "near_duplicate_rows": near_dup_rows,
            "total_duplicate_rows": total_dup_rows,
        },
        "invalid_reasons": dict(issue_counter),
        "total_revenue": float(round(total_revenue, 2)),
        "total_refunds": float(round(total_refunds, 2)),
        "net_revenue": float(round(net_revenue, 2)),
        "note": (
            "Total issue counts in invalid_reasons may exceed invalid_rows "
            "because a single row can have multiple issues."
        ),
    }
def write_cleaned_csv(rows, output_path):
    fieldnames = [
        "transaction_id",
        "customer_name_original",
        "customer_name_clean",
        "customer_key",
        "amount_original",
        "amount_clean",
        "transaction_date_original",
        "date_clean",
        "status_original",
        "status_clean",
        "order_id",
        "is_valid",
        "issues",
    ]
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "transaction_id": r["transaction_id"],
                    "customer_name_original": r["customer_name_original"],
                    "customer_name_clean": r["customer_name_clean"],
                    "customer_key": r["customer_key"],
                    "amount_original": r["amount_original"],
                    "amount_clean": r["amount_clean"],
                    "transaction_date_original": r["transaction_date_original"],
                    "date_clean": r["date_clean"],
                    "status_original": r["status_original"],
                    "status_clean": r["status_clean"],
                    "order_id": r["order_id"],
                    "is_valid": r["is_valid"],
                    "issues": ";".join(r["issues"]),
                }
            )
def write_report_json(report, output_path):
    with open(output_path, mode="w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
def reconcile_and_assert(rows, report, cleaned_path):
    assert report["valid_rows"] + report["invalid_rows"] == report["input_rows"]
    with open(cleaned_path, mode="r", encoding="utf-8-sig", newline="") as f:
        saved_rows = list(csv.DictReader(f))
    assert len(saved_rows) == report["input_rows"]
    saved_valid = sum(1 for r in saved_rows if r["is_valid"].lower() == "true")
    assert saved_valid == report["valid_rows"]
    saved_revenue = sum(
        Decimal(r["amount_clean"])
        for r in saved_rows
        if r["is_valid"].lower() == "true" and r["status_clean"] == "paid"
    )
    assert round(saved_revenue, 2) == round(Decimal(str(report["total_revenue"])), 2)
    for r in rows:
        if "DUPLICATE_ID" in r["issues"] or any(i.startswith("NEAR_DUPLICATE") for i in r["issues"]):
            assert r["is_valid"] == "false"
def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("input.csv"))
    parser.add_argument("--cleaned", type=Path, default=Path("cleaned.csv"))
    parser.add_argument("--report", type=Path, default=Path("report.json"))
    parser.add_argument("--day-first", action="store_true", default=DAY_FIRST)
    parser.add_argument("--reject-ambiguous", action="store_true", default=REJECT_AMBIGUOUS)
    args = parser.parse_args(argv)
    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        return 1
    raw_rows = []
    with open(args.input, mode="r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            raw_rows.append(row)
    processed_rows = process_rows(
        raw_rows,
        day_first=args.day_first,
        reject_ambiguous=args.reject_ambiguous,
    )
    final_rows = find_duplicates(processed_rows)
    report = build_report(final_rows)
    write_cleaned_csv(final_rows, args.cleaned)
    write_report_json(report, args.report)
    reconcile_and_assert(final_rows, report, args.cleaned)
    print(f"Total rows: {report['input_rows']}")
    print(f"Valid: {report['valid_rows']}, Invalid: {report['invalid_rows']}")
    print(f"Duplicates: {report['duplicates']['total_duplicate_rows']}")
    print(f"Total revenue: ${report['total_revenue']:,.2f}")
    print(f"Total refunds: ${report['total_refunds']:,.2f}")
    print(f"Net revenue: ${report['net_revenue']:,.2f}")
    return 0
if __name__ == "__main__":
    sys.exit(main())