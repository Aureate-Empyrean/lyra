// Two real browser tabs, unchanged P1 host SDK, and real disposable Lyra SQLite state.
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const readline = require("node:readline");
const playwright = require(
  process.env.PLAYWRIGHT_PATH ||
    path.resolve(__dirname, "../../../mnemosyne/node_modules/playwright"),
);
const root = path.resolve(__dirname, "../..");
let child, browser, base, ids;
const errors = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(predicate) {
  const end = Date.now() + 6000;
  while (!(await predicate())) {
    assert.ok(Date.now() < end, "state reached before timeout");
    await sleep(30);
  }
}
const scenario = (name, run) => test(name, { timeout: 30000 }, run);
before(async () => {
  child = spawn(
    process.env.PYTHON || path.join(root, ".venv/Scripts/python.exe"),
    [path.join(__dirname, "search_harness.py")],
    { cwd: root, windowsHide: true, stdio: ["pipe", "pipe", "pipe"] },
  );
  base = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error("harness timeout")), 15000);
    child.once("error", reject);
    child.stderr.on("data", (data) => process.stderr.write(data));
    readline.createInterface({ input: child.stdout }).once("line", (line) => {
      clearTimeout(timer);
      resolve(JSON.parse(line).url);
    });
  });
  browser = await playwright[process.env.BROWSER || "chromium"].launch({
    headless: true,
  });
  const response = await fetch(base + "/__fixture/ids");
  ids = await response.json();
});
after(async () => {
  await browser?.close();
  if (child) {
    const done = new Promise((resolve) => child.once("exit", resolve));
    child.stdin.end("\n");
    await Promise.race([done, sleep(7000)]);
    if (child.exitCode === null) child.kill();
  }
});
async function pair(kind = "movie") {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    reducedMotion: "reduce",
  });
  await context.route("**/*", (route) =>
    new URL(route.request().url()).origin === base
      ? route.continue()
      : route.abort(),
  );
  const pages = await Promise.all([context.newPage(), context.newPage()]);
  for (const page of pages) {
    page.setDefaultTimeout(6000);
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      base + "/?nav=1&route=" + encodeURIComponent(`/${kind}/${ids[kind]}`),
    );
    await page.frameLocator("#lyra").locator("[data-notes]").waitFor();
  }
  return {
    context,
    a: pages[0],
    b: pages[1],
    fa: pages[0].frameLocator("#lyra"),
    fb: pages[1].frameLocator("#lyra"),
  };
}
async function call(page, url, method = "GET", body) {
  const frame = await (
    await page.locator("#lyra").elementHandle()
  ).contentFrame();
  return frame.evaluate(([p, m, b]) => rawApi(p, m, b), [url, method, body]);
}
async function note(frame, text) {
  await frame.locator("[data-notes]").fill(text);
  await frame.locator("[data-notes]").press("Tab");
}
const movie = (page) => call(page, `/movies/${ids.movie}`);

scenario(
  "two tabs keep losing notes; reviewed retry conflicts again if a third change intervenes",
  async () => {
    const { context, a, b, fa, fb } = await pair();
    try {
      await note(fa, "Synthetic first winner");
      await until(
        async () => (await movie(a)).library.notes === "Synthetic first winner",
      );
      await note(fb, "Synthetic kept draft");
      await fb
        .getByRole("heading", { name: "Changed elsewhere", exact: true })
        .waitFor();
      assert.equal(
        await fb.locator("[data-notes]").inputValue(),
        "Synthetic kept draft",
      );
      assert.equal((await movie(b)).library.notes, "Synthetic first winner");
      await fb
        .getByRole("button", { name: "Review latest", exact: true })
        .click();
      await until(async () =>
        (await fb.locator("[data-latest]").innerText()).includes(
          "Synthetic first winner",
        ),
      );
      fs.mkdirSync(path.join(root, "artifacts"), { recursive: true });
      await b.screenshot({
        path: path.join(root, "artifacts/wp02b-conflict-desktop.png"),
        animations: "disabled",
        fullPage: true,
      });
      await b.setViewportSize({ width: 390, height: 844 });
      await b.screenshot({
        path: path.join(root, "artifacts/wp02b-conflict-phone.png"),
        animations: "disabled",
        fullPage: true,
      });
      await b.setViewportSize({ width: 1440, height: 960 });
      await note(fa, "Synthetic intervening winner");
      await until(
        async () =>
          (await movie(a)).library.notes === "Synthetic intervening winner",
      );
      await fb
        .getByRole("button", {
          name: "Apply my change after review",
          exact: true,
        })
        .click();
      await until(
        async () =>
          !(await fb
            .getByRole("button", {
              name: "Apply my change after review",
              exact: true,
            })
            .isEnabled()),
      );
      assert.equal(
        (await movie(b)).library.notes,
        "Synthetic intervening winner",
      );
      await fb
        .getByRole("button", { name: "Review latest", exact: true })
        .click();
      await until(async () =>
        (await fb.locator("[data-latest]").innerText()).includes(
          "Synthetic intervening winner",
        ),
      );
      await fb
        .getByRole("button", {
          name: "Apply my change after review",
          exact: true,
        })
        .click();
      await until(
        async () => (await movie(b)).library.notes === "Synthetic kept draft",
      );
      await until(
        async () => (await fb.locator("#personal-conflicts").count()) === 0,
      );
    } finally {
      await context.close();
    }
  },
);

scenario(
  "stale note draft keeps its original token through Back, Forward and browser refresh",
  async () => {
    const { context, a, b, fa, fb } = await pair();
    try {
      const old = await fb
        .locator("[data-notes]")
        .getAttribute("data-revision");
      await note(fa, "Synthetic saved elsewhere");
      await until(
        async () =>
          (await movie(a)).library.notes === "Synthetic saved elsewhere",
      );
      await fb.locator("[data-notes]").fill("Synthetic navigation draft");
      await fb.locator("nav [data-nav=movies]").click();
      await fb.locator("[data-filter]").first().waitFor();
      await b.goBack();
      await fb.locator("[data-notes]").waitFor();
      assert.equal(
        await fb.locator("[data-notes]").inputValue(),
        "Synthetic navigation draft",
      );
      assert.equal(
        await fb.locator("[data-notes]").getAttribute("data-revision"),
        old,
      );
      await b.goForward();
      await fb.locator("[data-filter]").first().waitFor();
      await b.goBack();
      await fb.locator("[data-notes]").waitFor();
      await b.reload();
      await fb.locator("[data-notes]").waitFor();
      assert.equal(
        await fb.locator("[data-notes]").inputValue(),
        "Synthetic navigation draft",
      );
      assert.equal(
        await fb.locator("[data-notes]").getAttribute("data-revision"),
        old,
      );
      await fb
        .getByRole("heading", { name: "Changed elsewhere", exact: true })
        .waitFor();
      assert.equal((await movie(b)).library.notes, "Synthetic saved elsewhere");
    } finally {
      await context.close();
    }
  },
);

scenario(
  "watchlist conflict and unsaved rating survive refresh without silently applying",
  async () => {
    const { context, a, b, fa, fb } = await pair();
    try {
      const current = (await movie(a)).library.status;
      const next = current === "planned" ? "watched" : "planned";
      await fa.locator("#status").selectOption(next);
      await until(async () => (await movie(a)).library.status === next);
      await fb.locator('[data-act=rate][data-value="7"]').click();
      await fb
        .getByRole("heading", { name: "Changed elsewhere", exact: true })
        .waitFor();
      assert.notEqual((await movie(b)).library.rating, 7);
      await b.reload();
      await fb
        .getByRole("heading", { name: "Changed elsewhere", exact: true })
        .waitFor();
      assert.match(await fb.locator("[data-pending]").innerText(), /7/);
      assert.notEqual((await movie(b)).library.rating, 7);
    } finally {
      await context.close();
    }
  },
);

scenario(
  "two tabs cannot silently overwrite series episode progress",
  async () => {
    const { context, a, b, fa, fb } = await pair("series");
    try {
      await fa.locator("[data-act=toggle-episode]").first().check();
      await until(
        async () =>
          (await call(a, `/series/${ids.series}`)).progress.watched === 1,
      );
      await fb.locator("[data-act=toggle-episode]").nth(1).check();
      await fb
        .getByRole("heading", { name: "Changed elsewhere", exact: true })
        .waitFor();
      assert.equal(
        (await call(b, `/series/${ids.series}`)).progress.watched,
        1,
      );
      assert.equal(
        await fb.locator("[data-act=toggle-episode]").nth(1).isChecked(),
        true,
      );
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  },
);

scenario(
  "a delayed successful save never drops text typed while it was in flight",
  async () => {
    const { context, a, fa } = await pair();
    try {
      let held = false;
      await a.route("**/lyra/api/library/movie/*", async (route) => {
        if (
          route.request().method() === "PUT" &&
          route.request().postDataJSON()?.notes === "Synthetic delayed save"
        ) {
          const response = await route.fetch();
          held = true;
          await sleep(500);
          await route.fulfill({ response });
        } else await route.continue();
      });
      await note(fa, "Synthetic delayed save");
      await until(() => held);
      await fa.locator("[data-notes]").fill("Synthetic newer typing");
      await fa.locator("[data-notes]").press("Tab");
      await until(
        async () => (await movie(a)).library.notes === "Synthetic newer typing",
      );
      assert.equal(
        await fa.locator("[data-notes]").inputValue(),
        "Synthetic newer typing",
      );
      assert.equal(await fa.locator("#personal-conflicts").count(), 0);
    } finally {
      await context.close();
    }
  },
);

scenario(
  "typing during a reviewed retry keeps the newer pending draft",
  async () => {
    const { context, a, b, fa, fb } = await pair();
    try {
      await note(fa, "Synthetic winner before retry");
      await until(
        async () =>
          (await movie(a)).library.notes === "Synthetic winner before retry",
      );
      await note(fb, "Synthetic reviewed submission");
      await fb
        .getByRole("button", { name: "Review latest", exact: true })
        .click();
      await until(
        async () =>
          await fb
            .getByRole("button", {
              name: "Apply my change after review",
              exact: true,
            })
            .isEnabled(),
      );
      let held = false;
      await b.route("**/lyra/api/library/movie/*", async (route) => {
        if (route.request().method() === "PUT") {
          const response = await route.fetch();
          held = true;
          await sleep(500);
          await route.fulfill({ response });
        } else await route.continue();
      });
      await fb
        .getByRole("button", {
          name: "Apply my change after review",
          exact: true,
        })
        .click();
      await until(() => held);
      await fb.locator("[data-notes]").fill("Synthetic edit during retry");
      await sleep(700);
      assert.equal(
        (await movie(b)).library.notes,
        "Synthetic reviewed submission",
      );
      assert.equal(
        await fb.locator("[data-notes]").inputValue(),
        "Synthetic edit during retry",
      );
      assert.match(
        await fb.locator("[data-pending]").innerText(),
        /Synthetic edit during retry/,
      );
      assert.equal(
        await fb
          .getByRole("button", {
            name: "Apply my change after review",
            exact: true,
          })
          .isEnabled(),
        false,
      );
    } finally {
      await context.close();
    }
  },
);

scenario(
  "library-wide settings conflict can be reviewed and retried inside the existing modal",
  async () => {
    const { context, a, b, fa, fb } = await pair("series");
    try {
      await fa.locator("nav [data-act=settings]").click();
      await fb.locator("nav [data-act=settings]").click();
      await fa.locator("#language").selectOption("sk-SK");
      await until(
        async () => (await call(a, "/state")).settings.language === "sk-SK",
      );
      await fb.locator("#language").selectOption("de-DE");
      await fb.locator("#dialog #personal-conflicts").waitFor();
      assert.equal((await call(b, "/state")).settings.language, "sk-SK");
      await fb
        .getByRole("button", { name: "Review latest", exact: true })
        .click();
      await until(async () =>
        (await fb.locator("[data-latest]").innerText()).includes("sk-SK"),
      );
      await fb
        .getByRole("button", {
          name: "Apply my change after review",
          exact: true,
        })
        .click();
      await until(
        async () => (await call(b, "/state")).settings.language === "de-DE",
      );
    } finally {
      await context.close();
    }
  },
);

scenario(
  "an open episode menu retains its original token across background refresh",
  async () => {
    const { context, a, b, fa, fb } = await pair("series");
    try {
      await fb.locator("[data-act=episode-menu]").nth(1).click();
      await fb
        .getByRole("menuitem", { name: "Watched up to here", exact: true })
        .waitFor();
      await fa.locator("[data-act=toggle-episode]").first().uncheck();
      await until(
        async () =>
          (await call(a, `/series/${ids.series}`)).progress.watched === 0,
      );
      const frame = await (
        await b.locator("#lyra").elementHandle()
      ).contentFrame();
      await frame.evaluate(() => refreshTitle());
      await fb
        .getByRole("menuitem", { name: "Watched up to here", exact: true })
        .click();
      await fb
        .getByRole("heading", { name: "Changed elsewhere", exact: true })
        .waitFor();
      assert.equal(
        (await call(b, `/series/${ids.series}`)).progress.watched,
        0,
      );
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  },
);

scenario(
  "concurrent removal leaves the losing draft recoverable and cannot resurrect the record",
  async () => {
    const { context, a, b, fa, fb } = await pair();
    try {
      await fa.locator("[data-act=title-menu]").click();
      await fa
        .getByRole("menuitem", { name: "Remove from library", exact: true })
        .click();
      await fa
        .locator("#dialog")
        .getByRole("button", { name: "Remove", exact: true })
        .click();
      await until(async () => (await movie(a)).library === null);
      await note(fb, "Synthetic kept after deletion");
      await fb
        .getByRole("button", { name: "Review latest", exact: true })
        .click();
      await until(async () =>
        (await fb.locator("[data-error]").innerText()).includes("removed"),
      );
      assert.equal(
        await fb
          .getByRole("button", {
            name: "Apply my change after review",
            exact: true,
          })
          .isEnabled(),
        false,
      );
      assert.equal((await movie(b)).library, null);
      assert.equal(
        await fb.locator("[data-notes]").inputValue(),
        "Synthetic kept after deletion",
      );
      assert.deepEqual(errors, []);
    } finally {
      await context.close();
    }
  },
);
