"use strict";

// ── Rebuild modal ─────────────────────────────────────────────────

// Status line + header pill for the rebuild dialog (same presentation
// contract as the update dialog's _setUpdateStatus).
function _setRebuildStatus(text) {
  if ($rebuildStatus) $rebuildStatus.textContent = text;
  if ($rebuildPill) {
    var cls = "upd-pill";
    var html;
    if (text.charAt(0) === "✓") {
      if (text.indexOf("restart required") !== -1) {
        cls += " st-needs-attention"; html = '<span class="status-dot needs-attention pulse"></span>Restart required';
      } else {
        cls += " st-active"; html = '<span class="status-dot active"></span>Done';
      }
    } else if (text.charAt(0) === "✗") {
      cls += " st-failed"; html = '<span class="status-dot failed"></span>Failed';
    } else {
      cls += " st-loading"; html = '<span class="status-dot loading pulse"></span>Applying…';
    }
    $rebuildPill.className = cls;
    $rebuildPill.innerHTML = html;
  }
  if ($rebuildStatus) {
    var msg = "update-status-msg";
    if (text.charAt(0) === "✓") $rebuildStatus.className = (text.indexOf("restart required") !== -1) ? msg + " st-warn" : msg + " st-ok";
    else if (text.charAt(0) === "✗") $rebuildStatus.className = msg + " st-err";
    else $rebuildStatus.className = msg;
  }
}

function openRebuildModal() {
  if (!$rebuildModal) return;
  _rebuildLog = "";
  _rebuildLogOffset = 0;
  _rebuildServerDown = false;
  _rebuildFinished = false;
  _rebuildPollInFlight = false;
  _rebuildPollFailures = 0;
  if ($rebuildLog) { $rebuildLog.textContent = ""; $rebuildLog.style.display = "none"; }
  var action = _rebuildIsEnabling ? "Enabling" : "Disabling";
  var label = _rebuildFeatureName || "feature";
  _setRebuildStatus(action + " " + label + "…");
  if ($rebuildSpinner) $rebuildSpinner.classList.add("spinning");
  if ($rebuildReboot) $rebuildReboot.style.display = "none";
  if ($rebuildSave) $rebuildSave.style.display = "none";
  if ($rebuildClose) $rebuildClose.disabled = true;
  if ($rebuildCloseHdr) $rebuildCloseHdr.disabled = true;
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
  if (_rebuildPollTimer) clearInterval(_rebuildPollTimer);
  pollRebuildStatus();
  _rebuildPollTimer = setInterval(pollRebuildStatus, UPDATE_POLL_INTERVAL);
}

function stopRebuildPoll() {
  if (_rebuildPollTimer) { clearInterval(_rebuildPollTimer); _rebuildPollTimer = null; }
}

async function pollRebuildStatus() {
  if (_rebuildFinished || _rebuildPollInFlight) return;
  _rebuildPollInFlight = true;
  try {
    var data = await apiFetchWithTimeout(
      "/api/rebuild/status?offset=" + _rebuildLogOffset,
      { cache: "no-store" },
      STATUS_POLL_FETCH_TIMEOUT
    );
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
    // If polling stays broken long past a normal restart, reload to
    // re-authenticate and show the resulting feature state.
    if (_rebuildPollFailures >= STATUS_POLL_MAX_FAILURES) {
      _rebuildFinished = true;
      stopRebuildPoll();
      window.location.reload();
      return;
    }
    if (!_rebuildServerDown) { _rebuildServerDown = true; _setRebuildStatus("Applying changes…"); }
  } finally {
    _rebuildPollInFlight = false;
  }
}

function onRebuildDone(result) {
  if ($rebuildSpinner) $rebuildSpinner.classList.remove("spinning");
  if ($rebuildClose) $rebuildClose.disabled = false;
  if ($rebuildCloseHdr) $rebuildCloseHdr.disabled = false;
  if (result === true) {
    _setRebuildStatus("✓ Done");
    // Auto-reload the page after a short delay so tiles and toggles reflect the new state
    setTimeout(function() { window.location.reload(); }, 1200);
  } else if (result === "reboot_required") {
    _setRebuildStatus("✓ Done — restart required");
    if ($rebuildReboot) $rebuildReboot.style.display = "inline-flex";
  } else {
    _setRebuildStatus("✗ Something went wrong");
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
