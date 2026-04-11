"""
SQLite-based progress tracker for resumable pipeline execution.
Tracks runs, cases, and document generation/upload status.

@Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DB_PATH


class ProgressTracker:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'in_progress',
                total_cases INTEGER DEFAULT 0,
                total_docs INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                internal_id TEXT NOT NULL UNIQUE,
                case_number INTEGER NOT NULL,
                litigation_stage TEXT NOT NULL,
                applicant_name TEXT NOT NULL,
                employer_name TEXT NOT NULL,
                data_generated INTEGER DEFAULT 0,
                pdfs_generated INTEGER DEFAULT 0,
                meruscase_id INTEGER,
                case_created INTEGER DEFAULT 0,
                docs_uploaded INTEGER DEFAULT 0,
                total_docs INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_internal_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                subtype TEXT NOT NULL,
                title TEXT NOT NULL,
                doc_date TEXT NOT NULL,
                output_format TEXT NOT NULL DEFAULT 'pdf',
                pdf_path TEXT,
                pdf_generated INTEGER DEFAULT 0,
                uploaded INTEGER DEFAULT 0,
                meruscase_doc_id INTEGER,
                error_message TEXT,
                FOREIGN KEY (case_internal_id) REFERENCES cases(internal_id),
                UNIQUE(case_internal_id, filename)
            );
        """)
        self.conn.commit()

        # Migrate existing databases that predate the output_format column
        try:
            self.conn.execute(
                "ALTER TABLE documents ADD COLUMN output_format TEXT NOT NULL DEFAULT 'pdf'"
            )
            self.conn.commit()
        except Exception:
            pass  # Column already exists — nothing to do

    # --- Run management ---

    def start_run(self, total_cases: int) -> int:
        cursor = self.conn.execute(
            "INSERT INTO runs (started_at, total_cases) VALUES (?, ?)",
            (datetime.now().isoformat(), total_cases),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_current_run(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE status = 'in_progress' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def complete_run(self, run_id: int) -> None:
        self.conn.execute(
            "UPDATE runs SET completed_at = ?, status = 'completed' WHERE id = ?",
            (datetime.now().isoformat(), run_id),
        )
        self.conn.commit()

    # --- Case management ---

    def register_case(
        self,
        run_id: int,
        internal_id: str,
        case_number: int,
        stage: str,
        applicant_name: str,
        employer_name: str,
        total_docs: int,
    ) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO cases
               (run_id, internal_id, case_number, litigation_stage,
                applicant_name, employer_name, total_docs)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, internal_id, case_number, stage, applicant_name, employer_name, total_docs),
        )
        self.conn.commit()

    def mark_case_data_generated(self, internal_id: str) -> None:
        self.conn.execute(
            "UPDATE cases SET data_generated = 1 WHERE internal_id = ?",
            (internal_id,),
        )
        self.conn.commit()

    def mark_case_pdfs_generated(self, internal_id: str, count: int) -> None:
        self.conn.execute(
            "UPDATE cases SET pdfs_generated = ?, status = 'pdfs_ready' WHERE internal_id = ?",
            (count, internal_id),
        )
        self.conn.commit()

    def mark_case_created(self, internal_id: str, meruscase_id: int) -> None:
        self.conn.execute(
            "UPDATE cases SET case_created = 1, meruscase_id = ?, status = 'case_created' WHERE internal_id = ?",
            (meruscase_id, internal_id),
        )
        self.conn.commit()

    def mark_case_uploaded(self, internal_id: str, docs_uploaded: int) -> None:
        self.conn.execute(
            "UPDATE cases SET docs_uploaded = ?, status = 'completed' WHERE internal_id = ?",
            (docs_uploaded, internal_id),
        )
        self.conn.commit()

    def mark_case_error(self, internal_id: str, error: str) -> None:
        self.conn.execute(
            "UPDATE cases SET status = 'error', error_message = ? WHERE internal_id = ?",
            (error, internal_id),
        )
        self.conn.commit()

    def get_case(self, internal_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM cases WHERE internal_id = ?", (internal_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_cases_by_status(self, status: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM cases WHERE status = ? ORDER BY case_number", (status,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cases_needing_creation(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM cases WHERE case_created = 0 AND pdfs_generated > 0 ORDER BY case_number"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cases_needing_upload(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM cases WHERE case_created = 1 AND status != 'completed' ORDER BY case_number"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_cases(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM cases ORDER BY case_number"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Document management ---

    def register_document(
        self,
        case_internal_id: str,
        filename: str,
        subtype: str,
        title: str,
        doc_date: str,
        output_format: str = "pdf",
    ) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO documents
               (case_internal_id, filename, subtype, title, doc_date, output_format)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (case_internal_id, filename, subtype, title, doc_date, output_format),
        )
        self.conn.commit()

    def mark_pdf_generated(self, case_internal_id: str, filename: str, pdf_path: str) -> None:
        self.conn.execute(
            "UPDATE documents SET pdf_generated = 1, pdf_path = ? WHERE case_internal_id = ? AND filename = ?",
            (pdf_path, case_internal_id, filename),
        )
        self.conn.commit()

    def mark_doc_uploaded(self, case_internal_id: str, filename: str, meruscase_doc_id: int) -> None:
        self.conn.execute(
            "UPDATE documents SET uploaded = 1, meruscase_doc_id = ? WHERE case_internal_id = ? AND filename = ?",
            (meruscase_doc_id, case_internal_id, filename),
        )
        self.conn.commit()

    def mark_doc_error(self, case_internal_id: str, filename: str, error: str) -> None:
        self.conn.execute(
            "UPDATE documents SET error_message = ? WHERE case_internal_id = ? AND filename = ?",
            (error, case_internal_id, filename),
        )
        self.conn.commit()

    def get_ungenerated_docs(self, case_internal_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE case_internal_id = ? AND pdf_generated = 0 ORDER BY doc_date",
            (case_internal_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unuploaded_docs(self, case_internal_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE case_internal_id = ? AND pdf_generated = 1 AND uploaded = 0 ORDER BY doc_date",
            (case_internal_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_docs_for_case(self, case_internal_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE case_internal_id = ? ORDER BY doc_date",
            (case_internal_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Status / reporting ---

    def get_status_summary(self) -> dict:
        run = self.get_current_run()
        if not run:
            # Check for completed runs
            row = self.conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            run = dict(row) if row else None

        if not run:
            return {"has_run": False}

        cases = self.conn.execute("SELECT * FROM cases WHERE run_id = ?", (run["id"],)).fetchall()
        total_cases = len(cases)
        cases_data_generated = sum(1 for c in cases if c["data_generated"])
        cases_pdfs_generated = sum(1 for c in cases if c["pdfs_generated"] > 0)
        cases_created = sum(1 for c in cases if c["case_created"])
        cases_completed = sum(1 for c in cases if c["status"] == "completed")
        cases_errored = sum(1 for c in cases if c["status"] == "error")

        total_docs = self.conn.execute(
            "SELECT COUNT(*) FROM documents d JOIN cases c ON d.case_internal_id = c.internal_id WHERE c.run_id = ?",
            (run["id"],),
        ).fetchone()[0]
        docs_generated = self.conn.execute(
            "SELECT COUNT(*) FROM documents d JOIN cases c ON d.case_internal_id = c.internal_id WHERE c.run_id = ? AND d.pdf_generated = 1",
            (run["id"],),
        ).fetchone()[0]
        docs_uploaded = self.conn.execute(
            "SELECT COUNT(*) FROM documents d JOIN cases c ON d.case_internal_id = c.internal_id WHERE c.run_id = ? AND d.uploaded = 1",
            (run["id"],),
        ).fetchone()[0]

        return {
            "has_run": True,
            "run_id": run["id"],
            "run_status": run["status"],
            "started_at": run["started_at"],
            "completed_at": run["completed_at"],
            "total_cases": total_cases,
            "cases_data_generated": cases_data_generated,
            "cases_pdfs_generated": cases_pdfs_generated,
            "cases_created_in_merus": cases_created,
            "cases_completed": cases_completed,
            "cases_errored": cases_errored,
            "total_docs": total_docs,
            "docs_pdf_generated": docs_generated,
            "docs_uploaded": docs_uploaded,
        }

    def close(self) -> None:
        self.conn.close()
