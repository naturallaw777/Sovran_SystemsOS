"use strict";

// ── Rebuild modal ─────────────────────────────────────────────────

function openRebuildModal() {
  if (!$rebuildModal) return;
  _rebuildLog = "";
  _rebuildLogOffset = 0;
  _rebuildServerDown = false;
  _rebuildFinished = false;
  _rebuildPollFailures = 0;
  if ($rebuildLog) { $rebuildLog.textContent = ""; $rebuildLog.style.display = "none"; }
  var action = _rebuildIsEnabling ? "Enabling" : "Disabling";
  var label = _rebuildFeatureName || "feature";
  if ($rebuildStatus) $rebuildStatus.textContent = action + " " + label + "…";
  if ($rebuildSpinner) $rebuildSpinner.classList.add("spinning");
  if ($rebuildReboot) $rebuildReboot.style.display = "none";
  if ($rebuildSave) $rebuildSave.style.display = "none";
  if ($rebuildClose) $rebuildClose.disabled = true;
  $rebuildModal.classList.add("open");
  // Delay first poll slightly to let the rebuild service start and clear stale log
  setTimeout(startRebuildPoll, 1500);
}

function closeRebuildModal() {
  if ($rebuildModal) $rebuildModal.classList.remove("open");
  stopRebuildPoll();
}

function appendRebuildLog(text) {
  if (!text) return;
  _rebuildLog += text;
  // Log is collected silently for error reports — not displayed to user
}

function startRebuildPoll() {
  pollRebuildStatus();
  _rebuildPollTimer = setInterval(pollRebuildStatus, UPDATE_POLL_INTERVAL);
}

function stopRebuildPoll() {
  if (_rebuildPollTimer) { clearInterval(_rebuildPollTimer); _rebuildPollTimer = null; }
}

async function pollRebuildStatus() {
  if (_rebuildFinished) return;
  try {
    var data = await apiFetch("/api/rebuild/status?offset=" + _rebuildLogOffset);
    _rebuildPollFailures = 0;
    if (_rebuildServerDown) { _rebuildServerDown = false; }
    if (data.log) appendRebuildLog(data.log);
    _rebuildLogOffset = data.offset;
    if (data.running) return;
    _rebuildFinished = true;
    stopRebuildPoll();
    if (data.result === "reboot_required") {
      onRebuildDone("reboot_required");
    } else {
      onRebuildDone(data.result === "success");
    }
  } catch (err) {
    _rebuildPollFailures += 1;
    // The Hub restarts itself during activation, which briefly drops this poll.
    // If polling stays broken long past a normal restart, the page's session
    // almost certainly no longer matches the server (e.g. the Hub restarted
    // and sessions were not recovered).  Reload to re-authenticate and show
    // the real feature state instead of spinning forever.
    if (_rebuildPollFailures >= STATUS_POLL_MAX_FAILURES) {
      _rebuildFinished = true;
      stopRebuildPoll();
      window.location.reload();
      return;
    }
    if (!_rebuildServerDown) { _rebuildServerDown = true; if ($rebuildStatus) $rebuildStatus.textContent = "Applying changes…"; }
  }
}

function onRebuildDone(result) {
  if ($rebuildSpinner) $rebuildSpinner.classList.remove("spinning");
  if ($rebuildClose) $rebuildClose.disabled = false;
  if (result === true) {
    if ($rebuildStatus) $rebuildStatus.textContent = "✓ Done";
    // Auto-reload the page after a short delay so tiles and toggles reflect the new state
    setTimeout(function() { window.location.reload(); }, 1200);
  } else if (result === "reboot_required") {
    if ($rebuildStatus) $rebuildStatus.textContent = "✓ Done — restart required";
    if ($rebuildReboot) $rebuildReboot.style.display = "inline-flex";
  } else {
    if ($rebuildStatus) $rebuildStatus.textContent = "✗ Something went wrong";
    if ($rebuildSave) $rebuildSave.style.display = "inline-flex";
    if ($rebuildReboot) $rebuildReboot.style.display = "inline-flex";
  }
}

function saveRebuildErrorReport() {
  var blob = new Blob([_rebuildLog], { type: "text/plain" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "sovran-rebuild-error-" + new Date().toISOString().split(".")[0].replace(/:/g, "-") + ".txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
