// Run with Playwright MCP browser_run_code_unsafe's filename argument.
// Uses the existing Ishara tab and real local models; resets the shared turn.
async (page) => {
  const base = new URL(page.url()).origin;
  if (!['127.0.0.1', 'localhost'].includes(new URL(base).hostname)
      || !(await page.title()).startsWith('Ishara')) throw new Error('Open the local Ishara tab first');
  const checks = [];
  function check(ok, name) {
    if (!ok) throw new Error(name);
    checks.push(name);
  }
  async function post(selector, endpoint, status = 200) {
    const pending = page.waitForResponse(response =>
      new URL(response.url()).pathname === endpoint && response.request().method() === 'POST');
    await page.locator(selector).click();
    const response = await pending, body = await response.json();
    await page.waitForFunction(() => !document.querySelector('#reset').disabled);
    if (response.status() !== status) throw new Error(JSON.stringify(body));
    return body;
  }
  async function rejectApproval(draft) {
    const response = await page.context().request.post(base + '/api/approve', {
      data: { draft_id: draft.draft_id, text: draft.text }, headers: { Origin: base },
    });
    return response.status() === 400;
  }
  await page.reload();
  await page.waitForFunction(() => document.querySelector('#message').textContent.startsWith('Ready.'));
  const config = await (await page.context().request.get(base + '/api/config')).json();
  async function analyze(name) {
    const clip = config.clips.find(item => item.name === name);
    if (!clip) throw new Error('Missing development clip: ' + name);
    await page.locator('#clip').selectOption(clip.id);
    return post('#analyze', '/api/analyze');
  }

  await post('#reset', '/api/reset');
  await analyze('clips/doctor/MVI_4471.MOV');
  await analyze('clips/tomorrow/MVI_5477.MOV');
  check(await page.locator('#concepts').textContent() === 'doctor + tomorrow', 'Real recognized concepts are displayed');
  await page.locator('#intent').selectOption('');
  check((await post('#draft', '/api/draft')).status === 'needs_intent', 'Ambiguous concepts require explicit intent');
  check(await page.locator('#approve').isDisabled(), 'Missing intent cannot be approved');
  await page.locator('#intent').selectOption('request_appointment');
  const suggestion = await post('#draft', '/api/draft');
  check(suggestion.concepts_source === 'slgcn_predictions', 'Recognized provenance is preserved');
  check(suggestion.source === 'fixed_template'
    && suggestion.text === 'I would like an appointment with a doctor tomorrow.',
    'Default template preserves the appointment request and tomorrow');
  check((await page.locator('#provenance').textContent()).includes('fixed intent template'),
    'Composer provenance matches the backend');
  const text = "I'd like an appointment with a doctor tomorrow, please.";
  await page.locator('#sentence').fill(text);
  const approval = await post('#approve', '/api/approve');
  check(approval.text === text && approval.edited, 'Edited text is approved exactly');
  check(approval.sent_to_bolna === false && approval.speech_status === 'not_connected', 'Approval sends no speech');
  check(await page.locator('#approve').isDisabled() && await rejectApproval(suggestion), 'Approval is single-use in UI and backend');

  const pending = await post('#draft', '/api/draft');
  await analyze('clips/doctor/MVI_4471.MOV');
  check(await page.locator('#approve').isDisabled() && await rejectApproval(pending), 'New analysis invalidates approval');
  const replacement = await post('#draft', '/api/draft');
  await post('#reset', '/api/reset');
  check(await rejectApproval(replacement), 'Reset invalidates backend approval');
  check(await page.locator('#draft').isDisabled() && await page.locator('#approve').isDisabled(), 'Reset clears available actions');

  await page.getByText('Sentence-only test with supplied concepts', { exact: true }).click();
  await page.locator('#manual').fill('doctor, tomorrow');
  const manual = await post('#manual-draft', '/api/draft');
  check(manual.concepts_source === 'manually_supplied_not_recognition', 'Manual provenance is explicit');
  await page.locator('#manual').fill('orange');
  await post('#manual-draft', '/api/draft', 400);
  check(await page.locator('#sentence').inputValue() === '', 'Failed draft clears old visible text');
  check(await page.locator('#provenance').textContent() === 'No suggestion yet.', 'Failed draft clears old provenance');
  check(await page.locator('#approve').isDisabled() && await rejectApproval(manual), 'Failed draft cannot reuse old approval');

  await page.locator('#manual').fill('hello');
  await page.locator('#intent').selectOption('greet');
  await post('#manual-draft', '/api/draft');
  await page.locator('#sentence').fill('   ');
  await post('#approve', '/api/approve', 400);
  check(!(await page.locator('#approve').isDisabled()), 'Blank approval remains editable');
  await page.locator('#sentence').fill('Hello — thank you.');
  const corrected = await post('#approve', '/api/approve');
  check(corrected.text === 'Hello — thank you.' && corrected.sent_to_bolna === false, 'Corrected Unicode text is preserved without speech');
  await page.locator('#manual').fill('today');
  await page.locator('#intent').selectOption('specify_day');
  const day = await post('#manual-draft', '/api/draft');
  check(day.text === 'I would like today.', 'Requested day remains a statement, not a question');
  await page.locator('#manual').fill('today, tomorrow');
  const conflict = await post('#manual-draft', '/api/draft');
  check(conflict.status === 'needs_review' && await page.locator('#sentence').inputValue() === ''
    && await page.locator('#approve').isDisabled() && await rejectApproval(day),
    'Conflicting days clear the sentence and invalidate approval');
  await post('#reset', '/api/reset');
  return { checks, suggestion: suggestion.text, approved: approval.text, finalState: 'reset' };
}
