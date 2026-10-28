import { chromium } from '@playwright/test';

// Entirely synthetic: no external URL, production cookie, screenshot or trace.
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setContent('<!doctype html><h1>MRJAM_SYNTHETIC_BROWSER</h1>');
  if ((await page.locator('h1').textContent()) !== 'MRJAM_SYNTHETIC_BROWSER') {
    throw new Error('synthetic assertion failed');
  }
  await browser.close();
  console.log('{"status":"ok","check":"synthetic_browser"}');
} catch {
  await browser?.close().catch(() => {});
  console.log('{"status":"error","code":"BROWSER_UNAVAILABLE"}');
  process.exitCode = 1;
}

