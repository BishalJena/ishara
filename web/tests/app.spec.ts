import {expect, test} from '@playwright/test';

const errors = new WeakMap<import('@playwright/test').Page, string[]>();
test.beforeEach(({page}) => {
  const list: string[] = []; errors.set(page, list);
  page.on('pageerror', error => list.push(error.message));
  page.on('console', message => {
    // The native WASM runtime writes its delegate-created INFO line to stderr.
    if (message.type() === 'error' && !message.text().startsWith('INFO: Created TensorFlow Lite')) list.push(message.text());
  });
});
test.afterEach(({page}) => { expect(errors.get(page)).toEqual([]); });

async function unlock(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByRole('button', {name: 'Live call', exact: true}).click();
  await page.getByLabel('Demo access code').fill('ishara-web-demo');
  await page.getByRole('button', {name: 'Open call desk'}).click();
  await expect(page.getByRole('heading', {name: 'Who are we calling today?'})).toBeVisible();
}

test('scripted demo covers setup, typed intervention and notes without calling REST', async ({page}) => {
  const dialRequests: string[] = [];
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/calls')) dialRequests.push(request.url()); });
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Who are we calling today?'})).toBeVisible();
  await page.screenshot({path: 'artifacts/desk-desktop.png', fullPage: true});
  await page.getByRole('button', {name: 'Start scripted call'}).click();
  await expect(page.getByLabel('Your reply')).toBeEnabled({timeout: 15000});
  await page.getByLabel('Your reply').fill('Could we do a little later?');
  await page.getByRole('button', {name: 'Preview and send reply'}).click();
  await expect(page.getByText('Your reply, polished')).toBeVisible();
  await page.screenshot({path: 'artifacts/call-desktop.png', fullPage: true});
  await expect(page.getByRole('heading', {name: /Appointment booked|follow-up is needed/})).toBeVisible({timeout: 20000});
  expect(dialRequests).toHaveLength(0);
});

test('browser cookie works through real REST and WebSocket with fake telephone service', async ({page}) => {
  await unlock(page);
  await page.getByRole('button', {name: 'Contacts', exact: true}).click();
  await page.getByRole('button', {name: /Clinic/}).click();
  await page.getByRole('button', {name: 'Place live call'}).click();
  await expect(page.getByLabel('Your reply')).toBeEnabled({timeout: 30000});
  await expect(page.getByRole('log', {name: 'Call captions'})).toContainText('Hello', {timeout: 15000});
  await page.getByLabel('Your reply').fill('Please wait a moment.');
  await page.getByRole('button', {name: 'Preview and send reply'}).click();
  await expect(page.getByText('Your reply, polished')).toBeVisible({timeout: 10000});
  await page.getByRole('button', {name: 'End call', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Make another call'})).toBeVisible({timeout: 15000});
  await expect(page.getByRole('heading', {name: 'The conversation'})).toBeVisible();
});

test('mobile setup has no horizontal overflow and controls remain usable', async ({page}) => {
  await page.setViewportSize({width: 320, height: 812});
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Who are we calling today?'})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Start scripted call'})).toBeVisible();
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  expect(fits).toBe(true);
  await page.screenshot({path: 'artifacts/desk-mobile.png', fullPage: true});
});

test('camera loads the actual Holistic tracker and uncertain footage stays unsent', async ({page}) => {
  test.setTimeout(180000);
  await unlock(page);
  await page.getByRole('button', {name: 'Open signing'}).click();
  await page.getByRole('button', {name: 'Enable camera'}).click();
  const record = page.getByRole('button', {name: 'Record one sign', exact: true});
  await expect(record).toBeEnabled({timeout: 120000});
  await record.click();
  await expect(record).toBeEnabled({timeout: 15000});
  await expect(page.getByText(/Keep your shoulders and hands visible|Record one complete sign/)).toBeVisible({timeout: 30000});
  await expect(page.getByRole('button', {name: /Use these words/})).toHaveCount(0);
  await page.screenshot({path: 'artifacts/camera-desktop.png', fullPage: true});
  await page.getByRole('button', {name: 'Turn off camera'}).click();
});

test('a pending video play promise cannot block camera model initialization', async ({page}) => {
  await page.addInitScript(() => {
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () {
      void play.call(this).catch(() => {});
      return new Promise<void>(() => {});
    };
  });
  await unlock(page);
  await page.setViewportSize({width: 320, height: 812});
  await page.setViewportSize({width: 1440, height: 1000});
  await page.getByRole('button', {name: 'Open signing'}).click();
  await page.getByRole('button', {name: 'Enable camera'}).click();
  await expect(page.getByRole('button', {name: 'Record one sign', exact: true})).toBeEnabled({timeout: 60000});
  await page.getByRole('button', {name: 'Turn off camera'}).click();
});


test('desktop keeps the prototype in a phone frame and settings preserve the caller name', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Who are we calling today?'})).toBeVisible();
  expect(await page.locator('.phone-device').evaluate(e => e.getBoundingClientRect().width)).toBe(402);
  await page.getByRole('button', {name: 'Settings', exact: true}).click();
  const settings = page.getByRole('dialog', {name: 'Settings'});
  await settings.getByLabel('Your name on the call').fill('Alex');
  await settings.getByRole('button', {name: 'Done', exact: true}).click();
  await expect(page.getByText('Hi Alex', {exact: true})).toBeVisible();
  await page.reload();
  await expect(page.getByText('Hi Alex', {exact: true})).toBeVisible();
});


test('the phone prototype opens even while backend authentication is unavailable', async ({page}) => {
  await page.route('**/web/session', () => {});
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Who are we calling today?'})).toBeVisible({timeout: 2000});
  await page.getByRole('button', {name: 'Start scripted call'}).click();
  await expect(page.getByLabel('Your reply')).toBeEnabled({timeout: 5000});
});


test('an accepted call survives a lost POST response without a second dial', async ({page}) => {
  let posts = 0;
  await page.route('**/calls', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    posts++;
    await route.fetch(); // the fake telephone call is already accepted
    await route.fulfill({status: 200, contentType: 'application/json', body: '{"call_id":'});
  });
  await unlock(page);
  await page.getByRole('button', {name: 'Contacts', exact: true}).click();
  await page.getByRole('button', {name: /Clinic/}).click();
  await page.getByRole('button', {name: 'Place live call'}).click();
  await expect(page.getByLabel('Your reply')).toBeEnabled({timeout: 20000});
  await expect(page.getByRole('log', {name: 'Call captions'})).toContainText('Hello', {timeout: 15000});
  await page.getByRole('button', {name: 'End call', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Make another call'})).toBeVisible({timeout: 15000});
  expect(posts).toBe(1);
});

test('backend status remains visible and offers a fresh service check', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button', {name: 'Backend status'}).click();
  const sheet = page.getByRole('dialog', {name: 'Backend status'});
  await expect(sheet.getByText(/ask the demo operator to verify/)).toBeVisible();
  await expect(sheet.getByRole('button', {name: /Check again|Checking/})).toBeVisible();
});


test('typing holds the actual pending agent proposal before sending a reviewed reply', async ({page}) => {
  await unlock(page);
  await page.getByRole('button', {name: 'Contacts', exact: true}).click();
  await page.getByRole('button', {name: /Clinic/}).click();
  await page.getByRole('button', {name: 'Place live call'}).click();
  await expect(page.getByText('Ishara is about to say', {exact: true})).toBeVisible({timeout: 30000});
  await page.getByLabel('Your reply').fill('Please wait a moment.');
  await expect(page.getByText('Ishara is about to say', {exact: true})).toHaveCount(0, {timeout: 1500});
  await page.getByRole('button', {name: 'Preview and send reply'}).click();
  await expect(page.getByText('Your reply, polished')).toBeVisible({timeout: 10000});
  await page.getByRole('button', {name: 'End call', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Make another call'})).toBeVisible({timeout: 15000});
});
