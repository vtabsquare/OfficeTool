let overlayEl = null;
let messageEl = null;
let activeCount = 0;
let fallbackTimer = null;

function ensureOverlay() {
  if (overlayEl && document.body.contains(overlayEl)) return overlayEl;

  overlayEl = document.createElement('div');
  overlayEl.id = 'global-submission-loading';
  overlayEl.className = 'submission-loading-overlay';
  overlayEl.setAttribute('aria-live', 'polite');
  overlayEl.setAttribute('aria-busy', 'true');
  overlayEl.innerHTML = `
    <div class="submission-loading-card" role="status">
      <div class="submission-loading-spinner" aria-hidden="true"></div>
      <div class="submission-loading-title">Submitting...</div>
      <div class="submission-loading-message">Please wait while we process your request.</div>
    </div>
  `;

  document.body.appendChild(overlayEl);
  messageEl = overlayEl.querySelector('.submission-loading-message');
  return overlayEl;
}

function clearFallbackTimer() {
  if (fallbackTimer) {
    clearTimeout(fallbackTimer);
    fallbackTimer = null;
  }
}

export function showSubmissionLoading(message = 'Please wait while we process your request.') {
  const overlay = ensureOverlay();
  activeCount += 1;
  if (messageEl) messageEl.textContent = message;
  overlay.classList.add('visible');
  clearFallbackTimer();
  fallbackTimer = setTimeout(() => {
    activeCount = 0;
    overlay.classList.remove('visible');
    clearFallbackTimer();
  }, 30000);
}

export function hideSubmissionLoading(force = false) {
  if (!overlayEl) return;
  activeCount = force ? 0 : Math.max(0, activeCount - 1);
  if (activeCount > 0) return;
  overlayEl.classList.remove('visible');
  clearFallbackTimer();
}

export async function runWithSubmissionLoading(task, message) {
  showSubmissionLoading(message);
  try {
    return await task();
  } finally {
    hideSubmissionLoading();
  }
}
