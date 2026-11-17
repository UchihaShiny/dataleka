import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("WCAG A/AA automated checks across every page in both themes", async ({
  page,
}) => {
  const failures = [];
  for (const theme of ["light", "dark"]) {
    await page.goto("/");
    await page.evaluate((t) => localStorage.setItem("datae-theme", t), theme);
    await page.reload();
    for (const id of [
      "overview",
      "ads",
      "products",
      "customers",
      "alerts",
      "trust",
      "ask",
      "reports",
    ]) {
      await page.goto("/#" + id);
      await expect(
        page.locator(`.nav button[aria-current=page]`),
      ).toContainText(
        {
          overview: "Tổng quan",
          ads: "Quảng cáo",
          products: "Sản phẩm",
          customers: "Khách",
          alerts: "Cảnh báo",
          trust: "Chỉ số",
          ask: "Hỏi Claude",
          reports: "Báo cáo",
        }[id],
      );
      await expect(page.locator(".loading")).toHaveCount(0);
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      if (result.violations.length)
        failures.push({
          page: `${theme}/${id}`,
          violations: result.violations.map((v) => ({
            id: v.id,
            nodes: v.nodes.map((n) => ({
              html: n.html,
              summary: n.failureSummary,
            })),
          })),
        });
    }
  }
  expect(failures).toEqual([]);
});
