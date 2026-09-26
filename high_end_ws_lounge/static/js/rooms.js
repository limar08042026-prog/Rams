function toLocalISOString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

document.addEventListener('DOMContentLoaded', function() {
    // DOM Query Selectors
    const openTimeToggle = document.getElementById('open-time-toggle');
    const endTimeInput = document.getElementById('end-time');
    const durationSelect = document.getElementById('duration-select');
    const endDisplay = document.getElementById('end-display');
    const hiddenOpenTime = document.getElementById('form-open-time');

    const roomSelector = document.getElementById('room-selector');
    const paxInput = document.getElementById('pax_count');
    const paxContainer = document.getElementById('pax_container')
    const startTimeInput = document.getElementById('start-time');
    const extraFeesSelect = document.getElementById('extra-fees-select');

    const addonQuantityInput = document.getElementById('addon-quantity');
    const extraFeeTotalInput = document.getElementById('extra-fee-total');
    const summaryContainer = document.getElementById('booking-summary-container');
    const paymentInfoPanel = document.getElementById('payment-info-panel');
    const paymentInfoData = document.getElementById('paymentInfoData');
    const currentUserRoleEl = document.getElementById('currentUserRole');
    const currentUserRole = currentUserRoleEl?.dataset.role || '';
    const receiptUploadSection = document.getElementById('receipt-upload-section');
    const paymentMethodLabel = document.getElementById('payment-method-label');
    const paymentInstructions = document.getElementById('payment-instructions');
    const paymentModal = document.getElementById('payment-modal');
    const paymentModalClose = document.getElementById('payment-modal-close');
    const modalPaymentMethod = document.getElementById('modal-payment-method');
    const modalAccountInfo = document.getElementById('modal-account-info');
    const modalInstructions = document.getElementById('modal-instructions');
    const modalQrImage = document.getElementById('modal-qr-image');
    const paymentDetailsButton = document.getElementById('show-payment-modal');
    const summaryDeposit = document.getElementById('summary-deposit');
    
    // Payment Type Elements
    const paymentTypeSection = document.getElementById('payment-type-section');
    const paymentAmountDisplay = document.getElementById('payment-amount-display');
    const displayTotalAmount = document.getElementById('display-total-amount');
    const displayDownpaymentAmount = document.getElementById('display-downpayment-amount');
    const displayFullpaymentAmount = document.getElementById('display-fullpayment-amount');
    const downpaymentRow = document.getElementById('downpayment-row');
    const fullpaymentRow = document.getElementById('fullpayment-row');
    const receiptAmountLabel = document.getElementById('receipt-amount-label');
    const paymentTypeRadios = document.querySelectorAll('input[name="payment_type"]');

    // Open Time Switch Handler (Option A: Safe Default Value without triggering Required Error)
if (openTimeToggle) {
    openTimeToggle.addEventListener('change', function() {
        if (hiddenOpenTime) {
            hiddenOpenTime.value = this.checked ? "true" : "false";
        }

        if (this.checked) {
            if (durationSelect) durationSelect.disabled = true;
            if (endDisplay) {
                endDisplay.disabled = true;
                endDisplay.value = 'Open Time (Per Minute / Hourly)';
                endDisplay.placeholder = "Open Time Activated";
            }
            
            if (endTimeInput) {
                endTimeInput.required = false;
                // Hatagan sang +8 Hours nga hidden value para indi mag-fail ang HTML5 / Flask validation
                if (startTimeInput && startTimeInput.value) {
                    const start = new Date(startTimeInput.value);
                    const safeEnd = new Date(start.getTime());
                    safeEnd.setHours(safeEnd.getHours() + 8);
                    endTimeInput.value = toLocalISOString(safeEnd);
                }
            }
        } else {
            if (durationSelect) durationSelect.disabled = false;
            if (endDisplay) {
                endDisplay.disabled = false;
                endDisplay.placeholder = "Auto-calculated end time";
            }
            if (endTimeInput) {
                endTimeInput.required = true;
            }
            if (typeof calculateEndTime === 'function') {
                calculateEndTime();
            }
        }

        if (typeof calculateTotal === 'function') {
            calculateTotal();
        }
    });
}


    function initializePaymentInfo() {
        if (paymentInfoData) {
            try {
                window.paymentInfo = JSON.parse(paymentInfoData.textContent || '{}');
            } catch (err) {
                console.warn('Invalid paymentInfo JSON:', err);
                window.paymentInfo = {};
            }
        }
    }

    async function loadPaymentInfo() {
        initializePaymentInfo();
        if (window.paymentInfo && Object.keys(window.paymentInfo).length) {
            updatePaymentInfo();
            return;
        }
        try {
            const res = await fetch('/api/payment-info');
            if (!res.ok) throw new Error('Failed to fetch payment info');
            const data = await res.json();
            window.paymentInfo = data;
            updatePaymentInfo();
        } catch (error) {
            console.warn('Unable to load payment info:', error);
        }
    }
    const depositNote = document.querySelector('.deposit-note');
    const paymentRadios = document.querySelectorAll('input[name="payment_method"]');

    // Summary Display Elements
    const summaryRoom = document.getElementById('summary-room');
    const summaryHours = document.getElementById('summary-hours');
    const summaryTotal = document.getElementById('summary-total');

    function updatePaymentTypeDisplay() {
        const selectedType = Array.from(paymentTypeRadios).find((radio) => radio.checked);
        if (!selectedType) return;

        const paymentType = selectedType.value;
        
        // FIX: Tangtangon ang tanan nga indi-numeric characters (manga ₱, commas, spaces) bag-o mag-parseFloat
        const totalText = summaryTotal ? summaryTotal.textContent : "0";
        const cleanTotalText = totalText.replace(/[^0-9.-]+/g, ""); 
        const totalAmount = parseFloat(cleanTotalText) || 0;

        if (displayTotalAmount) {
            displayTotalAmount.textContent = '₱' + totalAmount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        
        if (paymentType === 'Downpayment') {
            if (downpaymentRow) downpaymentRow.classList.remove('d-none');
            if (fullpaymentRow) fullpaymentRow.classList.add('d-none');
            
            const downpaymentAmount = totalAmount * 0.5;
            if (displayDownpaymentAmount) {
                displayDownpaymentAmount.textContent = '₱' + downpaymentAmount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }
            if (receiptAmountLabel) receiptAmountLabel.textContent = 'downpayment (50%)';
        } else {
            if (downpaymentRow) downpaymentRow.classList.add('d-none');
            if (fullpaymentRow) fullpaymentRow.classList.remove('d-none');
            
            if (displayFullpaymentAmount) {
                displayFullpaymentAmount.textContent = '₱' + totalAmount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }
            if (receiptAmountLabel) receiptAmountLabel.textContent = 'full payment';
        }
    }

    function updatePaymentInfo() {
        const selected = Array.from(paymentRadios).find((radio) => radio.checked);
        if (!selected) {
            paymentInfoPanel.classList.add('d-none');
            receiptUploadSection.classList.add('d-none');
            paymentTypeSection.classList.add('d-none');
            paymentAmountDisplay.classList.add('d-none');
            return;
        }

        const method = selected.value;
        const info = window.paymentInfo && window.paymentInfo[method];
        paymentInfoPanel.classList.remove('d-none');
        receiptUploadSection.classList.remove('d-none');
        paymentTypeSection.classList.remove('d-none');
        paymentAmountDisplay.classList.remove('d-none');
        
        paymentMethodLabel.textContent = `${method} Payment`;
        paymentInstructions.textContent = info
            ? 'Click "View Payment QR & Details" to see the account, QR code, and payment instructions.'
            : 'No payment settings are configured for this method. Please contact admin.';

        if (paymentDetailsButton) {
            paymentDetailsButton.classList.remove('d-none');
        }

        if (modalPaymentMethod && modalAccountInfo && modalInstructions) {
            modalPaymentMethod.textContent = `${method} Payment Details`;
            modalAccountInfo.textContent = info
                ? `${info.account_name || method} • ${info.account_number || 'No number configured yet'}`
                : `No account configured for ${method}.`;
            modalInstructions.textContent = info
                ? info.instructions || `Transfer the payment to the ${method} account and upload the receipt.`
                : 'Please contact admin for payment details.';

            if (info && info.qr_image) {
                modalQrImage.classList.remove('d-none');
                modalQrImage.src = info.qr_image;
            } else {
                modalQrImage.classList.add('d-none');
                modalQrImage.src = '';
            }
        }
        
        updatePaymentTypeDisplay();
    }

    function openPaymentModal() {
        if (!paymentModal) return;
        paymentModal.classList.remove('d-none');
    }

    function closePaymentModal() {
        if (!paymentModal) return;
        paymentModal.classList.add('d-none');
    }

    if (paymentDetailsButton) {
        paymentDetailsButton.addEventListener('click', openPaymentModal);
    }

    if (paymentModalClose) {
        paymentModalClose.addEventListener('click', closePaymentModal);
    }

    if (paymentModal) {
        paymentModal.addEventListener('click', function(e) {
            if (e.target === paymentModal) {
                closePaymentModal();
            }
        });
    }

// Helper function para sa Open Time minute-tier rate calculation (Sobra sa 1 Hour)
function calculateOpenTimeMinutesFee(minutes) {
    if (minutes <= 0) return 0;
    if (minutes >= 1 && minutes <= 12) return 5;
    if (minutes >= 13 && minutes <= 24) return 10;
    if (minutes >= 25 && minutes <= 36) return 15;
    if (minutes >= 37 && minutes <= 47) return 20;
    if (minutes >= 48 && minutes <= 60) return 25;
    return 35; // Default full hour rate
}

    function calculateTotal() {
        if (!roomSelector) return;

        const selectedRoom = roomSelector.options[roomSelector.selectedIndex];
        const startVal = startTimeInput ? startTimeInput.value : '';
        const roomText = selectedRoom ? selectedRoom.text.toLowerCase() : '';

        // 1. Dynamic Pax-Tier Rate Calculation
        let baseRate = parseFloat(selectedRoom?.dataset.rate) || 35;
        const paxCount = parseInt(paxInput?.value) || 1;

        // Check Lecture Room Tiers
        if (roomText.includes('lecture room')) {
            if (paxCount >= 1 && paxCount <= 5) {
                baseRate = 150;
            } else if (paxCount >= 6 && paxCount <= 10) {
                baseRate = 200;
            } else if (paxCount >= 11 && paxCount <= 15) {
                baseRate = 250;
            }
        } 
        // Check Event Room Tiers
        else if (roomText.includes('event room')) {
            if (paxCount >= 1 && paxCount <= 15) {
                baseRate = 300;
            } else if (paxCount >= 16 && paxCount <= 30) {
                baseRate = 400;
            } else {
                baseRate = 500;
            }
        }

        // 2. Addon Calculation
        const selectedAddonOption = extraFeesSelect?.options[extraFeesSelect.selectedIndex];
        const addonPrice = parseFloat(selectedAddonOption?.dataset.unitPrice || extraFeesSelect?.value || 0) || 0;
        const rawQty = addonQuantityInput?.value?.trim() ?? '';
        const quantity = (rawQty === '') ? 1 : Math.max(0, parseInt(rawQty, 10) || 0);
        const extraFeeTotal = addonPrice * quantity;

        if (extraFeeTotalInput) {
            extraFeeTotalInput.value = extraFeeTotal.toFixed(2);
        }

        // 3. Time Formatting & Duration Pricing
        let roomTotalFee = 0;
        let hoursDisplay = "1.0 hrs";

        if (startVal && !openTimeToggle?.checked && durationSelect?.value) {
            const start = new Date(startVal);
            const durationHours = parseFloat(durationSelect.value) || 1;

            const end = new Date(start.getTime());
            end.setHours(end.getHours() + durationHours);

            const formattedEndLocal = toLocalISOString(end);

            if (endTimeInput) endTimeInput.value = formattedEndLocal;
            if (endDisplay) endDisplay.value = formattedEndLocal.replace('T', ' ');

            roomTotalFee = baseRate * durationHours;
            hoursDisplay = durationHours.toFixed(1) + " hrs";

        } else if (openTimeToggle?.checked) {
            if (endTimeInput) {
                endTimeInput.value = ''; 
            }
            if (endDisplay) {
                endDisplay.value = 'Open Time (Per Minute / Hourly)';
            }
            roomTotalFee = baseRate;
            hoursDisplay = "Open Time (Initial 1 Hr)";
        }

        // 4. UI Summary Display & Deposits Updates
        if (selectedRoom && selectedRoom.value) {
            const total = roomTotalFee + extraFeeTotal;

            const addonLabel = extraFeesSelect?.options[extraFeesSelect.selectedIndex]?.text || '';
            const addonSummary = (addonPrice > 0 && quantity > 0)
                ? `${quantity} x ${addonLabel.replace(/\s*\(.*\)/, '')}`
                : 'None';

            if (summaryRoom) summaryRoom.textContent = selectedRoom.text.split('(')[0];
            if (summaryHours) summaryHours.textContent = hoursDisplay;

            const addonSummaryEl = document.getElementById('summary-addons');
            if (addonSummaryEl) addonSummaryEl.textContent = addonSummary;

            if (summaryTotal) {
                summaryTotal.textContent = '₱' + total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }

            const deposit = (total * 0.5).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            if (summaryDeposit) {
                summaryDeposit.textContent = `₱${deposit}`;
            }
            if (depositNote) {
                depositNote.classList.remove('d-none');
            }

            if (summaryContainer) summaryContainer.style.display = 'block';

            if (typeof updatePaymentTypeDisplay === 'function') {
                updatePaymentTypeDisplay();
            }
        } else {
            if (summaryContainer) summaryContainer.style.display = 'none';
            if (depositNote) depositNote.classList.add('d-none');
            if (paymentAmountDisplay) paymentAmountDisplay.classList.add('d-none');
        }
    }

    // ==========================================
    // LISTENERS FOR LIVE CALCULATION & PAYMENTS
    // ==========================================

    [roomSelector, startTimeInput, endTimeInput, durationSelect, extraFeesSelect, addonQuantityInput, paxInput].forEach(el => {
        if (!el) return;
        el.addEventListener('change', calculateTotal);
    });

    if (paxInput) {
        paxInput.addEventListener('input', calculateTotal);
    }

    if (addonQuantityInput) {
        addonQuantityInput.addEventListener('input', calculateTotal);
    }

    if (extraFeesSelect && addonQuantityInput) {
        extraFeesSelect.addEventListener('change', function () {
            const selectedPrice = parseFloat(this.value) || 0;

            if (selectedPrice > 0 && addonQuantityInput.value.trim() === '') {
                addonQuantityInput.value = 1;
            }
            
            if (selectedPrice === 0) {
                addonQuantityInput.value = 0;
            }
            calculateTotal();
        });
    }

    // Payment selection listeners
    if (paymentRadios && paymentRadios.length) {
        paymentRadios.forEach((radio) => {
            radio.addEventListener('change', updatePaymentInfo);
        });
    }

    // Payment type selection listeners
    if (paymentTypeRadios && paymentTypeRadios.length) {
        paymentTypeRadios.forEach((radio) => {
            radio.addEventListener('change', updatePaymentTypeDisplay);
        });
    }

    updatePaymentInfo();
    loadPaymentInfo();

    // ==========================================
    // PAX COUNT TOGGLE & VALIDATION LOGIC
    // ==========================================

    // Function para mag Hide / Show sang Pax Count Input Field
    function togglePaxField() {
        if (!roomSelector) return;

        const selectedOption = roomSelector.options[roomSelector.selectedIndex];
        const selectedText = selectedOption ? selectedOption.text.toLowerCase() : '';

        const isCapacityRoom = selectedText.includes('common area') || selectedText.includes('lecture room') || selectedText.includes('event room');

        if (isCapacityRoom) {
            if (paxContainer) paxContainer.style.display = 'flex';
            if (paxInput && !paxInput.value) paxInput.value = 1;
        } else {
            if (paxContainer) paxContainer.style.display = 'none';
            if (paxInput) paxInput.value = 1; // Reset sa 1 kon indi capacity-based room
        }
    }

    // Function para sa Pax Count Validation (Max 15 Pax sa Lecture Room)
    function validatePaxCount() {
        if (!roomSelector || !paxInput) return;

        const selectedOption = roomSelector.options[roomSelector.selectedIndex];
        const selectedText = selectedOption ? selectedOption.text.toLowerCase() : '';
        let pax = parseInt(paxInput.value) || 1;

        if (selectedText.includes('lecture room')) {
            if (pax > 15) {
                if (typeof Swal !== 'undefined') {
                    Swal.fire({
                        icon: 'warning',
                        title: 'Capacity Exceeded',
                        text: 'Lecture Room capacity is strictly limited to 15 pax max.'
                    });
                } else {
                    alert('Lecture Room capacity is strictly limited to 15 pax max.');
                }
                paxInput.value = 15;
            }
        }

        // Automatic recalculate sang total display
        calculateTotal();
    }

    // Event Listeners para sa Room Selector, Pax Input, Duration, kag Addons
    if (roomSelector) {
        roomSelector.addEventListener('change', function() {
            togglePaxField();
            validatePaxCount();
        });
    }

    if (paxInput) {
        paxInput.addEventListener('input', validatePaxCount);
    }

    if (durationSelect) {
        durationSelect.addEventListener('change', calculateTotal);
    }

    if (extraFeesSelect) {
        extraFeesSelect.addEventListener('change', calculateTotal);
    }

    if (addonQuantityInput) {
        addonQuantityInput.addEventListener('input', calculateTotal);
    }

    // Initial Run pag-load sang page
    togglePaxField();
    calculateTotal();

    // 4. Table Filtering Logic (New Upgrade)
    const filterDate = document.getElementById('filter-date');
    const filterStatus = document.getElementById('filter-status');
    const bookingRows = document.querySelectorAll('.booking-row');

    function filterTable() {
        const dateVal = filterDate.value;
        const statusVal = filterStatus.value.toLowerCase();

        bookingRows.forEach(row => {
            const rowDate = row.getAttribute('data-date'); // Expected format: YYYY-MM-DD...
            const rowStatus = row.getAttribute('data-status').toLowerCase();
            
            const matchesDate = !dateVal || rowDate.includes(dateVal);
            const matchesStatus = !statusVal || rowStatus === statusVal;

            row.style.display = (matchesDate && matchesStatus) ? '' : 'none';
        });
    }

    if (filterDate && filterStatus) {
        filterDate.addEventListener('input', filterTable);
        filterStatus.addEventListener('change', filterTable);
    }

    // 5. CSV Export Logic (New Upgrade)
    const exportBtn = document.getElementById('export-csv');
    if (exportBtn) {
        exportBtn.addEventListener('click', function() {
            let csv = 'Room,Start Time,End Time,Status\n';
            const rows = document.querySelectorAll('.booking-table tbody tr:not([style*="display: none"])');
            
            rows.forEach(row => {
                const cols = row.querySelectorAll('td');
                if (cols.length >= 4) {
                    const rowData = Array.from(cols).map(col => `"${col.textContent.trim()}"`);
                    csv += rowData.join(',') + '\n';
                }
            });

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.setAttribute('hidden', '');
            a.setAttribute('href', url);
            a.setAttribute('download', 'bookings_export.csv');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        });
    }

// 6. Booking Form Submission with Confirmation Modal
const bookingForm = document.getElementById('booking-form');
const submitBtn = document.getElementById('submit-booking');

if (submitBtn && bookingForm) {
    submitBtn.addEventListener('click', function(e) {
        e.preventDefault();

        // Prevent non-members from reserving on client-side
        if (currentUserRole && currentUserRole !== 'member') {
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'warning',
                    title: 'Members Only',
                    text: 'Only members can make reservations. Please login with a member account.',
                    confirmButtonColor: '#82cae8'
                });
            } else {
                if (typeof showToast === 'function') showToast('Only members can make reservations.', 'warning');
            }
            return;
        }
        
        // Validate required fields
        const customerName = document.querySelector('input[name="customer_name"]')?.value?.trim();
        const contactNumber = document.querySelector('input[name="contact_number"]')?.value?.trim();
        const roomId = roomSelector?.value;
        const startTime = startTimeInput?.value;
        const endTime = endTimeInput?.value;
        const isOpenTime = openTimeToggle?.checked;
        const paymentMethod = document.querySelector('input[name="payment_method"]:checked')?.value;
        const paymentType = document.querySelector('input[name="payment_type"]:checked')?.value;
        const receiptUpload = document.getElementById('receipt-upload');
        
        if (!customerName || !contactNumber || !roomId || !startTime || (!endTime && !isOpenTime)) {
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'warning',
                    title: 'Incomplete Information',
                    text: 'Please fill in all required fields.',
                    confirmButtonColor: '#82cae8'
                });
            } else {
                if (typeof showToast === 'function') showToast('Please fill in all required fields.', 'warning');
            }
            return;
        }
        
        if (!paymentMethod) {
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'warning',
                    title: 'Payment Method Required',
                    text: 'Please select a payment method.',
                    confirmButtonColor: '#82cae8'
                });
            } else {
                if (typeof showToast === 'function') showToast('Please select a payment method.', 'warning');
            }
            return;
        }
        
        if (!paymentType) {
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'warning',
                    title: 'Payment Type Required',
                    text: 'Please select a payment type.',
                    confirmButtonColor: '#82cae8'
                });
            } else {
                if (typeof showToast === 'function') showToast('Please select a payment type.', 'warning');
            }
            return;
        }
        
        if (receiptUpload && !receiptUpload.classList.contains('d-none') && !receiptUpload.value) {
            if (typeof Swal !== 'undefined') {
                Swal.fire({
                    icon: 'warning',
                    title: 'Receipt Required',
                    text: 'Please upload your payment receipt.',
                    confirmButtonColor: '#82cae8'
                });
            } else {
                if (typeof showToast === 'function') showToast('Please upload your payment receipt.', 'warning');
            }
            return;
        }
        
        // Show confirmation modal with booking details
        const selectedRoom = roomSelector.options[roomSelector.selectedIndex];
        const roomName = selectedRoom ? selectedRoom.text.split('(')[0].trim() : '';
        const totalAmount = summaryTotal ? summaryTotal.textContent : '0.00';
        
        // Confirm reservation action
        confirmAction('Confirm Reservation?', `Confirming reservation for ${customerName} in ${roomName}. Total: ${totalAmount}`, 'Yes, Reserve it!', 'Cancel')
            .then(confirmed => {
                if (confirmed) {
                    // Direct native form submission bypass (Prevents form.submit name shadowing issue)
                    HTMLFormElement.prototype.submit.call(bookingForm);
                }
            });
    });
}

    // 7. Simple Alert Auto-dismiss (Existing)
    const alerts = document.querySelectorAll('.modern-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => { alert.style.display = 'none'; }, 500);
        }, 5000);
    });
});