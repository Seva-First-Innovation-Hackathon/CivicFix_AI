import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';

async function verifyMapLive() {
  console.log('=== CIVICFIX AI: VERIFIED KEYLESS ESRI MAP TELEMETRY AUDIT ===');
  console.log('Launching headless Chrome via puppeteer-core...');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1280,850'],
    defaultViewport: { width: 1280, height: 850 },
  });

  const page = await browser.newPage();

  // Track network requests
  const tileRequests = [];
  const blockedOrForbidden = [];
  const obsoleteCartoRequests = [];
  const unexpectedEndpoints = [];

  page.on('response', (response) => {
    const url = response.url();
    const status = response.status();
    const headers = response.headers();

    if (url.includes('server.arcgisonline.com/ArcGIS/rest/services')) {
      tileRequests.push({
        url,
        status,
        contentType: headers['content-type'],
        contentLength: headers['content-length'],
      });
    }

    if (url.includes('cartocdn.com')) {
      obsoleteCartoRequests.push({ url, status });
    }

    if (
      url.includes('tile.openstreetmap.org') ||
      url.includes('nominatim') ||
      url.includes('api.maptiler.com') ||
      url.includes('maps.googleapis.com')
    ) {
      unexpectedEndpoints.push({ url, status });
    }

    if (status === 401 || status === 403 || status === 404 || status === 429) {
      if (url.includes('arcgisonline.com')) {
        blockedOrForbidden.push({ url, status });
      }
    }
  });

  try {
    // 1. Visit Citizen Login at /login
    console.log('\n[TEST 1] Logging in as Citizen at /login...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('input[type="email"]', { timeout: 8000 });
    await page.type('input[type="email"]', 'citizen.arjun@example.com');
    await page.type('input[type="password"]', 'CitizenPass2026!');
    await page.click('button[type="submit"]');

    await page.waitForFunction(() => window.location.pathname.includes('/citizen'), { timeout: 10000 });
    console.log('✓ Citizen logged in successfully. Current URL:', page.url());

    // 2. Report Issue Map (Picker mode)
    console.log('\n[TEST 2] Verifying Citizen Report Issue Map (mode="picker")...');
    await page.goto(`${BASE_URL}/citizen/report`, { waitUntil: 'domcontentloaded' });

    await page.waitForSelector('input[type="text"]', { timeout: 8000 });
    await page.type('input[type="text"]', 'Major Pothole on Road Near Market');
    await page.type('textarea', 'Deep pothole causing hazards to two-wheelers and pedestrians near the intersection.');

    // Click Continue: Step 1 -> Step 2
    const continueBtns1 = await page.$$('button');
    for (const b of continueBtns1) {
      const text = await (await b.getProperty('innerText')).jsonValue();
      if (text.includes('Continue')) {
        await b.click();
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 1000));

    // Click Continue: Step 2 -> Step 3 (Map)
    const continueBtns2 = await page.$$('button');
    for (const b of continueBtns2) {
      const text = await (await b.getProperty('innerText')).jsonValue();
      if (text.includes('Continue')) {
        await b.click();
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 1500));

    // Check map container
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    console.log('✓ Leaflet container rendered in Step 3');

    // Wait for tiles to settle
    await new Promise((r) => setTimeout(r, 2500));

    // Click on map to place pin
    const mapBox = await page.$('.leaflet-container');
    const box = await mapBox.boundingBox();
    if (box) {
      console.log(`Clicking map at (${box.x + box.width / 2}, ${box.y + box.height / 2})...`);
      await page.mouse.click(box.x + box.width / 2 + 40, box.y + box.height / 2 + 20);
      await new Promise((r) => setTimeout(r, 800));
    }

    await page.screenshot({ path: 'screenshot_citizen_report_map.png' });
    console.log('✓ Captured screenshot_citizen_report_map.png');

    // 3. Citizen Dashboard Map
    console.log('\n[TEST 3] Verifying Citizen Dashboard Map (mode="viewer")...');
    await page.goto(`${BASE_URL}/citizen`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await new Promise((r) => setTimeout(r, 2000));
    await page.screenshot({ path: 'screenshot_citizen_dashboard_map.png' });
    console.log('✓ Captured screenshot_citizen_dashboard_map.png');

    // 4. Municipal Staff Live Issue Map
    console.log('\n[TEST 4] Logging in as Municipal Staff at /staff/login...');
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${BASE_URL}/staff/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('input[type="email"]', { timeout: 8000 });
    await page.type('input[type="email"]', 'officer.sharma@civicfix.gov');
    await page.type('input[type="password"]', 'StaffSecure2026!');
    await page.click('button[type="submit"]');

    await page.waitForFunction(() => window.location.pathname.includes('/admin'), { timeout: 10000 });
    console.log('✓ Staff logged in successfully. Current URL:', page.url());

    console.log('Navigating to /admin/map...');
    await page.goto(`${BASE_URL}/admin/map`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await new Promise((r) => setTimeout(r, 2500));
    await page.screenshot({ path: 'screenshot_staff_live_map.png' });
    console.log('✓ Captured screenshot_staff_live_map.png');

    // 5. Field Crew Tasks Page & Interactive Map
    console.log('\n[TEST 5] Logging in as Field Crew at /staff/login...');
    await page.evaluate(() => localStorage.clear());
    await page.goto(`${BASE_URL}/staff/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('input[type="email"]', { timeout: 8000 });
    await page.type('input[type="email"]', 'crew.patel@civicfix.gov');
    await page.type('input[type="password"]', 'CrewSecure2026!');
    await page.click('button[type="submit"]');

    await page.waitForFunction(() => window.location.pathname.includes('/admin'), { timeout: 10000 });
    console.log('✓ Crew logged in successfully.');

    await page.goto(`${BASE_URL}/admin/crew-tasks`, { waitUntil: 'domcontentloaded' });

    // Click "Field Map (Interactive)" toggle button
    await new Promise((r) => setTimeout(r, 1000));
    const buttonsCrew = await page.$$('button');
    for (const b of buttonsCrew) {
      const text = await (await b.getProperty('innerText')).jsonValue();
      if (text.includes('Field Map')) {
        console.log('Clicking Field Map toggle button...');
        await b.click();
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 2000));
    await page.waitForSelector('.leaflet-container', { timeout: 10000 });
    await page.screenshot({ path: 'screenshot_crew_tasks_map.png' });
    console.log('✓ Captured screenshot_crew_tasks_map.png');

    // 6. Report Network Telemetry
    console.log('\n=== NETWORK REQUEST TELEMETRY AUDIT ===');
    console.log(`Total Esri World Street Map tile requests captured: ${tileRequests.length}`);

    const sampleRequests = tileRequests.slice(0, 10);
    for (const [i, req] of sampleRequests.entries()) {
      console.log(`  Tile #${i + 1}: ${req.url} -> HTTP ${req.status} (${req.contentType || 'unknown'})`);
    }

    console.log(`Blocked / 4xx tile requests: ${blockedOrForbidden.length}`);
    console.log(`Obsolete watermarked CARTO tile requests: ${obsoleteCartoRequests.length}`);
    console.log(`Prohibited endpoints requested (OSM/Nominatim/MapTiler/Google): ${unexpectedEndpoints.length}`);

    if (blockedOrForbidden.length > 0) {
      console.warn('Blocked tile requests:', blockedOrForbidden);
    }
    if (obsoleteCartoRequests.length > 0) {
      console.warn('Obsolete CARTO requests detected:', obsoleteCartoRequests);
    }
    if (unexpectedEndpoints.length > 0) {
      console.warn('Unexpected endpoints:', unexpectedEndpoints);
    }

    const allTilesOk = tileRequests.length > 0 && tileRequests.every((r) => r.status === 200);
    const zeroForbidden = blockedOrForbidden.length === 0;
    const zeroCarto = obsoleteCartoRequests.length === 0;
    const zeroUnexpected = unexpectedEndpoints.length === 0;

    console.log('\n=== VERIFICATION SUMMARY ===');
    console.log(`Real Esri World Street Map Tiles Loaded: ${allTilesOk ? 'PASS (200 OK)' : 'FAIL'}`);
    console.log(`Zero 401/403/404/429 Errors: ${zeroForbidden ? 'PASS' : 'FAIL'}`);
    console.log(`Zero Obsolete CARTO Watermarked Requests: ${zeroCarto ? 'PASS' : 'FAIL'}`);
    console.log(`Zero Prohibited Endpoints (No OSM/Nominatim): ${zeroUnexpected ? 'PASS' : 'FAIL'}`);

    if (allTilesOk && zeroForbidden && zeroCarto && zeroUnexpected) {
      console.log('\n🎉 ALL LIVE MAP VERIFICATION CHECKS PASSED WITH ZERO WATERMARKS!');
    } else {
      console.error('\n❌ Verification encountered issues.');
      process.exitCode = 1;
    }
  } catch (err) {
    console.error('Test execution error:', err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

verifyMapLive();
