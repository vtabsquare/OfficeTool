
import { state } from '../state.js';
import { getPageContentHTML } from '../utils.js';
import { renderModal, closeModal } from '../components/modal.js';
import { listEmployees, createEmployee } from '../features/employeeApi.js';
import { API_BASE_URL } from '../config.js';

export const renderEmployeesPage = async (filter: string = '') => {
    const controls = `<button id="add-employee-btn" class="btn btn-primary"><i class="fa-solid fa-plus"></i> ADD NEW</button>`;

    try {
        const { items } = await listEmployees();
        // Map API format to local state structure used by UI
        state.employees = (items || []).map((e: any) => ({
            id: e.employee_id,
            name: `${e.first_name || ''} ${e.last_name || ''}`.trim(),
            location: e.address || '',
            jobTitle: e.designation || '',
            contactNumber: e.contact_number || '',
            department: e.department || '',
            role: '',
            employmentType: 'Full-time',
            status: (e.active === true || e.active === 'true' || e.active === 1 || e.active === 'Active') ? 'Active' : 'Inactive'
        }));
    } catch (err) {
        console.error('Failed to load employees from backend:', err);
    }

    const filteredEmployees = state.employees.filter(e => 
        e.name.toLowerCase().includes(filter.toLowerCase()) ||
        e.id.toLowerCase().includes(filter.toLowerCase())
    );

    const tableRows = filteredEmployees.map(e => `
        <tr>
            <td><div class="employee-id-badge">${e.id ? e.id.slice(-2) : ''}</div></td>
            <td>${e.name || ''}</td>
            <td>${e.location || ''}</td>
            <td>${e.contactNumber || ''}</td>
            <td>${e.jobTitle || ''}</td>
            <td>${e.department || ''}</td>
            <td><span class="status-badge ${e.status ? e.status.toLowerCase() : 'inactive'}">${e.status || 'Inactive'}</span></td>
        </tr>
    `).join('');

    const content = `
        <div class="card">
            <div class="page-controls">
                <div class="header-search">
                    <i class="fa-solid fa-search"></i>
                    <input type="text" id="employee-search-input" placeholder="Search by name or ID" value="${filter}">
                </div>
            </div>
            <div class="table-container">
                <table class="table">
                    <thead><tr><th>Employee ID</th><th>Name</th><th>Address</th><th>Contact No</th><th>Designation</th><th>Department</th><th>Status</th></tr></thead>
                    <tbody>${tableRows || `<tr><td colspan="7" class="placeholder-text">No employees found. Click ADD NEW to add employees.</td></tr>`}</tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('app-content')!.innerHTML = getPageContentHTML('Employees', content, controls);
};

export const showAddEmployeeModal = () => {
    const formHTML = `
        <div class="form-group"><label for="firstName">First Name</label><input type="text" id="firstName" required></div>
        <div class="form-group"><label for="lastName">Last Name</label><input type="text" id="lastName"></div>
        <div class="form-group"><label for="address">Address</label><input type="text" id="address" required></div>
        <div class="form-group"><label for="contactNo">Contact No</label><input type="text" id="contactNo"></div>
        <div class="form-group"><label for="designation">Designation</label><input type="text" id="designation" required></div>
        <div class="form-group"><label for="department">Department</label><input type="text" id="department"></div>
        <div class="form-group"><label for="status">Status</label><select id="status"><option>Active</option><option>Inactive</option></select></div>
    `;
    renderModal('Add New Employee', formHTML, 'save-employee-btn');
};

export const handleAddEmployee = async (e: SubmitEvent) => {
    e.preventDefault();
    
    try {
        // Fetch the next employee ID from backend
        const response = await fetch(`${API_BASE_URL}/api/employees/last-id`);
        const data = await response.json();
        
        if (!data.success) {
            alert('Failed to generate employee ID');
            return;
        }
        
        const payload = {
            employee_id: data.next_id,
            first_name: (document.getElementById('firstName') as HTMLInputElement).value,
            last_name: (document.getElementById('lastName') as HTMLInputElement).value,
            email: '',
            contact_number: (document.getElementById('contactNo') as HTMLInputElement).value,
            address: (document.getElementById('address') as HTMLInputElement).value,
            department: (document.getElementById('department') as HTMLInputElement).value,
            designation: (document.getElementById('designation') as HTMLInputElement).value,
            doj: new Date().toISOString().split('T')[0],
            active: (document.getElementById('status') as HTMLSelectElement).value === 'Active'
        };
        
        await createEmployee(payload);
        
        // Update local cache for immediate UI feedback
        state.employees.push({
            id: payload.employee_id,
            name: `${payload.first_name} ${payload.last_name}`.trim(),
            location: payload.address,
            jobTitle: payload.designation,
            contactNumber: payload.contact_number,
            department: payload.department,
            role: '',
            employmentType: 'Full-time',
            status: payload.active ? 'Active' : 'Inactive'
        });
        closeModal();
        // Re-render employees list only if currently on Employees page
        if (window.location.hash === '#/employees') {
            renderEmployeesPage();
        } else {
            alert('Employee created successfully');
        }
    } catch (err) {
        console.error('Create employee failed:', err);
        alert(`Failed to create employee: ${err.message || err}`);
    }
};
