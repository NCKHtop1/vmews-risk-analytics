import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const issues = [];

async function verify(viewport, label) {
  const page = await browser.newPage({ viewport });
  page.on("pageerror", error => issues.push(`${label}: pageerror ${error.message}`));
  page.on("response", response => {
    if (response.status() !== 404) return;
    const url = new URL(response.url());
    if (url.hostname === "127.0.0.1" && url.pathname === "/api/solution-ai") return;
    issues.push(`${label}: 404 ${response.url()}`);
  });
  page.on("console", message => {
    if (message.type() !== "error") return;
    if (message.text().includes("Failed to load resource")) return;
    issues.push(`${label}: console ${message.text()}`);
  });
  await page.goto("http://127.0.0.1:8765/forecast-final.html?symbol=FPT", { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForSelector("#signalDeck .signalCard", { timeout: 120000 });
  const cards = await page.locator("#signalDeck .signalCard").count();
  assert.ok(cards >= 1 && cards <= 10, `${label}: cards=${cards}`);
  assert.match(await page.locator("#leaders .commandIndex").innerText(), /HOSE/);
  assert.doesNotMatch(await page.locator("#snapshotDate").innerText(), /ĐANG TẢI/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok(overflow <= 2, `${label}: horizontal overflow ${overflow}px`);
  assert.ok(await page.locator("#solutionAiGeminiWeb").count());
  await page.locator("#solutionAiNav").click();
  await page.waitForTimeout(350);
  assert.equal(await page.locator("#solutionAiPanel").isVisible(), true);
  assert.match(await page.locator("#solutionAiGeminiWeb").innerText(), /Tiếp tục trên Gemini Web/);
  await page.locator("#solutionAiInput").fill("Kiểm tra chuyển phiên đầy đủ sang Gemini");
  const handoff = await page.evaluate(() => {
    const contextPromise = window.__SOLUTION_AI_BUILD_CONTEXT__();
    return contextPromise.then(context => ({
      payload: window.__SOLUTION_AI_GEMINI_HANDOFF_PAYLOAD__("", context),
      prompt: window.__SOLUTION_AI_BUILD_GEMINI_HANDOFF__("", context),
    }));
  });
  assert.equal(handoff.payload.handoff.version, "VMEWS-GEMINI-HANDOFF-23.0");
  assert.equal(handoff.payload.forecast.symbol, "FPT");
  assert.ok(Object.keys(handoff.payload.forecast.horizons).length >= 1);
  assert.ok(Array.isArray(handoff.payload.forecast.topHOSECandidates));
  assert.match(handoff.payload.userIntent.currentQuestion, /Kiểm tra chuyển phiên/);
  assert.match(handoff.prompt, /ranking HOSE/);
  assert.match(handoff.prompt, /validation/);
  if (label === "desktop" && cards > 1) {
    const before = await page.locator("#carouselPosition").innerText();
    await page.waitForTimeout(3400);
    const after = await page.locator("#carouselPosition").innerText();
    assert.notEqual(after, before, "carousel should rotate close to 3 seconds");
  }
  await page.close();
}

await verify({ width: 1440, height: 1000 }, "desktop");
await verify({ width: 390, height: 844 }, "mobile");
await browser.close();
assert.deepEqual(issues, []);
console.log("V23 Gemini handoff + V22 browser E2E PASS");
