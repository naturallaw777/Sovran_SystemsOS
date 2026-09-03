"use strict";

// ── Update modal ──────────────────────────────────────────────────

async function openUpdateModal() {
  if (!$modal) return;

  // Reattach before checking for new updates. This makes a browser reload,
  // RDP reconnect, or suspended tab recover the authoritative systemd-backed
  // state instead of starting over or claiming the system is merely up to date.
  try {
    var current = await apiFetchWithTimeout(
      "/api/updates/status?offset=0",
      { cache: "no-store" },
      STATUS_POLL_FETCH_TIMEOUT
    );
    if (current.running || current.result === "reboot_required" || current.result === "failed") {
      // An in-progress update, a staged update awaiting reboot, or a prior
      // failed update — reattach to the persisted systemd/log state instead of
      // starting over or wrongly reporting "up to date".
      showExistingUpdate(current);
      return;
    }
  } catch (_) {
    // The normal start path below has its own visible error handling.
  }

  apiFetchWithTimeout(
    "/api/updates/check",
    { cache: "no-store" },
    STATUS_POLL_FETCH_TIMEOUT
  )
    .then(function(data) {
      if (!data.available) {
        stopUpdatePoll();
        _updateLog = "";
        _updateLogOffset = 0;
        _updateVisibleLogChars = 0;
        _updateFinished = true;
        _updateStatusUnavailable = false;
        if ($modalLog) $modalLog.textContent = "";
        if ($modalStatus) $modalStatus.textContent = "✓ System is already up to date";
        if ($modalSpinner) $modalSpinner.classList.remove("spinning");
        if ($btnReboot) $btnReboot.style.display = "none";
        if ($btnSave) $btnSave.style.display = "none";
        if ($btnRetryUpdate) $btnRetryUpdate.style.display = "none";
        if ($btnRetryRun) $btnRetryRun.style.display = "none";
        if ($btnCloseModal) $btnCloseModal.disabled = false;
        $modal.classList.add("open");
        return;
      }
      _doOpenUpdateModal();
    })
    .catch(function() {
      _doOpenUpdateModal();
    });
}

function prepareUpdateModal() {
  if (!$modal) return;
  stopUpdatePoll();
  _updateLog = "";
  _updateLogOffset = 0;
  _updateVisibleLogChars = 0;
  _updatePollInFlight = false;
  _serverWasDown = false;
  _updateFinished = false;
  _updateStatusUnavailable = false;
  _updatePollFailures = 0;
  if ($modalLog) $modalLog.textContent = "";
  if ($modalStatus) $modalStatus.textContent = "Starting update…";
  if ($modalSpinner) $modalSpinner.classList.add("spinning");
  if ($btnReboot) $btnReboot.style.display = "none";
  if ($btnSave) $btnSave.style.display = "none";
  if ($btnRetryUpdate) $btnRetryUpdate.style.display = "none";
  if ($btnRetryRun) $btnRetryRun.style.display = "none";
  if ($btnCloseModal) $btnCloseModal.disabled = true;
  $modal.classList.add("open");
}

function _doOpenUpdateModal() {
  prepareUpdateModal();
  startUpdate();
}

function showExistingUpdate(data) {
  prepareUpdateModal();
  if (data.log) appendLog(data.log);
  _updateLogOffset = Number(data.offset) || 0;

  if (data.running) {
    if ($modalStatus) $modalStatus.textContent = "Updating…";
    startUpdatePoll();
    return;
  }

  _updateFinished = true;
  if (data.result === "reboot_required") {
    onUpdateDone("reboot_required");
  } else if (data.result === "success") {
    onUpdateDone(true);
  } else {
    onUpdateDone(false);
  }
}

async function restoreUpdateModalIfNeeded() {
  if (!$modal || $modal.classList.contains("open")) return;
  try {
    var data = await apiFetchWithTimeout(
      "/api/updates/status?offset=0",
      { cache: "no-store" },
      STATUS_POLL_FETCH_TIMEOUT
    );
    if (data.running || data.result === "reboot_required") {
      showExistingUpdate(data);
    }
  } catch (_) {
    // Dashboard startup must remain usable when status cannot be reached.
  }
}

function closeUpdateModal() {
  if (!$modal) return;
  $modal.classList.remove("open");
  stopUpdatePoll();
}

function appendLog(text) {
  if (!text) return;
  _updateLog += text;
  if ($modalLog) {
    // Appending a text node avoids reparsing/replacing the complete log on
    // every two-second poll. Trim only occasionally once the visible log is
    // large; the complete _updateLog remains available for error reports.
    if (_updateVisibleLogChars + text.length > UPDATE_VISIBLE_LOG_MAX_CHARS) {
      var tail = _updateLog.slice(-UPDATE_VISIBLE_LOG_TRIM_CHARS);
      var notice = "[Earlier update output hidden from this view; it remains in the saved report.]\n\n";
      $modalLog.textContent = notice + tail;
      _updateVisibleLogChars = notice.length + tail.length;
    } else {
      $modalLog.appendChild(document.createTextNode(text));
      _updateVisibleLogChars += text.length;
    }
    $modalLog.scrollTop = $modalLog.scrollHeight;
  }
}

function startUpdate() {
  apiFetchWithTimeout(
    "/api/updates/run",
    { method: "POST" },
    STATUS_POLL_FETCH_TIMEOUT * 2
  )
    .then(function(data) {
      if (data.status === "no_updates") {
        if ($modalStatus) $modalStatus.textContent = "✓ System is already up to date";
        if ($modalSpinner) $modalSpinner.classList.remove("spinning");
        if ($btnReboot) $btnReboot.style.display = "none";
        if ($btnSave) $btnSave.style.display = "none";
        if ($btnRetryUpdate) $btnRetryUpdate.style.display = "none";
        if ($btnRetryRun) $btnRetryRun.style.display = "none";
        if ($btnCloseModal) $btnCloseModal.disabled = false;
        _updateFinished = true;
        return;
      }
      if (data.status === "already_running") appendLog("[Update already in progress, attaching…]\n\n");
      if ($modalStatus) $modalStatus.textContent = "Updating…";
      startUpdatePoll();
    })
    .catch(function(err) {
      appendLog("[Error: failed to start update — " + err + "]\n");
      onUpdateDone(false);
    });
}

function startUpdatePoll() {
  if (_updatePollTimer) clearInterval(_updatePollTimer);
  pollUpdateStatus();
  _updatePollTimer = setInterval(pollUpdateStatus, UPDATE_POLL_INTERVAL);
}

function stopUpdatePoll() {
  if (_updatePollTimer) { clearInterval(_updatePollTimer); _updatePollTimer = null; }
}

async function pollUpdateStatus() {
  // setInterval does not wait for an async callback. The guard prevents a slow
  // request from creating overlapping, out-of-order status polls.
  if (_updateFinished || _updatePollInFlight) return;
  _updatePollInFlight = true;
  try {
    var data = await apiFetchWithTimeout(
      "/api/updates/status?offset=" + _updateLogOffset,
      { cache: "no-store" },
      STATUS_POLL_FETCH_TIMEOUT
    );
    _updatePollFailures = 0;
    if (_serverWasDown) {
      _serverWasDown = false;
      if (!data.running) {
        // The update finished while the server or browser connection was away.
        // Re-fetch from offset 0 so the final result and complete tail agree.
        _updateLog = "";
        _updateLogOffset = 0;
        _updateVisibleLogChars = 0;
        if ($modalLog) $modalLog.textContent = "";
        try {
          var fullData = await apiFetchWithTimeout(
            "/api/updates/status?offset=0",
            { cache: "no-store" },
            STATUS_POLL_FETCH_TIMEOUT
          );
          if (fullData.log) appendLog(fullData.log);
          _updateLogOffset = fullData.offset;
          data = fullData;
        } catch (_) {
          if (data.log) appendLog(data.log);
          _updateLogOffset = data.offset;
        }
        if (data.result === "reboot_required") {
          appendLog("[Reconnected — update completed, reboot required.]\n");
        } else if (data.result === "success") {
          appendLog("[Reconnected — update completed successfully.]\n");
        } else {
          appendLog("[Reconnected — update encountered an error.]\n");
        }
        _updateFinished = true;
        stopUpdatePoll();
        if (data.result === "reboot_required") {
          onUpdateDone("reboot_required");
        } else {
          onUpdateDone(data.result === "success");
        }
        return;
      }
      appendLog("[Update status reconnected]\n");
      if ($modalStatus) $modalStatus.textContent = "Updating…";
    }
    if (data.log) appendLog(data.log);
    _updateLogOffset = data.offset;
    if (data.running) return;
    _updateFinished = true;
    stopUpdatePoll();
    if (data.result === "reboot_required") {
      onUpdateDone("reboot_required");
    } else if (data.result === "success") {
      onUpdateDone(true);
    } else {
      onUpdateDone(false);
    }
  } catch (err) {
    _updatePollFailures += 1;
    if (_updatePollFailures >= STATUS_POLL_MAX_FAILURES) {
      showUpdateStatusUnavailable();
      return;
    }
    if (!_serverWasDown) {
      _serverWasDown = true;
      appendLog("\n[Update status connection interrupted — retrying…]\n");
      if ($modalStatus) $modalStatus.textContent = "Reconnecting to update…";
    }
  } finally {
    _updatePollInFlight = false;
  }
}

function showUpdateStatusUnavailable() {
  _updateFinished = true;
  _updateStatusUnavailable = true;
  stopUpdatePoll();
  if ($modalSpinner) $modalSpinner.classList.remove("spinning");
  if ($modalStatus) $modalStatus.textContent = "Update status unavailable — update may still be running";
  appendLog("\n[The Hub could not confirm update status. The background update was not stopped. Select Retry Status after reconnecting.]\n");
  if ($btnRetryUpdate) $btnRetryUpdate.style.display = "inline-flex";
  if ($btnCloseModal) $btnCloseModal.disabled = false;
}

function retryUpdateStatus() {
  if (!$modal) return;
  _updateFinished = false;
  _updateStatusUnavailable = false;
  _updatePollFailures = 0;
  _serverWasDown = true;
  if ($modalSpinner) $modalSpinner.classList.add("spinning");
  if ($modalStatus) $modalStatus.textContent = "Reconnecting to update…";
  if ($btnRetryUpdate) $btnRetryUpdate.style.display = "none";
  if ($btnCloseModal) $btnCloseModal.disabled = true;
  startUpdatePoll();
}

// Re-run a failed (or never-applied) update from scratch.  The backend always
// allows this after a FAILED attempt even though flake.lock may already be
// advanced (the previous build never staged a bootable generation).
function retryUpdateRun() {
  if ($btnRetryRun) $btnRetryRun.style.display = "none";
  if ($btnSave) $btnSave.style.display = "none";
  if ($btnReboot) $btnReboot.style.display = "none";
  _doOpenUpdateModal();
}

function resumeUpdateStatusAfterInterruption() {
  if (!$modal || !$modal.classList.contains("open")) return;
  if (_updateStatusUnavailable) {
    retryUpdateStatus();
  } else if (!_updateFinished) {
    pollUpdateStatus();
  }
}

function onUpdateDone(result) {
  _updateStatusUnavailable = false;
  if ($modalSpinner) $modalSpinner.classList.remove("spinning");
  if ($btnRetryUpdate) $btnRetryUpdate.style.display = "none";
  if ($btnCloseModal) $btnCloseModal.disabled = false;
  if (result === true) {
    if ($modalStatus) $modalStatus.textContent = "✓ Update complete";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  } else if (result === "reboot_required") {
    if ($modalStatus) $modalStatus.textContent = "✓ Update complete — restart required";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  } else {
    if ($modalStatus) $modalStatus.textContent = "✗ Update failed — your system was not changed. Run the update again or save the error report for support.";
    if ($btnRetryRun) $btnRetryRun.style.display = "inline-flex";
    if ($btnSave) $btnSave.style.display = "inline-flex";
    if ($btnReboot) $btnReboot.style.display = "none";
  }
}

function saveErrorReport() {
  var blob = new Blob([_updateLog], { type: "text/plain" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "sovran-update-error-" + new Date().toISOString().split(".")[0].replace(/:/g, "-") + ".txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}


// ── Reboot ────────────────────────────────────────────────────────

var _rebootStartTime = 0;
var _serverWentDown = false;
var _rebootFailed = false;

function _setRebootStatus(msg) {
  if ($rebootSubmessage) $rebootSubmessage.textContent = msg;
}

function doReboot() {
  if ($modal) $modal.classList.remove("open");
  if ($rebuildModal) $rebuildModal.classList.remove("open");
  stopUpdatePoll();
  stopRebuildPoll();
  // Reset overlay to main card
  if ($rebootMainCard) $rebootMainCard.style.display = "";
  if ($rebootErrorCard) $rebootErrorCard.style.display = "none";
  _setRebootStatus("Sending restart request\u2026");
  if ($rebootOverlay) $rebootOverlay.classList.add("visible");
  _rebootStartTime = Date.now();
  _serverWentDown = false;
  _rebootFailed = false;
  var rebootCtrl = new AbortController();
  setTimeout(function() { rebootCtrl.abort(); }, REBOOT_REQUEST_TIMEOUT);
  fetch("/api/reboot", { method: "POST", signal: rebootCtrl.signal })
    .then(function(res) {
      if (!res.ok) {
        // Definitive HTTP error — server rejected the request before going down
        _rebootFailed = true;
        if ($rebootMainCard) $rebootMainCard.style.display = "none";
        if ($rebootErrorCard) $rebootErrorCard.style.display = "";
        // Leave overlay visible so the error card is shown
      }
      // HTTP 2xx: request accepted, proceed with polling
    })
    .catch(function() {
      // Connection dropped or request aborted — the server is likely already going
      // down as part of the restart. Treat as success and continue polling.
    });
  // Wait before the first check — NixOS shutdown after an update can take 20-40s
  setTimeout(waitForServerReboot, REBOOT_INITIAL_DELAY);
}

function waitForServerReboot() {
  if (_rebootFailed) return;
  // Update status on first check (server hasn't gone down yet)
  if (!_serverWentDown) _setRebootStatus("Waiting for the computer to shut down\u2026");
  var controller = new AbortController();
  var timeoutId = setTimeout(function() { controller.abort(); }, REBOOT_FETCH_TIMEOUT);

  fetch("/api/ping", { cache: "no-store", signal: controller.signal, headers: { "Connection": "close" } })
    .then(function(res) {
      clearTimeout(timeoutId);
      if (_serverWentDown) {
        // Server is responding after having been down — reboot is complete.
        // Any response (even 401/500) means the server process is back.
        _setRebootStatus("System is back online. Reconnecting\u2026");
        window.location.reload();
      } else if ((Date.now() - _rebootStartTime) < 90000) {
        // Server still responding but hasn't gone down yet — keep waiting
        setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
      } else {
        // Been over 90 seconds and server is responding — just reload
        _setRebootStatus("System is back online. Reconnecting\u2026");
        window.location.reload();
      }
    })
    .catch(function() {
      clearTimeout(timeoutId);
      if (!_serverWentDown) {
        _serverWentDown = true;
        _setRebootStatus("The computer is restarting\u2026");
      }
      setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
    });
}
