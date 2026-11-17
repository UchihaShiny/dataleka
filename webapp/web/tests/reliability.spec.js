import { test, expect } from "@playwright/test";
test("test backend is explicit isolated demo", async ({ request }) => {
  const meta = await (await request.get("/api/meta")).json();
  expect(meta.mode).toBe("demo");
});
test("explorer links preserve filters, ordering and pages through reload and history", async ({
  page,
}) => {
  await page.goto(
    "/#products?preset=14&q=Heron&line=Long+Sleeve&sort=units&dir=asc",
  );
  const explorer = page.locator(".explorer");
  await expect(explorer.getByLabel("Tìm kiếm")).toHaveValue("Heron");
  await expect(explorer.getByLabel("Dòng sản phẩm")).toHaveValue("Long Sleeve");
  await expect(
    explorer.getByRole("combobox", { name: /^Sắp xếp/ }),
  ).toHaveValue("units");
  await expect(
    explorer.getByRole("button", { name: /Tăng dần/ }),
  ).toBeVisible();
  await page.reload();
  await expect(explorer.locator("tbody tr")).toHaveCount(5);
  await explorer.getByRole("button", { name: "Xóa bộ lọc" }).click();
  await expect(explorer.locator("tbody tr")).toHaveCount(10);
  await explorer.getByRole("button", { name: "Tiếp", exact: true }).click();
  await expect(explorer.locator(".pagination")).toContainText("Trang 2/3");
  await page.reload();
  await expect(explorer.locator(".pagination")).toContainText("Trang 2/3");
  await page.getByRole("button", { name: "28 ngày", exact: true }).click();
  await expect(page).toHaveURL(/preset=28/);
  await page.goBack();
  await expect(page).toHaveURL(/preset=14/);
  await expect(explorer.locator(".pagination")).toContainText("Trang 2/3");
  await explorer.getByLabel("Tìm kiếm").fill("no-match");
  await expect(explorer.locator(".empty")).toBeVisible();
});
test("late preview cannot authorize an edited spec; cancelling dirty edits is deliberate", async ({
  page,
}) => {
  await page.goto("/#reports");
  await page.getByRole("button", { name: "Tạo biểu đồ mẫu" }).click();
  const editor = page.locator(".report-editor");
  await page.route("**/api/reports/preview", async (route) => {
    await new Promise((r) => setTimeout(r, 600));
    await route.continue();
  });
  await editor.getByRole("button", { name: "Xem trước", exact: true }).click();
  await editor.getByLabel("Tiêu đề").fill("Changed while preview pending");
  await page.waitForTimeout(700);
  await expect(
    editor.getByRole("button", { name: "Lưu biểu đồ", exact: true }),
  ).toHaveCount(0);
  await editor.getByRole("button", { name: "Xem trước", exact: true }).click();
  await expect(
    editor.getByRole("button", { name: "Lưu biểu đồ", exact: true }),
  ).toBeVisible();
  page.once("dialog", (d) => d.dismiss());
  await editor.getByRole("button", { name: "Hủy", exact: true }).click();
  await expect(editor).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await editor.getByRole("button", { name: "Hủy", exact: true }).click();
  await expect(editor).toHaveCount(0);
});
test("Ask can stop a partial stream, retry after outage and keep state across theme changes", async ({
  page,
}) => {
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'data: {"t":"text","s":"Partial answer"}\n\n',
    }),
  );
  await page.goto("/#ask");
  await page.getByLabel("Câu hỏi cho Claude").fill("Test outage");
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Kết nối dừng trước khi hoàn tất",
  );
  await page.unroute("**/api/chat");
  await page
    .getByRole("button", { name: "Gửi lại câu hỏi", exact: true })
    .click();
  await expect(page.locator(".preview .recharts-wrapper")).toBeVisible();
  await page.getByRole("button", { name: "Nền tối", exact: false }).click();
  await expect(page.locator(".msg.claude").last()).toContainText(
    "không gọi Claude",
  );
  // Delayed response makes cancellation observable; no Claude/cloud calls are used.
  await page.route("**/api/chat", async (route) => {
    await new Promise((r) => setTimeout(r, 1000));
    await route
      .fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: 'data: {"t":"done","text":"late"}\n\n',
      })
      .catch(() => {});
  });
  await page.getByLabel("Câu hỏi cho Claude").fill("Cancel this question");
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await page.getByRole("button", { name: "Dừng trả lời", exact: true }).click();
  await expect(page.getByRole("alert").last()).toContainText("Đã dừng trả lời");
  await page.reload();
  await expect(page.getByRole("alert").last()).toContainText("Đã dừng trả lời");
  await expect(
    page.getByRole("button", { name: "Gửi lại câu hỏi" }),
  ).toHaveCount(2);
});
test("snapshot waits for every chart preview and preview outage can be retried", async ({
  page,
}) => {
  await page.route("**/api/reports/preview", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: '{"detail":"Preview unavailable"}',
    }),
  );
  await page.goto("/#ask");
  await page.getByLabel("Câu hỏi cho Claude").fill("Preview error");
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Preview unavailable");
  await page.getByRole("button", { name: /Lưu bài phân tích/ }).click();
  await expect(
    page.getByRole("button", { name: "Lưu bản chụp", exact: true }),
  ).toBeDisabled();
  await page.unroute("**/api/reports/preview");
  await page
    .getByRole("button", { name: "Thử lại biểu đồ", exact: true })
    .click();
  await expect(page.locator(".preview .recharts-wrapper")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Lưu bản chụp", exact: true }),
  ).toBeEnabled();
});

test("interrupted chart save recovers without claiming it failed or succeeded", async ({
  page,
  request,
}) => {
  const spec = await (await request.get("/api/demo/spec")).json();
  await page.addInitScript(
    (spec) =>
      sessionStorage.setItem(
        "datae-chat-demo",
        JSON.stringify({
          session: null,
          msgs: [
            { role: "user", text: "Interrupted save" },
            {
              role: "claude",
              text: "Demo snapshot",
              done: true,
              reports: [spec],
              previews: {
                0: {
                  spec,
                  data: {
                    columns: ["date", "rev", "spend"],
                    rows: [{ date: "2026-11-15", rev: 10, spend: 5 }],
                    truncated: false,
                  },
                  saving: true,
                },
              },
            },
          ],
        }),
      ),
    spec,
  );
  await page.goto("/#ask");
  await expect(
    page.getByRole("button", {
      name: "Lưu biểu đồ (tự cập nhật)",
      exact: true,
    }),
  ).toBeEnabled();
  await expect(page.getByRole("alert")).toContainText(
    "kiểm tra trước khi lưu lại",
  );
});

test('mobile composer does not cover the error or retry control',async({page})=>{
 await page.setViewportSize({width:390,height:844})
 await page.addInitScript(()=>localStorage.setItem('datae-theme','dark'))
 await page.route('**/api/chat',route=>route.fulfill({status:200,contentType:'text/event-stream',body:'data: {"t":"text","s":"Phản hồi mô phỏng bị ngắt để kiểm tra phục hồi."}\n\n'}))
 await page.goto('/#ask')
 await page.getByLabel('Câu hỏi cho Claude').fill('Kiểm tra kết nối demo')
 await page.getByRole('button',{name:'Gửi',exact:true}).click()
 const retry=page.getByRole('button',{name:'Gửi lại câu hỏi',exact:true})
 await expect(retry).toBeVisible()
 const retryBox=await retry.boundingBox(),formBox=await page.locator('form.ask').boundingBox()
 expect(formBox.y).toBeGreaterThanOrEqual(retryBox.y+retryBox.height)
 await page.screenshot({path:'test-results/screens/ask-recovery-mobile-dark.png',fullPage:true})
 await page.unroute('**/api/chat')
 await retry.click()
 await expect(page.locator('.preview .recharts-wrapper')).toBeVisible()
})
