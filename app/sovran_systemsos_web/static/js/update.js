"use strict";

// ── Update modal ──────────────────────────────────────────────────

function openUpdateModal() {
  if (!$modal) return;
  apiFetch("/api/updates/check")
    .then(function(data) {
      if (!data.available) {
        stopUpdatePoll();
        _updateLog = "";
        _updateLogOffset = 0;
        _updateFinished = true;
        if ($modalLog) $modalLog.textContent = "";
        if ($modalStatus) $modalStatus.textContent = "✓ System is already up to date";
        if ($modalSpinner) $modalSpinner.classList.remove("spinning");
        if ($btnReboot) $btnReboot.style.display = "none";
        if ($btnSave) $btnSave.style.display = "none";
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

function _doOpenUpdateModal() {
  if (!$modal) return;
  _updateLog = "";
  _updateLogOffset = 0;
  _serverWasDown = false;
  _updateFinished = false;
  if ($modalLog) $modalLog.textContent = "";
  if ($modalStatus) $modalStatus.textContent = "Starting update…";
  if ($modalSpinner) $modalSpinner.classList.add("spinning");
  if ($btnReboot) $btnReboot.style.display = "none";
  if ($btnSave) $btnSave.style.display = "none";
  if ($btnCloseModal) $btnCloseModal.disabled = true;
  $modal.classList.add("open");
  startUpdate();
}

function closeUpdateModal() {
  if (!$modal) return;
  $modal.classList.remove("open");
  stopUpdatePoll();
}

function appendLog(text) {
  if (!text) return;
  _updateLog += text;
  if ($modalLog) { $modalLog.textContent += text; $modalLog.scrollTop = $modalLog.scrollHeight; }
}

function startUpdate() {
  fetch("/api/updates/run", { method: "POST" })
    .then(function(response) {
      if (!response.ok) return response.text().then(function(t) { throw new Error(t); });
      return response.json();
    })
    .then(function(data) {
      if (data.status === "no_updates") {
        if ($modalStatus) $modalStatus.textContent = "✓ System is already up to date";
        if ($modalSpinner) $modalSpinner.classList.remove("spinning");
        if ($btnReboot) $btnReboot.style.display = "none";
        if ($btnSave) $btnSave.style.display = "none";
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
  pollUpdateStatus();
  _updatePollTimer = setInterval(pollUpdateStatus, UPDATE_POLL_INTERVAL);
}

function stopUpdatePoll() {
  if (_updatePollTimer) { clearInterval(_updatePollTimer); _updatePollTimer = null; }
}

async function pollUpdateStatus() {
  if (_updateFinished) return;
  try {
    var data = await apiFetch("/api/updates/status?offset=" + _updateLogOffset);
    if (_serverWasDown) {
      _serverWasDown = false;
      if (!data.running) {
        // The update finished while the server was restarting.  Reset to
        // offset 0 and re-fetch so the complete log is shown from the top.
        _updateLog = "";
        _updateLogOffset = 0;
        if ($modalLog) $modalLog.textContent = "";
        try {
          var fullData = await apiFetch("/api/updates/status?offset=0");
          if (fullData.log) appendLog(fullData.log);
          _updateLogOffset = fullData.offset;
        } catch (e) {
          // If the re-fetch fails, fall through with whatever we have.
          if (data.log) appendLog(data.log);
          _updateLogOffset = data.offset;
        }
        if (data.result === "success") {
          appendLog("[Server restarted — update completed successfully.]\n");
        } else {
          appendLog("[Server restarted — update encountered an error.]\n");
        }
        _updateFinished = true;
        stopUpdatePoll();
        onUpdateDone(data.result === "success");
        return;
      }
      appendLog("[Server reconnected]\n");
      if ($modalStatus) $modalStatus.textContent = "Updating…";
    }
    if (data.log) appendLog(data.log);
    _updateLogOffset = data.offset;
    if (data.running) return;
    _updateFinished = true;
    stopUpdatePoll();
    if (data.result === "success") onUpdateDone(true);
    else onUpdateDone(false);
  } catch (err) {
    if (!_serverWasDown) { _serverWasDown = true; appendLog("\n[Server restarting — waiting for it to come back…]\n"); if ($modalStatus) $modalStatus.textContent = "Server restarting…"; }
  }
}

function onUpdateDone(success) {
  if ($modalSpinner) $modalSpinner.classList.remove("spinning");
  if ($btnCloseModal) $btnCloseModal.disabled = false;
  if (success) {
    if ($modalStatus) $modalStatus.textContent = "✓ Update complete";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  } else {
    if ($modalStatus) $modalStatus.textContent = "✗ Update failed";
    if ($btnSave) $btnSave.style.display = "inline-flex";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
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

function doReboot() {
  if ($modal) $modal.classList.remove("open");
  if ($rebuildModal) $rebuildModal.classList.remove("open");
  stopUpdatePoll();
  stopRebuildPoll();
  if ($rebootOverlay) $rebootOverlay.classList.add("visible");
  _rebootStartTime = Date.now();
  _serverWentDown = false;
  var rebootCtrl = new AbortController();
  setTimeout(function() { rebootCtrl.abort(); }, REBOOT_REQUEST_TIMEOUT);
  fetch("/api/reboot", { method: "POST", signal: rebootCtrl.signal }).catch(function() {});
  // Wait before the first check — NixOS shutdown after an update can take 20-40s
  setTimeout(waitForServerReboot, REBOOT_INITIAL_DELAY);
}

function waitForServerReboot() {
  var controller = new AbortController();
  var timeoutId = setTimeout(function() { controller.abort(); }, REBOOT_FETCH_TIMEOUT);

  fetch("/api/config", { cache: "no-store", signal: controller.signal, headers: { "Connection": "close" } })
    .then(function(res) {
      clearTimeout(timeoutId);
      if (res.ok && _serverWentDown) {
        // Server is back after having been down — reboot is complete
        window.location.reload();
      } else if (res.ok && !_serverWentDown && (Date.now() - _rebootStartTime) < 90000) {
        // Server still responding but hasn't gone down yet — keep waiting
        setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
      } else if (res.ok) {
        // Been over 90 seconds and server is responding — just reload
        window.location.reload();
      } else {
        _serverWentDown = true;
        setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
      }
    })
    .catch(function() {
      clearTimeout(timeoutId);
      _serverWentDown = true;
      setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
    });
}
