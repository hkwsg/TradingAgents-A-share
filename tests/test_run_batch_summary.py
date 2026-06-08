import json
import unittest
from unittest.mock import patch

import run_batch


def _write_report(root, name, trade_date=None):
    report_dir = root / "reports" / name
    report_dir.mkdir(parents=True)
    if trade_date:
        (report_dir / "原始数据.json").write_text(
            json.dumps({"trade_date": trade_date}, ensure_ascii=False),
            encoding="utf-8",
        )
    return report_dir


class TestRunBatchSummary(unittest.TestCase):
    def test_report_trade_date_prefers_raw_trade_date(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            from pathlib import Path

            tmp_path = Path(tmp)
            report_dir = _write_report(
                tmp_path,
                "600276_2026-06-06",
                trade_date="2026-06-05",
            )

            self.assertEqual(run_batch.report_trade_date(report_dir), "2026-06-05")

    def test_collect_reports_by_trade_date_uses_analysis_date(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _write_report(tmp_path, "600036_2026-06-05", trade_date="2026-06-05")
            _write_report(tmp_path, "601899_2026-06-05", trade_date="2026-06-05")
            _write_report(tmp_path, "600276_2026-06-06", trade_date="2026-06-05")
            _write_report(tmp_path, "600519_2026-06-04", trade_date="2026-06-04")

            with patch.object(run_batch, "PROJ", tmp_path):
                reports = run_batch.collect_reports_by_trade_date(
                    "2026-06-05",
                    ["600036", "601899", "600276"],
                )

        self.assertEqual(
            [ticker for ticker, _report_dir in reports],
            ["600036", "601899", "600276"],
        )
        self.assertEqual(
            [report_dir.name for _ticker, report_dir in reports],
            ["600036_2026-06-05", "601899_2026-06-05", "600276_2026-06-06"],
        )


if __name__ == "__main__":
    unittest.main()
