document.addEventListener('DOMContentLoaded', () => {
    // Global pause state flag
    let isSessionPaused = false;
    let remainingSeconds = 0;

    function formatRemainingTime(totalSeconds) {
        const seconds = Math.max(0, Number(totalSeconds) || 0);
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainder = Math.floor(seconds % 60);
        return `${String(hours).padStart(2, '0')}h ${String(minutes).padStart(2, '0')}m ${String(remainder).padStart(2, '0')}s`;
    }

    function renderSessionActivities(activities) {
        const feedContainer = document.getElementById('customer-activity-feed');
        if (!feedContainer) return;

        feedContainer.replaceChildren();
        if (!Array.isArray(activities) || activities.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'text-muted small py-2';
            empty.textContent = 'No activities recorded.';
            feedContainer.appendChild(empty);
            return;
        }

        activities.forEach(activity => {
            const item = document.createElement('div');
            item.className = 'activity-item py-2 border-bottom d-flex justify-content-between align-items-center';

            const details = document.createElement('div');
            const title = document.createElement('strong');
            const action = String(activity.title || 'Session activity');
            title.className = `${action.toLowerCase().includes('pause') ? 'text-warning' : 'text-success'} d-block`;
            title.style.fontSize = '14px';
            title.textContent = action;

            const description = document.createElement('small');
            description.className = 'text-muted';
            description.style.fontSize = '12px';
            description.textContent = activity.description || 'Session activity';
            details.append(title, description);

            const timestamp = document.createElement('span');
            timestamp.className = 'text-muted small';
            timestamp.textContent = activity.timestamp || '-';
            item.append(details, timestamp);
            feedContainer.appendChild(item);
        });
    }

    function renderLoungeSessionState(sessionData) {
        const noSessionView = document.getElementById('no-active-session-view');
        const activeSessionView = document.getElementById('active-session-view');
        const isActive = Boolean(sessionData && sessionData.is_checked_in && sessionData.is_active !== false);

        if (!isActive) {
            remainingSeconds = 0;
            noSessionView?.classList.remove('d-none');
            activeSessionView?.classList.add('d-none');
            return;
        }

        noSessionView?.classList.add('d-none');
        activeSessionView?.classList.remove('d-none');

        const planName = document.getElementById('customer-plan-name');
        const countdown = document.getElementById('customer-countdown-timer');
        const statusBadge = document.getElementById('customer-status-badge');
        if (planName) planName.textContent = sessionData.plan_name || 'INDIVIDUAL RATE';
        remainingSeconds = Math.max(0, Number(sessionData.remaining_seconds) || 0);
        if (countdown) countdown.textContent = formatRemainingTime(remainingSeconds);
        if (statusBadge) {
            statusBadge.textContent = sessionData.is_paused ? 'Paused' : 'Checked In';
            statusBadge.className = sessionData.is_paused ? 'badge bg-warning text-dark' : 'badge bg-success';
        }
    }

    setInterval(() => {
        if (!isSessionPaused && remainingSeconds > 0) remainingSeconds -= 1;
        const countdown = document.getElementById('customer-countdown-timer');
        if (countdown) countdown.textContent = formatRemainingTime(remainingSeconds);
    }, 1000);

    // 1. Digital Clock
    function updateClock() {
        const now = new Date();
        const options = { 
            month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit', second: '2-digit',
            hour12: true 
        };
        const clockEl = document.getElementById('clock');
        if (clockEl) clockEl.textContent = now.toLocaleString('en-US', options);
        const liveTimeEl = document.getElementById('current-live-time');
        if (liveTimeEl) liveTimeEl.textContent = now.toLocaleString('en-US', options);
    }
    setInterval(updateClock, 1000);
    updateClock();

    // 2. Real-Time Status & Pause State Sync Engine
    function syncTimelogStatus() {
        fetch('/api/membership/status')
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data || data.status !== 'success') return;

                isSessionPaused = Boolean(data.is_paused);
                renderLoungeSessionState(data);
                renderSessionActivities(data.activities);

                // Update Status Badge (Active vs Paused vs Not Checked In)
                const statusBadge = document.getElementById('sessionStatusBadge');
                const timerDisplay = document.getElementById('sessionTimer');

                if (statusBadge) {
                    if (isSessionPaused) {
                        statusBadge.textContent = 'PAUSED';
                        statusBadge.className = 'badge bg-warning text-dark';
                    } else if (data.is_checked_in) {
                        statusBadge.textContent = 'ACTIVE';
                        statusBadge.className = 'badge bg-success';
                    } else {
                        statusBadge.textContent = 'NOT CHECKED IN';
                        statusBadge.className = 'badge bg-secondary';
                    }
                }

                if (timerDisplay) {
                    if (isSessionPaused) {
                        timerDisplay.style.color = '#f59e0b'; // Amber / Yellow
                    } else {
                        timerDisplay.style.color = ''; // Reset to default theme color
                    }
                }
            })
            .catch(err => console.error("Timelog sync error:", err));
    }

    // Auto-check pause status every 2 seconds
    syncTimelogStatus();
    setInterval(syncTimelogStatus, 2000);

    // 3. Automatic Session Timer Engine (With Pause-Freeze Support)
    function initSessionTimer() {
        const timerDisplay = document.getElementById('sessionTimer');
        if (!timerDisplay) return;

        let endTimeStr = timerDisplay.getAttribute('data-endtime');
        if (!endTimeStr) return;

        // Fix Safari/iOS Date Parsing compatibility issue
        endTimeStr = endTimeStr.replace(' ', 'T');
        let endTime = new Date(endTimeStr).getTime();

        if (isNaN(endTime)) {
            timerDisplay.textContent = "INVALID TIME";
            return;
        }

        const countdownInterval = setInterval(() => {
            // KON NAKA-PAUSED: I-freeze ang countdown kag indi na pag-i-advance ang offset
            if (isSessionPaused) {
                // Adjust dynamic end-time moving forward by 1 sec to freeze remaining time visually
                endTime += 1000; 
                return;
            }

            const now = Date.now();
            const distance = endTime - now;

            // Time calculations
            if (distance <= 0) {
                clearInterval(countdownInterval);
                timerDisplay.textContent = "SESSION ENDED";
                timerDisplay.style.color = "#EB3223";
                
                // Refresh page to sync backend session status
                setTimeout(() => { location.reload(); }, 2000);
            } else {
                const totalHours = Math.floor(distance / (1000 * 60 * 60));
                const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((distance % (1000 * 60)) / 1000);

                // Formatting with leading zeros
                const hDisplay = String(totalHours).padStart(2, '0');
                const mDisplay = String(minutes).padStart(2, '0');
                const sDisplay = String(seconds).padStart(2, '0');
                
                timerDisplay.textContent = `${hDisplay}:${mDisplay}:${sDisplay}`;
            }
        }, 1000);
    }
    initSessionTimer();

    // 4. Legacy/Fallback Status Tracker
    function updateStatus() {
        fetch('/get_time_inside')
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data) return;
                const statusText = document.getElementById('statusText');
                if (!statusText) return;

                if (data.status === 'inside') {
                    statusText.textContent = isSessionPaused ? 'Session Paused' : 'Session in Progress';
                    statusText.className = isSessionPaused ? 'status-paused' : 'status-inside';
                } else {
                    statusText.textContent = 'Awaiting Reservation';
                    statusText.className = 'status-muted';
                }
            })
            .catch(err => console.error("Status check error:", err));
    }

    if (!document.getElementById('sessionTimer')) {
        setInterval(updateStatus, 5000);
        updateStatus();
    }

    // 5. Safe Modal Controller
    const modal = document.getElementById('confirmModal');
    const btnCloseModal = document.getElementById('btnCloseModal');
    
    if (btnCloseModal && modal) {
        btnCloseModal.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    window.addEventListener('click', (event) => {
        if (modal && event.target === modal) {
            modal.style.display = 'none';
        }
    });
});