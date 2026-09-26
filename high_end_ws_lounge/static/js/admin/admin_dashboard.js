const socket = (typeof io !== 'undefined') ? io() : null;

document.addEventListener('DOMContentLoaded', function() {
    console.log("Admin Dashboard Modern UI Active", socket ? "+ SocketIO" : "(no socket)");

    // Welcome typewriter effect (mirror of member dashboard)
    const adminNameSpan = document.getElementById('adminUserName');
    if (adminNameSpan) {
        const fullText = adminNameSpan.textContent;
        adminNameSpan.textContent = '';
        let i = 0;
        let isDeleting = false;

        function typeAdmin() {
            const currentText = isDeleting ? fullText.substring(0, i--) : fullText.substring(0, i++);
            adminNameSpan.textContent = currentText;

            if (!isDeleting && i > fullText.length) {
                setTimeout(() => { isDeleting = true; typeAdmin(); }, 3000);
            } else if (isDeleting && i < 0) {
                isDeleting = false;
                i = 0;
                setTimeout(typeAdmin, 500);
            } else {
                setTimeout(typeAdmin, isDeleting ? 50 : 100);
            }
        }
        setTimeout(typeAdmin, 800);
    }

    if (socket) {
        socket.on('new_reservation', function(data) {
            console.log('New reservation via socket:', data);
            // Only refresh dashboard for active sessions
            try {
                const activeStatuses = ['Checked-In', 'Walk-in', 'Active'];
                if (data && activeStatuses.includes(data.status)) {
                    try { showToast(`Now Active: ${data.customer} in ${data.room} (ID: ${data.id})`, 'info'); } catch (e) {}
                    location.reload();
                } else {
                    console.log('Reservation update (non-active) ignored for full reload:', data.status);
                }
            } catch (e) {
                console.error('Socket handler error', e);
            }
        });
    }
    
    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        return `(${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')})`;
    }

    function parseIsoDate(dateStr) {
        if (!dateStr) return null;
        let cleanStr = dateStr.trim();
        if (!cleanStr.endsWith('Z') && !cleanStr.includes('+') && !cleanStr.includes('-')) {
            cleanStr = cleanStr.replace(' ', 'T');
        }
        const parsed = new Date(cleanStr);
        return isNaN(parsed.getTime()) ? null : parsed;
    }

    if (typeof sessionInitialOffsets === 'undefined') {
        var sessionInitialOffsets = {};
    }

    function updateTimers() {
        const timers = document.querySelectorAll('.timer-text');
        const cards = document.querySelectorAll('.room-card');
        const now = new Date();
        let newlyExpired = false;

        // 1. Live Timers & Remaining Timers
        timers.forEach(timer => {
            const card = timer.closest('.room-card');
            const isPaused = (card && card.getAttribute('data-is-paused') === 'true') || timer.getAttribute('data-is-paused') === 'true';
            const startStr = timer.getAttribute('data-starttime');
            const endStr = timer.getAttribute('data-endtime');
            const remainingElem = card ? card.querySelector('.remaining-text') : null;

            // Kuhaon kon Open Time bala
            const isOpenTime = (card && card.getAttribute('data-isopentime') === 'true') || timer.getAttribute('data-isopentime') === 'true';

            // [BAG-O]: Kuhaon ang accumulated paused seconds gikan sa database attribute
            const accumPausedSecs = parseInt(
                timer.getAttribute('data-accumulated-paused-seconds') || 
                (card ? card.getAttribute('data-accumulated-paused-seconds') : '0'), 10
            ) || 0;

            if (!startStr) {
                timer.textContent = "(00:00:00)";
                if (remainingElem) remainingElem.textContent = "(00:00:00)";
                return;
            }

            const startTime = parseIsoDate(startStr);
            const endTime = parseIsoDate(endStr);

            if (!startTime) {
                timer.textContent = '(00:00:00)';
                return;
            }

            const endRow = Array.from(card?.querySelectorAll('.info-row') || [])
                .find(row => row.querySelector('.info-label')?.textContent.trim().toLowerCase() === 'end');
            const endValue = endRow?.querySelector('.info-value');
            if (endValue && endTime) {
                endValue.textContent = endTime.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true
                });
            }

            // Stop Live Timer when session has ended
            if (!isOpenTime && endTime && now >= endTime) {
                timer.textContent = '(EXPIRED)';

                if (remainingElem) {
                    remainingElem.textContent = '(EXPIRED)';
                    remainingElem.style.color = '#b91c1c';
                }

                return;
            }
            const timerKey = startStr + (endStr || '');

            // Standard Initial Calibration (Para lang sa bag-o gid nag-start nga session)
            if (!(timerKey in sessionInitialOffsets)) {
                sessionInitialOffsets[timerKey] = 0;
            }

            const clockOffset = sessionInitialOffsets[timerKey] || 0;

            // ==========================================
            // KON NAKA-PAUSE
            // ==========================================
            if (isPaused) {
                const pausedAtStr = timer.getAttribute('data-pausedat') || (card ? card.getAttribute('data-pausedat') : null);
                let freezeEndTime = now;
                
                if (pausedAtStr) {
                    freezeEndTime = parseIsoDate(pausedAtStr) || now;
                }

                const pausedElapsed = Math.max(
                    0,
                    Math.floor((freezeEndTime - startTime) / 1000) - clockOffset - accumPausedSecs
                );

                timer.textContent = `${formatTime(pausedElapsed)} ⏸ (PAUSED)`;

                if (remainingElem && endTime) {
                    const pausedRemaining = Math.max(0, Math.floor((endTime - freezeEndTime) / 1000) + clockOffset);
                    remainingElem.textContent = `${formatTime(pausedRemaining)} ⏸`;
                }
                return;
            }

            // ==========================================
            // KON RUNNING / RESUMED (Active State)
            // ==========================================
            const rawElapsed = Math.floor((now - startTime) / 1000) - clockOffset;
            
            // Both session types display active elapsed time, excluding prior pauses.
            timer.textContent = formatTime(Math.max(0, rawElapsed - accumPausedSecs));

            // Active remaining time (Para sa Fixed Time)
            if (remainingElem && endTime) {
                const remaining = Math.max(0, Math.floor((endTime - now) / 1000) + clockOffset);
                remainingElem.textContent = formatTime(remaining);
                
                if (remaining <= 300 && remaining > 0) {
                    remainingElem.style.color = "#ef4444"; 
                } else if (remaining === 0) {
                    remainingElem.textContent = "(EXPIRED)";
                    remainingElem.style.color = "#b91c1c";
                } else {
                    remainingElem.style.color = "#2563eb";
                }
            }
        });

        // 2. Expired Checkers
        cards.forEach(card => {
            const endStr = card.getAttribute('data-endtime') || (card.querySelector('.timer-text') ? card.querySelector('.timer-text').getAttribute('data-endtime') : null);
            const isOpenTime = card.getAttribute('data-isopentime') === 'true';
            const isPaused = card.getAttribute('data-is-paused') === 'true';

            if (isPaused) {
                card.classList.remove('session-expired');
                return;
            }

            if (endStr && !isOpenTime) {
                const endTime = parseIsoDate(endStr);
                if (endTime && now >= endTime) {
                    if (!card.classList.contains('session-expired')) {
                        card.classList.add('session-expired');
                        newlyExpired = true;
                    }
                } else {
                    card.classList.remove('session-expired');
                }
            }
        });

        if (newlyExpired && typeof sortExpiredCards === 'function') {
            sortExpiredCards();
        }
    }

    // Loop Initialization
    updateTimers();
    setInterval(updateTimers, 1000);
    window.updateAdminDashboardTimers = updateTimers;

    // PAUSE BUTTON TRANSITION
    function handlePauseTransition(event, formElement) {
        event.preventDefault();

        const btn = formElement.querySelector('button[type="submit"]');
        if (btn) {
            btn.innerHTML = "⏸ Pausing...";
            btn.style.backgroundColor = "#ffc107";
            btn.style.color = "#000";
            btn.disabled = true;
        }

        setTimeout(() => {
            formElement.submit();
        }, 1500); 
    }

    // Global scope registration para sa HTML
    window.handlePauseTransition = handlePauseTransition;

    // Function to move expired cards to the top of their grid
    function sortExpiredCards() {
        const grids = document.querySelectorAll('.room-grid, .common-area-grid');
        grids.forEach(grid => {
            const cards = Array.from(grid.querySelectorAll('.room-card'));
            cards.sort((a, b) => {
                const aExpired = a.classList.contains('session-expired') ? 1 : 0;
                const bExpired = b.classList.contains('session-expired') ? 1 : 0;
                return bExpired - aExpired;
            });
            // Re-append in sorted order
            cards.forEach(card => grid.appendChild(card));
        });
    }

    function standardizeRoomGridColumns() {
        const columns = window.innerWidth >= 768
            ? 'repeat(2, minmax(0, 1fr))'
            : '1fr';

        document.querySelectorAll('.common-area-grid, #roomGridContainer').forEach(grid => {
            grid.style.gridTemplateColumns = columns;
        });
    }

    standardizeRoomGridColumns();
    window.addEventListener('resize', standardizeRoomGridColumns);

    function updateClock() {
        const clockEl = document.getElementById('dashboardClock');
        if (!clockEl) return;
        const now = new Date();
        let hours = now.getHours();
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const seconds = now.getSeconds().toString().padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12 || 12;
        clockEl.textContent = `${hours.toString().padStart(2, '0')}:${minutes}:${seconds} ${ampm}`;
    }

    const searchInput = document.getElementById('dashboardSearch');
    const dashboardCards = document.querySelectorAll('.room-card'); 
    const noResultsEl = document.getElementById('noSearchResults');

    function filterDashboardCards() {
        const query = searchInput?.value.trim().toLowerCase() || '';
        let visibleCount = 0;

        dashboardCards.forEach(card => {
            const customer = (card.dataset.customer || '').toLowerCase();
            const room = (card.dataset.room || '').toLowerCase();
            const matches = !query || customer.includes(query) || room.includes(query);
            card.style.display = matches ? '' : 'none';
            if (matches) visibleCount += 1;
        });

        if (noResultsEl) {
            noResultsEl.style.display = visibleCount === 0 ? 'block' : 'none';
        }
    }

    if (searchInput) {
        searchInput.addEventListener('input', filterDashboardCards);
    }

    function bindAdminActionButtons() {
        document.body.addEventListener('click', (event) => {
            const addTimeBtn = event.target.closest('.add-time-btn');
            if (addTimeBtn) {
                event.preventDefault();
                const resId = addTimeBtn.dataset.reservationId;
                if (resId) {
                    openExtendTimeModal(resId);
                }
                return;
            }

            const endSessionBtn = event.target.closest('.end-session-btn');
            if (endSessionBtn) {
                event.preventDefault();
                const resId = endSessionBtn.dataset.reservationId;
                if (resId) {
                    handleCheckout(resId);
                }
            }
        });
    }

    bindAdminActionButtons();

    function formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }


function renderOccupants(list) {
    const container = document.getElementById('occupantsList');
    const countEl = document.getElementById('occupantsCount');

    if (!container || !countEl) {
        return;
    }

    const activeOccupants = list.filter(member => !member.is_paused);
    container.innerHTML = '';
    countEl.textContent = activeOccupants.length.toString();

    if (!activeOccupants.length) {
        const empty = document.createElement('p');
        empty.className = 'no-occupants';
        empty.textContent = 'No active common area occupants.';
        container.appendChild(empty);
        return;
    }

    activeOccupants.forEach(member => {
        const item = document.createElement('div');
        item.className = 'occupant-item';
        
        const formattedEndTime = member.end_time
            ? new Date(member.end_time).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                hour12: true
            })
            : 'N/A';

        item.innerHTML = `
            <div class="occupant-name">${member.name}</div>

            <div class="occupant-time">
                Checked in: ${member.formatted_check_in || 'N/A'}
            </div>

            <div class="occupant-time">
                Ends: ${formattedEndTime}
            </div>

            <div class="occupant-elapsed">
                Time Used:
                <span
                    class="time-used"
                    data-elapsed-seconds="${member.elapsed_seconds || 0}"
                    data-is-paused="${member.is_paused ? 'true' : 'false'}"
                    data-synced-at="${Date.now()}"
                >00:00:00</span>
            </div>
        `;
        container.appendChild(item);
    });

    updateOccupantTimers();
}

function updateOccupantTimers() {
    document.querySelectorAll('.time-used').forEach(el => {
        let baseSeconds =
            parseInt(el.dataset.elapsedSeconds || '0', 10);

        if (isNaN(baseSeconds) || baseSeconds < 0) {
            baseSeconds = 0;
        }

        const isPaused =
            el.dataset.isPaused === 'true';

        if (isPaused) {
            el.textContent =
                `${formatDuration(baseSeconds)} (PAUSED)`;
            return;
        }

        const syncedAt =
            parseInt(el.dataset.syncedAt || Date.now(), 10);

        const elapsedSinceSync = Math.floor(
            (Date.now() - syncedAt) / 1000
        );

        const displaySeconds =
            baseSeconds + Math.max(0, elapsedSinceSync);

        el.textContent =
            formatDuration(displaySeconds);
    });
}

// Helper Function para sa Open Time Minute Tiers Pricing
function calculateOpenTimeFee(totalMinutes, hourlyRate = 35) {
    if (totalMinutes <= 0) return 0;

    const fullHours = Math.floor(totalMinutes / 60);
    const remMins = totalMinutes % 60;

    let minuteFee = 0;
    if (remMins >= 1 && remMins <= 12) minuteFee = 5;
    else if (remMins >= 13 && remMins <= 24) minuteFee = 10;
    else if (remMins >= 25 && remMins <= 36) minuteFee = 15;
    else if (remMins >= 37 && remMins <= 47) minuteFee = 20;
    else if (remMins >= 48 && remMins <= 59) minuteFee = 25;
    else if (remMins === 0 && fullHours > 0) minuteFee = 0;

    return (fullHours * hourlyRate) + minuteFee;
}

function fetchCommonAreaOccupants() {
    fetch('/admin/api/dashboard/common-area-occupants')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && Array.isArray(data.occupants)) {
                renderOccupants(data.occupants);
            }
        })
        .catch(err => {
            console.error('Failed to load common area occupants', err);
        });
}

function loadTodayWaitingList() {
    fetch('/admin/api/dashboard/today-waiting-list')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('today-waiting-list-container');
            const countBadge = document.getElementById('waiting-list-count-badge');
            if (!container) return;
            if (countBadge) countBadge.textContent = data.count || 0;

            if (!Array.isArray(data.waiting_list) || data.waiting_list.length === 0) {
                container.innerHTML = '<p class="no-data">No upcoming reservations.</p>';
                return;
            }

            container.innerHTML = data.waiting_list.map(item => {
                const status = item.status || 'Pending';
                const normalized = String(status).trim().toLowerCase();
                const className = normalized === 'confirmed' ? 'status-confirmed' : normalized === 'waiting' ? 'status-waiting' : 'status-pending';
                return `
                    <div class="waiting-item">
                        <p class="waiting-name">Next: ${item.customer_name}</p>
                        <p class="waiting-details">(${item.room_name}, ${item.start_time} - ${item.end_time})</p>
                        <span class="waiting-status ${className}">${status}</span>
                    </div>
                `;
            }).join('');
        })
        .catch(err => console.error("Failed to load today's waiting list", err));
}

function updateCommonAreaCardStats(data) {
    const commonArea = data && data.common_area ? data.common_area : data;
    if (!commonArea) return;

    const occupied = commonArea.occupied;
    const available = commonArea.available;

    const summaryItems = document.querySelectorAll('.occupancy-summary-section .summary-item');
    summaryItems.forEach(item => {
        const label = item.querySelector('.summary-label')?.textContent.toLowerCase() || '';
        const value = item.querySelector('.summary-value');
        if (!value) return;
        if (label.includes('occupied')) value.textContent = occupied;
        if (label.includes('available')) value.textContent = available;
    });

}

function updateRoomStatusCards(data) {
    if (!Array.isArray(data?.rooms)) return;

    function ensureRoomTimerRows(card, room, occupied) {
        const existingTimer = card.querySelector('.timer-text');
        const existingRemaining = card.querySelector('.remaining-text');
        if (!occupied) {
            existingTimer?.closest('.info-row')?.remove();
            existingRemaining?.closest('.info-row')?.remove();
            return;
        }

        const details = card.querySelector('.room-card-body') || card;
        const actionButtons = card.querySelector('.room-action-buttons');
        const timerRow = existingTimer?.closest('.info-row') || document.createElement('div');
        timerRow.className = 'info-row';
        if (!existingTimer) {
            timerRow.innerHTML = '<span class="info-label">Live Timer</span><span class="timer-text">(00:00:00)</span>';
            if (actionButtons) details.insertBefore(timerRow, actionButtons.parentElement === details ? actionButtons : null);
            else details.appendChild(timerRow);
        }

        const remainingRow = existingRemaining?.closest('.info-row') || document.createElement('div');
        remainingRow.className = 'info-row';
        if (!existingRemaining) {
            remainingRow.innerHTML = '<span class="info-label">Remaining</span><span class="remaining-text" style="font-weight: bold; color: #dc2626;">(00:00:00)</span>';
            if (actionButtons) details.insertBefore(remainingRow, actionButtons.parentElement === details ? actionButtons : null);
            else details.appendChild(remainingRow);
        }

        const timer = timerRow.querySelector('.timer-text');
        timer.dataset.starttime = room.start_time || '';
        timer.dataset.endtime = room.is_open_time ? '' : (room.end_time || '');
        timer.dataset.isopentime = room.is_open_time ? 'true' : 'false';
        timer.dataset.isPaused = room.is_paused ? 'true' : 'false';
        timer.dataset.accumulatedPausedSeconds = card.dataset.accumulatedPausedSeconds || '0';
    }

    function addButtonAttributes(button, room, reservationId) {
        button.dataset.reservationId = reservationId;
        button.dataset.customerName = room.occupant_name || 'Customer';
        button.dataset.roomName = room.name || 'Room';
        button.dataset.startTime = room.start_time || '';
        button.dataset.endTime = room.end_time || '';
        button.dataset.roomRate = room.room_rate || 0;
        button.dataset.totalAmount = room.total_amount || 0;
        button.dataset.extraFee = room.extra_fee || 0;
        button.dataset.isOpenTime = room.is_open_time ? 'true' : 'false';
    }

    function renderRoomActions(card, room, occupied) {
        let buttonContainer = card.querySelector('.room-action-buttons');
        if (!occupied) {
            if (buttonContainer) buttonContainer.remove();
            return;
        }

        const reservationId = Number(room.reservation_id);
        if (!Number.isInteger(reservationId)) return;
        if (!buttonContainer) {
            buttonContainer = document.createElement('div');
            buttonContainer.className = 'card-action-row room-action-buttons';
            buttonContainer.style.cssText = 'display: flex; gap: 4px; align-items: center; justify-content: space-between; width: 100%; margin-top: 10px;';
            (card.querySelector('.room-card-footer') || card).appendChild(buttonContainer);
        }

        buttonContainer.replaceChildren();
        if (!room.is_open_time) {
            const addTimeButton = document.createElement('button');
            addTimeButton.type = 'button';
            addTimeButton.className = 'btn-end-session add-time-btn';
            addTimeButton.textContent = 'Add Time';
            addTimeButton.style.cssText = 'flex: 1; height: 34px; padding: 0 4px; font-size: 11px; font-weight: bold; background-color: #22c55e; color: #fff; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap; margin: 0;';
            addButtonAttributes(addTimeButton, room, reservationId);
            buttonContainer.appendChild(addTimeButton);
        }

        const pauseForm = document.createElement('form');
        pauseForm.method = 'post';
        pauseForm.action = `/admin/toggle_pause_reservation/${reservationId}`;
        pauseForm.style.cssText = 'flex: 1; margin: 0; padding: 0; display: flex;';
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) pauseForm.appendChild(csrfInput.cloneNode(true));
        pauseForm.onsubmit = event => {
            if (room.is_paused) return true;
            handlePauseTransition(event, pauseForm);
        };
        const pauseButton = document.createElement('button');
        pauseButton.type = 'submit';
        pauseButton.className = 'btn-end-session';
        pauseButton.style.cssText = `width: 100%; height: 34px; padding: 0 4px; font-size: 11px; font-weight: bold; background-color: ${room.is_paused ? '#ffc107' : '#6c757d'}; color: ${room.is_paused ? '#000' : '#fff'}; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap; margin: 0;`;
        pauseButton.textContent = room.is_paused ? 'Resume' : 'Pause';
        pauseForm.appendChild(pauseButton);
        buttonContainer.appendChild(pauseForm);

        const endButton = document.createElement('button');
        endButton.type = 'button';
        endButton.className = 'btn-end-session end-session-btn';
        endButton.textContent = 'End Session';
        endButton.style.cssText = 'flex: 1; height: 34px; padding: 0 4px; font-size: 11px; font-weight: bold; background-color: #1e3a8a; color: #fff; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap; margin: 0;';
        addButtonAttributes(endButton, room, reservationId);
        buttonContainer.appendChild(endButton);

        const deleteForm = document.createElement('form');
        deleteForm.method = 'post';
        deleteForm.action = `/admin/delete_reservation/${reservationId}`;
        deleteForm.className = 'confirm-delete-form';
        deleteForm.style.cssText = 'margin: 0; padding: 0; display: inline-block;';
        if (csrfInput) deleteForm.appendChild(csrfInput.cloneNode(true));
        deleteForm.onsubmit = () => window.confirm('Do you confirm to delete or cancel this session now?');
        const deleteButton = document.createElement('button');
        deleteButton.type = 'submit';
        deleteButton.className = 'btn-end-session btn-error custom-x-btn';
        deleteButton.title = 'Delete Reservation';
        deleteButton.textContent = '✕';
        deleteButton.style.cssText = 'width: 34px; height: 34px; min-width: 34px; background-color: #dc3545; border: none; border-radius: 4px; cursor: pointer; margin: 0; padding: 0; color: #fff; font-size: 18px; font-weight: bold; line-height: 1;';
        deleteForm.appendChild(deleteButton);
        buttonContainer.appendChild(deleteForm);
    }

    data.rooms.forEach(room => {
        const card = Array.from(document.querySelectorAll('#roomGridContainer .room-card'))
            .find(candidate => candidate.dataset.room === room.name.trim().toLowerCase());
        if (!card) return;

        const occupied = room.status === 'OCCUPIED';
        const statusPill = card.querySelector('.status-pill');
        const statusText = card.querySelector('.status-text');
        const nameValue = card.querySelector('.name-row .info-value');
        const startValue = Array.from(card.querySelectorAll('.info-row'))
            .find(row => row.querySelector('.info-label')?.textContent.trim().toLowerCase() === 'start')
            ?.querySelector('.info-value');
        const endValue = Array.from(card.querySelectorAll('.info-row'))
            .find(row => row.querySelector('.info-label')?.textContent.trim().toLowerCase() === 'end')
            ?.querySelector('.info-value');

        card.dataset.customer = (room.occupant_name || '').toLowerCase();
        card.dataset.endtime = room.end_time || '';
        card.dataset.isopentime = room.is_open_time ? 'true' : 'false';
        card.dataset.isPaused = room.is_paused ? 'true' : 'false';
        if (statusPill) {
            statusPill.textContent = occupied ? 'Occupied' : 'Available';
            statusPill.classList.toggle('occupied', occupied);
            statusPill.classList.toggle('available', !occupied);
        }
        if (statusText) {
            statusText.textContent = occupied ? 'Occupied' : 'Available';
            statusText.classList.toggle('occupied', occupied);
            statusText.classList.toggle('available', !occupied);
        }
        if (nameValue) nameValue.textContent = room.occupant_name || '---';
        if (startValue) startValue.textContent = room.start_time ? new Date(room.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true }) : '---';
        if (endValue) endValue.textContent = room.end_time ? new Date(room.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true }) : '---';
        ensureRoomTimerRows(card, room, occupied);
        renderRoomActions(card, room, occupied);
        if (typeof window.updateAdminDashboardTimers === 'function') {
            window.updateAdminDashboardTimers();
        }
    });
}

function fetchCommonAreaCardStats() {
    fetch('/admin/api/dashboard/room-status')
        .then(response => response.json())
        .then(data => {
            updateCommonAreaCardStats(data);
            updateRoomStatusCards(data);
        })
        .catch(err => console.error('Failed to load common area room status', err));
}

fetchCommonAreaOccupants();
loadTodayWaitingList();
fetchCommonAreaCardStats();
setInterval(fetchCommonAreaOccupants, 10000);
setInterval(loadTodayWaitingList, 5000);
setInterval(fetchCommonAreaCardStats, 10000);
setInterval(updateOccupantTimers, 1000);

// End Session Button Logic
window.handleCheckout = function(resId) {
    // Updated selector to be more robust
    const btn = document.querySelector(`.end-session-btn[data-reservation-id="${resId}"]`);
    if (!btn) {
        console.error("End Session button not found for ID:", resId);
        return;
    }

    const customerName = btn.dataset.customerName || 'Customer';
    const roomName = btn.dataset.roomName || 'Room';
    
    const storedTotal = parseFloat(btn.getAttribute('data-total-amount')) || 0;
    const rate = parseFloat(btn.getAttribute('data-room-rate')) || 35;
    const extra = parseFloat(btn.getAttribute('data-extra-fee')) || 0;
    const startStr = btn.getAttribute('data-start-time');
    const isOpenTime = btn.getAttribute('data-is-open-time') === 'true';
    
    let total = 0;
    let displayDuration = "";

    // CHECKOUT LOGIC:
    if (!isOpenTime) {
        total = storedTotal.toFixed(2);
        displayDuration = "Fixed Session (Original Time)";
    } 
    // If Open Time: Calculate based on Minute Tiers
    else if (isOpenTime && startStr) {
        const start = new Date(startStr);
        const now = new Date();
        const diffMs = Math.max(60000, now - start);
        
        // Exact total minutes
        const totalMinutes = Math.max(1, Math.floor(diffMs / 60000));
        
        // Compute tiered room fee + extra fee
        const roomFee = calculateOpenTimeFee(totalMinutes, rate);
        total = (roomFee + extra).toFixed(2);
        
        // Format display duration
        const fullHours = Math.floor(totalMinutes / 60);
        const remMins = totalMinutes % 60;
        
        if (fullHours > 0) {
            displayDuration = `${totalMinutes} mins (${fullHours} hr/s ${remMins} mins)`;
        } else {
            displayDuration = `${totalMinutes} mins`;
        }
    } else {
        total = (rate + extra).toFixed(2);
        displayDuration = "Fixed Session";
    }
    
    const confirmMsg = `End session for ${customerName} (${roomName})?\n\n` +
                       `Duration: ${displayDuration}\n` +
                       `Total Payable: ₱${total}`;

    confirmAction('End Session?', confirmMsg, 'End Session', 'Cancel').then(confirmed => {
        if (!confirmed) return;
        // Redirect to the backend route to finalize the checkout
        window.location.href = `/admin/walkin_checkout/${resId}?final_bill=${total}`;
    });
};

    const addTimeModal = document.getElementById('addTimeModal');
    const extendHoursInput = document.getElementById('extendHoursInput');
    const extendCustomerEl = document.getElementById('extendCustomer');
    const extendRoomEl = document.getElementById('extendRoom');
    const extendCurrentEndEl = document.getElementById('extendCurrentEnd');
    const extendOriginalTotalEl = document.getElementById('extendOriginalTotal');
    const extendUpdatedTotalEl = document.getElementById('extendUpdatedTotal');
    const extendRateEl = document.getElementById('extendRate');
    const extendSummaryCustomer = document.getElementById('extendSummaryCustomer');
    const extendSummaryRoom = document.getElementById('extendSummaryRoom');
    const extendSummaryHours = document.getElementById('extendSummaryHours');
    const extendSummaryEnd = document.getElementById('extendSummaryEnd');
    const extendSummaryTotal = document.getElementById('extendSummaryTotal');
    const confirmExtendBtn = document.getElementById('confirmExtendBtn');
    const closeExtendModalBtn = document.getElementById('closeExtendModalBtn');

    let activeExtendReservation = null;

    function formatCurrency(value) {
        return `₱${parseFloat(value || 0).toFixed(2)}`;
    }

    function formatDateTime(date) {
        return date.toLocaleTimeString(undefined, {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true,
        });
    }

    function closeExtendModal() {
        if (addTimeModal) {
            addTimeModal.classList.remove('active');
        }
        activeExtendReservation = null;
    }

    function updateExtendModalPreview() {
        if (!activeExtendReservation || !extendHoursInput) return;

        const addedHours = Math.max(1, parseInt(extendHoursInput.value, 10) || 1);
        const originalTotal = parseFloat(activeExtendReservation.currentTotal || 0);
        const rate = parseFloat(activeExtendReservation.roomRate || 0);
        const extraTotal = originalTotal + addedHours * rate;

        extendSummaryHours.textContent = addedHours;
        extendSummaryTotal.textContent = formatCurrency(extraTotal);
        extendUpdatedTotalEl.textContent = formatCurrency(extraTotal);

        if (activeExtendReservation.currentEnd && !activeExtendReservation.isOpenTime) {
            const endDate = new Date(activeExtendReservation.currentEnd);
            endDate.setHours(endDate.getHours() + addedHours);
            extendSummaryEnd.textContent = formatDateTime(endDate);
        } else if (activeExtendReservation.isOpenTime) {
            extendSummaryEnd.textContent = 'Open-time session';
        } else {
            extendSummaryEnd.textContent = '---';
        }
    }

    window.openExtendTimeModal = function(resId) {
        const btn = document.querySelector(`.add-time-btn[data-reservation-id="${resId}"]`);
        if (!btn) {
            console.error('Add Time button not found for ID:', resId);
            return;
        }

        const isOpenTime = btn.getAttribute('data-is-open-time') === 'true';

        activeExtendReservation = {
            resId,
            customer: btn.dataset.customerName || 'Customer',
            room: btn.dataset.roomName || 'Room',
            currentEnd: btn.dataset.endTime || '',
            roomRate: parseFloat(btn.dataset.roomRate) || 0,
            currentTotal: parseFloat(btn.dataset.totalAmount) || 0,
            extraFee: parseFloat(btn.dataset.extraFee) || 0,
            isOpenTime,
        };

        if (extendCustomerEl) extendCustomerEl.textContent = activeExtendReservation.customer;
        if (extendRoomEl) extendRoomEl.textContent = activeExtendReservation.room;
        if (extendCurrentEndEl) {
            extendCurrentEndEl.textContent = activeExtendReservation.currentEnd
                ? formatDateTime(new Date(activeExtendReservation.currentEnd))
                : '---';
        }
        if (extendRateEl) extendRateEl.textContent = formatCurrency(activeExtendReservation.roomRate);
        if (extendOriginalTotalEl) extendOriginalTotalEl.textContent = formatCurrency(activeExtendReservation.currentTotal);
        if (extendSummaryCustomer) extendSummaryCustomer.textContent = activeExtendReservation.customer;
        if (extendSummaryRoom) extendSummaryRoom.textContent = activeExtendReservation.room;
        if (extendHoursInput) extendHoursInput.value = '1';

        const modalTitle = document.getElementById('extendModalTitle');
        const modalNote = document.getElementById('extendModalNote');
        if (modalTitle) {
            modalTitle.textContent = activeExtendReservation.isOpenTime ? 'Adjust Open-Time Session' : 'Extend Fixed Session';
        }
        if (modalNote) {
            modalNote.textContent = activeExtendReservation.isOpenTime
                ? 'This is an open-time session. Adding hours will add billable amount, not change the live timer.'
                : 'Add extra time to the fixed session. The end time and total bill will update.';
        }

        updateExtendModalPreview();

        if (addTimeModal) {
            addTimeModal.classList.add('active');
        }
    };

    if (extendHoursInput) {
        extendHoursInput.addEventListener('input', updateExtendModalPreview);
    }

    if (closeExtendModalBtn) {
        closeExtendModalBtn.addEventListener('click', closeExtendModal);
    }

    if (confirmExtendBtn) {
        confirmExtendBtn.addEventListener('click', function() {
            if (!activeExtendReservation) return;
            const addedHours = Math.max(1, parseInt(extendHoursInput.value, 10) || 1);
            confirmExtendBtn.disabled = true;
            confirmExtendBtn.textContent = 'Extending...';

            fetch(`/admin/extend_time/${activeExtendReservation.resId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ added_hours: addedHours }),
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status !== 'success') {
                        throw new Error(data.message || 'Failed to extend time.');
                    }

                    const card = document.querySelector(`.add-time-btn[data-reservation-id="${activeExtendReservation.resId}"]`)?.closest('.room-card');
                    if (card) {
                        const newEndTime = data.new_end_time || card.dataset.endtime;
                        card.dataset.endtime = newEndTime;
                        card.classList.remove('session-expired');

                        card.querySelectorAll('.timer-text').forEach(timer => {
                            timer.setAttribute('data-endtime', newEndTime);
                        });

                        const endRow = Array.from(card.querySelectorAll('.info-row')).find(row => {
                            const label = row.querySelector('.info-label');
                            return label && label.textContent.trim() === 'End';
                        });
                        if (endRow) {
                            const value = endRow.querySelector('.info-value');
                            if (value) {
                                value.textContent = formatDateTime(new Date(data.new_end_time));
                            }
                        }
                        const buttons = card.querySelectorAll(`[data-reservation-id="${activeExtendReservation.resId}"]`);
                        buttons.forEach(el => {
                            el.dataset.totalAmount = data.new_total;
                            if (data.new_end_time) {
                                el.dataset.endTime = data.new_end_time;
                            }
                            if (typeof data.new_extra_fee !== 'undefined') {
                                el.dataset.extraFee = data.new_extra_fee;
                            }
                        });

                        updateTimers();
                    }

                    showToast(data.message, 'success');
                    closeExtendModal();
                })
                .catch(error => {
                    console.error('Extend Time error:', error);
                    showToast(error.message || 'Unable to extend time at the moment.', 'error');
                })
                .finally(() => {
                    confirmExtendBtn.disabled = false;
                    confirmExtendBtn.textContent = 'Confirm Extend';
                });
        });
    }

    // Initialize systems
    setInterval(updateTimers, 1000);
    updateTimers();
    sortExpiredCards(); 

    updateClock();
    setInterval(updateClock, 1000);

});