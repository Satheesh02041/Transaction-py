#!/usr/bin/env python3
"""
Unit and Integration Tests for Challenge 1: Messy Transactions Cleaner.
Complies with all testing requirements for Quadance Technologies Junior Developer Assignment.
"""

import csv
import json
import unittest
from decimal import Decimal
from pathlib import Path

from solution import (
    clean_name,
    parse_date,
    normalize_status,
    parse_amount,
    find_duplicates,
    process_rows,
    build_report,
    reconcile_and_assert,
)


class TestCustomerNames(unittest.TestCase):
    def test_name_trim_and_title_case(self):
        """Trim whitespace and title case messy name strings."""
        clean, key, issues = clean_name(" priya menon ")
        self.assertEqual(clean, "Priya Menon")
        self.assertEqual(key, "priya menon")
        self.assertEqual(issues, [])

    def test_name_all_caps(self):
        """Standardize ALL CAPS names."""
        clean, key, issues = clean_name("SARA THOMAS")
        self.assertEqual(clean, "Sara Thomas")
        self.assertEqual(key, "sara thomas")
        self.assertEqual(issues, [])

    def test_name_last_comma_first(self):
        """Standardize 'LAST, First' notation."""
        clean, key, issues = clean_name("Rao, Anita")
        self.assertEqual(clean, "Anita Rao")
        self.assertEqual(key, "anita rao")
        self.assertEqual(issues, [])

    def test_name_missing_or_blank(self):
        """Flag missing and whitespace-only customer names."""
        clean, key, issues = clean_name("")
        self.assertEqual(clean, "")
        self.assertIn("MISSING_NAME", issues)

        clean2, key2, issues2 = clean_name("   ")
        self.assertEqual(clean2, "")
        self.assertIn("MISSING_NAME", issues2)


class TestTransactionDates(unittest.TestCase):
    def test_date_valid_formats(self):
        """Convert supported valid date formats into YYYY-MM-DD."""
        d1, issues1 = parse_date("2026-09-06")
        self.assertEqual(d1, "2026-09-06")
        self.assertEqual(issues1, [])

        d2, issues2 = parse_date("2026/09/04")
        self.assertEqual(d2, "2026-09-04")
        self.assertEqual(issues2, [])

        d3, issues3 = parse_date("03/09/2026", day_first=True, reject_ambiguous=False)
        self.assertEqual(d3, "2026-09-03")
        self.assertEqual(issues3, [])

        d4, issues4 = parse_date("05-09-2026", day_first=True, reject_ambiguous=False)
        self.assertEqual(d4, "2026-09-05")
        self.assertEqual(issues4, [])

    def test_date_invalid_impossible(self):
        """Reject impossible dates and non-date strings."""
        d1, issues1 = parse_date("2026-15-08")
        self.assertEqual(d1, "")
        self.assertIn("INVALID_DATE", issues1)

        d2, issues2 = parse_date("not a date")
        self.assertEqual(d2, "")
        self.assertIn("INVALID_DATE", issues2)

        d3, issues3 = parse_date("2026-02-30")
        self.assertEqual(d3, "")
        self.assertIn("INVALID_DATE", issues3)

    def test_date_ambiguous_policy(self):
        """Flag ambiguous dates when reject_ambiguous is True."""
        d, issues = parse_date("03/09/2026", day_first=True, reject_ambiguous=True)
        self.assertEqual(d, "")
        self.assertIn("AMBIGUOUS_DATE", issues)

    def test_date_missing(self):
        """Flag missing and empty dates."""
        d, issues = parse_date("")
        self.assertEqual(d, "")
        self.assertIn("MISSING_DATE", issues)


class TestTransactionAmounts(unittest.TestCase):
    def test_amount_thousands_separator(self):
        """Parse standard comma thousands separators e.g. '1,470.00'."""
        amt, issues = parse_amount('"1,470.00"', status_clean="paid")
        self.assertEqual(amt, "1470.00")
        self.assertEqual(issues, [])

    def test_amount_european_formatting(self):
        """Parse European currency notation e.g. '1.234,56 €'."""
        amt, issues = parse_amount("1.234,56 €", status_clean="paid")
        self.assertEqual(amt, "1234.56")
        self.assertEqual(issues, [])

    def test_amount_missing_and_malformed(self):
        """Flag missing, N/A, and malformed amount strings."""
        amt1, issues1 = parse_amount("", status_clean="paid")
        self.assertEqual(amt1, "")
        self.assertIn("MISSING_AMOUNT", issues1)

        amt2, issues2 = parse_amount("N/A", status_clean="paid")
        self.assertEqual(amt2, "")
        self.assertIn("INVALID_AMOUNT", issues2)

        amt3, issues3 = parse_amount("oops", status_clean="paid")
        self.assertEqual(amt3, "")
        self.assertIn("INVALID_AMOUNT", issues3)

    def test_amount_zero(self):
        """Flag zero amount transactions as ZERO_AMOUNT."""
        amt, issues = parse_amount("0", status_clean="paid")
        self.assertEqual(amt, "0.00")
        self.assertIn("ZERO_AMOUNT", issues)

    def test_amount_negative_rules(self):
        """Negative amounts are valid only when status is refund."""
        # Non-refund status (e.g. pending, paid)
        amt_pend, issues_pend = parse_amount("-250", status_clean="pending")
        self.assertEqual(amt_pend, "-250.00")
        self.assertIn("NEGATIVE_AMOUNT", issues_pend)

        amt_paid, issues_paid = parse_amount("-250", status_clean="paid")
        self.assertEqual(amt_paid, "-250.00")
        self.assertIn("NEGATIVE_AMOUNT", issues_paid)

        # Refund status -> Valid
        amt_ref, issues_ref = parse_amount("-250", status_clean="refund")
        self.assertEqual(amt_ref, "-250.00")
        self.assertEqual(issues_ref, [])

        # Accounting parenthesis format
        amt_paren, issues_paren = parse_amount("(20.00)", status_clean="paid")
        self.assertEqual(amt_paren, "-20.00")
        self.assertIn("NEGATIVE_AMOUNT", issues_paren)


class TestTransactionStatuses(unittest.TestCase):
    def test_status_normalization_and_synonyms(self):
        """Normalize known statuses and synonyms."""
        s1, i1 = normalize_status("PAID")
        self.assertEqual(s1, "paid")
        self.assertEqual(i1, [])

        s2, i2 = normalize_status(" completed ")
        self.assertEqual(s2, "paid")
        self.assertEqual(i2, [])

        s3, i3 = normalize_status("canceled")
        self.assertEqual(s3, "cancelled")
        self.assertEqual(i3, [])

        s4, i4 = normalize_status("refunded")
        self.assertEqual(s4, "refund")
        self.assertEqual(i4, [])

        s5, i5 = normalize_status("processing")
        self.assertEqual(s5, "pending")
        self.assertEqual(i5, [])

    def test_status_missing_and_unknown(self):
        """Flag missing or unknown statuses."""
        s_miss, i_miss = normalize_status("")
        self.assertEqual(s_miss, "")
        self.assertIn("MISSING_STATUS", i_miss)

        s_unk, i_unk = normalize_status("weird_status")
        self.assertEqual(s_unk, "unknown")
        self.assertIn("UNKNOWN_STATUS", i_unk)


class TestDuplicateDetection(unittest.TestCase):
    def test_repeated_transaction_id_with_conflicting_details(self):
        """Detect repeated transaction ID reusing ID with different customer details."""
        raw_rows = [
            {
                "transaction_id": "TX0008",
                "customer_name": "Neha Das",
                "amount": "1196",
                "transaction_date": "2026/09/04",
                "status": "pending",
                "order_id": "ORD025",
            },
            {
                "transaction_id": "TX0008",
                "customer_name": "Aarav Shah",
                "amount": "1196",
                "transaction_date": "2026-09-02",
                "status": "paid",
                "order_id": "ORD025",
            },
        ]
        processed = process_rows(raw_rows, day_first=True, reject_ambiguous=False)
        final_rows = find_duplicates(processed)

        self.assertEqual(final_rows[0]["is_valid"], "true")
        self.assertEqual(final_rows[1]["is_valid"], "false")
        self.assertIn("DUPLICATE_ID", final_rows[1]["issues"])

    def test_near_duplicate_vs_different_statuses(self):
        """
        Verify real-world near-duplicate is detected for same payment entered twice,
        while a refund on the same order is preserved as a separate valid transaction.
        """
        raw_rows = [
            {
                "transaction_id": "TX0069",
                "customer_name": "Meera Nair",
                "amount": "1200",
                "transaction_date": "2026-09-03",
                "status": "refund",
                "order_id": "ORD081",
            },
            {
                "transaction_id": "TX0070",
                "customer_name": "Meera Nair",
                "amount": "1200",
                "transaction_date": "2026-09-03",
                "status": "paid",
                "order_id": "ORD081",
            },
            {
                "transaction_id": "TX0071",
                "customer_name": " Meera   Nair ",
                "amount": "1200.00",
                "transaction_date": "03/09/2026",
                "status": "paid",
                "order_id": "ORD081",
            },
        ]
        processed = process_rows(raw_rows, day_first=True, reject_ambiguous=False)
        final_rows = find_duplicates(processed)

        # TX0069 refund is valid, not marked near-duplicate
        self.assertEqual(final_rows[0]["transaction_id"], "TX0069")
        self.assertEqual(final_rows[0]["is_valid"], "true")
        self.assertEqual(final_rows[0]["issues"], [])

        # TX0070 is the original paid transaction
        self.assertEqual(final_rows[1]["transaction_id"], "TX0070")
        self.assertEqual(final_rows[1]["is_valid"], "true")
        self.assertEqual(final_rows[1]["issues"], [])

        # TX0071 is near-duplicate of TX0070
        self.assertEqual(final_rows[2]["transaction_id"], "TX0071")
        self.assertEqual(final_rows[2]["is_valid"], "false")
        self.assertIn("NEAR_DUPLICATE(of TX0070)", final_rows[2]["issues"])


class TestReconciliation(unittest.TestCase):
    def test_full_dataset_reconciliation(self):
        """Verify row counts, valid/invalid partitioning, and financial reconciliation."""
        input_path = Path("input.csv")
        if not input_path.exists():
            self.skipTest("input.csv not found in working directory.")

        raw_rows = []
        with open(input_path, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                raw_rows.append(r)

        processed = process_rows(raw_rows, day_first=True, reject_ambiguous=False)
        final_rows = find_duplicates(processed)
        report = build_report(final_rows)

        # Invariant 1: input_rows == valid_rows + invalid_rows
        self.assertEqual(report["input_rows"], 73)
        self.assertEqual(report["valid_rows"] + report["invalid_rows"], report["input_rows"])
        self.assertEqual(report["valid_rows"], 56)
        self.assertEqual(report["invalid_rows"], 17)

        # Invariant 2: duplicate counts
        self.assertEqual(report["duplicates"]["duplicate_transaction_id_rows"], 2)
        self.assertEqual(report["duplicates"]["near_duplicate_rows"], 1)
        self.assertEqual(report["duplicates"]["total_duplicate_rows"], 3)

        # Invariant 3: financial reconciliation
        self.assertEqual(report["total_revenue"], 85206.00)
        self.assertEqual(report["total_refunds"], 1200.00)
        self.assertEqual(report["net_revenue"], 84006.00)


if __name__ == "__main__":
    unittest.main()
