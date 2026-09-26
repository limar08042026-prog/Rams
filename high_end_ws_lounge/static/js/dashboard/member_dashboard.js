document.addEventListener('DOMContentLoaded', function() {
    // 1. Live Clock with Date (PHT Synchronized local display)
    function updateClock() {
        const now = new Date();
        const options = { 
            month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit', second: '2-digit',
            hour12: true 
        };
        const timeString = now.toLocaleString('en-US', options);
        const clockEl = document.getElementById('dashboardClock');
        if (clockEl) clockEl.textContent = timeString;
    }
    setInterval(updateClock, 1000);
    updateClock();

    // Persistent Membership Expiry Countdown with localStorage
    function initMembershipExpiryCountdown() {
        const countdownEl = document.getElementById('membershipExpiryCountdown');
        if (!countdownEl) return;

        const expiryISO = countdownEl.dataset.expiry;
        const membershipId = countdownEl.dataset.membershipId;

        if (!expiryISO || expiryISO === 'None' || expiryISO === '') {
            countdownEl.textContent = 'N/A';
            return;
        }

        if (membershipId) {
            localStorage.setItem(`membership_expiry_${membershipId}`, expiryISO);
        }
        countdownEl.setAttribute('data-remaining-source', 'session-timer');
    }

    // Automatic Run
    initMembershipExpiryCountdown();

    // 2. Typewriter Effect
    const nameSpan = document.getElementById('userName');
    if (nameSpan) {
        const fullText = nameSpan.textContent; 
        nameSpan.textContent = '';
        let i = 0;
        let isDeleting = false;

        function type() {
            const currentText = isDeleting ? fullText.substring(0, i--) : fullText.substring(0, i++);
            nameSpan.textContent = currentText;

            if (!isDeleting && i > fullText.length) {
                setTimeout(() => { isDeleting = true; type(); }, 3000);
            } 
            else if (isDeleting && i < 0) {
                isDeleting = false;
                i = 0;
                setTimeout(type, 500);
            } 
            else {
                setTimeout(type, isDeleting ? 50 : 100);
            }
        }
        setTimeout(type, 1000);
    }

        const welcomeEl = document.querySelector('.welcome-text');
        if (welcomeEl) {
            welcomeEl.style.opacity = '0';
            welcomeEl.style.transform = 'translateX(-10px)';
            setTimeout(() => {
                welcomeEl.style.transition = 'all 0.45s ease-out';
                welcomeEl.style.opacity = '1';
                welcomeEl.style.transform = 'translateX(0)';
            }, 400);
        }

    // 4. SEARCH AND FILTER FUNCTIONALITY
    const searchInput = document.getElementById('reservationSearch');
    const statusFilter = document.getElementById('statusFilter');

    function filterTable() {
        const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';
        const filterValue = statusFilter ? statusFilter.value.toLowerCase().trim() : 'all';

        // 1. Filter Table Rows
        const tableRows = document.querySelectorAll('#reservationTable tbody tr, table .filterable-row');
        tableRows.forEach(row => {
            const text = row.innerText.toLowerCase();
            const rowStatusAttr = (row.getAttribute('data-status') || '').toLowerCase().trim();
            const statusBadge = row.querySelector('.status-badge, .badge');
            const badgeText = statusBadge ? statusBadge.innerText.toLowerCase().trim() : '';
            const status = rowStatusAttr || badgeText;

            const matchesSearch = text.includes(searchTerm);
            
            let matchesFilter = (filterValue === 'all' || filterValue === 'all status' || status.includes(filterValue));

            if (filterValue === 'ended' || filterValue === 'completed') {
                matchesFilter = (status.includes('ended') || status.includes('completed') || status.includes('expired'));
            } else if (filterValue === 'confirmed' || filterValue === 'approved') {
                matchesFilter = (status.includes('approved') || status.includes('confirmed') || status.includes('active'));
            } else {
                matchesFilter = (filterValue === 'all' || filterValue === 'all status' || status.includes(filterValue));
            }

            if (matchesSearch && matchesFilter) {
                row.style.setProperty('display', '', 'important');
            } else {
                row.style.setProperty('display', 'none', 'important');
            }
        });

        // 2. Filter Solo Plans Cards
        const planCards = document.querySelectorAll('.plan-card, .solo-plan-card, div.filterable-row, .reservations-section .card');
        planCards.forEach(card => {
            if (card.closest('.member-stats-grid') || card.classList.contains('stat-card')) return;

            const text = card.innerText.toLowerCase();
            const cardStatusAttr = (card.getAttribute('data-status') || '').toLowerCase().trim();
            const badgeEl = card.querySelector('.badge, .status-badge, [class*="badge"]');
            const badgeText = badgeEl ? badgeEl.innerText.toLowerCase().trim() : '';
            const status = cardStatusAttr || badgeText;

            const matchesSearch = text.includes(searchTerm);
            
            let matchesFilter = (filterValue === 'all' || filterValue === 'all status' || status.includes(filterValue));

            if (filterValue === 'ended' || filterValue === 'completed') {
                matchesFilter = (status.includes('ended') || status.includes('completed') || status.includes('expired'));
            } else if (filterValue === 'confirmed' || filterValue === 'approved') {
                matchesFilter = (status.includes('approved') || status.includes('confirmed') || status.includes('active'));
            }

            if (matchesSearch && matchesFilter) {
                card.style.setProperty('display', '', 'important');
            } else {
                card.style.setProperty('display', 'none', 'important');
            }
        });
    }

    if (searchInput) searchInput.addEventListener('input', filterTable);
    if (statusFilter) statusFilter.addEventListener('change', filterTable);

    // 5. Delete Plan Action Event Listener
    document.addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('delete-plan-btn')) {
            const btn = e.target;
            const planId = btn.getAttribute('data-plan-id');
            const cardElement = btn.closest('.filterable-row');

            if (confirm('Are you sure you want to delete this plan?')) {
                if (cardElement) {
                    cardElement.style.transition = 'all 0.3s ease';
                    cardElement.style.opacity = '0';
                    setTimeout(() => {
                        cardElement.remove();
                    }, 300);
                }
            }
        }
    });
    
    // 5. EXPORT TO CSV
    const exportBtn = document.getElementById('exportCSV');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            let csv = [];
            const rows = document.querySelectorAll("#reservationTable tr");
            
            for (let i = 0; i < rows.length; i++) {
                if (rows[i].style.display !== "none") {
                    let row = [], cols = rows[i].querySelectorAll("td, th");
                    for (let j = 0; j < cols.length; j++) {
                        let cellText = cols[j].innerText.trim().replace(/\n/g, ' '); 
                        row.push('"' + cellText + '"');
                    }
                    csv.push(row.join(","));
                }
            }

            const csvFile = new Blob(["\uFEFF" + csv.join("\n")], {type: "text/csv;charset=utf-8;"}); // \uFEFF para sa Excel UTF-8 support
            const downloadLink = document.createElement("a");
            downloadLink.download = `WSLounge_Reservations_${new Date().toLocaleDateString()}.csv`;
            downloadLink.href = window.URL.createObjectURL(csvFile);
            downloadLink.style.display = "none";
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);
        });
    }

    function showEmptyAttendanceState() {
        const tableBody = document.querySelector('#recent-attendance-tbody')
            || document.querySelector('#recent-attendance-table tbody');
        if (!tableBody) return;

        tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4" style="font-size: 13px;"><em>No recent attendance history available.</em></td></tr>';
    }

    document.querySelectorAll('.attendance-delete-button').forEach((button) => {
        button.addEventListener('click', async () => {
            const logId = button.dataset.attendanceId;
            if (!logId || !window.confirm('Remove this attendance record from your view?')) return;

            button.disabled = true;
            try {
                const response = await fetch(`/api/customer/attendance/${logId}/delete`, { method: 'DELETE' });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.message || 'Unable to remove attendance record.');

                document.getElementById(`attendance-row-${logId}`)?.remove();
                if (!document.querySelector('#recent-attendance-tbody tr')) showEmptyAttendanceState();
            } catch (error) {
                button.disabled = false;
                console.error('Error deleting attendance record:', error);
            }
        });
    });

    const clearAttendanceButton = document.getElementById('btn-clear-all-attendance');
    if (clearAttendanceButton) {
        clearAttendanceButton.addEventListener('click', async () => {
            if (!window.confirm('Are you sure you want to clear all attendance history?')) return;

            clearAttendanceButton.disabled = true;
            try {
                const response = await fetch('/api/customer/attendance/clear-all', { method: 'DELETE' });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.message || 'Unable to clear attendance history.');
                showEmptyAttendanceState();
            } catch (error) {
                console.error('Error clearing attendance history:', error);
            } finally {
                clearAttendanceButton.disabled = false;
            }
        });
    }

    // 6. Notification System
    function showNotification(message) {
    const container = document.getElementById('notificationContainer');
    if (container) {
        if (container.children.length > 0) return;

        const toast = document.createElement('div');
        toast.className = 'status-badge badge-pending';
        toast.style.padding = '15px';
        toast.style.marginBottom = '10px';
        toast.style.boxShadow = '0 4px 10px rgba(0,0,0,0.1)';
        toast.style.display = 'block';
        toast.innerHTML = `<i class="fas fa-bell"></i> ${message}`;
        
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 500);
        }, 5000);
    }
}

    let hasShownExpiringWarning = false;

    function checkExpiringSessionNotification() {
        const countdownEl = document.getElementById('membershipExpiryCountdown');
        const container = document.getElementById('notificationContainer');

        if (!countdownEl) return;

        const rawCheckedIn = (countdownEl.getAttribute('data-is-checked-in') || '').toString().toLowerCase().trim();
        const isCheckedIn = (rawCheckedIn === 'true' || rawCheckedIn === '1');

        const rawPaused = (countdownEl.getAttribute('data-is-paused') || '').toString().toLowerCase().trim();
        const isPaused = (rawPaused === 'true' || rawPaused === '1');

        if (!isCheckedIn || isPaused) {
            if (container) container.innerHTML = '';
            hasShownExpiringWarning = false;
            return;
        }

        const remainingSeconds = parseInt(countdownEl.getAttribute('data-remaining-seconds')) || 0;

        const THRESHOLD_SECONDS = 900; 

        if (remainingSeconds > 0 && remainingSeconds <= THRESHOLD_SECONDS) {
            if (!hasShownExpiringWarning) {
                showNotification("YOUR PLAN IS EXPIRING SOON! RENEW NOW TO KEEP ACCESS.");
                hasShownExpiringWarning = true;
            }
        } else {
            if (container && remainingSeconds > THRESHOLD_SECONDS) {
                container.innerHTML = '';
            }
        }
    }

  // === 7. SESSION DURATION & LIVE TIMER ENGINE ===
    const membershipCard = document.getElementById('membershipCard');
    let sessionIntervalId = null;
    let liveMembershipCountdownInterval = null;
    let lastRenderedMembershipRemainingSeconds = null;
    const previousMemberState = {
        isCheckedIn: null,
        membershipStatus: null,
        isInitialized: false,
        reloadRequested: false,
    };

    function formatMembershipTimestamp(isoValue) {
        const timestamp = parseISOToTimestamp(isoValue);
        if (!timestamp) return null;
        return new Date(timestamp).toLocaleString('en-US', {
            month: 'long',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
    }

    function renderLiveMembershipCountdown(totalSeconds) {
        const countdownEl = document.getElementById('membershipExpiryCountdown');
        const remainingHoursEl = document.querySelector('#remainingHours .hours-value');
        const safeSeconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
        const formatted = formatHMS(safeSeconds);
        const hours = Math.floor(safeSeconds / 3600);
        const minutes = Math.floor((safeSeconds % 3600) / 60);
        const seconds = safeSeconds % 60;

        if (countdownEl) countdownEl.textContent = formatted;
        if (remainingHoursEl) remainingHoursEl.textContent = `${hours}h ${minutes}m ${seconds}s`;
    }

    function startLiveMembershipCountdown(endTimeIso, isPaused = false) {
        if (liveMembershipCountdownInterval) {
            clearInterval(liveMembershipCountdownInterval);
            liveMembershipCountdownInterval = null;
        }

        if (isPaused) {
            return;
        }

        const targetEpochMs = new Date(endTimeIso || '').getTime();
        if (!Number.isFinite(targetEpochMs)) return;

        const updateTick = () => {
            const remainingSeconds = Math.max(0, Math.floor((targetEpochMs - Date.now()) / 1000));
            lastRenderedMembershipRemainingSeconds = remainingSeconds;
            renderLiveMembershipCountdown(remainingSeconds);
            if (remainingSeconds <= 0 && liveMembershipCountdownInterval) {
                clearInterval(liveMembershipCountdownInterval);
                liveMembershipCountdownInterval = null;
            }
        };

        updateTick();
        if (!isPaused) {
            liveMembershipCountdownInterval = setInterval(updateTick, 1000);
        }
    }

    function stopLiveMembershipCountdown() {
        if (liveMembershipCountdownInterval) {
            clearInterval(liveMembershipCountdownInterval);
            liveMembershipCountdownInterval = null;
        }
    }

    // Helper formatting functions
    function formatHMS(seconds) {
        if (!seconds || seconds < 0) seconds = 0;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    // Helper to safely parse dates with fallback for Naive ISO strings
    function parseISOToTimestamp(isoStr) {
        if (!isoStr || isoStr === 'None' || isoStr === '' || isoStr === 'null' || isoStr === 'undefined') return null;
        
        let formattedStr = isoStr;
        if (!isoStr.includes('Z') && !isoStr.includes('+') && !isoStr.includes('-')) {
            formattedStr = isoStr + '+08:00';
        }
        const dt = new Date(formattedStr).getTime();
        return isNaN(dt) ? null : dt;
    }

    // Core calculation & rendering function
    function updateSessionTimer() {
        const timerContainer = document.getElementById('sessionTimerContainer');
        if (!timerContainer) return;

        // Attributes reading
        const checkInTimeISO = timerContainer.getAttribute('data-checkin-time');
        const pausedAtISO = timerContainer.getAttribute('data-paused-at');
        const accumulatedPausedSec = parseFloat(timerContainer.getAttribute('data-accumulated-paused')) || 0;

        const rawPaused = (timerContainer.getAttribute('data-is-paused') || '').toString().toLowerCase().trim();
        const isPaused = (rawPaused === 'true' || rawPaused === '1');

        const checkInDate = parseISOToTimestamp(checkInTimeISO);
        if (!checkInDate) return;

        let netElapsedSeconds = 0;
        
        if (isPaused) {
            const pausedDate = parseISOToTimestamp(pausedAtISO);

            if (pausedDate) {
                const rawElapsedSec = Math.floor((pausedDate - checkInDate) / 1000);
                netElapsedSeconds = Math.max(0, rawElapsedSec - accumulatedPausedSec);
            } else {
                if (!timerContainer.hasAttribute('data-frozen-seconds')) {
                const currentRaw = Math.floor((Date.now() - checkInDate) / 1000);
                const frozenVal = Math.max(0, currentRaw - accumulatedPausedSec);
                timerContainer.setAttribute('data-frozen-seconds', frozenVal.toString());
            }
            netElapsedSeconds = parseFloat(timerContainer.getAttribute('data-frozen-seconds')) || 0;
        }
        } else {
            timerContainer.removeAttribute('data-frozen-seconds');
            const rawElapsedSec = Math.floor((Date.now() - checkInDate) / 1000);
            netElapsedSeconds = Math.max(0, rawElapsedSec - accumulatedPausedSec);
        }

        // Update UI Elements
        const sessionTimer = document.getElementById('sessionTimer') || document.getElementById('session_duration_display');
        const hoursSpent = document.getElementById('hoursSpent');

        if (sessionTimer) {
            sessionTimer.textContent = formatHMS(netElapsedSeconds);
            if (isPaused) {
                sessionTimer.style.color = '#f59e0b'; // Amber/Yellow
            } else {
                sessionTimer.style.color = '';
            }
        }

        if (hoursSpent) {
            const h = Math.floor(netElapsedSeconds / 3600);
            const m = Math.floor((netElapsedSeconds % 3600) / 60);
            hoursSpent.textContent = `${h}h ${m}m`;
        }

        // === DYNAMIC REMAINING TIME FORMAT (Base on Actual Customer Plan) ===
        const remainingHoursEl = document.getElementById('remainingHours');
        if (remainingHoursEl) {            

            const planTotalHours = parseFloat(timerContainer?.getAttribute('data-plan-hours')) || 0;
            const planTotalSeconds = planTotalHours * 3600;
            const remainingSec = Math.max(0, planTotalSeconds - netElapsedSeconds);

            const remH = Math.floor(remainingSec / 3600);
            const remM = Math.floor((remainingSec % 3600) / 60);
            const remS = Math.floor(remainingSec % 60);

            const formattedRemainingStr = `${remH}h ${remM}m ${remS}s`;

            const hoursValueSpan = remainingHoursEl.querySelector('.hours-value');
            if (hoursValueSpan) {
                hoursValueSpan.textContent = formattedRemainingStr;
            } else {
                remainingHoursEl.textContent = formattedRemainingStr;
            }

            const countdownEl = document.getElementById('membershipExpiryCountdown');
            if (countdownEl) {
                countdownEl.textContent = formattedRemainingStr;
                countdownEl.setAttribute('data-remaining-seconds', Math.floor(remainingSec).toString());
                countdownEl.style.color = '#e53e3e';
                countdownEl.style.fontWeight = 'bold';
            }
        }
    }

    // Interval Controller Engine (Starts or Stops timer cleanly)
    function refreshTimerIntervalState() {
        const timerContainer = document.getElementById('sessionTimerContainer');
        
        // Clear existing interval always to prevent duplicate loops
        if (sessionIntervalId) {
            clearInterval(sessionIntervalId);
            sessionIntervalId = null;
        }

        if (!timerContainer) return;

        const rawPaused = (timerContainer.getAttribute('data-is-paused') || '').toString().toLowerCase().trim();
        const isPaused = (rawPaused === 'true' || rawPaused === '1');

        // Render once immediately
        updateSessionTimer();

        // STRICT CHECK: Mag-start lang sang 1-second interval kon ACTIVE (NOT PAUSED)
        if (!isPaused) {
            sessionIntervalId = setInterval(updateSessionTimer, 1000);
        }
    }

    // Engine Initialization
    function initSessionTimerEngine() {
        refreshTimerIntervalState();
    }

    // Automatic Initialization on DOM Load
    document.addEventListener('DOMContentLoaded', initSessionTimerEngine);

   // === 8. API LIVE POLLING & SYNC ENGINE ===
    async function syncSessionStatus() {
        if (!membershipCard) return;

        try {
            // 1. Fetch membership overall status
            const statusRes = await fetch('/api/membership/status');
            if (!statusRes.ok) return;
            const statusData = await statusRes.json();

            const isNoMembership = statusData.status === 'error'
                && statusData.message === 'No membership found';
            if (statusData.status !== 'success' && !isNoMembership) return;

            const currentMemberState = {
                isCheckedIn: Boolean(statusData.is_checked_in),
                membershipStatus: String(
                    statusData.membership_status
                    || statusData.member_status
                    || (isNoMembership ? 'NONE' : 'UNKNOWN')
                ).toUpperCase(),
            };

            if (!previousMemberState.isInitialized) {
                previousMemberState.isCheckedIn = currentMemberState.isCheckedIn;
                previousMemberState.membershipStatus = currentMemberState.membershipStatus;
                previousMemberState.isInitialized = true;
            } else {
                const checkInChanged = previousMemberState.isCheckedIn !== currentMemberState.isCheckedIn;
                const statusChanged = previousMemberState.membershipStatus !== currentMemberState.membershipStatus;

                previousMemberState.isCheckedIn = currentMemberState.isCheckedIn;
                previousMemberState.membershipStatus = currentMemberState.membershipStatus;

                if ((checkInChanged || statusChanged) && !previousMemberState.reloadRequested) {
                    previousMemberState.reloadRequested = true;
                    window.location.reload();
                    return;
                }
            }

            if (isNoMembership) return;

            const planNameEl = document.querySelector('#membershipCard .membership-plan');
            if (planNameEl && statusData.plan_name) {
                planNameEl.textContent = statusData.plan_name;
            }

            const totalHoursEl = document.querySelector('#totalHours .hours-value');
            const remainingHoursEl = document.querySelector('#remainingHours .hours-value');
            const formatHours = (seconds) => {
                const totalSeconds = Math.max(0, Math.round(Number(seconds) || 0));
                const hours = Math.floor(totalSeconds / 3600);
                const minutes = Math.floor((totalSeconds % 3600) / 60);
                const remainder = totalSeconds % 60;
                return `${hours}h ${minutes}m ${remainder}s`;
            };
            if (totalHoursEl && statusData.total_seconds !== undefined) {
                totalHoursEl.textContent = formatHours(statusData.total_seconds);
            }
            if (remainingHoursEl && !statusData.is_checked_in && statusData.total_seconds !== undefined) {
                remainingHoursEl.textContent = formatHours(statusData.total_seconds);
            }

            const dashboardStatus = (statusData.member_status || '').toUpperCase();
            const statusDetail = Array.from(document.querySelectorAll('#membershipCard .detail-item'))
                .find((item) => item.querySelector('label')?.textContent.trim().toLowerCase() === 'status');
            const detailStatusBadge = statusDetail?.querySelector('.badge');
            if (detailStatusBadge) {
                if (dashboardStatus === 'PAUSED' || statusData.is_paused) {
                    detailStatusBadge.className = 'badge bg-warning text-dark';
                    detailStatusBadge.textContent = '⏸ Session Paused';
                } else if (statusData.is_checked_in) {
                    detailStatusBadge.className = 'badge bg-success';
                    detailStatusBadge.textContent = '✓ Checked In';
                } else {
                    detailStatusBadge.className = 'badge bg-secondary';
                    detailStatusBadge.textContent = 'Not Checked In';
                }
            }

            const membershipBadge = document.querySelector('#membershipCard .membership-badge');
            if (membershipBadge) {
                membershipBadge.classList.toggle('active', Boolean(statusData.is_checked_in || statusData.is_active));
                membershipBadge.classList.toggle('expired', !statusData.is_checked_in && !statusData.is_active);
                membershipBadge.textContent = statusData.is_checked_in ? 'IN LOUNGE' : 'READY TO CHECK IN';
            }

            // Update Badge Status sa Screen
            const statusBadge = document.querySelector('.detail-value .badge, .status-badge');
            if (statusBadge) {
                const isExpiredOrZero = statusData.hours_left <= 0 || !statusData.is_active;

                if (!statusData.is_checked_in) {
                    statusBadge.className = 'badge bg-secondary';
                    statusBadge.textContent = 'Not Checked In';
                } else if (statusData.is_paused) {
                    statusBadge.className = 'badge bg-warning text-dark';
                    statusBadge.textContent = '⏸ Session Paused';
                } else {
                    statusBadge.className = 'badge bg-success';
                    statusBadge.textContent = '✓ Checked In';
                }
            }

            // Sync Expiry Countdown Attributes
            const countdownEl = document.getElementById('membershipExpiryCountdown');
            if (countdownEl) {
                countdownEl.setAttribute('data-is-checked-in', statusData.is_checked_in ? 'true' : 'false');
                const isPaused = statusData.member_status === 'PAUSED' || statusData.is_paused;
                countdownEl.setAttribute('data-is-paused', isPaused ? 'true' : 'false');
                countdownEl.setAttribute('data-member-status', statusData.member_status || '');
            }

            // Sync Session Timer Attributes
            const timerContainer = document.getElementById('sessionTimerContainer');
            if (timerContainer) {
                const isPaused = statusData.member_status === 'PAUSED' || statusData.is_paused;
                timerContainer.setAttribute('data-is-paused', isPaused ? 'true' : 'false');
            }

            // 2. Fetch Active Session Elapsed Time
            if (statusData.is_checked_in) {
                const sessionRes = await fetch('/api/membership/current-session');
                if (sessionRes.ok) {
                    const sessionData = await sessionRes.json();
                    if (sessionData.status === 'success' && timerContainer) {
                        
                        // Sync Timestamps sa Container para saligan sang Section 7
                        if (sessionData.check_in_time) {
                            timerContainer.setAttribute('data-checkin-time', sessionData.check_in_time);
                        }
                        if (sessionData.paused_at) {
                            timerContainer.setAttribute('data-paused-at', sessionData.paused_at);
                        }
                        if (sessionData.accumulated_paused_seconds !== undefined) {
                            timerContainer.setAttribute('data-accumulated-paused', sessionData.accumulated_paused_seconds);
                        } else if (sessionData.accumulated_paused_sec !== undefined) {
                            timerContainer.setAttribute('data-accumulated-paused', sessionData.accumulated_paused_sec);
                        }

                        // Trigger smooth timer interval check nga wala nagaguba sang UI
                        if (typeof refreshTimerIntervalState === 'function') {
                            refreshTimerIntervalState();
                        } else if (typeof updateSessionTimer === 'function') {
                            updateSessionTimer();
                        }
                    }

                    if (sessionData.status === 'success') {
                        const startedOnEl = document.getElementById('startedOnDisplay');
                        const expiresOnEl = document.getElementById('expiresOnDisplay');
                        const startedText = formatMembershipTimestamp(sessionData.check_in_time);
                        const expiresText = formatMembershipTimestamp(statusData.expiry_date);

                        if (startedOnEl && startedText) startedOnEl.textContent = startedText;
                        if (expiresOnEl && expiresText) expiresOnEl.textContent = expiresText;

                        if (countdownEl) {
                            countdownEl.setAttribute('data-expiry', statusData.expiry_date || '');
                        }
                        startLiveMembershipCountdown(
                            countdownEl?.getAttribute('data-expiry') || statusData.expiry_date,
                            Boolean(statusData.is_paused || statusData.member_status === 'PAUSED')
                        );
                    }
                }
            } else {
                // Kon wala nakacheck-in, reset attributes & DOM displays
                if (sessionIntervalId) {
                    clearInterval(sessionIntervalId);
                    sessionIntervalId = null;
                }
                stopLiveMembershipCountdown();
                if (timerContainer) {
                    timerContainer.setAttribute('data-is-paused', 'false');
                    timerContainer.removeAttribute('data-checkin-time');
                    timerContainer.removeAttribute('data-paused-at');
                    timerContainer.setAttribute('data-accumulated-paused', '0');
                }

                const sessionTimer = document.getElementById('sessionTimer') || document.getElementById('session_duration_display');
                if (sessionTimer) sessionTimer.textContent = '00:00:00';

                const countdownEl = document.getElementById('membershipExpiryCountdown');
                if (countdownEl) {
                    countdownEl.textContent = '--:--:--';
                    countdownEl.setAttribute('data-remaining-seconds', '0');
                    countdownEl.style.color = '#718096';
                }

                const remainingHoursEl = document.getElementById('remainingHours');
                if (remainingHoursEl) {
                    const hoursValue = remainingHoursEl.querySelector('.hours-value');
                    if (hoursValue) hoursValue.textContent = '0h 0m 0s';
                }
                lastRenderedMembershipRemainingSeconds = 0;

                const hoursSpent = document.getElementById('hoursSpent');
                if (hoursSpent) hoursSpent.textContent = '0h 0m';
            }

            // Dynamic update sang total plan hours nga gina-avail sang customer
            if (statusData.plan_hours || statusData.total_plan_hours || statusData.hours_left) {
                const actualPlanHours = parseFloat(statusData.plan_hours || statusData.total_plan_hours || statusData.hours_left) || 0;
                const timerContainer = document.getElementById('sessionTimerContainer');
                if (timerContainer) {
                    timerContainer.setAttribute('data-plan-hours', actualPlanHours.toString());
                }
            }

            const startedOnEl = document.getElementById('startedOnDisplay');
            if (startedOnEl && statusData.check_in_time) {
                const startDate = parseISOToTimestamp(statusData.check_in_time);
                if (startDate) {
                    const dt = new Date(startDate);
                    const options = { month: 'long', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true };
                    startedOnEl.textContent = dt.toLocaleDateString('en-US', options);
                }
            }

            const expiresOnEl = document.getElementById('expiresOnDisplay') || document.querySelector('.expires-on-display');
            if (expiresOnEl && statusData.expiry_date) {
                const expDate = new Date(statusData.expiry_date);
                if (!isNaN(expDate.getTime())) {
                    const formattedDateStr = expDate.toLocaleDateString('en-US', {
                        month: 'long',
                        day: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true
                    });
                    expiresOnEl.textContent = formattedDateStr;
                }
            }

        } catch (err) {
            console.error('Error syncing status with admin database:', err);
        }
    }

    // Auto-sync kada 2 ka segundo para instant feedback sa Admin actions
    if (membershipCard) {
        syncSessionStatus();
        setInterval(syncSessionStatus, 2000);
    }
});