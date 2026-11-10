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
  await page.screenshot({
    path: "test-results/parent-diff.png",
    fullPage: true,
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
  await page.getByLabel("Worker filter").selectOption("worker-0");
  await page.screenshot({
    path: "test-results/worker-timeline.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "analytics", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Search analytics" }),
  ).toBeVisible();
  await expect(page.locator(".recharts-line-curve").first()).toBeVisible();
  await page.screenshot({ path: "test-results/analytics.png", fullPage: true });
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

test("browse fixture experiment and navigate to replay", async ({ page }) => {
  await page.route("**/api/experiments", (route) =>
    route.fulfill({
      json: {
        data: [
          {
            experiment_id: "experiment-fixture",
            summary: { stage: "validation" },
          },
        ],
        warnings: [],
      },
    }),
  );
  await page.route("**/api/experiments/experiment-fixture", (route) =>
    route.fulfill({
      json: {
        data: {
          summary: {
            fixture: true,
            completed_trials: 1,
            expected_trials: 1,
            metrics: {
              baseline: {
                solved: 1,
                trials: 1,
                solve_rate: 1,
                solve_ci95: [0.2, 1],
                cost_per_solved: null,
                recovery_rate: null,
                recovery_opportunities: 0,
              },
            },
          },
          trials: [
            {
              problem_id: "fixture",
              variant: "baseline",
              run_id: "synthetic-dashboard",
              grade: { passed: true, status: "PASS" },
            },
          ],
        },
        warnings: [],
      },
    }),
  );
  await page.goto("/experiments");
  await page
    .getByLabel("Experiment", { exact: true })
    .selectOption("experiment-fixture");
  await expect(
    page.getByText("Fixture data — not model performance", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Unknown / undefined" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/experiment.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Open search tree" }).click();
  await expect(
    page.getByRole("heading", {
      name: "SYNTHETIC · 500 candidate performance fixture",
    }),
  ).toBeVisible();
});
