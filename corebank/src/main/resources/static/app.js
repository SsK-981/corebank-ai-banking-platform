document.addEventListener('DOMContentLoaded', () => {
    let currentAccount = null;
    let session = JSON.parse(localStorage.getItem('corebank-session') || 'null');

    const moneyFormatter = new Intl.NumberFormat('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });

    const elements = {
        health: document.getElementById('health-status'),
        loginForm: document.getElementById('login-form'),
        registerForm: document.getElementById('register-form'),
        logoutButton: document.getElementById('logout-button'),
        currentUser: document.getElementById('current-user'),
        createForm: document.getElementById('create-account-form'),
        findForm: document.getElementById('find-account-form'),
        findNumberForm: document.getElementById('find-number-form'),
        depositForm: document.getElementById('deposit-form'),
        withdrawForm: document.getElementById('withdraw-form'),
        transferForm: document.getElementById('transfer-form'),
        renameForm: document.getElementById('rename-form'),
        closeButton: document.getElementById('close-account'),
        downloadButton: document.getElementById('download-statement'),
        refreshAccounts: document.getElementById('refresh-accounts'),
        refreshTransactions: document.getElementById('refresh-transactions'),
        refreshAdmin: document.getElementById('refresh-admin'),
        refreshRisk: document.getElementById('refresh-risk'),
        accountsTable: document.getElementById('accounts-table'),
        transactionsTable: document.getElementById('transactions-table'),
        riskSignals: document.getElementById('risk-signals'),
        accountsHeading: document.getElementById('accounts-heading'),
        holderName: document.getElementById('display-holder-name'),
        accountMeta: document.getElementById('display-account-meta'),
        balance: document.getElementById('display-balance')
    };

    function amountValue(id) {
        return Number.parseFloat(document.getElementById(id).value).toFixed(2);
    }

    function showMessage(id, message, isSuccess = true) {
        const element = document.getElementById(id);
        element.textContent = message;
        element.className = `message ${isSuccess ? 'success' : 'error'}`;
    }

    function apiUnavailableMessage() {
        if (window.location.protocol === 'file:') {
            return 'Open the app at http://localhost:8080 after starting Spring Boot. Do not open index.html directly.';
        }
        return 'API unavailable. Make sure the Spring Boot server is running on port 8080.';
    }

    function authHeader() {
        if (!session?.token) {
            return {};
        }
        return { Authorization: `Basic ${session.token}` };
    }

    function saveSession(email, password, user) {
        session = {
            email,
            token: btoa(`${email}:${password}`),
            user
        };
        localStorage.setItem('corebank-session', JSON.stringify(session));
        renderSession();
    }

    function clearSession() {
        session = null;
        currentAccount = null;
        localStorage.removeItem('corebank-session');
        renderSession();
        resetDashboard();
    }

    function renderSession() {
        if (!session?.user) {
            elements.currentUser.textContent = 'You are not logged in.';
            elements.logoutButton.classList.add('hidden');
            updateRoleLayout();
            return;
        }

        elements.currentUser.textContent = `Logged in as ${session.user.fullName} (${session.user.role})`;
        elements.logoutButton.classList.remove('hidden');
        updateRoleLayout();
    }

    function isCurrentAdmin() {
        return session?.user?.role === 'ADMIN';
    }

    function updateRoleLayout() {
        const loggedIn = Boolean(session?.user);
        document.querySelectorAll('.signed-in-panel').forEach(panel => {
            panel.classList.toggle('hidden', !loggedIn);
        });
        document.querySelectorAll('.role-customer').forEach(panel => {
            panel.classList.toggle('hidden', !loggedIn || isCurrentAdmin());
        });
        document.querySelectorAll('.role-admin').forEach(panel => {
            panel.classList.toggle('hidden', !loggedIn || !isCurrentAdmin());
        });
        elements.accountsHeading.textContent = isCurrentAdmin() ? 'All Customer Accounts' : 'My Account';
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
            let message = response.status === 401 ? 'Login required or password is incorrect' : 'Request failed';
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

    function setCurrentAccount(account) {
        currentAccount = account;
        elements.holderName.textContent = account.holderName;
        elements.accountMeta.textContent = `ID ${account.accountId} | ${account.accountNumber} | ${account.active ? 'Active' : 'Closed'}`;
        elements.balance.textContent = moneyFormatter.format(Number(account.balance));
        document.getElementById('rename-holder').value = account.holderName;
        loadTransactions();
        loadRiskInsights();
        loadAccounts();
        if (isCurrentAdmin()) {
            loadAdminSummary();
        }
    }

    function resetDashboard() {
        elements.holderName.textContent = 'No account selected';
        elements.accountMeta.textContent = 'Create or search for an account to begin.';
        elements.balance.textContent = '0.00';
        elements.accountsTable.innerHTML = '';
        elements.transactionsTable.innerHTML = '';
        resetRiskInsights();
        renderEmptyRow(elements.accountsTable, 6, 'Login to view accounts.');
        renderEmptyRow(elements.transactionsTable, 5, 'Select an account to view transactions.');
    }

    function requireLogin(messageId) {
        if (!session?.token) {
            showMessage(messageId, 'Login first.', false);
            return false;
        }
        return true;
    }

    function requireAccount(messageId) {
        if (!requireLogin(messageId)) {
            return false;
        }
        if (!currentAccount) {
            showMessage(messageId, 'Load an account first.', false);
            return false;
        }
        return true;
    }

    async function loadAccount(accountId) {
        const account = await request(`/accounts/${accountId}`);
        setCurrentAccount(account);
        return account;
    }

    async function loadAccounts() {
        if (!session?.token) {
            resetDashboard();
            return;
        }

        const page = await request('/accounts?size=50');
        elements.accountsTable.innerHTML = '';

        if (page.content.length === 0) {
            renderEmptyRow(elements.accountsTable, 6, 'No accounts yet.');
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

    async function loadTransactions() {
        elements.transactionsTable.innerHTML = '';

        if (!currentAccount) {
            renderEmptyRow(elements.transactionsTable, 5, 'Select an account to view transactions.');
            return;
        }

        const page = await request(`/accounts/${currentAccount.accountId}/transactions?size=25`);

        if (page.content.length === 0) {
            renderEmptyRow(elements.transactionsTable, 5, 'No transactions yet.');
            return;
        }

        page.content.forEach(transaction => {
            const row = document.createElement('tr');
            appendCell(row, transaction.referenceNumber);
            appendCell(row, formatType(transaction.type));
            appendCell(row, `Rs ${moneyFormatter.format(Number(transaction.amount))}`);
            appendCell(row, new Date(transaction.timestamp).toLocaleString());
            appendCell(row, transaction.description || '-');
            elements.transactionsTable.appendChild(row);
        });
    }

    async function loadAdminSummary() {
        if (!session?.token || !isCurrentAdmin()) {
            return;
        }

        try {
            const summary = await request('/accounts/admin/summary');
            document.getElementById('stat-total').textContent = summary.totalAccounts;
            document.getElementById('stat-active').textContent = summary.activeAccounts;
            document.getElementById('stat-closed').textContent = summary.closedAccounts;
            document.getElementById('stat-transactions').textContent = summary.totalTransactions;
            document.getElementById('stat-balance').textContent = moneyFormatter.format(Number(summary.totalBankBalance));
        } catch {
            document.getElementById('stat-total').textContent = '-';
            document.getElementById('stat-active').textContent = '-';
            document.getElementById('stat-closed').textContent = '-';
            document.getElementById('stat-transactions').textContent = '-';
            document.getElementById('stat-balance').textContent = '-';
        }
    }

    async function loadRiskInsights() {
        resetRiskInsights();

        if (!currentAccount || !session?.token) {
            return;
        }

        const insight = await request(`/accounts/${currentAccount.accountId}/risk-insights`);
        document.getElementById('risk-level').textContent = insight.riskLevel;
        document.getElementById('risk-score').textContent = insight.riskScore;
        document.getElementById('risk-credits').textContent = moneyFormatter.format(Number(insight.totalCredits));
        document.getElementById('risk-debits').textContent = moneyFormatter.format(Number(insight.totalDebits));
        document.getElementById('risk-largest').textContent = moneyFormatter.format(Number(insight.largestTransaction));
        document.getElementById('risk-recommendation').textContent = insight.recommendation;

        elements.riskSignals.innerHTML = '';
        if (insight.signals.length === 0) {
            const item = document.createElement('li');
            item.textContent = 'No elevated risk signals detected.';
            elements.riskSignals.appendChild(item);
            return;
        }

        insight.signals.forEach(signal => {
            const item = document.createElement('li');
            item.innerHTML = `<strong>${signal.title}</strong><span>${signal.detail}</span><em>+${signal.points}</em>`;
            elements.riskSignals.appendChild(item);
        });
    }

    function resetRiskInsights() {
        document.getElementById('risk-level').textContent = 'LOW';
        document.getElementById('risk-score').textContent = '0';
        document.getElementById('risk-credits').textContent = '0.00';
        document.getElementById('risk-debits').textContent = '0.00';
        document.getElementById('risk-largest').textContent = '0.00';
        document.getElementById('risk-recommendation').textContent = 'Select an account to calculate risk signals.';
        elements.riskSignals.innerHTML = '';
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

        if (value.length >= 6) {
            return { toAccountNumber: value };
        }

        return { toAccountId: Number(value) };
    }

    elements.loginForm.addEventListener('submit', async event => {
        event.preventDefault();
        const email = document.getElementById('login-email').value.trim().toLowerCase();
        const password = document.getElementById('login-password').value;
        const token = btoa(`${email}:${password}`);

        try {
            session = { email, token };
            const user = await request('/auth/me');
            saveSession(email, password, user);
            showMessage('login-result', 'Login successful.');
            loadAccounts();
            if (isCurrentAdmin()) {
                loadAdminSummary();
            }
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
            const user = await request('/auth/register', {
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
            showMessage('register-result', 'User created and logged in.');
            loadAccounts();
            if (isCurrentAdmin()) {
                loadAdminSummary();
            }
        } catch (error) {
            showMessage('register-result', error.message, false);
        }
    });

    elements.logoutButton.addEventListener('click', clearSession);

    elements.createForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireLogin('create-result')) return;

        try {
            const account = await request('/accounts/create', {
                method: 'POST',
                body: JSON.stringify({
                    holderName: document.getElementById('account-name').value,
                    initialBalance: amountValue('initial-balance')
                })
            });
            setCurrentAccount(account);
            elements.createForm.reset();
            showMessage('create-result', 'Account created successfully.');
        } catch (error) {
            showMessage('create-result', error.message, false);
        }
    });

    elements.findForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireLogin('find-result')) return;

        try {
            const account = await loadAccount(document.getElementById('find-account-id').value);
            showMessage('find-result', `Loaded ${account.holderName}.`);
        } catch (error) {
            showMessage('find-result', error.message, false);
        }
    });

    elements.findNumberForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireLogin('find-result')) return;

        try {
            const number = document.getElementById('find-account-number').value.trim();
            const account = await request(`/accounts/number/${encodeURIComponent(number)}`);
            setCurrentAccount(account);
            showMessage('find-result', `Loaded ${account.holderName}.`);
        } catch (error) {
            showMessage('find-result', error.message, false);
        }
    });

    elements.depositForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireAccount('deposit-result')) return;

        try {
            const account = await request(`/accounts/${currentAccount.accountId}/deposit`, {
                method: 'POST',
                body: JSON.stringify({ amount: amountValue('deposit-amount') })
            });
            setCurrentAccount(account);
            elements.depositForm.reset();
            showMessage('deposit-result', 'Deposit completed.');
        } catch (error) {
            showMessage('deposit-result', error.message, false);
        }
    });

    elements.withdrawForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!requireAccount('withdraw-result')) return;

        try {
            const account = await request(`/accounts/${currentAccount.accountId}/withdraw`, {
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
            const transfer = await request('/accounts/transfer', {
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
            const account = await request(`/accounts/${currentAccount.accountId}`, {
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
            const account = await request(`/accounts/${currentAccount.accountId}`, { method: 'DELETE' });
            setCurrentAccount(account);
            showMessage('account-action-result', 'Account closed.');
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });

    elements.downloadButton.addEventListener('click', async () => {
        if (!requireAccount('account-action-result')) return;

        try {
            const response = await fetch(`/accounts/${currentAccount.accountId}/statement.csv`, {
                headers: authHeader()
            });
            if (!response.ok) {
                throw new Error('Could not export statement');
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `account-${currentAccount.accountId}-statement.csv`;
            link.click();
            URL.revokeObjectURL(url);
        } catch (error) {
            showMessage('account-action-result', error.message, false);
        }
    });

    elements.refreshAccounts.addEventListener('click', loadAccounts);
    elements.refreshTransactions.addEventListener('click', loadTransactions);
    elements.refreshAdmin.addEventListener('click', loadAdminSummary);
    elements.refreshRisk.addEventListener('click', loadRiskInsights);

    fetch('/accounts/health')
        .then(response => response.text())
        .then(message => {
            elements.health.textContent = message;
            elements.health.classList.add('ok');
        })
        .catch(() => {
            elements.health.textContent = 'API unavailable';
            elements.health.title = apiUnavailableMessage();
            elements.health.classList.add('bad');
        });

    renderSession();
    if (session?.token) {
        request('/auth/me')
            .then(user => {
                session.user = user;
                localStorage.setItem('corebank-session', JSON.stringify(session));
                renderSession();
                loadAccounts();
                if (isCurrentAdmin()) {
                    loadAdminSummary();
                }
            })
            .catch(clearSession);
    } else {
        resetDashboard();
    }
});
