import sqlite3
import unittest

from migrate_sqlite_to_postgres import ID_TABLES, TABLES, _sqlite_rows


class SQLiteMigrationTests(unittest.TestCase):
    def test_import_list_covers_visual_data_tables(self):
        self.assertIn("brand_logos", TABLES)
        self.assertIn("visual_reviews", TABLES)
        self.assertIn("brand_logos", ID_TABLES)
        self.assertNotIn("visual_reviews", ID_TABLES)

    def test_rows_with_composite_primary_key_are_ordered_without_id(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE visual_reviews (submission_id INTEGER, version INTEGER, "
                "status TEXT, PRIMARY KEY (submission_id, version))")
            conn.executemany(
                "INSERT INTO visual_reviews VALUES (?, ?, ?)",
                [(2, 1, "partial"), (1, 2, "complete"), (1, 1, "failed")])

            columns, rows = _sqlite_rows(
                conn, "visual_reviews", {"submission_id", "version", "status"})

            self.assertEqual(columns, ["submission_id", "version", "status"])
            self.assertEqual(
                [(row["submission_id"], row["version"]) for row in rows],
                [(1, 1), (1, 2), (2, 1)])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
