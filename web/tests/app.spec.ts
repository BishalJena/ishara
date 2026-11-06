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
  await page.locator('#request').fill('Book a check-up tomorrow morning.');
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
  await expect(page.getByRole('heading', {name: 'Transcript'})).toBeVisible();
  expect(await page.locator('.notes-primary').evaluate(e => Boolean(e.compareDocumentPosition(document.querySelector('.notes-transcript')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
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
  await expect(page.getByRole('button', {name: /Edit sentence/})).toHaveCount(0);
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

test('backend status lives in Settings and leaves the home composer clear', async ({page}) => {
  await page.goto('/');
  await expect(page.locator('summary[aria-label="Backend status"]')).toHaveCount(0);
  await page.getByRole('button', {name: 'Settings', exact: true}).click();
  const settings = page.getByRole('dialog', {name: 'Settings', exact: true});
  await settings.locator('summary[aria-label="Backend status"]').click();
  const details = settings.getByRole('region', {name: 'Backend status', exact: true});
  await expect(details.getByText(/ask the demo operator to verify/)).toBeVisible();
  await expect(details.getByRole('button', {name: /Check again|Checking/})).toBeVisible();
  await settings.getByRole('button', {name: 'Done', exact: true}).click();
  await expect(page.locator('summary')).toHaveCount(0);
  await expect(page.getByRole('heading', {name: 'Who are we calling today?'})).toBeVisible();
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


test('saved calls refresh into the same concise presentation, persist it and keep transcript secondary', async ({page}) => {
  const notes = {call_id: 'saved-fixture', ready: true, outcome: 'unclear', summary: ['They offered: tomorrow.', 'You answered: yes.'], follow_ups: [], open_questions: [], stepped_in: 0, transcript: [{speaker: 'receptionist', text: 'Please provide your registration ID first.', at: 1}]};
  await page.addInitScript(record => { if (!localStorage.getItem('ishara.calls')) localStorage.setItem('ishara.calls', JSON.stringify([record])); }, {id: 'saved-fixture', contact: 'City Clinic', request: 'Book a check-up tomorrow morning.', at: 1, demo: false, notes});
  await page.route('**/web/session', route => route.fulfill({json: {authenticated: true}}));
  await page.route('**/web/contacts', route => route.fulfill({json: {contacts: []}}));
  await page.route('**/calls/recent', route => route.fulfill({json: {calls: []}}));
  let refreshes = 0;
  const presentation = {version: 1, status: 'ready', title: 'Appointment with Dr. Rao', overview: 'The clinic needs a registration ID before booking.', key_points: ['No appointment was confirmed.', 'Tomorrow morning was discussed.'], next_step: 'Provide the registration ID.'};
  await page.route('**/calls/saved-fixture/notes', route => { refreshes++; return route.fulfill({json: {...notes, bolna_summary: 'The clinic booked a check-up tomorrow at 10:30.', presentation}}); });
  await page.goto('/');
  await expect(page.locator('.recent-row')).toContainText('Book a check-up tomorrow morning');
  await page.locator('.recent-row').first().click();
  const summary = page.locator('.notes-primary');
  await expect(summary.getByRole('heading', {name: 'Call summary', exact: true})).toBeVisible();
  await expect(summary.getByRole('heading', {name: presentation.title, exact: true})).toBeVisible();
  await expect(summary.getByText(presentation.overview)).toBeVisible();
  await expect(summary.getByText(presentation.next_step)).toBeVisible();
  await expect(summary.getByText('Outcome not confirmed')).toBeVisible();
  await expect(summary).not.toContainText('They offered:');
  await expect(summary).not.toContainText('The clinic booked');
  await expect(page.getByText(/may be inaccurate|handled the call from|read the transcript for exact words/i)).toHaveCount(0);
  expect(await summary.evaluate(e => Boolean(e.compareDocumentPosition(document.querySelector('.notes-transcript')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await expect(page.getByText('Please provide your registration ID first.', {exact: true})).not.toBeVisible();
  await page.getByText('Transcript', {exact: true}).click();
  await expect(page.getByText('Please provide your registration ID first.', {exact: true})).toBeVisible();
  expect(refreshes).toBe(1);
  await page.screenshot({path: '/tmp/ishara-summary-web-desktop.png', fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: '/tmp/ishara-summary-web-mobile.png', fullPage: true});
  await page.getByRole('button', {name: 'Make another call'}).click();
  await expect(page.locator('.recent-row')).toContainText(presentation.title);
  await page.reload();
  await expect(page.locator('.recent-row')).toContainText(presentation.title);
  await page.locator('.recent-row').first().click();
  await expect(page.locator('.notes-primary').getByText(presentation.overview)).toBeVisible();
});


test('live calls start with an empty general request instead of the scripted clinic goal', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button', {name: 'Live call', exact: true}).click();
  await page.getByLabel('Demo access code').fill('ishara-web-demo');
  await page.getByRole('button', {name: 'Open call desk'}).click();
  await expect(page.locator('#request')).toHaveValue('');
  await page.locator('#request').fill('Ask a plumber about fixing a leaking pipe.');
  let purpose = '';
  await page.route('**/briefs', async route => {
    purpose = route.request().postDataJSON().purpose;
    await route.fulfill({status: 422, json: {detail: 'Fixture stops before dialing'}});
  });
  await page.getByRole('button', {name: 'Contacts', exact: true}).click();
  await page.getByRole('button', {name: /Clinic/}).click();
  // The fixture response deliberately stops before a telephone request.
  const dialogErrors = errors.get(page)!;
  await page.getByRole('button', {name: 'Place live call'}).click();
  await expect(page.getByRole('alert')).toContainText('Check your details and try again.');
  expect(purpose).toBe('general');
  // An intentional HTTP error is expected in this regression, unlike a page error.
  for (let i = dialogErrors.length - 1; i >= 0; i--) if (dialogErrors[i].includes('422')) dialogErrors.splice(i, 1);
});


test('signing word review deduplicates, preserves the request and never dials or speaks', async ({page}) => {
  const providerWrites: string[] = [];
  page.on('request', request => { if (request.method() === 'POST' && /\/(calls|briefs)$/.test(request.url())) providerWrites.push(request.url()); });
  await unlock(page);
  await page.locator('#request').fill('Please ask about the renewal.');
  await page.getByRole('button', {name: 'Open signing'}).click();
  await page.getByRole('button', {name: 'All 8 words · tap to choose'}).click();
  const palette = page.getByRole('region', {name: 'Say it with a sign'}).getByLabel('Supported signing words');
  await palette.getByRole('button', {name: 'hello', exact: true}).click();
  await palette.getByRole('button', {name: 'hello', exact: true}).click();
  await palette.getByRole('button', {name: 'please', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Remove hello', exact: true})).toHaveCount(1);
  await expect(page.getByRole('button', {name: 'Remove please', exact: true})).toHaveCount(1);
  await page.screenshot({path: 'artifacts/signing-word-review.png', fullPage: true});
  await page.getByRole('button', {name: 'Edit sentence', exact: true}).click();
  await expect(page.locator('#request')).toHaveValue('Please ask about the renewal. hello please');
  expect(providerWrites).toEqual([]);
});


test('uncertain recognition offers three explicit choices without adding question marks', async ({page}) => {
  await page.route('**/web/recognize', route => route.fulfill({json: {kind: 'unsure', suggestions: ['hello', 'yes', 'no'], reason: 'Choose a word'}}));
  await unlock(page);
  await page.getByRole('button', {name: 'Open signing'}).click();
  await page.getByRole('button', {name: 'Enable camera'}).click();
  await expect(page.getByRole('button', {name: 'Record one sign', exact: true})).toBeEnabled({timeout: 60000});
  await page.getByRole('button', {name: 'Record one sign', exact: true}).click();
  const choices = page.getByLabel('Sign suggestions');
  await expect(choices.getByRole('button')).toHaveCount(3, {timeout: 20000});
  await expect(page.getByRole('button', {name: /^Remove /})).toHaveCount(0);
  await page.screenshot({path: 'artifacts/signing-three-choices.png', fullPage: true});
  await choices.getByRole('button', {name: 'yes', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Remove yes', exact: true})).toBeVisible();
  await expect(choices).toHaveCount(0);
});
