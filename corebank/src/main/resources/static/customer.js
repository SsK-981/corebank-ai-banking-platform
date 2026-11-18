document.addEventListener('DOMContentLoaded', () => {
  const STORAGE_KEY = 'corebank-customer-session';
  const HELP_STATE_PREFIX = 'corebank-help-state:';
  const TRANSFER_KEY_PREFIX = 'corebank-pending-transfer:';
  const money = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  });
  let session = readSession();
  let accounts = [];
  let currentAccount = null;
  let conversationId = null;
  let selectedHelpCard = null;
  let helpTranscript = [];
  let helpCaseOffer = false;
  let supportInFlight = false;
  let lastFailedHelpRequest = null;
  let currentPage = 'overview';
  let pendingTransfer = null;
  let unresolvedTransfer = null;
  let inFlightTransfer = null;
  let recipientLookupTimer;
  let recipientLookup;
  const sameAccountMessage =
    'The recipient account must be different from the source account.';
  let transactionRequest = 0;
  const $ = (id) => document.getElementById(id);

  function readSession() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    } catch {
      return null;
    }
  }
  function message(id, text, success = true) {
    const node = $(id);
    node.textContent = text;
    node.className = `message ${success ? 'success' : 'error'}`;
  }
  function hideMessage(id) {
    $(id).classList.add('hidden');
  }
  function tokenHeader() {
    return session?.token ? { Authorization: `Basic ${session.token}` } : {};
  }
  function transferStorageKey() {
    const customer =
      session?.user?.id ?? session?.user?.email ?? session?.email;
    return customer ? `${TRANSFER_KEY_PREFIX}${customer}` : null;
  }
  function helpStateKey() {
    const identity =
      session?.user?.id ?? session?.user?.email ?? session?.email;
    return identity ? `${HELP_STATE_PREFIX}${identity}` : null;
  }
  function saveHelpState() {
    const key = helpStateKey();
    if (!key) return;
    sessionStorage.setItem(
      key,
      JSON.stringify({
        conversationId,
        selectedHelpCard,
        helpCaseOffer,
        messages: helpTranscript.slice(-80),
        lastFailedHelpRequest,
      }),
    );
  }
  function restoreHelpState() {
    const key = helpStateKey();
    if (!key) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
      if (!saved) return;
      conversationId = saved.conversationId || null;
      helpCaseOffer = Boolean(saved.helpCaseOffer);
      lastFailedHelpRequest = saved.lastFailedHelpRequest || null;
      $('chat-retry').classList.toggle('hidden', !lastFailedHelpRequest);
      $('chat-messages').replaceChildren();
      helpTranscript = [];
      for (const item of saved.messages || []) renderHelpMessage(item);
      if (!helpTranscript.length)
        renderHelpMessage({
          role: 'assistant',
          text: 'Hello! How can I help you today?',
        });
      $('help-case-offer').classList.toggle('hidden', !helpCaseOffer);
      showHelpTransaction(saved.selectedHelpCard || null);
    } catch {
      sessionStorage.removeItem(key);
    }
  }
  function readUnresolvedTransfer() {
    const key = transferStorageKey();
    try {
      const saved = key
        ? JSON.parse(sessionStorage.getItem(key) || 'null')
        : null;
      return saved?.key && saved?.payload ? saved : null;
    } catch {
      return null;
    }
  }
  function saveUnresolvedTransfer(transfer) {
    const key = transferStorageKey();
    unresolvedTransfer = transfer;
    if (key && transfer) sessionStorage.setItem(key, JSON.stringify(transfer));
    updateTransferRetry();
  }
  function clearUnresolvedTransfer() {
    const key = transferStorageKey();
    if (key) sessionStorage.removeItem(key);
    unresolvedTransfer = null;
    updateTransferRetry();
  }
  function updateTransferRetry() {
    const retry = $('transfer-retry');
    const detail = $('transfer-pending-detail');
    const payload = unresolvedTransfer?.payload;
    retry.classList.toggle('hidden', !payload);
    retry.disabled = Boolean(inFlightTransfer);
    detail.classList.toggle('hidden', !payload);
    detail.textContent = payload
      ? `Resolve the ${money.format(Number(payload.amount))} transfer to account ending in ${payload.toAccountNumber.slice(-4)} before sending another transfer.`
      : '';
    $('transfer-form').querySelector('button[type="submit"]').disabled =
      Boolean(unresolvedTransfer || inFlightTransfer);
  }
  async function request(url, options = {}, authenticated = true) {
    let response;
    try {
      response = await fetch(url, {
        ...options,
        headers: {
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...(authenticated ? tokenHeader() : {}),
          ...options.headers,
        },
      });
    } catch {
      throw new Error(
        'CoreBank is unavailable right now. Please check your connection and try again.',
      );
    }
    if (!response.ok) {
      const status = response.status;
      let text =
        response.status === 401 || response.status === 403
          ? 'Your session has expired. Please sign in again.'
          : `Request failed (${response.status}).`;
      try {
        const data = await response.json();
        text =
          data.messages?.join(', ') ||
          (typeof data.detail === 'string' ? data.detail : data.message) ||
          text;
      } catch {}
      const error = new Error(text);
      error.status = status;
      throw error;
    }
    if (response.status === 204) return null;
    return response.json();
  }
  function showAuthTab(tab) {
    const isLogin = tab === 'login';
    $('login-tab').classList.toggle('active', isLogin);
    $('register-tab').classList.toggle('active', !isLogin);
    $('login-tab').setAttribute('aria-selected', String(isLogin));
    $('register-tab').setAttribute('aria-selected', String(!isLogin));
    $('login-pane').classList.toggle('hidden', !isLogin);
    $('register-pane').classList.toggle('hidden', isLogin);
  }
  function setSession(email, password, user) {
    session = { email, token: btoa(`${email}:${password}`), user };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    unresolvedTransfer = readUnresolvedTransfer();
    renderSession();
    updateTransferRetry();
  }
  function renderSession() {
    const loggedIn = Boolean(session?.user);
    $('auth-view').classList.toggle('hidden', loggedIn);
    $('app-view').classList.toggle('hidden', !loggedIn);
    if (loggedIn) {
      const name = session.user.fullName || session.user.email || 'Customer';
      $('header-name').textContent = name;
      $('avatar-initials').textContent = name
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part[0])
        .join('')
        .toUpperCase();
      const hour = new Date().getHours();
      $('welcome-line').textContent =
        `${hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'}, ${name.split(' ')[0]}`;
    }
  }
  function logout() {
    const helpKey = helpStateKey();
    if (helpKey) sessionStorage.removeItem(helpKey);
    session = null;
    sessionStorage.removeItem(STORAGE_KEY);
    currentAccount = null;
    accounts = [];
    conversationId = null;
    selectedHelpCard = null;
    helpTranscript = [];
    lastFailedHelpRequest = null;
    $('chat-retry').classList.add('hidden');
    helpCaseOffer = false;
    supportInFlight = false;
    pendingTransfer = null;
    unresolvedTransfer = null;
    inFlightTransfer = null;
    updateTransferRetry();
    transactionRequest++;
    clearRecipientPreview();
    for (const id of ['account-cards', 'recent-transactions', 'activity-list'])
      $(id).replaceChildren();
    for (const id of [
      'login-password',
      'chat-input',
      'rename-holder',
      'transfer-to',
      'transfer-amount',
    ])
      $(id).value = '';
    for (const id of [
      'accounts-error',
      'transactions-error',
      'recent-error',
      'transfer-result',
      'account-action-result',
      'open-result',
    ])
      hideMessage(id);
    $('chat-messages').replaceChildren();
    $('help-transaction-context').replaceChildren();
    $('help-transaction-context').classList.add('hidden');
    $('help-transaction-options').replaceChildren();
    $('help-transaction-options').classList.add('hidden');
    $('help-cases').replaceChildren();
    $('help-cases').classList.add('hidden');
    $('help-case-offer').classList.add('hidden');
    setSupportBusy(false);
    addBubble('assistant', 'Hello! How can I help you today?');
    $('chat-input').value = '';
    $('chat-error').classList.add('hidden');
    renderSession();
    showAuthTab('login');
  }
  function appendText(parent, tag, text, className) {
    const el = document.createElement(tag);
    el.textContent = text;
    if (className) el.className = className;
    parent.append(el);
    return el;
  }
  function renderAccounts() {
    const grid = $('account-cards');
    grid.replaceChildren();
    $('open-account-form').classList.toggle('hidden', accounts.length > 0);
    if (!accounts.length) {
      appendText(
        grid,
        'p',
        'No accounts yet. Create an account to get started.',
        'empty-state',
      );
      currentAccount = null;
      updateAccountSelectors();
      return;
    }
    currentAccount =
      accounts.find((a) => a.accountId === currentAccount?.accountId) ||
      accounts[0];
    accounts.forEach((account) => {
      const card = document.createElement('article');
      card.className = `account-card${account.accountId === currentAccount.accountId ? ' selected' : ''}${account.active ? '' : ' inactive'}`;
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.setAttribute(
        'aria-pressed',
        String(account.accountId === currentAccount.accountId),
      );
      card.setAttribute(
        'aria-label',
        `${account.holderName}, account number ${account.accountNumber}, balance ${money.format(Number(account.balance))}. ${account.active ? 'Active' : 'Closed'}. Select account.`,
      );
      appendText(card, 'div', '', 'account-card-top');
      card.firstChild.append(
        Object.assign(document.createElement('p'), {
          className: 'eyebrow',
          textContent: 'COREBANK ACCOUNT',
        }),
        Object.assign(document.createElement('span'), {
          className: 'account-status',
          textContent: account.active ? '● Active' : 'Closed',
        }),
      );
      appendText(card, 'h3', account.holderName);
      appendText(card, 'div', account.accountNumber, 'account-number');
      appendText(card, 'div', 'AVAILABLE BALANCE', 'balance-label');
      appendText(
        card,
        'div',
        money.format(Number(account.balance)),
        'account-balance',
      );
      const choose = () => selectAccount(account);
      card.addEventListener('click', choose);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          choose();
        }
      });
      grid.append(card);
    });
    $('rename-holder').value = currentAccount.holderName;
    updateAccountSelectors();
  }
  function updateAccountSelectors() {
    [
      ['transfer-from', false],
      ['activity-account', true],
    ].forEach(([id, includeClosed]) => {
      const select = $(id);
      select.replaceChildren();
      accounts
        .filter((a) => includeClosed || a.active)
        .forEach((account) => {
          const option = document.createElement('option');
          option.value = account.accountId;
          option.textContent = `${account.holderName} · ${account.accountNumber}`;
          select.append(option);
        });
      if (currentAccount && (includeClosed || currentAccount.active))
        select.value = String(currentAccount.accountId);
    });
  }
  function selectAccount(account) {
    currentAccount = account;
    renderAccounts();
    loadTransactions();
  }
  async function loadAccounts() {
    $('accounts-error').classList.add('hidden');
    const activeSession = session;
    try {
      const page = await request('/customer/accounts?size=50');
      if (session !== activeSession) return;
      accounts = page.content || [];
      renderAccounts();
      await loadTransactions();
    } catch (error) {
      if (session !== activeSession) return;
      $('accounts-error').textContent =
        `Could not refresh accounts: ${error.message}`;
      $('accounts-error').classList.remove('hidden');
    }
  }
  function transactionDescription(t) {
    return (
      t.description ||
      t.failureReason ||
      t.type.toLowerCase().replaceAll('_', ' ')
    );
  }
  function renderTransaction(container, t, activity = false) {
    const row = document.createElement('div');
    row.className = activity ? 'activity-row' : 'recent-row';
    appendText(
      row,
      'span',
      t.type === 'DEPOSIT' ? '↓' : t.type === 'WITHDRAWAL' ? '↗' : '↕',
      'tx-icon',
    );
    const main = appendText(row, 'div', '', 'tx-main');
    appendText(main, 'strong', transactionDescription(t));
    appendText(
      main,
      'small',
      t.referenceNumber ? `Ref ${t.referenceNumber}` : 'Transaction',
    );
    const credit = ['DEPOSIT', 'TRANSFER_RECEIVED'].includes(t.type);
    const sign = t.status === 'FAILED' ? '' : credit ? '+' : '−';
    const amount = appendText(
      row,
      'div',
      `${sign}${money.format(Number(t.amount))}`,
      `tx-amount${credit && sign ? ' debit' : ''}`,
    );
    appendText(amount, 'span', t.status || 'POSTED', 'tx-status');
    if (activity)
      appendText(
        row,
        'div',
        new Date(t.timestamp).toLocaleString(),
        'activity-date',
      );
    if (activity) {
      const help = appendText(row, 'button', 'Get help', 'activity-help');
      help.type = 'button';
      help.setAttribute(
        'aria-label',
        `Get help with ${t.referenceNumber || 'this transaction'}`,
      );
      help.addEventListener('click', () => {
        if (!t.referenceNumber || supportInFlight) return;
        navigate('help');
        sendSupport(
          'Get help with this transaction',
          'select_transaction',
          t.referenceNumber,
        );
      });
    }
    container.append(row);
  }
  async function loadTransactions() {
    const requestId = ++transactionRequest;
    $('transactions-error').classList.add('hidden');
    $('recent-error').classList.add('hidden');
    $('recent-transactions').replaceChildren();
    $('activity-list').replaceChildren();
    if (!currentAccount) {
      appendText(
        $('recent-transactions'),
        'p',
        'Choose an account to see recent activity.',
        'empty-state',
      );
      appendText(
        $('activity-list'),
        'p',
        'Choose an account to see transactions.',
        'empty-state',
      );
      return;
    }
    try {
      const page = await request(
        `/customer/accounts/${currentAccount.accountId}/transactions?size=50`,
      );
      if (requestId !== transactionRequest) return;
      const rows = page.content || [];
      if (!rows.length) {
        appendText(
          $('recent-transactions'),
          'p',
          'No transactions yet.',
          'empty-state',
        );
        appendText(
          $('activity-list'),
          'p',
          'No transactions yet.',
          'empty-state',
        );
        return;
      }
      rows
        .slice(0, 4)
        .forEach((t) => renderTransaction($('recent-transactions'), t));
      rows.forEach((t) => renderTransaction($('activity-list'), t, true));
    } catch (error) {
      if (requestId !== transactionRequest) return;
      for (const id of ['transactions-error', 'recent-error']) {
        $(id).textContent = `Could not refresh transactions: ${error.message}`;
        $(id).classList.remove('hidden');
      }
    }
  }
  function renderPage(page) {
    const pageNames = {
      overview: 'Overview',
      transfer: 'Transfer',
      activity: 'Activity',
      help: 'Help',
    };
    Object.keys(pageNames).forEach((name) =>
      $(`${name}-page`).classList.toggle('hidden', name !== page),
    );
    document.querySelectorAll('.nav-link').forEach((link) => {
      const active = link.dataset.page === page;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    $('page-title').textContent = pageNames[page];
    currentPage = page;
  }
  function navigate(page, { historyEntry = true } = {}) {
    if (!['overview', 'transfer', 'activity', 'help'].includes(page))
      page = 'overview';
    if (historyEntry && page !== currentPage)
      history.pushState({ page }, '', `#${page}`);
    else if (!location.hash) history.replaceState({ page }, '', `#${page}`);
    renderPage(page);
  }
  function scrollHelpThread() {
    const thread = $('chat-thread');
    thread.scrollTop = thread.scrollHeight;
  }
  function addBubble(role, text) {
    const bubble = appendText(
      $('chat-messages'),
      'div',
      text,
      `chat-bubble ${role}`,
    );
    scrollHelpThread();
    return bubble;
  }
  function supportError(error) {
    $('chat-error').textContent = error.message;
    $('chat-error').classList.remove('hidden');
  }

  function bindHelpNextAction(button) {
    button.addEventListener('click', () => {
      const statement = button.dataset.helpNextAction === 'download_statement';
      navigate(statement ? 'overview' : 'transfer');
      $(statement ? 'download-statement' : 'transfer-to').focus();
    });
  }

  function renderHelpMessage(item) {
    if (item.role === 'user' || item.role === 'assistant') {
      if (typeof item.text !== 'string') return;
      addBubble(item.role, item.text);
    } else if (item.kind === 'summary' && typeof item.text === 'string') {
      const summary = appendText(
        $('chat-messages'),
        'div',
        '',
        'help-case-confirmation',
      );
      appendText(summary, 'strong', 'Case summary');
      appendText(summary, 'p', item.text);
    } else if (
      item.kind === 'action' &&
      ['download_statement', 'open_transfer'].includes(item.action)
    ) {
      const actions = appendText(
        $('chat-messages'),
        'div',
        '',
        'chat-next-actions',
      );
      const button = appendText(
        actions,
        'button',
        item.action === 'download_statement'
          ? 'Go to statement download'
          : 'Go to Transfer',
        'quiet-button',
      );
      button.type = 'button';
      button.dataset.helpNextAction = item.action;
      bindHelpNextAction(button);
    } else if (item.kind === 'tools' && typeof item.text === 'string') {
      const detail = appendText($('chat-messages'), 'details', '');
      appendText(detail, 'summary', 'Agent activity');
      appendText(detail, 'p', item.text);
    } else return;
    helpTranscript.push(item);
  }

  function showHelpTransaction(transaction) {
    selectedHelpCard = transaction?.reference ? transaction : null;
    const panel = $('help-transaction-context');
    panel.replaceChildren();
    panel.classList.toggle('hidden', !selectedHelpCard);
    if (!selectedHelpCard) return;
    const header = appendText(panel, 'div', '', 'help-context-heading');
    appendText(header, 'strong', 'Selected transaction');
    const clear = appendText(header, 'button', 'Clear', 'quiet-button help-clear-transaction');
    clear.type = 'button';
    clear.setAttribute('aria-label', 'Clear selected transaction');
    clear.addEventListener('click', () =>
      sendSupport('Clear selected transaction', 'clear_transaction'),
    );
    appendText(panel, 'span', helpTransactionDetails(selectedHelpCard));
  }
  function helpLabel(value) {
    if (value === 'withdraw') return 'Withdrawal';
    const text = value.replaceAll('_', ' ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function helpTransactionDetails(transaction) {
    const timestamp = transaction.timestamp
      ? new Date(transaction.timestamp)
      : null;
    return [
      transaction.reference,
      transaction.type ? helpLabel(transaction.type) : '',
      transaction.amount != null
        ? money.format(Number(transaction.amount))
        : '',
      transaction.status ? helpLabel(transaction.status) : '',
      timestamp && !Number.isNaN(timestamp.getTime())
        ? timestamp.toLocaleDateString('en-IN')
        : '',
    ]
      .filter(Boolean)
      .join(' · ');
  }

  function renderHelpOptions(options = []) {
    const panel = $('help-transaction-options');
    panel.replaceChildren();
    if (!options.length) {
      panel.classList.add('hidden');
      return;
    }
    appendText(panel, 'strong', 'Choose the transaction you mean');
    options.forEach((transaction) => {
      const button = appendText(
        panel,
        'button',
        helpTransactionDetails(transaction),
        'help-option',
      );
      button.type = 'button';
      button.addEventListener('click', () =>
        sendSupport(
          'Please help me with this transaction.',
          'select_transaction',
          transaction.reference,
        ),
      );
    });
    panel.classList.remove('hidden');
  }
  function renderHelpCases(cases = [], showDetails = false) {
    const panel = $('help-cases');
    panel.replaceChildren();
    appendText(panel, 'strong', 'My support cases');
    if (!cases.length)
      appendText(panel, 'p', 'No support cases yet.', 'empty-state');
    cases.forEach((item) => {
      const card = appendText(panel, 'article', '', 'help-case-card');
      appendText(card, 'strong', item.ticket_id || 'Support case');
      appendText(
        card,
        'span',
        `${helpLabel(item.status || 'Status unavailable')} · ${helpLabel(item.issue_type || 'Support request')}${item.transaction_reference ? ` · ${item.transaction_reference}` : ''}`,
      );
      const summary = item.case_summary || item.summary;
      if (summary) appendText(card, 'p', summary, 'help-case-summary');
      if (showDetails && item.ticket_id) {
        const button = appendText(card, 'button', 'View case', 'quiet-button help-case-detail');
        button.type = 'button';
        button.addEventListener('click', () => sendSupport(`Show case ${item.ticket_id}`));
      }
    });
    panel.classList.remove('hidden');
  }
  function setSupportBusy(busy) {
    supportInFlight = busy;
    document
      .querySelectorAll(
        '#chat-form input, #chat-form button, [data-help-message], [data-help-action], ' +
          '#request-help-case, .help-option, .help-case-detail, .activity-help, .help-clear-transaction',
      )
      .forEach((control) => {
        control.disabled = busy;
      });
  }

  async function sendSupport(
    text,
    action,
    transactionReference,
    retry = false,
  ) {
    if (!text || !session?.user || supportInFlight) return;
    const requestData = { text, action, transactionReference };
    if (!retry) lastFailedHelpRequest = null;
    $('chat-retry').classList.add('hidden');
    const activeSession = session;
    const previousOffer = helpCaseOffer;
    setSupportBusy(true);
    $('help-case-offer').classList.add('hidden');
    $('chat-error').classList.add('hidden');
    if (!retry) renderHelpMessage({ role: 'user', text });
    saveHelpState();
    const waiting = addBubble('assistant', 'One moment…');
    try {
      const body = { message: text, conversation_id: conversationId };
      if (action) body.action = action;
      if (transactionReference)
        body.transaction_reference = transactionReference;
      const result = await request('/customer/support/chat', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (session !== activeSession) return;
      conversationId = result.conversation_id;
      lastFailedHelpRequest = null;
      $('chat-retry').classList.add('hidden');
      waiting.remove();
      renderHelpMessage({ role: 'assistant', text: result.response });
      if (result.case_summary)
        renderHelpMessage({ kind: 'summary', text: result.case_summary });
      if (result.next_action)
        renderHelpMessage({ kind: 'action', action: result.next_action });
      if (
        result.selected_transaction ||
        result.case_offer ||
        ['select_transaction', 'clear_transaction'].includes(action)
      ) {
        showHelpTransaction(result.selected_transaction);
      }
      renderHelpOptions(result.transaction_options || []);
      if (action === 'list_cases' || result.cases?.length)
        renderHelpCases(result.cases || [], !/\bTCK-[A-Z0-9]+\b/i.test(text));
      else $('help-cases').classList.add('hidden');
      helpCaseOffer = Boolean(result.case_offer);
      $('help-case-offer').classList.toggle('hidden', !helpCaseOffer);
      const tools = (result.tools_used || []).join(', ');
      if (tools) renderHelpMessage({ kind: 'tools', text: tools });
      scrollHelpThread();
      saveHelpState();
    } catch (error) {
      waiting.remove();
      if (session === activeSession) {
        $('help-case-offer').classList.toggle('hidden', !previousOffer);
        supportError(error);
        if (!error.status || error.status >= 500) {
          lastFailedHelpRequest = requestData;
          $('chat-retry').classList.remove('hidden');
        }
        saveHelpState();
      }
    } finally {
      if (session === activeSession) {
        setSupportBusy(false);
      }
    }
  }

  $('retry-chat').addEventListener('click', () => {
    if (lastFailedHelpRequest)
      sendSupport(
        lastFailedHelpRequest.text,
        lastFailedHelpRequest.action,
        lastFailedHelpRequest.transactionReference,
        true,
      );
  });

  document.querySelectorAll('[data-help-message]').forEach((button) =>
    button.addEventListener('click', () => {
      navigate('help');
      sendSupport(button.dataset.helpMessage);
    }),
  );
  document
    .querySelectorAll('[data-help-action="list_cases"]')
    .forEach((button) =>
      button.addEventListener('click', () =>
        sendSupport('Show my support cases.', 'list_cases'),
      ),
    );
  $('request-help-case').addEventListener('click', () =>
    sendSupport('Open a support case'),
  );
  $('confirm-help-case').addEventListener('click', () => {
    if (!helpCaseOffer || supportInFlight) return;
    $('confirm-help-case').disabled = true;
    sendSupport(
      'Please open the support case.',
      'confirm_case',
    ).finally(() => {
      $('confirm-help-case').disabled = false;
    });
  });

  window.addEventListener('popstate', () => {
    const page = location.hash.slice(1);
    renderPage(
      ['overview', 'transfer', 'activity', 'help'].includes(page)
        ? page
        : 'overview',
    );
  });

  $('login-tab').addEventListener('click', () => showAuthTab('login'));
  $('register-tab').addEventListener('click', () => showAuthTab('register'));
  async function login(email, password) {
    email = email.trim().toLowerCase();
    try {
      session = { email, token: btoa(`${email}:${password}`) };
      const user = await request('/auth/customer/me');
      setSession(email, password, user);
      hideMessage('login-result');
      navigate('overview');
      await loadAccounts();
    } catch (error) {
      session = null;
      message('login-result', error.message, false);
    }
  }
  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await login($('login-email').value, $('login-password').value);
  });
  $('demo-login').addEventListener('click', async () => {
    const button = $('demo-login');
    button.disabled = true;
    try {
      await login($('demo-customer').value, 'password123');
    } finally {
      button.disabled = false;
    }
  });
  $('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    hideMessage('register-result');
    const email = $('register-email').value.trim().toLowerCase(),
      password = $('register-password').value;
    try {
      const user = await request(
        '/auth/customer/register',
        {
          method: 'POST',
          body: JSON.stringify({
            fullName: $('register-name').value.trim(),
            email,
            password,
          }),
        },
        false,
      );
      setSession(email, password, user);
      try {
        const account = await request('/customer/accounts', {
          method: 'POST',
          body: JSON.stringify({
            holderName: $('register-holder-name').value.trim(),
            initialBalance: Number($('register-opening-deposit').value).toFixed(
              2,
            ),
          }),
        });
        accounts = [account];
        currentAccount = account;
        $('register-form').reset();
        renderSession();
        renderAccounts();
        navigate('overview');
      } catch (error) {
        navigate('overview');
        await loadAccounts();
        $('open-holder').value = $('register-holder-name').value;
        message(
          'open-result',
          `Your profile was created. Please retry opening the account: ${error.message}`,
          false,
        );
      }
    } catch (error) {
      message('register-result', error.message, false);
    }
  });
  $('open-account-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await request('/customer/accounts', {
        method: 'POST',
        body: JSON.stringify({
          holderName: $('open-holder').value.trim(),
          initialBalance: Number($('open-deposit').value).toFixed(2),
        }),
      });
      $('open-account-form').reset();
      hideMessage('open-result');
      await loadAccounts();
    } catch (error) {
      message('open-result', error.message, false);
    }
  });
  $('withdraw-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!currentAccount?.active)
      return message(
        'account-action-result',
        'Select an active account first.',
        false,
      );
    const button = $('withdraw-form').querySelector('button');
    button.disabled = true;
    try {
      await request(`/customer/accounts/${currentAccount.accountId}/withdraw`, {
        method: 'POST',
        body: JSON.stringify({
          amount: Number($('withdraw-amount').value).toFixed(2),
        }),
      });
      $('withdraw-form').reset();
      message('account-action-result', 'Withdrawal completed.');
      await loadAccounts();
    } catch (error) {
      message('account-action-result', error.message, false);
    } finally {
      button.disabled = false;
    }
  });
  $('logout-button').addEventListener('click', logout);
  document.querySelectorAll('[data-page]').forEach((link) =>
    link.addEventListener('click', (e) => {
      e.preventDefault();
      navigate(link.dataset.page);
    }),
  );
  document
    .querySelectorAll('[data-goto]')
    .forEach((button) =>
      button.addEventListener('click', () => navigate(button.dataset.goto)),
    );
  $('refresh-accounts').addEventListener('click', loadAccounts);
  $('refresh-transactions').addEventListener('click', loadTransactions);
  $('activity-account').addEventListener('change', () => {
    const account = accounts.find(
      (a) => String(a.accountId) === $('activity-account').value,
    );
    if (account) selectAccount(account);
  });
  $('download-statement').addEventListener('click', async () => {
    if (!currentAccount)
      return message(
        'account-action-result',
        'Select an account first.',
        false,
      );
    try {
      const response = await fetch(
        `/customer/accounts/${currentAccount.accountId}/statement.csv`,
        { headers: tokenHeader() },
      );
      if (!response.ok) throw new Error('Could not download the statement.');
      const blob = await response.blob(),
        link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `account-${currentAccount.accountId}-statement.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      message('account-action-result', error.message, false);
    }
  });
  $('close-account').addEventListener('click', async () => {
    if (!currentAccount)
      return message(
        'account-action-result',
        'Select an account first.',
        false,
      );
    const accepted = window.confirm(
      `Close account ending ${currentAccount.accountNumber.slice(-4)}? The account must have a zero balance. This action cannot be undone.`,
    );
    if (!accepted) return;
    try {
      const updated = await request(
        `/customer/accounts/${currentAccount.accountId}`,
        { method: 'DELETE' },
      );
      accounts = accounts.map((a) =>
        a.accountId === updated.accountId ? updated : a,
      );
      currentAccount = updated;
      renderAccounts();
      message('account-action-result', 'Account closed.');
    } catch (error) {
      message('account-action-result', error.message, false);
    }
  });

  function transferSource() {
    return accounts.find(
      (account) => String(account.accountId) === $('transfer-from').value,
    );
  }

  function clearRecipientPreview() {
    clearTimeout(recipientLookupTimer);
    recipientLookup?.abort();
    hideMessage('recipient-preview');
  }

  async function lookupRecipient(from, to, signal) {
    const query = new URLSearchParams({ accountNumber: to });
    return request(
      `/customer/accounts/${from.accountId}/transfer-recipient?${query}`,
      { signal },
    );
  }

  function renderRecipientCard(maskedName, accountNumber) {
    const card = $('recipient-preview');
    card.className = 'recipient-card';
    card.replaceChildren();

    const icon = appendText(card, 'span', '✓', 'recipient-card-icon');
    icon.setAttribute('aria-hidden', 'true');
    const details = appendText(card, 'div', '', 'recipient-card-details');
    appendText(details, 'span', 'Recipient found', 'recipient-card-label');
    appendText(details, 'strong', maskedName, 'recipient-card-name');
    appendText(
      details,
      'span',
      `Account ending in ${accountNumber.slice(-4)}`,
      'recipient-card-account',
    );
  }

  function showRecipientPreview() {
    clearRecipientPreview();
    hideMessage('transfer-result');
    const from = transferSource();
    const to = $('transfer-to').value.trim();
    if (!from || !/^\d{12}$/.test(to)) return;
    if (to === from.accountNumber) {
      message('recipient-preview', sameAccountMessage, false);
      return;
    }

    recipientLookup = new AbortController();
    const { signal } = recipientLookup;
    recipientLookupTimer = setTimeout(async () => {
      try {
        const recipient = await lookupRecipient(from, to, signal);
        if (!signal.aborted) {
          renderRecipientCard(recipient.maskedName, to);
        }
      } catch (error) {
        if (!signal.aborted) message('recipient-preview', error.message, false);
      }
    }, 250);
  }

  $('transfer-to').addEventListener('input', showRecipientPreview);
  $('transfer-from').addEventListener('change', showRecipientPreview);
  $('transfer-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (unresolvedTransfer || inFlightTransfer) return;
    const from = transferSource(),
      to = $('transfer-to').value.trim(),
      amount = Number($('transfer-amount').value);
    if (!from)
      return message(
        'transfer-result',
        'Choose an active source account.',
        false,
      );
    if (!/^\d{12}$/.test(to))
      return message(
        'transfer-result',
        'Enter a valid account number using digits only.',
        false,
      );
    if (to === from.accountNumber) {
      return message('transfer-result', sameAccountMessage, false);
    }
    if (!Number.isFinite(amount) || amount <= 0)
      return message(
        'transfer-result',
        'Enter an amount greater than zero.',
        false,
      );
    clearRecipientPreview();
    hideMessage('transfer-result');
    recipientLookup = new AbortController();
    const { signal } = recipientLookup;
    const submit = e.currentTarget.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      const recipient = await lookupRecipient(from, to, signal);
      if (signal.aborted) return;
      if (
        transferSource()?.accountId !== from.accountId ||
        $('transfer-to').value.trim() !== to ||
        Number($('transfer-amount').value) !== amount
      )
        return;

      renderRecipientCard(recipient.maskedName, to);
      pendingTransfer = {
        from,
        to,
        amount: amount.toFixed(2),
      };
      $('confirm-dialog').returnValue = '';
      $('dialog-title').textContent = 'Review transfer';
      $('dialog-copy').textContent =
        `Send ${money.format(amount)} from ${from.holderName} (${from.accountNumber}) to ${recipient.maskedName} (${to})?`;
      $('confirm-dialog').showModal();
    } catch (error) {
      if (!signal.aborted) message('transfer-result', error.message, false);
    } finally {
      submit.disabled = false;
    }
  });
  $('confirm-dialog').addEventListener('close', async () => {
    const transfer = pendingTransfer;
    pendingTransfer = null;
    if ($('confirm-dialog').returnValue !== 'confirm' || !transfer) return;
    if (unresolvedTransfer || inFlightTransfer || !session?.user) return;
    const stored = {
      key: crypto.randomUUID(),
      payload: {
        fromAccountId: transfer.from.accountId,
        toAccountNumber: transfer.to,
        amount: transfer.amount,
      },
    };
    saveUnresolvedTransfer(stored);
    await sendTransfer(stored);
  });

  async function sendTransfer(transfer) {
    if (inFlightTransfer) return;
    const activeSession = session;
    inFlightTransfer = transfer;
    updateTransferRetry();
    try {
      const result = await request('/customer/accounts/transfer', {
        method: 'POST',
        headers: { 'Idempotency-Key': transfer.key },
        body: JSON.stringify(transfer.payload),
        signal: AbortSignal.timeout(15000),
      });
      if (session !== activeSession) return;
      if (!result?.referenceNumber) {
        throw new Error('CoreBank did not return a transfer receipt.');
      }
      clearUnresolvedTransfer();
      $('transfer-form').reset();
      clearRecipientPreview();
      message(
        'transfer-result',
        `Transfer complete · Receipt reference ${result.referenceNumber}`,
      );
      loadAccounts();
    } catch (error) {
      if (session !== activeSession) return;
      if (error.status === 400 || error.status === 404) {
        clearUnresolvedTransfer();
        message('transfer-result', error.message, false);
      } else {
        message(
          'transfer-result',
          `${error.message} The outcome is unconfirmed. Use Retry transfer to send the same request safely.`,
          false,
        );
      }
    } finally {
      if (inFlightTransfer === transfer) {
        inFlightTransfer = null;
        updateTransferRetry();
      }
    }
  }

  $('transfer-retry').addEventListener('click', () => {
    if (unresolvedTransfer) sendTransfer(unresolvedTransfer);
  });

  $('chat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = $('chat-input').value.trim();
    $('chat-input').value = '';
    await sendSupport(text);
  });

  renderSession();
  if (session?.token) {
    request('/auth/customer/me')
      .then((user) => {
        session.user = user;
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
        unresolvedTransfer = readUnresolvedTransfer();
        renderSession();
        updateTransferRetry();
        restoreHelpState();
        return loadAccounts();
      })
      .catch(logout);
  } else {
    showAuthTab('login');
  }
  const initialPage = location.hash.slice(1);
  renderPage(
    ['overview', 'transfer', 'activity', 'help'].includes(initialPage)
      ? initialPage
      : 'overview',
  );
});
