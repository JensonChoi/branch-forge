import { test, expect } from "@playwright/test";
test("inspect, replay, seek and view worker activity", async ({ page }) => {
  const start = Date.now();
  await page.goto("/runs/synthetic-dashboard");
  await expect(
    page.getByRole("heading", {
      name: "SYNTHETIC · 500 candidate performance fixture",
    }),
  ).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(501);
  console.log(`500-node render: ${Date.now() - start} ms`);
  await page.getByLabel("Select candidate").selectOption("candidate-0");
  await expect(
    page.getByRole("heading", { name: "Visible evaluation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Parent diff", exact: true }).click();
  await expect(page.locator(".monaco-diff-editor")).toBeVisible({
    timeout: 15000,
  });
  await page.getByRole("button", { name: "Parent diff", exact: true }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  const seekStart = Date.now();
  await page.getByRole("button", { name: "End", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(501);
  console.log(`5000-event seek and render: ${Date.now() - seekStart} ms`);
  await page
    .getByRole("button", { name: "Previous event", exact: true })
    .click();
  await page.getByRole("button", { name: "timeline", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Worker activity" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "analytics", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Search analytics" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "tree", exact: true }).click();
  await page
    .getByRole("button", { name: "Final snapshot", exact: true })
    .click();
  await page.screenshot({ path: "test-results/dashboard.png", fullPage: true });
});

test("replay a recorded local run when available", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/runs?limit=500");
  const rows = (await response.json()).data.items;
  let id: string | undefined;
  for (const row of rows) {
    if (row.run_id === "synthetic-dashboard") continue;
    const detail = await request.get(`/api/runs/${row.run_id}`);
    if ((await detail.json()).data.detailed_replay) {
      id = row.run_id;
      break;
    }
  }
  test.skip(
    !id,
    "No recorded v2 run available; synthetic replay is covered separately",
  );
  await page.goto(`/runs/${id}`);
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "End", exact: true }).click();
  await expect(page.locator(".search-node.final")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Final snapshot", exact: true })
    .click();
  await page.getByLabel("Select candidate").selectOption({ index: 2 });
  await expect(page.locator(".monaco-editor").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/recorded-run.png",
    fullPage: true,
  });
});
