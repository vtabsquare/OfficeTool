
import { getPageContentHTML } from '../utils.js';
import { API_BASE_URL } from '../config.js';

export const renderTimeTrackerPage = () => {
    const content = `<div class="card"><p class="placeholder-text">Time Tracker page is under construction.</p></div>`;
    document.getElementById('app-content')!.innerHTML = getPageContentHTML('My Team Timesheet', content);
};

export const renderInboxPage = () => {
    const content = `
    <div class="inbox-container">
        <div class="inbox-sidebar">
            <div class="inbox-category active" data-category="all">All</div>
            <div class="inbox-category" data-category="attendance">Attendance</div>
            <div class="inbox-category" data-category="leaves">Leaves</div>
            <div class="inbox-category" data-category="timesheet">Timesheet</div>
        </div>
        <div class="inbox-content">
            <div class="inbox-tabs">
                <div class="inbox-tab active" data-tab="awaiting">Awaiting approval</div>
                <div class="inbox-tab" data-tab="requests">My requests</div>
                <div class="inbox-tab" data-tab="completed">Completed</div>
            </div>
            <div class="inbox-list">
                <div class="placeholder-text">
                    <i class="fa-solid fa-spinner fa-spin fa-2x" style="color:#007bff; margin-bottom: 1rem;"></i>
                    <p>Loading inbox items...</p>
                </div>
            </div>
        </div>
    </div>
    `;
    document.getElementById('app-content')!.innerHTML = getPageContentHTML('Inbox', content);

    // Load inbox items
    loadInboxItems();

    // Set up event listeners
    setupInboxEventListeners();
}

const loadInboxItems = async (category = 'all', status = 'awaiting') => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/inbox`);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to load inbox items');
        }

        const items = data.items || [];
        renderInboxItems(items, category, status);

    } catch (error) {
        console.error('Error loading inbox items:', error);
        const inboxList = document.querySelector('.inbox-list') as HTMLElement;
        if (inboxList) {
            inboxList.innerHTML = `
                <div class="placeholder-text">
                    <i class="fa-solid fa-exclamation-triangle fa-3x" style="color:#dc3545; margin-bottom: 1rem;"></i>
                    <p>Failed to load inbox items. Please try again.</p>
                </div>
            `;
        }
    }
}

const renderInboxItems = (items: any[], category: string, status: string) => {
    const inboxList = document.querySelector('.inbox-list') as HTMLElement;
    if (!inboxList) return;

    // Filter items based on category and status
    let filteredItems = items;

    if (category !== 'all') {
        if (category === 'attendance') {
            filteredItems = items.filter(item => item.type === 'attendance_submission');
        } else if (category === 'leaves') {
            filteredItems = items.filter(item => item.type === 'leave_request');
        } else if (category === 'timesheet') {
            filteredItems = items.filter(item => item.type === 'timesheet');
        }
    }

    if (status === 'awaiting') {
        filteredItems = filteredItems.filter(item => item.status === 'pending');
    } else if (status === 'completed') {
        filteredItems = filteredItems.filter(item => item.status === 'approved' || item.status === 'rejected');
    }

    if (filteredItems.length === 0) {
        inboxList.innerHTML = `
            <div class="placeholder-text">
                <i class="fa-solid fa-envelope-open fa-3x" style="color:#ddd; margin-bottom: 1rem;"></i>
                <p>No ${status} ${category} requests found.</p>
            </div>
        `;
        return;
    }

    const itemsHTML = filteredItems.map(item => {
        const statusClass = item.status === 'pending' ? 'status-pending' :
                           item.status === 'approved' ? 'status-approved' : 'status-rejected';
        const statusText = item.status === 'pending' ? 'Pending' :
                          item.status === 'approved' ? 'Approved' : 'Rejected';

        let actionsHTML = '';
        if (item.status === 'pending') {
            actionsHTML = `
                <div class="inbox-item-actions">
                    <button class="btn btn-success btn-sm approve-btn" data-item-id="${item.id}">
                        <i class="fa-solid fa-check"></i> Approve
                    </button>
                    <button class="btn btn-danger btn-sm reject-btn" data-item-id="${item.id}">
                        <i class="fa-solid fa-times"></i> Reject
                    </button>
                </div>
            `;
        }

        const typeIcon = item.type === 'attendance_submission' ? 'fa-calendar-check' :
                         item.type === 'leave_request' ? 'fa-calendar-minus' : 'fa-clock';

        return `
            <div class="inbox-item">
                <div class="inbox-item-header">
                    <div class="inbox-item-icon">
                        <i class="fa-solid ${typeIcon}"></i>
                    </div>
                    <div class="inbox-item-info">
                        <h4>${item.title}</h4>
                        <p class="inbox-item-meta">
                            From: ${item.sender} | ${new Date(item.created_date).toLocaleDateString()}
                        </p>
                    </div>
                    <div class="inbox-item-status ${statusClass}">
                        ${statusText}
                    </div>
                </div>
                <div class="inbox-item-content">
                    <p>${item.description}</p>
                    ${actionsHTML}
                </div>
            </div>
        `;
    }).join('');

    inboxList.innerHTML = itemsHTML;

    // Set up action button event listeners
    setupActionButtons();
}

const setupInboxEventListeners = () => {
    // Category filter listeners
    const categories = document.querySelectorAll('.inbox-category');
    categories.forEach(cat => {
        cat.addEventListener('click', (e) => {
            const target = e.target as HTMLElement;
            const category = target.getAttribute('data-category') || 'all';

            // Update active category
            document.querySelectorAll('.inbox-category').forEach(c => c.classList.remove('active'));
            target.classList.add('active');

            // Reload items with new category
            const activeTab = document.querySelector('.inbox-tab.active') as HTMLElement;
            const status = activeTab?.getAttribute('data-tab') || 'awaiting';
            loadInboxItems(category, status);
        });
    });

    // Tab filter listeners
    const tabs = document.querySelectorAll('.inbox-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            const target = e.target as HTMLElement;
            const status = target.getAttribute('data-tab') || 'awaiting';

            // Update active tab
            document.querySelectorAll('.inbox-tab').forEach(t => t.classList.remove('active'));
            target.classList.add('active');

            // Reload items with new status
            const activeCategory = document.querySelector('.inbox-category.active') as HTMLElement;
            const category = activeCategory?.getAttribute('data-category') || 'all';
            loadInboxItems(category, status);
        });
    });
}

const setupActionButtons = () => {
    // Approve buttons
    const approveButtons = document.querySelectorAll('.approve-btn');
    approveButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const target = e.target as HTMLElement;
            const itemId = target.getAttribute('data-item-id') || target.closest('.approve-btn')?.getAttribute('data-item-id');

            if (!itemId) return;

            try {
                const response = await fetch(`${API_BASE_URL}/api/inbox/${itemId}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const data = await response.json();

                if (data.success) {
                    alert('Item approved successfully!');
                    // Reload inbox items
                    const activeCategory = document.querySelector('.inbox-category.active') as HTMLElement;
                    const activeTab = document.querySelector('.inbox-tab.active') as HTMLElement;
                    const category = activeCategory?.getAttribute('data-category') || 'all';
                    const status = activeTab?.getAttribute('data-tab') || 'awaiting';
                    loadInboxItems(category, status);
                } else {
                    alert(`Failed to approve: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.error('Error approving item:', error);
                alert('Failed to approve item. Please try again.');
            }
        });
    });

    // Reject buttons
    const rejectButtons = document.querySelectorAll('.reject-btn');
    rejectButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const target = e.target as HTMLElement;
            const itemId = target.getAttribute('data-item-id') || target.closest('.reject-btn')?.getAttribute('data-item-id');

            if (!itemId) return;

            const reason = prompt('Enter rejection reason (optional):');

            try {
                const response = await fetch(`${API_BASE_URL}/api/inbox/${itemId}/reject`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reason })
                });

                const data = await response.json();

                if (data.success) {
                    alert('Item rejected successfully!');
                    // Reload inbox items
                    const activeCategory = document.querySelector('.inbox-category.active') as HTMLElement;
                    const activeTab = document.querySelector('.inbox-tab.active') as HTMLElement;
                    const category = activeCategory?.getAttribute('data-category') || 'all';
                    const status = activeTab?.getAttribute('data-tab') || 'awaiting';
                    loadInboxItems(category, status);
                } else {
                    alert(`Failed to reject: ${data.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.error('Error rejecting item:', error);
                alert('Failed to reject item. Please try again.');
            }
        });
    });
}

export const renderProjectsPage = () => {
    const content = `
        <div class="card">
            <div class="table-container">
                <table class="table">
                    <thead><tr><th>Work item id & name</th><th>Project</th><th>Client</th><th>Status</th><th>Due date</th><th>Priority</th><th>Time spent</th></tr></thead>
                    <tbody><tr><td colspan="7" class="placeholder-text">No tasks assigned.</td></tr></tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('app-content')!.innerHTML = getPageContentHTML('My tasks', content);
};
