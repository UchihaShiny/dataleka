import { test, expect } from "@playwright/test";
const pages = [
  "overview",
  "ads",
  "products",
  "customers",
  "alerts",
  "trust",
  "ask",
  "reports",
];
test("all pages, four viewports, themes, persistence, no page overflow", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    for (const theme of ["light", "dark"]) {
      await page.goto("/");
      await page.evaluate((t) => localStorage.setItem("datae-theme", t), theme);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      for (const id of pages) {
        await page.goto("/#" + id);
        await expect(
          page.locator(`.nav button[aria-current=page]`),
        ).toHaveCount(1);
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
        await expect(page.locator(".loading")).toHaveCount(0, {
          timeout: 15000,
        });
        await expect(page.locator("main")).not.toContainText(
          "Trang này gặp lỗi",
        );
        await expect(page.locator("main")).not.toContainText(
          "Không tải được số",
        );
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        if (viewport.width === 1440 || viewport.width === 390)
          await page.screenshot({
            path: `test-results/screens/${id}-${viewport.width}-${theme}.png`,
            fullPage: true,
          });
      }
      await page.reload();
      expect(await page.locator("html").getAttribute("data-theme")).toBe(theme);
    }
  }
  expect(errors).toEqual([]);
});
test("filters, detail, aggregate export, keyboard and empty results", async ({
  page,
}) => {
  await page.goto("/#products?preset=14");
  const explorer = page.locator(".explorer");
  await expect(
    explorer.getByRole("button", { name: "↓ Xuất CSV tổng hợp" }),
  ).toBeEnabled();
  await explorer.getByLabel("Tìm kiếm").fill("Heron");
  await expect(explorer.locator("tbody tr")).toHaveCount(5);
  await explorer.getByLabel("Dòng sản phẩm").selectOption("Long Sleeve");
  await explorer
    .getByRole("combobox", { name: /^Sắp xếp/ })
    .selectOption("units");
  await explorer.locator(".text-link").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const download = page.waitForEvent("download");
  await explorer.getByRole("button", { name: "↓ Xuất CSV tổng hợp" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("deerlys-aggregate.csv");
  const stream = await file.createReadStream();
  let csv = "";
  for await (const chunk of stream) csv += chunk;
  expect(csv).toContain("Heron");
  expect(csv).not.toContain("customer_key");
  await explorer.getByLabel("Tìm kiếm").fill("no-such-design");
  await expect(
    explorer.getByText("Không có kết quả. Thử từ khóa hoặc bộ lọc khác."),
  ).toBeVisible();
  await expect(
    explorer.getByRole("button", { name: "↓ Xuất CSV tổng hợp" }),
  ).toBeDisabled();
});
test("stale responses never replace active page; outage and recovery", async ({
  page,
}) => {
  await page.route("**/api/page/overview*", async (route) => {
    await new Promise((r) => setTimeout(r, 500));
    await route.continue();
  });
  await page.goto("/#overview");
  await page.evaluate(() => (location.hash = "ads?preset=28"));
  await expect(page.locator(".explore-head h3")).toHaveText(
    "Campaign theo kỳ chọn",
  );
  await expect(page.locator("h1")).toContainText("Quảng cáo");
  await page.route("**/api/page/products*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Mất kết nối thử nghiệm" }),
    }),
  );
  await page.evaluate(() => (location.hash = "products"));
  await expect(page.getByRole("alert")).toContainText("Mất kết nối thử nghiệm");
  await page.unroute("**/api/page/products*");
  await page.getByRole("button", { name: "Thử lại" }).click();
  await expect(page.locator(".explorer")).toBeVisible();
});
test("create, preview, save, edit, reopen, deliberate delete live chart", async ({
  page,
}) => {
  await page.goto("/#reports");
  await page.getByRole("button", { name: "Tạo biểu đồ mẫu" }).click();
  const editor = page.locator(".report-editor");
  await editor.getByLabel("Tiêu đề").fill("QA live chart");
  await editor.getByRole("button", { name: "Xem trước" }).click();
  await expect(editor.locator(".recharts-wrapper")).toBeVisible();
  await editor
    .getByRole("button", { name: "Lưu biểu đồ", exact: true })
    .click();
  let report = page
    .locator("section.report")
    .filter({ hasText: "QA live chart" });
  await expect(report).toBeVisible();
  await report.getByRole("button", { name: "Sửa", exact: true }).click();
  await report.getByLabel("Tiêu đề").fill("QA edited chart");
  await report.getByRole("button", { name: "Xem trước" }).click();
  await report
    .getByRole("button", { name: "Lưu biểu đồ", exact: true })
    .click();
  await expect(page.locator(".report-editor")).toHaveCount(0);
  await page.reload();
  report = page
    .locator("section.report")
    .filter({ hasText: "QA edited chart" });
  await expect(report).toBeVisible();
  page.once("dialog", (d) => d.dismiss());
  await report.getByRole("button", { name: "Xoá", exact: true }).click();
  await expect(report).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await report.getByRole("button", { name: "Xoá", exact: true }).click();
  await expect(report).toHaveCount(0);
});
test("Ask demo analysis, preview, snapshot save and reopen", async ({
  page,
}) => {
  await page.goto("/#ask");
  await page.getByLabel("Câu hỏi cho Claude").fill("Phân tích dữ liệu demo");
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await expect(page.locator(".preview .recharts-wrapper")).toBeVisible();
  await expect(page.locator(".msg.claude")).toContainText("không gọi Claude");
  await page.getByRole("button", { name: /Lưu bài phân tích/ }).click();
  await page.getByLabel("Tên bản chụp").fill("QA fixed snapshot");
  await page.getByRole("button", { name: "Lưu bản chụp", exact: true }).click();
  await expect(page.locator(".row.ok")).toContainText("Đã lưu");
  await page.goto("/#reports");
  let snapshot = page
    .locator("section.analysis")
    .filter({ hasText: "QA fixed snapshot" });
  await snapshot.locator(".an-title").click();
  await expect(snapshot.locator(".an-body")).toContainText("dữ liệu giả lập");
  await expect(snapshot.locator(".recharts-wrapper")).toBeVisible();
  await page.reload();
  snapshot = page
    .locator("section.analysis")
    .filter({ hasText: "QA fixed snapshot" });
  await expect(snapshot).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await snapshot.getByRole("button", { name: "Xoá", exact: true }).click();
  await expect(snapshot).toHaveCount(0);
});
test("mobile navigation and reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Mở menu", exact: true }).click();
  await expect(page.locator("aside")).toBeVisible();
  await page.getByRole("button", { name: "Sản phẩm", exact: true }).click();
  await expect(page.locator(".explorer")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mở menu", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: "Mở menu", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Mở menu", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  expect(
    await page
      .locator(".side")
      .evaluate((e) => getComputedStyle(e).transitionDuration),
  ).toBe("0s");
});
