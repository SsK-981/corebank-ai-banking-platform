document.addEventListener('DOMContentLoaded', () => {
    let currentAccount = null;
    let session = JSON.parse(localStorage.getItem('corebank-customer-session') || 'null');

    const moneyFormatter = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const elements = {
        loginForm: document.getElementById('login-form'),
        registerForm: document.getElementById('register-form'),
        logoutButton: document.getElementById('logout-button'),
        currentUser: document.getElementById('current-user'),
        withdrawForm: document.getElementById('withdraw-form'),
        transferForm: document.getElementById('transfer-form'),
        renameForm: document.getElementById('rename-form'),
        closeButton: document.getElementById('close-account'),
        downloadButton: document.getElementById('download-statement'),
        refreshAccounts: document.getElementById('refresh-accounts'),
        refreshTransactions: document.getElementById('refresh-transactions'),
        accountsTable: document.getElementById('accounts-table'),
        transactionsTable: document.getElementById('transactions-table'),
        holderName: document.getElementById('display-holder-name'),
        accountMeta: document.getElementById('display-account-meta'),
        balance: document.getElementById('display-balance')
    };

    function amountValue(id) {
        return Number.parseFloat(document.getElementById(id).value).toFixed(2);
    }

    function apiUnavailableMessage() {
        return window.location.protocol === 'file:'
                ? 'Open the app at http://localhost:8080/customer.html after starting Spring Boot.'
                : 'API unavailable. Make sure the Spring Boot server is running on port 8080.';
    }

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
            throw new Error(apiUnavailableMessage());
        }

        if (!response.ok) {
            let message = response.status === 401 || response.status === 403
                    ? 'Customer access required. Use a CUSTOMER account.'
                    : 'Request failed';
            try {
                const error = await response.json();
                message = error.messages?.join(', ') || message;
            } catch {
                message = response.statusText || message;
            }
            throw new Error(message);
        }

        if (response.status === 204) {
            return null;
        }
        return response.json();
    }

    function saveSession(email, password, user) {
        session = { email, token: btoa(`${email}:${password}`), user };
        localStorage.setItem('corebank-customer-session', JSON.stringify(session));
        renderSession();
    }

    function clearSession() {
        session = null;
        currentAccount = null;
        localStorage.removeItem('corebank-customer-session');
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
        elements.accountMeta.textContent = 'Create or select your account to begin.';
        elements.balance.textContent = '0.00';
        elements.accountsTable.innerHTML = '';
        elements.transactionsTable.innerHTML = '';
        renderEmptyRow(elements.accountsTable, 5, session ? 'No accounts yet.' : 'Login to view your accounts.');
        renderEmptyRow(elements.transactionsTable, 5, 'Select an account to view transactions.');
    }

    function requireAccount(messageId) {
        if (!session?.token) {
            showMessage(messageId, 'Login first.', false);
            return false;
        }
        if (!currentAccount) {
            showMessage(messageId, 'Select an account first.', false);
            return false;
        }
        return true;
    }

    function setCurrentAccount(account) {
        currentAccount = account;
        elements.holderName.textContent = account.holderName;
        elements.accountMeta.textContent = `ID ${account.accountId} | ${account.accountNumber} | ${account.active ? 'Active' : 'Closed'}`;
        elements.balance.textContent = moneyFormatter.format(Number(account.balance));
        document.getElementById('rename-holder').value = account.holderName;
        loadAccounts();
        loadTransactions();
    }

    async function loadAccounts() {
        if (!session?.token) {
            resetDashboard();
            return;
        }
        const page = await request('/customer/accounts?size=50');
        elements.accountsTable.innerHTML = '';
        if (page.content.length === 0) {
            renderEmptyRow(elements.accountsTable, 5, 'No accounts yet.');
            return;
        }
        page.content.forEach(account => {
            const row = document.createElement('tr');
            row.addEventListener('click', () => setCurrentAccount(account));
            appendCell(row, account.accountId);
            appendCell(row, account.accountNumber);
            appendCell(row, account.holderName);
            appendCell(row, `Rs ${moneyFormatter.format(Number(account.balance))}`);
            appendCell(row, account.active ? 'Active' : 'Closed');
            elements.accountsTable.appendChild(row);
        });
        if (!currentAccount && page.content[0]) {
            setCurrentAccount(page.content[0]);
        }
    }

    async function loadTransactions() {
        elements.transactionsTable.innerHTML = '';
        if (!currentAccount) {
            renderEmptyRow(elements.transactionsTable, 6, 'Select an account to view transactions.');
            return;
        }
        const page = await request(`/customer/accounts/${currentAccount.accountId}/transactions?size=25`);
        if (page.content.length === 0) {
            renderEmptyRow(elements.transactionsTable, 6, 'No transactions yet.');
            return;
        }
        page.content.forEach(transaction => {
            const row = document.createElement('tr');
            appendCell(row, transaction.referenceNumber);
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

    function destinationPayload() {
        const value = document.getElementById('transfer-to').value.trim();
        return value.length >= 6 ? { toAccountNumber: value } : { toAccountId: Number(value) };
    }

    elements.loginForm.addEventListener('submit', async event => {
        event.preventDefault();
        const email = document.getElementById('login-email').value.trim().toLowerCase();
        const password = document.getElementById('login-password').value;
        try {
            session = { email, token: btoa(`${email}:${password}`) };
            const user = await request('/auth/customer/me');
            saveSession(email, password, user);
            showMessage('login-result', 'Customer login successful.');
            loadAccounts();
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
            const user = await request('/auth/customer/register', {
                method: 'POST',
                body: JSON.stringify({
                    fullName: document.getElementById('register-name').value,
                    email,
                    password
                })
            }, false);
            saveSession(email, password, user);
            const account = await request('/customer/accounts', {
                method: 'POST',
                body: JSON.stringify({
                    holderName: document.getElementById('register-holder-name').value,
                    initialBalance: amountValue('register-opening-deposit')
                })
            });
            elements.registerForm.reset();
            setCurrentAccount(account);
            showMessage('register-result', 'Customer and bank account created.');
        } catch (error) {
            showMessage('register-result', error.message, false);
        }
    });

    elements.logoutButton.addEventListener('click', clearSession);
    elements.withdrawForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireAccount('withdraw-result')) return;
        try {
            const account = await request(`/customer/accounts/${currentAccount.accountId}/withdraw`, {
                method: 'POST',
                body: JSON.stringify({ amount: amountValue('withdraw-amount') })
            });
            setCurrentAccount(account);
            elements.withdrawForm.reset();
            showMessage('withdraw-result', 'Withdrawal completed.');
        } catch (error) {
            showMessage('withdraw-result', error.message, false);
        }
    });

    elements.transferForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireAccount('transfer-result')) return;
        try {
            const transfer = await request('/customer/accounts/transfer', {
                method: 'POST',
                body: JSON.stringify({
                    fromAccountId: currentAccount.accountId,
                    ...destinationPayload(),
                    amount: amountValue('transfer-amount')
                })
            });
            setCurrentAccount(transfer.fromAccount);
            elements.transferForm.reset();
            showMessage('transfer-result', `Transfer completed. Ref ${transfer.referenceNumber}.`);
        } catch (error) {
            showMessage('transfer-result', error.message, false);
        }
    });

    elements.renameForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireAccount('account-action-result')) return;
        try {
            const account = await request(`/customer/accounts/${currentAccount.accountId}`, {
                method: 'PUT',
                body: JSON.stringify({ holderName: document.getElementById('rename-holder').value })
            });
            setCurrentAccount(account);
            showMessage('account-action-result', 'Holder name updated.');
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });

    elements.closeButton.addEventListener('click', async () => {
        if (!requireAccount('account-action-result')) return;
        try {
            const account = await request(`/customer/accounts/${currentAccount.accountId}`, { method: 'DELETE' });
            setCurrentAccount(account);
            showMessage('account-action-result', 'Account closed.');
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });

    elements.downloadButton.addEventListener('click', async () => download(`/customer/accounts/${currentAccount.accountId}/statement.csv`, `account-${currentAccount.accountId}-statement.csv`, 'account-action-result'));
    elements.refreshAccounts.addEventListener('click', loadAccounts);
    elements.refreshTransactions.addEventListener('click', loadTransactions);

    async function download(url, filename, messageId) {
        if (!requireAccount(messageId)) return;
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

    renderSession();
    if (session?.token) {
        request('/auth/customer/me')
            .then(user => {
                session.user = user;
                localStorage.setItem('corebank-customer-session', JSON.stringify(session));
                renderSession();
                loadAccounts();
            })
            .catch(clearSession);
    } else {
        resetDashboard();
    }
});
