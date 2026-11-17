"""Credential-free product regressions. Run as a separate process: python tests/test_product_app.py."""

import os

os.environ["DATAE_MODE"] = "demo"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
import json
from decimal import Decimal, ROUND_HALF_UP
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from dashboard import kpi, queries as q
from pipelines.dates import last_complete_day
from webapp.api import main, demo, pages, reports


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.a = patch.object(reports, "STORE", Path(self.temp.name) / "reports.json")
        self.a.start()
        self.b = patch.object(
            reports, "ANALYSES", Path(self.temp.name) / "analyses.json"
        )
        self.b.start()
        self.client = TestClient(main.app, raise_server_exceptions=False)
        main._state["cache"].clear()

    def tearDown(self):
        self.a.stop()
        self.b.stop()
        self.temp.cleanup()

    def test_real_contracts_without_network(self):
        with (
            patch.object(
                q, "readonly_client", side_effect=AssertionError("credential access")
            ),
            patch(
                "requests.sessions.Session.request",
                side_effect=AssertionError("external call"),
            ),
        ):
            for endpoint in [
                "meta",
                "definitions",
                "health",
                *[f"page/{p}?preset=28" for p in pages.PAGES],
            ]:
                r = self.client.get("/api/" + endpoint)
                self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(
                self.client.post("/api/chat", json={"message": "Demo"}).status_code, 200
            )

    def test_independent_arithmetic_and_coherent_aggregates(self):
        data = self.client.get("/api/page/overview").json()["data"]
        rows = data["days"]
        t = data["totals"]
        rev = sum(r["rev"] for r in rows)
        spend = sum(r["spend"] for r in rows)
        orders = sum(r["orders"] for r in rows)
        self.assertAlmostEqual(t["mer"], rev / spend)
        self.assertAlmostEqual(t["aov"], rev / orders)
        self.assertAlmostEqual(
            t["cm_est"],
            float(
                sum(
                    (
                        Decimal(str(r["rev"])) * Decimal("0.682")
                        - Decimal(str(r["spend"]))
                    ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
                    for r in rows
                )
            ),
        )
        ads = self.client.get("/api/page/ads").json()["data"]
        prod = self.client.get("/api/page/products").json()["data"]
        self.assertAlmostEqual(sum(r["spend"] for r in ads["campaigns"]), spend)
        self.assertAlmostEqual(
            sum(r["rev"] for r in ads["types"]),
            sum(r["revenue"] for r in prod["explore"]),
        )

    def test_refund_fixture_periods_are_additive(self):
        end = demo.END
        from datetime import timedelta

        current = demo.refunds(end - timedelta(days=6), end)
        previous = demo.refunds(end - timedelta(days=13), end - timedelta(days=7))
        combined = demo.refunds(end - timedelta(days=13), end)
        self.assertEqual(combined, (current[0] + previous[0], current[1] + previous[1]))

    def test_missing_days_equal_length_do_not_compare(self):
        ctx = pages.context(demo.fetch, demo.END, "7")

        def gaps(sql, p):
            df = demo.fetch(sql, p)
            if sql == q.DAILY_KPI:
                return df.iloc[[i for i in range(len(df)) if i not in (1, 8)]]
            return df

        d = pages.overview(gaps, ctx)
        self.assertFalse(d["comparable"])
        self.assertIsNone(d["totals"]["rev"])
        self.assertIsNone(d["days"][1]["rev"])
        self.assertTrue(all(v is None for v in d["change"].values()))

    def test_null_not_zero(self):
        self.assertIsNone(kpi.totals([])["rev"])
        rows = [dict(rev=0, orders=0, spend=0, cm_est=0)]
        self.assertEqual(kpi.totals(rows)["rev"], 0)
        self.assertIsNone(kpi.totals(rows)["mer"])
        rows[0]["spend"] = float("nan")
        self.assertIsNone(kpi.totals(rows)["spend"])
        flag = kpi.roas_flags([dict(product_line="X", rev=10, spend=None)], 1.47)[0]
        self.assertIsNone(flag["roas"])
        self.assertEqual(flag["status"], "chưa đủ dữ liệu")

    def test_phoenix_midnight(self):
        self.assertEqual(
            last_complete_day(datetime(2026, 11, 16, 6, 59, tzinfo=timezone.utc)),
            date(2026, 11, 14),
        )
        self.assertEqual(
            last_complete_day(datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)),
            date(2026, 11, 15),
        )

    def test_forecast_validation_and_staleness(self):
        ctx = pages.context(demo.fetch, demo.END, "7")
        for bad in ("bounds", "days"):

            def broken(sql, p):
                df = demo.fetch(sql, p)
                if sql == q.FORECAST:
                    if bad == "days":
                        return df.iloc[:13]
                    df.loc[0, "lo"] = 100000
                return df

            self.assertIsNone(pages.alerts(broken, ctx)["forecast"])
        ctx["end_max"] = demo.END.replace(day=16)
        self.assertTrue(pages.alerts(demo.fetch, ctx)["forecast"]["stale"])

    def test_save_preview_edit_reopen_snapshot_delete(self):
        c = self.client
        self.assertEqual(
            c.post("/api/reports/preview", json={"spec": demo.SPEC}).status_code, 200
        )
        live = c.post("/api/reports", json={"spec": demo.SPEC}).json()
        rid = live["id"]
        spec = {**demo.SPEC, "title": "Changed"}
        self.assertEqual(
            c.put("/api/reports/" + rid, json={"spec": spec}).json()["title"], "Changed"
        )
        snapshot = c.post(
            "/api/analyses",
            json={"title": "Snapshot", "text": "Fixed text", "specs": [demo.SPEC]},
        ).json()
        before = c.get("/api/analyses/" + snapshot["id"]).json()
        with patch.object(
            demo,
            "run_report",
            return_value={"columns": [], "rows": [], "truncated": False},
        ):
            self.assertEqual(c.get("/api/analyses/" + snapshot["id"]).json(), before)
        self.assertEqual(c.get("/api/reports/" + rid + "/data").status_code, 200)
        self.assertEqual(c.delete("/api/reports/" + rid).status_code, 200)
        self.assertEqual(c.delete("/api/reports/" + rid).status_code, 404)
        self.assertEqual(c.delete("/api/analyses/" + snapshot["id"]).status_code, 200)

    def test_malformed_outage_recovery_preserves_content(self):
        c = self.client
        for payload in [
            {"message": ""},
            {"message": "a" * 4001},
            {"message": "ok", "session": "bad"},
        ]:
            self.assertEqual(c.post("/api/chat", json=payload).status_code, 422)
        self.assertEqual(c.get("/api/not-real").status_code, 404)
        self.assertEqual(
            c.post(
                "/api/reports", json={"spec": dict(demo.SPEC, sql="delete from x")}
            ).status_code,
            400,
        )
        self.assertEqual(
            c.post(
                "/api/reports", json={"spec": dict(demo.SPEC, sql="select 1")}
            ).status_code,
            400,
        )
        with patch.object(main, "fetch", side_effect=RuntimeError("outage")):
            self.assertEqual(c.get("/api/page/overview").status_code, 503)
        self.assertEqual(c.get("/api/page/overview").status_code, 200)
        reports.STORE.write_text("{broken")
        self.assertEqual(
            c.post("/api/reports", json={"spec": demo.SPEC}).status_code, 400
        )
        self.assertEqual(reports.STORE.read_text(), "{broken")

    def test_no_pipeline_fallback(self):
        from pipelines import bq

        with (
            patch.dict(os.environ, {"MCP_CREDENTIALS": ""}),
            patch.object(bq, "client", side_effect=AssertionError("pipeline")),
        ):
            with self.assertRaises(RuntimeError):
                bq.mcp_client()

    def test_new_queries_match_local_model_schemas(self):
        import yaml
        import sqlglot
        from sqlglot import exp

        root = Path(__file__).resolve().parents[1]
        models = yaml.safe_load(
            (root / "transform/models/marts/_marts.yml").read_text()
        )["models"]
        columns = {m["name"]: {c["name"] for c in m.get("columns", [])} for m in models}
        required = {
            "fct_lines": {
                "product_title",
                "product_line",
                "line_revenue",
                "current_quantity",
                "quantity",
                "order_date",
            },
            "mart_cohort_clv": {
                "cohort_month",
                "month_offset",
                "cohort_size",
                "avg_cum_rev",
                "median_cum_rev",
                "ci_low",
                "ci_high",
                "multiple_of_first",
                "is_complete",
            },
            "load_status": {"complete_through", "method", "built_at"},
        }
        for table, fields in required.items():
            self.assertTrue(fields <= columns[table], table)
        for sql in [
            q.PRODUCTS,
            q.CLV,
            q.HEALTH,
            q.LOAD_EVIDENCE,
            q.TYPE_ROAS,
            q.CAMPAIGNS,
            q.EMAIL_WEEKLY,
        ]:
            tree = sqlglot.parse_one(sql.format(p="demo"), read="bigquery")
            self.assertIsInstance(tree, exp.Query)
            for table in tree.find_all(exp.Table):
                if table.catalog:
                    self.assertEqual((table.catalog, table.db), ("demo", "gold"))

    def test_health_unknown_is_unknown(self):
        h = self.client.get("/api/health").json()
        self.assertTrue(all(r["verified_ingestion"] is None for r in h["sources"]))
        defs = self.client.get("/api/definitions").json()
        self.assertEqual(len(defs["metrics"]), 29)


if __name__ == "__main__":
    unittest.main(verbosity=2)
