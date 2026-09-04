"""002 — Append-only submission_receipts (reject UPDATE/DELETE)."""

SQL = """
CREATE TRIGGER IF NOT EXISTS submission_receipts_no_update
BEFORE UPDATE ON submission_receipts
BEGIN
  SELECT RAISE(ABORT, 'SUBMISSION_RECEIPT_IMMUTABLE');
END;

CREATE TRIGGER IF NOT EXISTS submission_receipts_no_delete
BEFORE DELETE ON submission_receipts
BEGIN
  SELECT RAISE(ABORT, 'SUBMISSION_RECEIPT_IMMUTABLE');
END;
"""
