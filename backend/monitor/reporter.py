"""
============================================================
reporter.py — 报告生成
============================================================
将指标和评估结果汇总为前端可消费的 JSON 格式。
"""

import json
import os
from backend.config import DATA_DIR


class ReportGenerator:
    """评估报告生成器。"""

    def __init__(self):
        self.reports: list[dict] = []
        self.report_dir = os.path.join(DATA_DIR, "evaluations")
        os.makedirs(self.report_dir, exist_ok=True)

    def add_report(self, tick: int, evaluations: list[dict]):
        """添加一份评估报告。"""
        report = {
            "tick": tick,
            "evaluations": evaluations,
            "overall": round(
                sum(e["scores"].get("overall", 5) for e in evaluations) / max(len(evaluations), 1),
                1,
            ),
            "top_performer": max(evaluations, key=lambda e: e["scores"].get("overall", 0))["name"]
            if evaluations else "N/A",
        }
        self.reports.append(report)

        # 保存到文件
        filepath = os.path.join(self.report_dir, f"report_tick_{tick}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def get_latest(self) -> dict | None:
        """获取最近的报告。"""
        return self.reports[-1] if self.reports else None

    def get_all(self) -> list[dict]:
        """获取所有报告。"""
        return self.reports


report_generator = ReportGenerator()
