document.addEventListener('DOMContentLoaded', function() {
    const openBtn = document.getElementById('openWalkinBtn');
    const closeBtn = document.getElementById('closeModalBtn');
    const modal = document.getElementById('walkinModal');
    const walkinForm = document.getElementById('walkinForm');

    function showWalkinConflict(message) {
        let alertBox = document.getElementById('walkin-conflict-alert');
        if (!alertBox && modal) {
            alertBox = document.createElement('div');
            alertBox.id = 'walkin-conflict-alert';
            alertBox.className = 'alert alert-danger d-none';
            alertBox.setAttribute('role', 'alert');
            walkinForm?.prepend(alertBox);
        }
        if (alertBox) {
            alertBox.textContent = message || 'Time Conflict detected.';
            alertBox.classList.remove('d-none');
        } else {
            alert(message || 'Time Conflict detected.');
        }
    }

    if (walkinForm) {
        walkinForm.addEventListener('submit', async function(event) {
            event.preventDefault();
            try {
                const response = await fetch(walkinForm.action, {
                    method: 'POST',
                    body: new FormData(walkinForm),
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const result = await response.json();
                if (!response.ok || !result.success) {
                    showWalkinConflict(result.message);
                    return;
                }
                location.reload();
            } catch (error) {
                console.error('Walk-in error:', error);
                showWalkinConflict('Unable to check in the walk-in. Please try again.');
            }
        });
    }

    if (openBtn && modal) {
        openBtn.addEventListener('click', function() {
            modal.classList.add('active');
            document.body.style.overflow = 'hidden';
        });
    }

    if (closeBtn && modal) {
        closeBtn.addEventListener('click', function() {
            modal.classList.remove('active');
            document.body.style.overflow = '';
        });
    }

    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    }

    // Live preview logic
    const fName = document.getElementById('f-name');
    const fContact = document.getElementById('f-contact');
    const fArea = document.getElementById('f-area');
    const fPax = document.getElementById('f-pax');
    const paxWrapper = document.getElementById('pax-count-wrapper');
    const fStartTime = document.getElementById('f-start-time');
    const fDurationSelect = document.getElementById('f-duration-select');
    const fEndTime = document.getElementById('f-end-time');
    const fEndDisplay = document.getElementById('f-end-display');
    const fOpenTime = document.getElementById('f-open-time');
    const fFees = document.getElementById('f-fees');
    const fDiscount = document.getElementById('f-discount');

        // === FUNCTION PARA MAG HIDE / SHOW SANG PAX COUNT ===
        function togglePaxVisibility() {
        if (!fArea || !paxWrapper) return;
        
        const opt = fArea.options[fArea.selectedIndex];
        const roomName = opt ? opt.text.toLowerCase() : '';
        const isLectureRoom = roomName.includes('lecture room');
        const isEventRoom = roomName.includes('event room');

        if (isLectureRoom || isEventRoom) {
            paxWrapper.classList.remove('d-none');
            paxWrapper.style.removeProperty('display');

            if (fPax) {
                if (isLectureRoom) {
                    fPax.setAttribute('max', '15');
                    if (parseInt(fPax.value, 10) > 15) {
                        fPax.value = 15;
                    }
                } else {
                    fPax.removeAttribute('max');
                }
            }
        } else {
            paxWrapper.classList.add('d-none');
            paxWrapper.style.setProperty('display', 'none', 'important');
            if (fPax) {
                fPax.value = 1;
                fPax.removeAttribute('max');
            }
        }
    }

    togglePaxVisibility();

// Predefined add-ons
const predefinedAddonSelect = document.getElementById('f-predefined-addon');
const predefinedAddonQtyInput = document.getElementById('f-predefined-addon-qty');
const addonsJsonField = document.getElementById('addons_json');
const addonSubtotalField = document.getElementById('addon_subtotal');
const pAddonTotalDisplay = document.getElementById('p-addon-total-display');

const ADDON_NAMES = {
    'Projector': 'Projector',
    'Extra Chairs': 'Extra Chairs',
    'Extension Cord': 'Extension Cord',
    'Whiteboard Set': 'Whiteboard Set',
};

function normalizeAddonQty(raw) {
    if (raw === null || raw === undefined) return 1;
    if (typeof raw === 'string' && raw.trim() === '') return 1;
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n) || n < 1) return 1;
    return n;
}

function computePredefinedAddon() {
    if (!predefinedAddonSelect) {
        return { addonName: null, quantity: 1, unitPrice: 0, subtotal: 0 };
    }
    const selectedValue = predefinedAddonSelect.value || 'None';
    if (!selectedValue || selectedValue === 'None') {
        return { addonName: null, quantity: 1, unitPrice: 0, subtotal: 0 };
    }

    const opt = predefinedAddonSelect.options[predefinedAddonSelect.selectedIndex];
    const unitPrice = parseFloat(opt?.dataset?.unitPrice) || 0;
    const quantity = normalizeAddonQty(predefinedAddonQtyInput?.value);
    const subtotal = quantity * unitPrice;

    const addonName = ADDON_NAMES[selectedValue] || selectedValue;

    return { addonName, quantity, unitPrice, subtotal };
}

let addonNameToIdCache = null;

async function ensureAddonIdCache() {
    if (addonNameToIdCache) return addonNameToIdCache;
    try {
        const res = await fetch('/api/addons', { method: 'GET', headers: { 'Content-Type': 'application/json' } });
        if (!res.ok) throw new Error('Failed to load addons');
        const data = await res.json();
        addonNameToIdCache = new Map((data.addons || []).map(a => [a.name, a.id]));
        return addonNameToIdCache;
    } catch (e) {
        addonNameToIdCache = new Map();
        return addonNameToIdCache;
    }
}

async function updatePredefinedAddonFields() {
    const result = computePredefinedAddon();

    if (pAddonTotalDisplay) {
        pAddonTotalDisplay.textContent = '₱' + (result.subtotal || 0).toFixed(2);
    }

    if (!addonsJsonField || !addonSubtotalField) return;

    if (!result.addonName) {
        addonSubtotalField.value = '0.00';
        addonsJsonField.value = JSON.stringify([]);
        return;
    }

    const qty = normalizeAddonQty(predefinedAddonQtyInput?.value);
    const unitPrice = result.unitPrice;
    const subtotal = qty * unitPrice;

    const cache = await ensureAddonIdCache();
    const addonId = cache.get(result.addonName);

    if (!addonId) {
        addonsJsonField.value = JSON.stringify([
            {
                addon_name: result.addonName,
                quantity: qty,
                unit_price: unitPrice,
                subtotal: subtotal,
            },
        ]);
        addonSubtotalField.value = subtotal.toFixed(2);
        return;
    }

    addonsJsonField.value = JSON.stringify([
        {
            addon_id: addonId,
            addon_name: result.addonName,
            quantity: qty,
            unit_price: unitPrice,
            subtotal: subtotal,
        },
    ]);

    addonSubtotalField.value = subtotal.toFixed(2);
}

const pCustomer = document.getElementById('p-customer');
const pContact = document.getElementById('p-contact');
const pArea = document.getElementById('p-area');
const pStart = document.getElementById('p-start');
const pEnd = document.getElementById('p-end');
const pDuration = document.getElementById('p-duration');

const pFeesDisplay = document.getElementById('p-fees-display');
const pTotal = document.getElementById('p-total');
const totalPriceInput = document.getElementById('total_price');

function toLocalISOString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function formatDateTimeLocal(value) {
    if (!value) return '----';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
    });
}

// === TIER CALCULATOR LOGIC ===
function getTierRate(roomName, paxCount, defaultBaseRate) {
    const name = roomName ? roomName.toLowerCase() : '';
    const pax = parseInt(paxCount) || 1;

    if (name.includes('lecture room')) {
        if (pax <= 5) return 150;
        if (pax <= 10) return 200;
        return 250;
    } else if (name.includes('event room')) {
        if (pax <= 15) return 300;
        if (pax <= 30) return 400;
        return 500;
    }
    
    return defaultBaseRate;
}

function updateWalkinPreview() {
    togglePaxVisibility();

    if (pCustomer) pCustomer.textContent = fName?.value || '----';
    if (pContact) pContact.textContent = fContact?.value || '----';
    if (pArea) {
        const opt = fArea?.options[fArea.selectedIndex];
        pArea.textContent = opt ? opt.text.split(' (')[0] : '----';
    }

    if (pStart) pStart.textContent = fStartTime?.value ? formatDateTimeLocal(fStartTime.value) : 'Now';

    const extraFee = parseFloat(fFees?.value) || 0;
    const addonSubtotal = parseFloat(addonSubtotalField?.value || 0) || 0;
    if (pFeesDisplay) pFeesDisplay.textContent = '₱' + extraFee.toFixed(2);

    let total = 0;
    let duration = 0;

    if (fOpenTime?.checked) {
        if (pEnd) pEnd.textContent = 'OPEN TIME';
        duration = 1;
    } else if (fStartTime?.value && fDurationSelect?.value) {
        const start = new Date(fStartTime.value);
        const durationHours = parseFloat(fDurationSelect.value) || 1;
        
        const end = new Date(start.getTime());
        end.setHours(end.getHours() + durationHours);

        const formattedEndLocal = toLocalISOString(end);

        if (pEnd) pEnd.textContent = formatDateTimeLocal(formattedEndLocal);
        if (fEndTime) fEndTime.value = formattedEndLocal;
        if (fEndDisplay) fEndDisplay.value = formattedEndLocal;
        duration = durationHours;
    } else if (fStartTime?.value && fEndTime?.value) {
        if (pEnd) pEnd.textContent = formatDateTimeLocal(fEndTime.value);
        const s = new Date(fStartTime.value);
        const e = new Date(fEndTime.value);
        let diff = (e - s) / 1000 / 60 / 60;
        if (diff <= 0) diff += 24;
        duration = diff;
    }

    if (pDuration) {
        if (fOpenTime?.checked) {
            pDuration.textContent = 'Open Time';
        } else {
            pDuration.textContent = duration > 0 ? duration.toFixed(1) + ' Hr/s' : '----';
        }
    }

    // TIER RATE CALCULATION
    const opt = fArea?.options[fArea.selectedIndex];
    const roomNameText = opt ? opt.text : '';
    const rateMatch = opt ? roomNameText.match(/₱(\d+)/) : null;
    const fallbackRate = rateMatch ? parseInt(rateMatch[1]) : 0;

    const paxValue = fPax ? fPax.value : 1;
    const baseRate = getTierRate(roomNameText, paxValue, fallbackRate);

    const discount = fDiscount ? parseFloat(fDiscount.value) : 0;

    if (fOpenTime?.checked) {
        let roomCost = baseRate * (1 - discount);
        total = roomCost + extraFee + addonSubtotal;
    } else {
        let roomCost = baseRate * duration * (1 - discount);
        total = roomCost + extraFee + addonSubtotal;
    }

    if (pTotal) {
        const label = fOpenTime?.checked ? ' (Initial)' : '';
        pTotal.textContent = '₱' + total.toLocaleString(undefined, {minimumFractionDigits: 2}) + label;
    }
    if (totalPriceInput) {
        totalPriceInput.value = total.toFixed(2);
    }
}

// Addon listeners
if (predefinedAddonSelect) {
    predefinedAddonSelect.addEventListener('change', function() {
        updatePredefinedAddonFields().then(updateWalkinPreview);
    });
}
if (predefinedAddonQtyInput) {
    predefinedAddonQtyInput.addEventListener('input', function() {
        const n = normalizeAddonQty(predefinedAddonQtyInput.value);
        predefinedAddonQtyInput.value = n;
        updatePredefinedAddonFields().then(updateWalkinPreview);
    });
}

// Attach event listeners correctly without inner loop calls
const walkinInputs = [fName, fContact, fArea, fPax, fStartTime, fDurationSelect, fEndTime, fFees, fDiscount];
walkinInputs.forEach(el => {
    if (el) {
        el.addEventListener('input', updateWalkinPreview);
        el.addEventListener('change', updateWalkinPreview);
    }
});

function updateOpenTimeAvailability() {
    if (fOpenTime) {
        fOpenTime.disabled = false;
    }
}

if (fArea) {
    fArea.addEventListener('change', function() {
        updateOpenTimeAvailability();
        updateWalkinPreview();
    });
    updateOpenTimeAvailability();
}

if (fOpenTime) {
    fOpenTime.addEventListener('change', function() {
        if (fEndTime) fEndTime.disabled = this.checked;
        if (this.checked) {
            if (fEndTime) fEndTime.value = '';
            if (fEndDisplay) fEndDisplay.value = '';
        } else if (fStartTime?.value && fDurationSelect?.value) {
            const start = new Date(fStartTime.value);
            const durationHours = parseFloat(fDurationSelect.value) || 1;
            const end = new Date(start.getTime() + durationHours * 3600 * 1000);
            if (fEndTime) fEndTime.value = end.toISOString().slice(0, 16);
            if (fEndDisplay) fEndDisplay.value = end.toISOString().slice(0, 16);
        }
        updateWalkinPreview();
    });
}

// Set start time to now by default
if (fStartTime && !fStartTime.value) {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    fStartTime.value = `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Initial calculation call
updateWalkinPreview();

    // Ensure confirm button shows confirmation modal before submitting the form
    const confirmBtn = document.querySelector('#walkinModal .btn-confirm-blue');
    if (confirmBtn && walkinForm) {
        confirmBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Validate required fields
            if (!fName.value.trim() || !fArea.value || !fStartTime.value) {
                // Use SweetAlert2 if available, otherwise use native alert
                if (typeof Swal !== 'undefined') {
                    Swal.fire({
                        icon: 'warning',
                        title: 'Incomplete Data',
                        text: 'Please fill in all required fields.',
                        confirmButtonColor: '#82cae8'
                    });
                } else {
                    if (typeof showToast === 'function') showToast('Please fill in all required fields.', 'warning');
                    showToast('Please fill in all required fields.', 'warning');
                }
                return;
            }

            // Show confirmation modal with walk-in details
            const confirmationTitle = 'Confirm Walk-in?';
            const confirmationText = `Confirm walk-in for ${fName.value}. Total: ${pTotal.innerText}`;

            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    title: confirmationTitle,
                    text: confirmationText,
                    icon: 'question',
                    showCancelButton: true,
                    confirmButtonColor: '#82cae8',
                    cancelButtonColor: '#d90429',
                    confirmButtonText: 'Yes, Check In!',
                    didOpen: function() {
                        setTimeout(() => {
                            Swal.getConfirmButton().focus();
                        }, 100);
                    }
                }).then(result => {
                    if (result.isConfirmed) {
                        walkinForm.requestSubmit();
                    }
                });
            } else if (typeof confirmAction === 'function') {
                confirmAction(confirmationTitle, confirmationText, 'Yes, Check In!', 'Cancel')
                    .then(confirmed => { if (confirmed) walkinForm.requestSubmit(); });
            } else {
                walkinForm.requestSubmit();
            }
        });
    }

});