// Run real updater JS with minimal DOM/network stubs; no browser dependencies.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
function element() {
  return { textContent: '', innerHTML: '', className: '', disabled: false, style: {},
    classList: { add() {}, remove() {}, contains() { return true; } }, appendChild() {} };
}
const names = ['$modal', '$modalSpinner', '$modalStatus', '$modalLog', '$btnReboot', '$btnSave',
 '$btnRetryUpdate', '$btnRetryRun', '$btnCloseModal', '$btnCheckAgain', '$updateCloseBtn',
 '$updPill', '$updLastChecked', '$btnStartUpdate', '$updInstalled', '$updLatest', '$updChannel'];
const ctx = { console, window: {}, document: { createTextNode: x => x },
  STATUS_POLL_FETCH_TIMEOUT: 15000, UPDATE_POLL_INTERVAL: 2000,
  setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {},
  _updateLog: '', _updateLogOffset: 0, _updateVisibleLogChars: 0, _updatePollTimer: null,
  _updatePollInFlight: false, _updateFinished: false, _updateStatusUnavailable: false,
  _updatePollFailures: 0, _serverWasDown: false };
for (const n of names) ctx[n] = element();
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/sovran_systemsos_web/static/js/update.js'), 'utf8'), ctx);
(async () => {
  let calls = [];
  let check = {available: true, installed_version: '1.0.0', latest_version: '1.1.0', channel: 'stable', status: 'idle'};
  ctx.apiFetchWithTimeout = async (url, opts) => {
    calls.push([url, opts.method]);
    if (url.includes('/status')) return {running: false, result: 'idle'};
    if (url.includes('/check')) return check;
    return {status: 'started'};
  };
  await ctx.openUpdateModal();
  assert.deepStrictEqual(calls.map(x => x[0]), ['/api/updates/status?offset=0', '/api/updates/check']);
  assert.equal(ctx.$updInstalled.textContent, '1.0.0');
  assert.equal(ctx.$updLatest.textContent, '1.1.0');
  assert.equal(ctx.$btnStartUpdate.style.display, 'inline-flex');
  ctx._doOpenUpdateModal();
  assert.equal(calls[2][0], '/api/updates/run');
  check = {...check, available: false, latest_version: '1.0.0'};
  await ctx.openUpdateModal();
  assert.equal(ctx.$btnStartUpdate.style.display, 'none');
  assert.match(ctx.$modalStatus.textContent, /up to date/);
  check = {...check, available: null, latest_version: null};
  await ctx.openUpdateModal();
  assert.equal(ctx.$btnStartUpdate.style.display, 'none');
  assert.match(ctx.$modalStatus.textContent, /unavailable/);
  ctx.apiFetchWithTimeout = async () => { throw Error('offline'); };
  await ctx.openUpdateModal();
  assert.equal(ctx.$btnStartUpdate.style.display, 'none');
  assert.match(ctx.$modalStatus.textContent, /unavailable/);
  // A previously started operation is reattached rather than restarted.
  calls = [];
  ctx.apiFetchWithTimeout = async url => { calls.push(url); return {running:false, result:'reboot_required', log:'', offset:0}; };
  await ctx.openUpdateModal();
  assert.equal(calls.length, 1);
  assert.equal(ctx.$btnReboot.style.display, 'inline-flex');
})().catch(e => { console.error(e); process.exitCode = 1; });
