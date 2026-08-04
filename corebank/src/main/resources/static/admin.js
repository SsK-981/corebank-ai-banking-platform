document.addEventListener('DOMContentLoaded', () => {
    let currentAccount = null;
    let session = JSON.parse(localStorage.getItem('corebank-admin-session') || 'null');

    const moneyFormatter = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const elements = {
        loginForm: document.getElementById('login-form'),
        registerForm: document.getElementById('register-form'),
        logoutButton: document.getElementById('logout-button'),
        currentUser: document.getElementById('current-user'),
        refreshAdmin: document.getElementById('refresh-admin'),
        refreshCustomers: document.getElementById('refresh-customers'),
        searchForm: document.getElementById('search-form'),
        creditForm: document.getElementById('credit-form'),
        renameForm: document.getElementById('rename-form'),
        closeButton: document.getElementById('close-account'),
        downloadButton: document.getElementById('download-statement'),
        exportAccounts: document.getElementById('export-accounts'),
        exportTransactions: document.getElementById('export-transactions'),
        customersTable: document.getElementById('customers-table'),
        accountsTable: document.getElementById('accounts-table'),
        transactionsTable: document.getElementById('transactions-table'),
        holderName: document.getElementById('display-holder-name'),
        accountMeta: document.getElementById('display-account-meta'),
        balance: document.getElementById('display-balance')
    };

    function showMessage(id, message, isSuccess = true) {
        const element = document.getElementById(id);
        element.textContent = message;
        element.className = `message ${isSuccess ? 'success' : 'error'}`;
    }

    function authHeader() {
        return session?.token ? { Authorization: `Basic ${session.token}` } : {};
    }

    async function request(url, options = {}, authenticated = true) {
        let response;
        try {
            response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...(authenticated ? authHeader() : {}),
                    ...options.headers
                },
                ...options
            });
        } catch {
            throw new Error('API unavailable. Make sure the Spring Boot server is running on port 8080.');
        }

        if (!response.ok) {
            let message = response.status === 401 || response.status === 403
                    ? 'Admin access required. Use an ADMIN account.'
                    : 'Request failed';
            try {
                const error = await response.json();
                message = error.messages?.join(', ') || message;
            } catch {
                message = response.statusText || message;
            }
            throw new Error(message);
        }
        if (response.status === 204) return null;
        return response.json();
    }

    function saveSession(email, password, user) {
        session = { email, token: btoa(`${email}:${password}`), user };
        localStorage.setItem('corebank-admin-session', JSON.stringify(session));
        renderSession();
    }

    function clearSession() {
        session = null;
        currentAccount = null;
        localStorage.removeItem('corebank-admin-session');
        renderSession();
        resetDashboard();
    }

    function renderSession() {
        const loggedIn = Boolean(session?.user);
        elements.currentUser.textContent = loggedIn
                ? `Logged in as ${session.user.fullName} (${session.user.role})`
                : 'You are not logged in.';
        elements.logoutButton.classList.toggle('hidden', !loggedIn);
        document.querySelectorAll('.signed-in-panel').forEach(panel => panel.classList.toggle('hidden', !loggedIn));
    }

    function resetDashboard() {
        elements.holderName.textContent = 'No account selected';
        elements.accountMeta.textContent = 'Select an account from the admin table.';
        elements.balance.textContent = '0.00';
        elements.customersTable.innerHTML = '';
        elements.accountsTable.innerHTML = '';
        elements.transactionsTable.innerHTML = '';
    }

    function setCurrentAccount(account) {
        currentAccount = account;
        elements.holderName.textContent = account.holderName;
        elements.accountMeta.textContent = `ID ${account.accountId} | ${account.accountNumber} | ${account.ownerEmail} | ${account.active ? 'Active' : 'Closed'}`;
        elements.balance.textContent = moneyFormatter.format(Number(account.balance));
        document.getElementById('rename-holder').value = account.holderName;
        loadAccountTransactions(account.accountId);
    }

    async function loadAdminSummary() {
        const summary = await request('/admin/summary');
        document.getElementById('stat-total').textContent = summary.totalAccounts;
        document.getElementById('stat-active').textContent = summary.activeAccounts;
        document.getElementById('stat-closed').textContent = summary.closedAccounts;
        document.getElementById('stat-transactions').textContent = summary.totalTransactions;
        document.getElementById('stat-balance').textContent = moneyFormatter.format(Number(summary.totalBankBalance));
    }

    async function loadCustomers() {
        const page = await request('/admin/customers?size=50');
        elements.customersTable.innerHTML = '';
        if (page.content.length === 0) {
            renderEmptyRow(elements.customersTable, 6, 'No customers yet.');
            return;
        }
        page.content.forEach(user => {
            const row = document.createElement('tr');
            appendCell(row, user.id);
            appendCell(row, user.fullName);
            appendCell(row, user.email);
            appendCell(row, user.role);
            appendCell(row, user.kycStatus || 'PENDING');
            const actionCell = document.createElement('td');
            if (user.role === 'CUSTOMER') {
                const action = document.createElement('div');
                action.className = 'table-action';
                const select = document.createElement('select');
                ['PENDING', 'VERIFIED', 'REJECTED'].forEach(status => {
                    const option = document.createElement('option');
                    option.value = status;
                    option.textContent = status;
                    option.selected = status === (user.kycStatus || 'PENDING');
                    select.appendChild(option);
                });
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = 'Save';
                button.addEventListener('click', async () => {
                    button.disabled = true;
                    try {
                        await request(`/admin/customers/${encodeURIComponent(user.email)}/kyc`, {
                            method: 'PATCH',
                            body: JSON.stringify({ status: select.value })
                        });
                        await loadCustomers();
                    } catch (error) {
                        showMessage('login-result', error.message, false);
                    } finally {
                        button.disabled = false;
                    }
                });
                action.append(select, button);
                actionCell.appendChild(action);
            } else {
                actionCell.textContent = '-';
            }
            row.appendChild(actionCell);
            elements.customersTable.appendChild(row);
        });
    }

    async function loadAccounts() {
        const query = encodeURIComponent(document.getElementById('account-search').value.trim());
        const page = await request(`/admin/accounts?size=50&query=${query}`);
        elements.accountsTable.innerHTML = '';
        if (page.content.length === 0) {
            renderEmptyRow(elements.accountsTable, 6, 'No accounts found.');
            return;
        }
        page.content.forEach(account => {
            const row = document.createElement('tr');
            row.addEventListener('click', () => setCurrentAccount(account));
            appendCell(row, account.accountId);
            appendCell(row, account.accountNumber);
            appendCell(row, account.holderName);
            appendCell(row, account.ownerEmail);
            appendCell(row, `Rs ${moneyFormatter.format(Number(account.balance))}`);
            appendCell(row, account.active ? 'Active' : 'Closed');
            elements.accountsTable.appendChild(row);
        });
    }

    async function loadAllTransactions() {
        const page = await request('/admin/transactions?size=50');
        renderAdminTransactions(page.content);
    }

    async function loadAccountTransactions(accountId) {
        const page = await request(`/admin/accounts/${accountId}/transactions?size=50`);
        renderCustomerStyleTransactions(page.content);
    }

    function renderAdminTransactions(transactions) {
        elements.transactionsTable.innerHTML = '';
        if (transactions.length === 0) {
            renderEmptyRow(elements.transactionsTable, 8, 'No transactions yet.');
            return;
        }
        transactions.forEach(transaction => {
            const row = document.createElement('tr');
            appendCell(row, transaction.referenceNumber);
            appendCell(row, transaction.accountNumber);
            appendCell(row, transaction.ownerEmail);
            appendCell(row, formatType(transaction.type));
            appendCell(row, transaction.status || 'POSTED');
            appendCell(row, `Rs ${moneyFormatter.format(Number(transaction.amount))}`);
            appendCell(row, new Date(transaction.timestamp).toLocaleString());
            appendCell(row, transaction.failureReason || transaction.description || '-');
            elements.transactionsTable.appendChild(row);
        });
    }

    function renderCustomerStyleTransactions(transactions) {
        elements.transactionsTable.innerHTML = '';
        if (transactions.length === 0) {
            renderEmptyRow(elements.transactionsTable, 8, 'No transactions for this account.');
            return;
        }
        transactions.forEach(transaction => {
            const row = document.createElement('tr');
            appendCell(row, transaction.referenceNumber);
            appendCell(row, currentAccount.accountNumber);
            appendCell(row, currentAccount.ownerEmail);
            appendCell(row, formatType(transaction.type));
            appendCell(row, transaction.status || 'POSTED');
            appendCell(row, `Rs ${moneyFormatter.format(Number(transaction.amount))}`);
            appendCell(row, new Date(transaction.timestamp).toLocaleString());
            appendCell(row, transaction.failureReason || transaction.description || '-');
            elements.transactionsTable.appendChild(row);
        });
    }

    function renderEmptyRow(tableBody, colspan, message) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = colspan;
        cell.textContent = message;
        row.appendChild(cell);
        tableBody.appendChild(row);
    }

    function appendCell(row, value) {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
    }

    function formatType(type) {
        return type.toLowerCase().replaceAll('_', ' ');
    }

    async function download(url, filename, messageId = 'account-action-result') {
        try {
            const response = await fetch(url, { headers: authHeader() });
            if (!response.ok) throw new Error('Could not export CSV');
            const blob = await response.blob();
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (error) {
            showMessage(messageId, error.message, false);
        }
    }

    async function loadDashboard() {
        await Promise.all([loadAdminSummary(), loadCustomers(), loadAccounts(), loadAllTransactions()]);
    }

    elements.loginForm.addEventListener('submit', async event => {
        event.preventDefault();
        const email = document.getElementById('login-email').value.trim().toLowerCase();
        const password = document.getElementById('login-password').value;
        try {
            session = { email, token: btoa(`${email}:${password}`) };
            const user = await request('/auth/admin/me');
            saveSession(email, password, user);
            showMessage('login-result', 'Admin login successful.');
            loadDashboard();
        } catch (error) {
            clearSession();
            showMessage('login-result', error.message, false);
        }
    });

    elements.registerForm.addEventListener('submit', async event => {
        event.preventDefault();
        const email = document.getElementById('register-email').value.trim().toLowerCase();
        const password = document.getElementById('register-password').value;
        try {
            const user = await request('/auth/admin/register', {
                method: 'POST',
                body: JSON.stringify({
                    fullName: document.getElementById('register-name').value,
                    email,
                    password,
                    adminCode: document.getElementById('register-admin-code').value
                })
            }, false);
            saveSession(email, password, user);
            elements.registerForm.reset();
            showMessage('register-result', 'Admin created and logged in.');
            loadDashboard();
        } catch (error) {
            showMessage('register-result', error.message, false);
        }
    });

    elements.logoutButton.addEventListener('click', clearSession);
    elements.refreshAdmin.addEventListener('click', loadAdminSummary);
    elements.refreshCustomers.addEventListener('click', loadCustomers);
    elements.searchForm.addEventListener('submit', event => {
        event.preventDefault();
        loadAccounts();
    });
    elements.creditForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!currentAccount) {
            showMessage('account-action-result', 'Select an account first.', false);
            return;
        }
        try {
            const account = await request(`/admin/accounts/${currentAccount.accountId}/credit`, {
                method: 'POST',
                body: JSON.stringify({ amount: document.getElementById('credit-amount').value })
            });
            setCurrentAccount(account);
            elements.creditForm.reset();
            loadAccounts();
            loadAdminSummary();
            showMessage('account-action-result', 'Account credited.');
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });
    elements.renameForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!currentAccount) {
            showMessage('account-action-result', 'Select an account first.', false);
            return;
        }
        try {
            const account = await request(`/admin/accounts/${currentAccount.accountId}`, {
                method: 'PUT',
                body: JSON.stringify({ holderName: document.getElementById('rename-holder').value })
            });
            setCurrentAccount(account);
            loadAccounts();
            showMessage('account-action-result', 'Holder name updated.');
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });
    elements.closeButton.addEventListener('click', async () => {
        if (!currentAccount) {
            showMessage('account-action-result', 'Select an account first.', false);
            return;
        }
        try {
            const account = await request(`/admin/accounts/${currentAccount.accountId}`, { method: 'DELETE' });
            setCurrentAccount(account);
            loadAccounts();
            loadAdminSummary();
            showMessage('account-action-result', 'Account closed.');
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });
    elements.downloadButton.addEventListener('click', () => {
        if (!currentAccount) {
            showMessage('account-action-result', 'Select an account first.', false);
            return;
        }
        download(`/admin/accounts/${currentAccount.accountId}/statement.csv`, `account-${currentAccount.accountId}-statement.csv`);
    });
    elements.exportAccounts.addEventListener('click', () => download('/admin/accounts.csv', 'accounts.csv'));
    elements.exportTransactions.addEventListener('click', () => download('/admin/transactions.csv', 'transactions.csv'));

    renderSession();
    if (session?.token) {
        request('/auth/admin/me')
            .then(user => {
                session.user = user;
                localStorage.setItem('corebank-admin-session', JSON.stringify(session));
                renderSession();
                loadDashboard();
            })
            .catch(clearSession);
    } else {
        resetDashboard();
    }
});
