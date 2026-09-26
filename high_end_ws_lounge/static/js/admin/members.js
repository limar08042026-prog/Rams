document.addEventListener('DOMContentLoaded', function() {
    
    // === HELPER FALLBACKS (Prevents Uncaught ReferenceErrors) ===
    function showToastFallback(message, type = 'info') {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            alert(`[${type.toUpperCase()}]: ${message}`);
        }
    }

    async function confirmActionFallback(title, message, confirmBtnText = 'Confirm', cancelBtnText = 'Cancel') {
        if (typeof window.confirmAction === 'function') {
            return await window.confirmAction(title, message, confirmBtnText, cancelBtnText);
        } else {
            return window.confirm(`${title}\n\n${message}`);
        }
    }

    function showAlert(message, type = 'info') {
        showToastFallback(message, type);
    }

    const remainingTimeIntervals = new WeakMap();

    function formatRemainingTime(remainingSeconds) {
        const totalSeconds = Math.max(0, Math.floor(Number(remainingSeconds) || 0));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        return `${String(hours).padStart(2, '0')}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`;
    }

    function updateRemainingTimeBadge(card, remainingSeconds, isPaused, isSessionActive = true, endTimeIso = null) {
        const badge = card?.querySelector('.remaining-time-badge strong');
        if (!badge) return;

        const previousInterval = remainingTimeIntervals.get(card);
        if (previousInterval) clearInterval(previousInterval);

        const endTarget = new Date(endTimeIso || card?.dataset.endTime || '').getTime();
        let currentSeconds = Math.max(0, Math.floor(Number(remainingSeconds) || 0));
        const render = () => {
            if (!isPaused && Number.isFinite(endTarget)) {
                currentSeconds = Math.max(0, Math.floor((endTarget - Date.now()) / 1000));
            }
            badge.textContent = formatRemainingTime(currentSeconds);
        };

        render();
        if (isPaused) {
            remainingTimeIntervals.delete(card);
            badge.classList.add('text-warning');
            badge.closest('.remaining-time-badge').style.backgroundColor = '#fff3cd';
        } else if (isSessionActive && currentSeconds > 0) {
            badge.classList.remove('text-warning');
            remainingTimeIntervals.set(card, setInterval(render, 1000));
        } else {
            remainingTimeIntervals.delete(card);
            badge.classList.remove('text-warning');
            badge.closest('.remaining-time-badge').style.backgroundColor = '#edf2f7';
            badge.style.color = '#718096';
        }
    }

    function renderMemberActivityLogs(container, activityLogs) {
        container.replaceChildren();

        if (!Array.isArray(activityLogs) || activityLogs.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'member-activity-log-empty';
            empty.textContent = 'No activity recorded yet.';
            container.appendChild(empty);
            return;
        }

        activityLogs.forEach((activity) => {
            const item = document.createElement('div');
            item.className = 'member-activity-log';

            const event = document.createElement('div');
            event.className = 'member-activity-log-event';
            event.textContent = activity.event || 'Session activity';
            event.style.color = activity.event === 'Paused' ? '#d69e2e' : '#38a169';

            const timestamp = document.createElement('p');
            timestamp.className = 'member-activity-log-time';
            timestamp.textContent = activity.timestamp || '-';

            const details = document.createElement('p');
            details.className = 'member-activity-log-details';
            details.textContent = activity.details || '';

            item.append(event, timestamp, details);
            container.appendChild(item);
        });
    }

    async function refreshMemberActivityLogs(membershipId, card) {
        const targetCard = card || document.querySelector(
            `.member-list-card[data-membership-id="${membershipId}"], .member-list-card[data-user-id="${membershipId}"]`
        );
        const logContainer = targetCard?.querySelector('.member-activity-logs');
        if (!logContainer || !membershipId) return;

        try {
            const response = await fetch(`/admin/api/member/${membershipId}/attendance`);
            const data = await response.json();
            if (!response.ok || data.status !== 'success') {
                throw new Error(data.message || 'Unable to load activity.');
            }
            renderMemberActivityLogs(logContainer, data.activity_logs);

            const fallbackSeconds = Number(data.hours_left || 0) * 3600;
            updateRemainingTimeBadge(
                targetCard,
                data.remaining_seconds !== undefined ? data.remaining_seconds : fallbackSeconds,
                Boolean(data.is_paused),
                data.is_checked_in === true,
                targetCard.dataset.endTime
            );

            const visitCount = targetCard.querySelector('.member-activity-logs-count');
            if (visitCount && Array.isArray(data.attendance)) {
                visitCount.dataset.visitCount = String(data.attendance.length);
                visitCount.textContent = `Daily session history ${data.attendance.length} visits`;
            }
        } catch (error) {
            logContainer.replaceChildren();
            const message = document.createElement('p');
            message.className = 'member-activity-log-empty';
            message.textContent = 'Activity unavailable.';
            logContainer.appendChild(message);
            console.warn('Member activity fetch failed:', error);
        }
    }

    window.refreshMemberActivityLogs = refreshMemberActivityLogs;

    function appendActivityRow(container, entry) {
        if (!container || !entry) return;
        const row = document.createElement('div');
        row.className = 'member-activity-log';

        const event = document.createElement('div');
        event.className = 'member-activity-log-event';
        event.textContent = entry.action || 'Session activity';
        event.style.color = entry.action === 'Paused' ? '#d69e2e' : '#38a169';

        const timestamp = document.createElement('div');
        timestamp.className = 'member-activity-log-time';
        timestamp.textContent = entry.timestamp || '-';

        const details = document.createElement('div');
        details.className = 'member-activity-log-details';
        details.textContent = entry.description || 'Session activity';

        row.append(event, timestamp, details);
        container.replaceChildren(row);
    }

    function updateCheckedInCard(card, membershipId, userId, result) {
        if (!card) return;
        const sessionGroup = card.querySelector('.session-action-group');
        const memberName = card.querySelector('.member-name')?.textContent.trim() || 'Member';
        if (sessionGroup) {
            sessionGroup.replaceChildren();

            const checkedInButton = document.createElement('button');
            checkedInButton.className = 'btn-check-in disabled-btn';
            checkedInButton.type = 'button';
            checkedInButton.disabled = true;
            checkedInButton.textContent = 'Checked In';

            const pauseButton = document.createElement('button');
            pauseButton.className = 'btn-pause-session btn-secondary';
            pauseButton.type = 'button';
            pauseButton.id = `pause-btn-${membershipId}`;
            pauseButton.dataset.membershipId = membershipId;
            pauseButton.dataset.memberId = userId;
            pauseButton.dataset.memberName = memberName;
            pauseButton.dataset.isPaused = 'false';
            pauseButton.textContent = 'Pause Session';
            pauseButton.onclick = () => window.handlePauseClick(pauseButton);

            const checkoutButton = document.createElement('button');
            checkoutButton.className = 'btn-deactivate';
            checkoutButton.type = 'button';
            checkoutButton.textContent = 'Check-Out Customer';
            checkoutButton.onclick = () => window.handleCheckout(userId);

            sessionGroup.append(checkedInButton, pauseButton, checkoutButton);
        }

        const status = card.querySelector(`#status-text-${CSS.escape(userId)}`);
        if (status) {
            status.textContent = 'Checked In';
            status.classList.remove('status-paused');
            status.classList.add('status-checkin');
        }

        const renewButton = card.querySelector('.renew-btn');
        if (renewButton) {
            renewButton.disabled = true;
            renewButton.style.opacity = '0.65';
            renewButton.style.cursor = 'not-allowed';
        }

        const logs = card.querySelector('.member-activity-logs');
        if (logs) {
            logs.replaceChildren();
            appendActivityRow(logs, result.new_log || {
                action: 'Check-In',
                description: 'Session started',
                timestamp: result.check_in_time || new Date().toLocaleString()
            });
        }
    }

    async function handleCheckoutWithoutReload(userId) {
        const card = document.querySelector(`.member-list-card[data-user-id="${userId}"]`);
        if (!card || typeof Swal === 'undefined') return;

        const result = await Swal.fire({
            title: 'Check Out',
            text: 'Check out this member now?',
            icon: 'question',
            showCancelButton: true,
            confirmButtonColor: '#7367f0',
            cancelButtonColor: '#6e7881',
            confirmButtonText: 'Confirm',
            cancelButtonText: 'Cancel'
        });
        if (!result.isConfirmed) return;

        try {
            const response = await fetch(`/admin/api/member/${userId}/check-out`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            if (data.status !== 'success') {
                await Swal.fire('Error!', data.message || 'Unable to check out member.', 'error');
                return;
            }

            const sessionGroup = card.querySelector('.session-action-group');
            if (sessionGroup) {
                sessionGroup.replaceChildren();
                const checkedOutButton = document.createElement('button');
                checkedOutButton.type = 'button';
                checkedOutButton.className = 'btn-deactivate';
                checkedOutButton.disabled = true;
                checkedOutButton.textContent = 'Checked Out';
                sessionGroup.appendChild(checkedOutButton);
            }

            const status = card.querySelector(`#status-text-${CSS.escape(userId)}`);
            if (status) {
                status.textContent = 'Checked Out';
                status.classList.remove('status-checkin', 'status-paused');
            }

            const logs = card.querySelector('.member-activity-logs');
            if (logs) logs.replaceChildren();
            updateRemainingTimeBadge(card, Number(data.hours_left || 0) * 3600, false, false);

            const renewButton = card.querySelector('.renew-btn');
            if (renewButton) {
                renewButton.disabled = false;
                renewButton.style.opacity = '';
                renewButton.style.cursor = 'pointer';
            }

            await Swal.fire({
                title: 'Success!',
                text: data.message,
                icon: 'success',
                timer: 1500,
                showConfirmButton: false
            });
        } catch (error) {
            console.error('Checkout error:', error);
            await Swal.fire('Error!', 'Something went wrong.', 'error');
        }
    }

    window.handleCheckout = handleCheckoutWithoutReload;

    document.querySelectorAll('.member-activity-logs').forEach((container) => {
        const card = container.closest('.member-list-card');
        refreshMemberActivityLogs(container.dataset.activityMembershipId, card);
    });


    // === 1. TAB SWITCHING LOGIC ===
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    async function clearMemberNotificationTab(tabName, badgeId) {
        const badge = document.getElementById(badgeId);
        const currentCount = Number(badge?.textContent || 0);
        if (badge) {
            badge.textContent = '0';
            badge.style.display = 'none';
            badge.classList.add('d-none');
        }
        sessionStorage.setItem(`${tabName}_tab_badge_count`, String(currentCount));
        try {
            await fetch(`/admin/api/admin/notifications/clear-tab?tab=${encodeURIComponent(tabName)}`, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
        } catch (error) {
            console.warn('Unable to clear member notification badge:', error);
        }
    }

    async function updateMemberTabNotificationBadges() {
        try {
            const response = await fetch('/admin/api/admin/notifications-count', {
                headers: { 'Cache-Control': 'no-cache' }
            });
            if (!response.ok) return;
            const data = await response.json();

            const updateBadge = (id, count) => {
                const badge = document.getElementById(id);
                if (!badge) return;
                const key = id === 'membership-request-tab-badge'
                    ? 'requests_tab_badge_count'
                    : 'members_tab_badge_count';
                const dismissedCount = Number(sessionStorage.getItem(key) || 0);
                const visibleCount = Math.max(0, Number(count || 0) - dismissedCount);
                badge.textContent = String(visibleCount);
                badge.style.display = visibleCount > 0 ? 'inline-flex' : 'none';
                badge.classList.toggle('d-none', visibleCount === 0);
            };

            updateBadge('membership-request-tab-badge', data.pending_memberships);
            updateBadge('member-list-tab-badge', data.new_members_count);
        } catch (error) {
            console.warn('Unable to update member tab notification badges:', error);
        }
    }

    updateMemberTabNotificationBadges();
    setInterval(updateMemberTabNotificationBadges, 3000);

    document.addEventListener('submit', (event) => {
        const form = event.target.closest('#requestsList form');
        if (!form) return;

        const isApproval = form.action.includes('/approve_membership/');
        const requestsBadge = document.getElementById('membership-request-tab-badge');
        const currentRequestCount = Number(requestsBadge?.textContent || 1);
        const nextRequestCount = Math.max(0, currentRequestCount - 1);
        sessionStorage.setItem('requests_tab_badge_count', String(nextRequestCount));
        if (requestsBadge) {
            requestsBadge.textContent = String(nextRequestCount);
            requestsBadge.style.display = nextRequestCount > 0 ? 'inline-flex' : 'none';
            requestsBadge.classList.toggle('d-none', nextRequestCount === 0);
        }

        if (isApproval) {
            sessionStorage.removeItem('members_tab_badge_count');
            const memberListBadge = document.getElementById('member-list-tab-badge');
            if (memberListBadge) {
                const nextCount = (Number(memberListBadge.textContent) || 0) + 1;
                memberListBadge.textContent = String(nextCount);
                memberListBadge.classList.remove('d-none');
            }
        }
    });

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTab = button.getAttribute('data-tab');

            if (targetTab === 'requests') {
                clearMemberNotificationTab('requests', 'membership-request-tab-badge');
            } else if (targetTab === 'list') {
                clearMemberNotificationTab('members', 'member-list-tab-badge');
            }

            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabPanels.forEach(panel => panel.classList.remove('active'));

            button.classList.add('active');
            const targetPanel = document.getElementById(targetTab);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }
        });
    });


    // === 2. MODAL HELPER FUNCTIONS ===
    const receiptModal = document.getElementById('receiptModal');
    const recordsModal = document.getElementById('recordsModal');

    function openModal(modal) {
        if (!modal) return;
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal(modal) {
        if (!modal) return;
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }

    function createReceiptPreview(receiptUrl, requestName) {
        const body = document.getElementById('receiptModalBody');
        if (!body) return;
        body.innerHTML = '';

        if (!receiptUrl) {
            const placeholder = document.createElement('div');
            placeholder.className = 'records-empty-state';
            placeholder.innerHTML = `<p>No receipt has been uploaded for ${requestName} yet.</p>`;
            body.appendChild(placeholder);
            return;
        }

        const isImage = /\.(png|jpe?g|gif|webp)$/i.test(receiptUrl);
        if (isImage) {
            const img = document.createElement('img');
            img.src = receiptUrl;
            img.alt = `Receipt for ${requestName}`;
            img.className = 'receipt-modal-image';
            body.appendChild(img);
            return;
        }

        const link = document.createElement('a');
        link.href = receiptUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = `Open receipt for ${requestName}`;
        link.className = 'btn-view-records';
        body.appendChild(link);
    }


    // === 3. MEMBERSHIP REQUEST CARD INJECTION ===
    function createRequestCard(req, container, useMock = false) {
        const card = document.createElement('div');
        card.className = 'request-card';
        card.setAttribute('data-request', JSON.stringify(req));

        const info = document.createElement('div');
        info.className = 'request-info';
        info.innerHTML = `<h3 class="customer-name">${req.user?.name || 'Unknown'}</h3>
            <p class="detail-text">Email: ${req.user?.email || 'N/A'}</p>
            <p class="detail-text">Contact Number: ${req.user?.phone || 'N/A'}</p>`;

        const plan = document.createElement('div');
        plan.className = 'request-plan';
        const created = new Date(req.created_at || Date.now()).toLocaleString();
        plan.innerHTML = `<h4 class="column-title">Selected Plan</h4>
            <p class="plan-name">${req.plan_name || 'N/A'}</p>
            <p class="detail-text">Date Requested: ${created}</p>`;

        const pay = document.createElement('div');
        pay.className = 'request-payment';
        pay.innerHTML = `<h4 class="column-title">Payment Verification</h4>
            <button class="btn-check-receipt" data-receipt-url="${req.receipt_url || ''}" data-request-name="${req.user?.name || 'User'}">Check</button>`;

        const actions = document.createElement('div');
        actions.className = 'request-actions';

        const approveForm = document.createElement('form');
        approveForm.method = 'POST';
        approveForm.action = '#';
        approveForm.innerHTML = `<button type="submit" class="btn-approve">Approve</button>`;

        const rejectForm = document.createElement('form');
        rejectForm.method = 'POST';
        rejectForm.action = '#';
        rejectForm.innerHTML = `<button type="submit" class="btn-reject">Reject</button>`;

        actions.appendChild(approveForm);
        actions.appendChild(rejectForm);

        card.appendChild(info);
        card.appendChild(plan);
        card.appendChild(pay);
        card.appendChild(actions);

        container.appendChild(card);

        // Attach receipt viewer logic to dynamic button
        const checkBtn = card.querySelector('.btn-check-receipt');
        checkBtn.addEventListener('click', () => {
            if (useMock) {
                showAlert(`Mock: Open receipt for ${req.user?.name || 'user'}`);
            } else {
                createReceiptPreview(req.receipt_url, req.user?.name || 'this request');
                openModal(receiptModal);
            }
        });

        if (useMock) {
            approveForm.addEventListener('submit', (e) => {
                e.preventDefault();
                card.style.opacity = '0.6';
                card.style.transition = 'opacity 0.25s';
                card.querySelector('.request-plan .plan-name').innerText += ' (Activated)';
                const btn = approveForm.querySelector('button');
                btn.innerText = 'Approved';
                btn.disabled = true;
                setTimeout(() => card.remove(), 800);
            });

            rejectForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const btn = rejectForm.querySelector('button');
                btn.innerText = 'Rejected';
                btn.disabled = true;
                card.style.opacity = '0.6';
                setTimeout(() => card.remove(), 600);
            });
        }
    }

    const requestsList = document.getElementById('requestsList');
    if (requestsList) {
        try {
            const raw = JSON.parse(requestsList.getAttribute('data-requests') || '[]');
            const pending = (raw && Array.isArray(raw)) ? raw.filter(r => (r.status || '').toString().toLowerCase() === 'pending') : [];

            const existing = requestsList.querySelectorAll('.request-card');
            if (existing.length === 0 && pending.length > 0) {
                pending.forEach(r => createRequestCard(r, requestsList, false));
            }
        } catch (e) {
            console.warn('Failed to parse membership requests data', e);
        }
    }


    // === 4. GLOBAL MODAL EVENT BINDINGS ===
    document.querySelectorAll('.btn-check-receipt').forEach((btn) => {
        btn.addEventListener('click', () => {
            const receiptUrl = btn.dataset.receiptUrl;
            const requestName = btn.dataset.requestName || 'this request';
            createReceiptPreview(receiptUrl, requestName);
            openModal(receiptModal);
        });
    });

    document.querySelectorAll('.modal-close').forEach((btn) => {
        btn.addEventListener('click', (event) => {
            const modal = event.target.closest('.modal-overlay');
            closeModal(modal);
        });
    });


    // === 5. ATTENDANCE RECORDS & CHECK-IN LOGIC ===
    document.querySelectorAll('.btn-view-records').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const membershipId = btn.dataset.membershipId;
            const body = document.getElementById('recordsModalBody');
            if (!body) return;

            if (!membershipId) {
                body.innerHTML = '<div class="records-empty-state"><p>No membership found for this user.</p></div>';
                openModal(recordsModal);
                return;
            }

            body.innerHTML = '<p class="modal-placeholder">Loading attendance history...</p>';
            openModal(recordsModal);

            try {
                const response = await fetch(`/admin/api/member/${membershipId}/attendance`);
                const data = await response.json();

                if (!response.ok || data.status !== 'success') {
                    body.innerHTML = `<div class="records-empty-state"><p>${data.message || 'Unable to get attendance history.'}</p></div>`;
                    return;
                }

                if (!data.attendance || data.attendance.length === 0) {
                    body.innerHTML = `<div class="records-empty-state"><p>No attendance records recorded for <strong>${data.member_name || 'this member'}</strong>.</p></div>`;
                    return;
                }

                const visitsByDate = data.attendance.reduce((groups, log) => {
                    const date = log.date || 'Unknown date';
                    if (!groups[date]) groups[date] = [];
                    groups[date].push(log);
                    return groups;
                }, {});

                const visitRows = Object.entries(visitsByDate).map(([date, visits]) => visits.map(log => `
                    <div class="history-visit-row">
                        <div>
                            <strong>${date}</strong>
                            <span>${log.check_in || 'N/A'} - ${log.check_out || 'Still checked in'}</span>
                        </div>
                        <strong>${log.hours || '0'}</strong>
                    </div>
                `).join('')).join('');

                const activityRows = Array.isArray(data.activity_logs) ? data.activity_logs.map(activity => `
                    <div class="history-activity-row">
                        <span class="history-activity-event">${activity.event || 'Session activity'}</span>
                        <span class="history-activity-time">${activity.timestamp || 'N/A'}</span>
                        <small>${activity.details || ''}</small>
                    </div>
                `).join('') : '';

                body.innerHTML = `
                    <div class="history-summary">
                        <div>
                            <strong>${data.member_name}</strong>
                            <span>${Number(data.hours_left || 0).toFixed(2)} hrs remaining</span>
                        </div>
                        <span>${data.attendance.length} visit${data.attendance.length === 1 ? '' : 's'}</span>
                    </div>
                    <div class="member-history-layout">
                        <section class="member-history-visits">
                            <h4>Visit Days</h4>
                            ${visitRows || '<p class="history-muted">No visits recorded.</p>'}
                        </section>
                        <section class="member-history-activity">
                            <h4>Session Activity</h4>
                            ${activityRows || '<p class="history-muted">No session activity recorded.</p>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                body.innerHTML = `<div class="records-empty-state"><p>${err.message || 'Unable to retrieve history.'}</p></div>`;
            }
        });
    });

    document.querySelectorAll('.btn-check-in').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const membershipId = btn.dataset.membershipId || btn.dataset.userId;
            const isCheckedIn = btn.dataset.isCheckedIn === 'true';

            if (!membershipId) {
                showAlert('User or Membership ID missing.', 'error');
                return;
            }

            const confirmMessage = isCheckedIn ? 'End the active session for this member?' : 'Check in this member now?';
            const confirmed = await confirmActionFallback(isCheckedIn ? 'End Session' : 'Check In', confirmMessage);
            if (!confirmed) return;

            const endpoint = isCheckedIn 
                ? `/admin/api/member/${membershipId}/check-out` 
                : `/admin/api/member/${membershipId}/check-in`;

            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

            try {
                const response = await fetch(endpoint, { 
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });
                const result = await response.json().catch(() => ({}));

                if (!response.ok || result.status !== 'success') {
                    showAlert(result.message || 'Membership action failed.', 'error');
                    return;
                }
                showAlert(result.message || 'Action completed successfully.', 'success');
                const card = btn.closest('.member-list-card');
                const userId = btn.dataset.userId || '';
                updateCheckedInCard(card, membershipId, userId, result);
                await refreshMemberActivityLogs(membershipId, card);
            } catch (err) {
                showAlert(err.message || 'Membership action failed.', 'error');
            }
        });
    });


    // === 6. ADMIN MEMBER ACTIONS (Renew / Deactivate / Reactivate / Delete / Pause) ===
    async function postJson(url, payload) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

        const headers = { 
            'Content-Type': 'application/json' 
        };
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }

        const resp = await fetch(url, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload)
        });

        const data = await resp.json().catch(() => ({}));

        if (!resp.ok) {
            const msg = data && data.message ? data.message : `Request failed (HTTP ${resp.status})`;
            throw new Error(msg);
        }
        return data;
    }

        document.querySelectorAll('.btn-renew').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const userId = btn.getAttribute('data-user-id');
            if (!userId) return;

            const prevText = btn.innerText;
            btn.disabled = true;
            btn.innerText = 'Renewing...';

            try {
                await postJson('/admin/renew_member', { user_id: Number(userId) });
                showAlert('Membership renewed successfully.', 'success');

                // 1. I-save sa localStorage para sa tab navigation script
                localStorage.setItem("activeMemberTab", "list");

                // 2. Tadtaron ang tab parameter para exact gid sa HTML ('list')
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('tab', 'list');

                // 3. Mag-hulat sang 500ms para mabasa sang user ang success toast/alert
                setTimeout(() => {
                    window.location.href = currentUrl.toString();
                }, 500);

            } catch (err) {
                showAlert(err && err.message ? err.message : 'Renew failed.', 'error');
                btn.disabled = false;
                btn.innerText = prevText;
            }
        });
    });

    document.querySelectorAll('.btn-deactivate').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const userId = btn.getAttribute('data-user-id');
            if (!userId) return;

            const confirmed = await confirmActionFallback('Deactivate member?', 'Deactivate this member account?', 'Deactivate', 'Cancel');
            if (!confirmed) return;

            const prevText = btn.innerText;
            btn.disabled = true;
            btn.innerText = 'Deactivating...';

            try {
                await postJson('/admin/deactivate_member', { user_id: Number(userId) });
                showAlert('Account deactivated successfully.', 'success');
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('tab', 'member_list');
                window.location.href = currentUrl.toString();
            } catch (err) {
                showAlert(err && err.message ? err.message : 'Deactivation failed.', 'error');
            } finally {
                btn.disabled = false;
                btn.innerText = prevText;
            }
        });
    });

    document.querySelectorAll('.btn-reactivate').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const userId = btn.getAttribute('data-user-id');
            if (!userId) return;

            const prevText = btn.innerText;
            btn.disabled = true;
            btn.innerText = 'Reactivating...';

            try {
                await postJson('/admin/reactivate_member', { user_id: Number(userId) });
                showAlert('Account reactivated successfully.', 'success');
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('tab', 'member_list');
                window.location.href = currentUrl.toString();
            } catch (err) {
                showAlert(err && err.message ? err.message : 'Reactivation failed.', 'error');
            } finally {
                btn.disabled = false;
                btn.innerText = prevText;
            }
        });
    });

    document.querySelectorAll('.btn-delete-member').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const userId = btn.getAttribute('data-user-id');
            if (!userId) return;

            const confirmed = await confirmActionFallback('Delete account?', 'This will permanently delete all data for this account. Are you sure?', 'Delete', 'Cancel');
            if (!confirmed) return;

            const prevText = btn.innerText;
            btn.disabled = true;
            btn.innerText = 'Deleting...';

            try {
                await postJson(`/admin/delete_member/${Number(userId)}`, {});
                showAlert('Account permanently deleted.', 'success');
                window.location.reload();
            } catch (err) {
                showAlert(err && err.message ? err.message : 'Delete failed.', 'error');
            } finally {
                btn.disabled = false;
                btn.innerText = prevText;
            }
        });
    });

    // === PAUSE / RESUME SESSION LOGIC (ADMIN SIDE) ===
async function handlePauseClick(btnElement) {
    if (btnElement.disabled) return;

    const membershipId = btnElement.getAttribute('data-membership-id');
    const isCurrentlyPaused = btnElement.getAttribute('data-is-paused') === 'true';
    const memberName = btnElement.getAttribute('data-member-name') || 'Member';

    const actionText = isCurrentlyPaused ? "RESUME" : "PAUSE";
    const message = `Are you sure you want to ${actionText} the session for ${memberName}?`;

    const confirmed = await confirmActionFallback(`${actionText} Session`, message);
    if (!confirmed) return;

    btnElement.disabled = true;

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        const res = await fetch(`/admin/api/member/${membershipId}/toggle-pause`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });

        const data = await res.json();

        if (res.ok && data.status === 'success') {
            const newIsPaused = data.is_paused !== undefined ? data.is_paused : !isCurrentlyPaused;
            const card = btnElement.closest('.member-list-card');
            
            // 1. Instantly Update Button Attributes
            btnElement.setAttribute('data-is-paused', newIsPaused ? 'true' : 'false');
            btnElement.innerHTML = newIsPaused ? '▶ Resume Session' : '⏸ Pause Session';
            btnElement.classList.toggle('btn-warning', newIsPaused);
            btnElement.classList.toggle('btn-secondary', !newIsPaused);
            btnElement.style.backgroundColor = '';
            btnElement.disabled = false;

            if (card) {
                if (data.remaining_seconds !== undefined) {
                    if (data.new_end_time) card.dataset.endTime = data.new_end_time;
                    updateRemainingTimeBadge(card, data.remaining_seconds, newIsPaused, true, data.new_end_time);
                }
                const statusElement = card.querySelector(`#status-text-${CSS.escape(btnElement.getAttribute('data-member-id') || '')}`);
                if (statusElement) {
                    statusElement.textContent = newIsPaused ? 'Paused' : 'Checked In';
                    statusElement.classList.toggle('status-paused', newIsPaused);
                    statusElement.classList.toggle('status-checkin', !newIsPaused);
                }

                const logContainer = card.querySelector('.member-activity-logs');
                if (logContainer) {
                    const logRow = document.createElement('div');
                    logRow.className = 'member-activity-log';

                    const event = document.createElement('div');
                    event.className = 'member-activity-log-event';
                    const logEntry = data.log_entry || data.new_log || {};
                    event.textContent = logEntry.action || (newIsPaused ? 'Paused' : 'Resumed');
                    event.style.color = newIsPaused ? '#d69e2e' : '#38a169';

                    const timestamp = document.createElement('div');
                    timestamp.className = 'member-activity-log-time';
                    timestamp.textContent = new Intl.DateTimeFormat('en-US', {
                        timeZone: 'Asia/Manila',
                        month: 'short',
                        day: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true
                    }).format(new Date()).replace(',', ' -');
                    timestamp.textContent = logEntry.timestamp || timestamp.textContent;

                    const details = document.createElement('div');
                    details.className = 'member-activity-log-details';
                    details.textContent = logEntry.description || (newIsPaused ? 'Session paused' : 'Session resumed');

                    logRow.append(event, timestamp, details);
                    logContainer.prepend(logRow);

                }
            }

            showAlert(data.message || `Session ${newIsPaused ? 'paused' : 'resumed'} successfully.`, 'success');
            await refreshMemberActivityLogs(membershipId, card);
        } else {
            showAlert(data.message || 'Failed to update session.', 'error');
            btnElement.disabled = false;
        }
    } catch (err) {
        console.error('Pause toggle error:', err);
        btnElement.disabled = false;
        showAlert('Server error occurred while updating session status.', 'error');
    }
}

document.addEventListener('click', function(e) {
    const pauseBtn = e.target.closest('.btn-pause-session, .btn-pause');
    if (pauseBtn) {
        e.preventDefault();
        e.stopPropagation();
        handlePauseClick(pauseBtn);
    }
});

window.handlePauseClick = handlePauseClick;

// === PAUSE / RESUME INITIAL STATE AUTO-CHECKER ===
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.btn-pause-session, .btn-pause').forEach(pauseBtn => {
        const isPaused = pauseBtn.getAttribute('data-is-paused') === 'true';

        if (isPaused) {
            pauseBtn.innerHTML = '▶ Resume Session';
            pauseBtn.style.backgroundColor = '#f59e0b';
        } else {
            pauseBtn.innerHTML = '⏸ Pause Session';
            pauseBtn.style.backgroundColor = '#6b7280';
        }
    });
});

    // === 7. SEARCH & FILTER LOGIC ===
    const searchInput = document.getElementById('memberListSearch');
    const memberCards = document.querySelectorAll('#list .member-list-card');
    const deactivatedSearchInput = document.getElementById('deactivatedListSearch');
    const deactivatedFilterDate = document.getElementById('deactivatedDateFilter');
    const deactivatedCards = document.querySelectorAll('#deactivated .member-list-card');

    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            const searchTerm = searchInput.value.toLowerCase();

            memberCards.forEach(card => {
                const cardText = card.getAttribute('data-searchable') || '';
                if (cardText.toLowerCase().includes(searchTerm)) {
                    card.style.display = 'grid';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    }

    if (deactivatedSearchInput || deactivatedFilterDate) {
        const filterDeactivated = () => {
            const searchTerm = deactivatedSearchInput ? deactivatedSearchInput.value.toLowerCase() : '';
            const selectedDate = deactivatedFilterDate ? deactivatedFilterDate.value : '';

            deactivatedCards.forEach(card => {
                const searchable = card.getAttribute('data-searchable') || '';
                const deactivatedDate = card.getAttribute('data-deactivated-date') || '';
                const matchesText = !searchTerm || searchable.toLowerCase().includes(searchTerm);
                const matchesDate = !selectedDate || deactivatedDate >= selectedDate;

                if (matchesText && matchesDate) {
                    card.style.display = 'grid';
                } else {
                    card.style.display = 'none';
                }
            });
        };

        if (deactivatedSearchInput) {
            deactivatedSearchInput.addEventListener('keyup', filterDeactivated);
        }
        if (deactivatedFilterDate) {
            deactivatedFilterDate.addEventListener('change', filterDeactivated);
        }
    }


    // === 8. DATE DISPLAY ===
    const dateDisplay = id => {
        const element = document.getElementById(id);
        if (element) {
            const now = new Date();
            const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
            element.innerText = now.toLocaleDateString('en-US', options);
        }
    };
    dateDisplay('currentDateDisplay');

});