import os
import subprocess
import sys
import unittest


class PostgresFlowScriptTests(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("RUN_POSTGRES_FLOW") == "1",
        "set RUN_POSTGRES_FLOW=1 and point DATABASE_URL at a disposable test database",
    )
    def test_end_to_end_postgres_flow_script(self):
        script = os.path.join(os.path.dirname(__file__), "run_postgres_flow.py")
        result = subprocess.run([sys.executable, script], check=False)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
