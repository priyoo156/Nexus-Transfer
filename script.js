// Global variables to store order data
let uploadedFiles = [];
let orderData = {
    fileName: 'No file',
    totalPages: 0,
    copies: 1,
    colorMode: 'color',
    orientation: 'front',
    pageRange: 'all',
    customRange: '',
    totalAmount: 0
};

// Navigation functionality
function navigateTo(pageName) {
    // Hide all pages
    const allPages = document.querySelectorAll('.page');
    allPages.forEach(page => page.classList.remove('active'));

    // Show selected page
    const selectedPage = document.getElementById(pageName);
    if (selectedPage) {
        selectedPage.classList.add('active');
    }

    // Update active nav item
    const allNavItems = document.querySelectorAll('.nav-item');
    allNavItems.forEach(item => item.classList.remove('active'));

    const activeNavItem = document.querySelector(`[data-page="${pageName}"]`);
    if (activeNavItem) {
        activeNavItem.classList.add('active');
    }

    // Update order summary when navigating to payment
    if (pageName === 'payment') {
        updateOrderSummary();
    }

    // Close mobile menu
    const navLinks = document.getElementById('navLinks');
    if (navLinks) {
        navLinks.classList.remove('show');
    }

    // Scroll to top
    window.scrollTo(0, 0);
}

// Toggle mobile menu
function toggleMenu() {
    const navLinks = document.getElementById('navLinks');
    if (navLinks) {
        navLinks.classList.toggle('show');
    }
}

// Prevent default link behavior
document.addEventListener('DOMContentLoaded', function() {
    // Show upload page by default
    navigateTo('upload');

    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const pageName = this.getAttribute('data-page');
            navigateTo(pageName);
        });
    });

    // Upload functionality
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');

    if (uploadArea) {
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            this.style.backgroundColor = '#E8F0FE';
            this.style.borderColor = '#744BCE';
        });

        uploadArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            this.style.backgroundColor = '#F9F9F9';
            this.style.borderColor = '#744BCE';
        });

        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            this.style.backgroundColor = '#F9F9F9';
            const files = e.dataTransfer.files;
            handleFiles(files);
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            handleFiles(this.files);
        });
    }

    // Settings event listeners
    const colorRadios = document.querySelectorAll('input[name="colorMode"]');
    colorRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            orderData.colorMode = this.value;
            calculateTotal();
        });
    });

    const orientationRadios = document.querySelectorAll('input[name="orientation"]');
    orientationRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            orderData.orientation = this.value;
            calculateTotal();
        });
    });

    const pageRangeRadios = document.querySelectorAll('input[name="pageRange"]');
    pageRangeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            orderData.pageRange = this.value;
            calculateTotal();
        });
    });

    const customRangeInput = document.getElementById('customRange');
    if (customRangeInput) {
        customRangeInput.addEventListener('input', function() {
            orderData.customRange = this.value;
            calculateTotal();
        });
    }

    togglePageRangeInput();
    calculateTotal();

    // Payment button listeners
    const paymentBtns = document.querySelectorAll('.payment-btn');
    paymentBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            selectPaymentMethod(this.textContent.trim(), this);
        });
    });

    const payNowBtn = document.querySelector('.payment-methods .btn-primary');
    if (payNowBtn) {
        payNowBtn.addEventListener('click', processPayment);
    }
});

// Handle file uploads
function handleFiles(files) {
    const uploadedFilesDiv = document.getElementById('uploadedFiles');
    
    if (!uploadedFilesDiv) return;

    uploadedFilesDiv.innerHTML = '';
    uploadedFiles.length = 0; // Clear previous files
    let totalPages = 0;

    for (let file of files) {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <div class="file-info">
                <div class="file-name">📄 ${file.name}</div>
                <div class="file-size">${(file.size / 1024).toFixed(2)} KB</div>
            </div>
            <button class="remove-btn" onclick="removeFile('${file.name}')">Remove</button>
        `;
        uploadedFilesDiv.appendChild(fileItem);

        // Store file data
        const fileData = {
            name: file.name,
            size: file.size,
            type: file.type
        };
        uploadedFiles.push(fileData);

        // Estimate pages based on file type
        let pages = 1;
        if (file.type === 'application/pdf') {
            // For PDF, rough estimate: 50KB per page
            pages = Math.max(1, Math.ceil(file.size / 51200));
        } else if (file.type.startsWith('image/')) {
            // Images are typically 1 page
            pages = 1;
        } else {
            // Documents: rough estimate
            pages = Math.max(1, Math.ceil(file.size / 102400));
        }
        
        totalPages += pages;
    }

    // Update order data
    orderData.fileName = files.length === 1 ? files[0].name : `${files.length} files`;
    orderData.totalPages = totalPages;

    // Update total pages display
    const totalPagesSpan = document.getElementById('totalPages');
    if (totalPagesSpan) {
        totalPagesSpan.textContent = totalPages;
    }

    // Calculate total amount
    calculateTotal();
}

// Remove file function
function removeFile(fileName) {
    uploadedFiles = uploadedFiles.filter(file => file.name !== fileName);
    
    // Re-render uploaded files
    const uploadedFilesDiv = document.getElementById('uploadedFiles');
    uploadedFilesDiv.innerHTML = '';
    
    let totalPages = 0;
    uploadedFiles.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <div class="file-info">
                <div class="file-name">📄 ${file.name}</div>
                <div class="file-size">${(file.size / 1024).toFixed(2)} KB</div>
            </div>
            <button class="remove-btn" onclick="removeFile('${file.name}')">Remove</button>
        `;
        uploadedFilesDiv.appendChild(fileItem);

        // Recalculate pages
        let pages = 1;
        if (file.type === 'application/pdf') {
            pages = Math.max(1, Math.ceil(file.size / 51200));
        } else if (file.type.startsWith('image/')) {
            pages = 1;
        } else {
            pages = Math.max(1, Math.ceil(file.size / 102400));
        }
        totalPages += pages;
    });

    orderData.fileName = uploadedFiles.length === 1 ? uploadedFiles[0].name : 
                        uploadedFiles.length > 1 ? `${uploadedFiles.length} files` : 'No file';
    orderData.totalPages = totalPages;

    const totalPagesSpan = document.getElementById('totalPages');
    if (totalPagesSpan) {
        totalPagesSpan.textContent = totalPages;
    }

    calculateTotal();
}

// Copies management
function increaseCopies() {
    const copiesValue = document.getElementById('copiesValue');
    if (copiesValue) {
        let currentValue = parseInt(copiesValue.textContent);
        copiesValue.textContent = currentValue + 1;
        orderData.copies = currentValue + 1;
        calculateTotal();
    }
}

function decreaseCopies() {
    const copiesValue = document.getElementById('copiesValue');
    if (copiesValue) {
        let currentValue = parseInt(copiesValue.textContent);
        if (currentValue > 1) {
            copiesValue.textContent = currentValue - 1;
            orderData.copies = currentValue - 1;
            calculateTotal();
        }
    }
}

// Calculate total amount
function calculateTotal() {
    const pricePerPage = orderData.colorMode === 'bw' ? 2 : 10;
    let pagesToPrint = orderData.totalPages;
    
    // Handle custom page range
    if (orderData.pageRange === 'custom' && orderData.customRange) {
        pagesToPrint = parseCustomRange(orderData.customRange);
    }
    
    // Handle double-sided printing
    if (orderData.orientation === 'double') {
        pagesToPrint = Math.ceil(pagesToPrint / 2);
    }
    
    orderData.totalAmount = pagesToPrint * orderData.copies * pricePerPage;
}

// Parse custom page range (simplified)
function parseCustomRange(range) {
    // Simple implementation - count numbers and ranges
    const parts = range.split(',');
    let total = 0;
    
    parts.forEach(part => {
        part = part.trim();
        if (part.includes('-')) {
            const [start, end] = part.split('-').map(n => parseInt(n.trim()));
            if (!isNaN(start) && !isNaN(end)) {
                total += (end - start + 1);
            }
        } else {
            const num = parseInt(part);
            if (!isNaN(num)) {
                total += 1;
            }
        }
    });
    
    return total > 0 ? total : orderData.totalPages;
}

// Toggle page range input
function togglePageRangeInput() {
    const pageRangeInput = document.getElementById('pageRangeInput');
    const pageRangeRadios = document.querySelectorAll('input[name="pageRange"]');

    if (pageRangeInput) {
        const customRangeSelected = Array.from(pageRangeRadios).some(radio => 
            radio.value === 'custom' && radio.checked
        );

        pageRangeInput.style.display = customRangeSelected ? 'block' : 'none';
    }
}

// Update order summary
function updateOrderSummary() {
    const fileNameElement = document.querySelector('.summary-value');
    const copiesElement = document.querySelectorAll('.summary-value')[1];
    const amountElement = document.querySelectorAll('.summary-value')[2];
    
    if (fileNameElement) fileNameElement.textContent = orderData.fileName;
    if (copiesElement) copiesElement.textContent = orderData.copies;
    if (amountElement) amountElement.textContent = `₹ ${orderData.totalAmount.toFixed(2)}`;
}

// Payment functions
function selectPaymentMethod(method, button) {
    // Remove active class from all buttons
    const paymentBtns = document.querySelectorAll('.payment-btn');
    paymentBtns.forEach(btn => btn.classList.remove('active'));
    
    // Add active class to selected button
    if (button) {
        button.classList.add('active');
    }
    
    // Store selected payment method
    orderData.paymentMethod = method;
}

function processPayment() {
    if (!orderData.paymentMethod) {
        // Show error message instead of alert
        const payBtn = document.querySelector('.payment-methods .btn-primary');
        if (payBtn) {
            payBtn.textContent = 'Please select payment method';
            payBtn.style.background = '#ff4757';
            setTimeout(() => {
                payBtn.textContent = 'Pay Now';
                payBtn.style.background = '';
            }, 2000);
        }
        return;
    }
    
    // Navigate to payment success page
    updateSuccessDetails();
    navigateTo('payment-success');
}

function updateSuccessDetails() {
    const fileName = document.getElementById('successFileName');
    const copies = document.getElementById('successCopies');
    const amount = document.getElementById('successAmount');

    if (fileName) fileName.textContent = orderData.fileName;
    if (copies) copies.textContent = orderData.copies;
    if (amount) amount.textContent = `₹ ${orderData.totalAmount.toFixed(2)}`;
}

function saveSettingsAndContinue() {
    // Save print settings and move to payment page
    calculateTotal();
    updateOrderSummary();
    navigateTo('payment');
}

// FAQ toggle (if needed)
function toggleFAQ(element) {
    const content = element.nextElementSibling;
    if (content) {
        content.style.display = content.style.display === 'none' ? 'block' : 'none';
    }
}
