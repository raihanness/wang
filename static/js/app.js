// Wang app shell — Turbo-aware sheet + appbar logic (loaded once in <head>)
(function () {
  function syncAppbar() {
    const el = document.querySelector('.appbar-title');
    if (!el) return;
    el.textContent = 'Wang';
  }

  function getIconHref(name) {
    if (!name) return '';
    const cleanName = String(name).trim();
    if (document.getElementById('icon-' + cleanName)) {
      return '#icon-' + cleanName;
    }
    return '/static/img/icons.svg#icon-' + cleanName;
  }

  function setSvgIcon(el, name) {
    if (!el || !name) return;
    const href = getIconHref(name);
    const use = el.tagName && el.tagName.toLowerCase() === 'use' ? el : el.querySelector('use');
    if (use) {
      use.setAttribute('href', href);
    } else if (el.tagName && el.tagName.toLowerCase() === 'svg') {
      el.innerHTML = `<use href="${href}"></use>`;
    } else {
      el.innerHTML = `<svg class="icon"><use href="${href}"></use></svg>`;
    }
  }

  function resolveExternalIcons(root) {
    const context = root && root.querySelectorAll ? root : document;
    const uses = context.querySelectorAll('svg > use[href^="#icon-"]');
    for (let i = 0; i < uses.length; i++) {
      const use = uses[i];
      const href = use.getAttribute('href');
      const id = href.slice(1);
      if (!document.getElementById(id)) {
        use.setAttribute('href', '/static/img/icons.svg' + href);
      }
    }
  }

  window.getIconHref = getIconHref;
  window.setSvgIcon = setSvgIcon;
  window.resolveExternalIcons = resolveExternalIcons;


  function syncThemeUI() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const icon = document.getElementById('theme-icon');
    const btn = document.getElementById('theme-toggle');
    const meta = document.getElementById('meta-theme-color');
    if (icon) {
      setSvgIcon(icon, current === 'dark' ? 'light_mode' : 'dark_mode');
    }
    if (btn) {
      const label = current === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
      btn.setAttribute('aria-label', label);
      btn.setAttribute('title', label);
    }
    if (meta) {
      meta.setAttribute('content', current === 'dark' ? '#11100f' : '#FFF7F3');
    }
    if (window.AndroidBridge && typeof window.AndroidBridge.setSystemTheme === 'function') {
      try {
        window.AndroidBridge.setSystemTheme(current === 'dark');
      } catch (e) {}
    }
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('wang-theme', next);
    } catch (e) { }
    syncThemeUI();
    mountGraphs();
  }

  // ── Total Balance Privacy (Eye Toggle) ────────────────────
  function isBalanceHidden() {
    return localStorage.getItem('wang-balance-hidden') === '1';
  }

  function syncBalancePrivacy() {
    const hidden = isBalanceHidden();
    const btn = document.getElementById('hero-privacy-toggle');
    const icon = document.getElementById('hero-privacy-icon');
    const amountEl = document.getElementById('hero-balance-amount');

    if (icon) {
      setSvgIcon(icon, hidden ? 'visibility_off' : 'visibility');
    }
    if (btn) {
      const label = hidden ? 'Show balance' : 'Hide balance';
      btn.setAttribute('aria-label', label);
      btn.setAttribute('title', label);
    }
    if (amountEl) {
      const raw = amountEl.dataset.rawBalance || '';
      if (hidden) {
        amountEl.innerHTML = '<span class="currency">Rp</span><span class="value masked">••••••</span>';
      } else {
        const val = raw.replace(/^Rp\s*/, '');
        amountEl.innerHTML = '<span class="currency">Rp</span><span class="value">' + val + '</span>';
      }
    }
    const cashflowEl = document.getElementById('hero-cashflow-val');
    if (cashflowEl) {
      const rawCf = cashflowEl.dataset.rawCashflow || '';
      cashflowEl.textContent = hidden ? '••••••' : rawCf;
    }
  }

  function toggleBalancePrivacy() {
    const next = !isBalanceHidden();
    try {
      localStorage.setItem('wang-balance-hidden', next ? '1' : '0');
    } catch (e) { }
    syncBalancePrivacy();
    if (window.wangPlaySound) window.wangPlaySound('tap');
  }

  document.addEventListener('click', (e) => {
    if (e.target.closest('#hero-privacy-toggle')) {
      e.preventDefault();
      toggleBalancePrivacy();
    }
  });

  // ── Web Audio Synthesizer (Cute tactile micro-sounds) ─────
  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx && (window.AudioContext || window.webkitAudioContext)) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContextClass();
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function isSoundEnabled() {
    const saved = localStorage.getItem('wang-sound');
    return saved === null || saved === '1'; // enabled by default
  }

  function syncSoundUI() {
    const enabled = isSoundEnabled();
    const icon = document.getElementById('sound-icon');
    const btn = document.getElementById('sound-toggle');
    if (icon) {
      setSvgIcon(icon, enabled ? 'volume_up' : 'volume_off');
    }
    if (btn) {
      const label = enabled ? 'Mute sound effects' : 'Enable sound effects';
      btn.setAttribute('aria-label', label);
      btn.setAttribute('title', label);
      btn.classList.toggle('muted-sound', !enabled);
    }
  }

  function toggleSound() {
    const current = isSoundEnabled();
    const next = !current;
    try {
      localStorage.setItem('wang-sound', next ? '1' : '0');
    } catch (e) { }
    syncSoundUI();
    if (next) {
      playSound('success');
    }
  }

  function playSound(type) {
    if (!isSoundEnabled()) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const now = ctx.currentTime;

      if (type === 'tap') {
        // Soft bubble pop for keypad & digits
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(460, now);
        osc.frequency.exponentialRampToValueAtTime(180, now + 0.035);
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.035);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.04);
      } else if (type === 'click') {
        // Mellow click for tabs, chips, swatches
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(580, now);
        osc.frequency.exponentialRampToValueAtTime(260, now + 0.025);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.025);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.03);
      } else if (type === 'success') {
        // Pleasant cheerful chime
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        const gain = ctx.createGain();
        osc1.type = 'sine';
        osc2.type = 'sine';
        osc1.frequency.setValueAtTime(523.25, now);
        osc1.frequency.setValueAtTime(659.25, now + 0.08);
        osc2.frequency.setValueAtTime(783.99, now + 0.08);
        gain.gain.setValueAtTime(0.14, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.26);
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);
        osc1.start(now);
        osc2.start(now + 0.08);
        osc1.stop(now + 0.28);
        osc2.stop(now + 0.28);
      } else if (type === 'delete') {
        // Soft wooden knock
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(240, now);
        osc.frequency.exponentialRampToValueAtTime(80, now + 0.08);
        gain.gain.setValueAtTime(0.16, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.09);
      }
    } catch (e) { }

    // Haptic feedback for supported mobile devices
    if (navigator.vibrate) {
      try {
        if (type === 'tap') navigator.vibrate(8);
        else if (type === 'success') navigator.vibrate([12, 40, 18]);
        else if (type === 'delete') navigator.vibrate([20, 30, 20]);
        else navigator.vibrate(6);
      } catch (e) { }
    }
  }
  window.wangPlaySound = playSound;

  function syncBottomNav() {
    const page = document.body.dataset.page || '';
    const bottomNav = document.querySelector('.bottomnav');
    if (bottomNav) {
      if (page === 'login' || page === 'signup') {
        bottomNav.style.display = 'none';
      } else {
        bottomNav.style.display = '';
      }
    }
    const navItems = document.querySelectorAll('.bottomnav .bn-item');
    navItems.forEach(item => {
      const target = item.dataset.nav;
      let active = false;
      if (target === 'dashboard' && page === 'dashboard') {
        active = true;
      } else if (target === 'wallets' && page.startsWith('wallet')) {
        active = true;
      } else if (target === 'graphs' && page === 'graphs') {
        active = true;
      } else if (target === 'categories' && page.startsWith('category')) {
        active = true;
      }
      item.classList.toggle('active', active);
    });
  }

  function syncSheetStateWithAndroid() {
    if (!window.AndroidBridge || !window.AndroidBridge.setScrollableActive) return;
    const anyOpen = document.querySelector('.sheet.open, .detail-sheet.open, .budget-sheet.open, .filter-sheet.open, .confirm-sheet.open, .picker.open, .date-sheet.open, .month-popover.open, #lightbox.active');
    window.AndroidBridge.setScrollableActive(!!anyOpen);
  }
  window.syncSheetStateWithAndroid = syncSheetStateWithAndroid;

  function openSheet() {
    const sheet = document.getElementById('add-sheet');
    const overlay = document.getElementById('sheet-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.add('open');
    overlay.classList.add('show');
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
    document.body.style.overflow = 'hidden';
    if (window.wangRefreshWallets) {
      window.wangRefreshWallets();
    }
    resolveExternalIcons(sheet);
  }

  function closeSheet() {
    const sheet = document.getElementById('add-sheet');
    const overlay = document.getElementById('sheet-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.remove('open');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
    if (window.wangResetSheet) {
      window.wangResetSheet();
    }
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(false);
    }
  }
  window.openSheet = openSheet;
  window.closeSheet = closeSheet;

  // ── Transaction Detail Bottom Sheet ───────────────────────
  let activeDetailData = null;

  function openDetailSheet(data) {
    activeDetailData = data;
    const sheet = document.getElementById('detail-sheet');
    const overlay = document.getElementById('detail-overlay');
    if (!sheet || !overlay) return;

    const iconEl = document.getElementById('dt-icon');
    const symbolEl = document.getElementById('dt-symbol');
    const amtEl = document.getElementById('dt-amount');
    const catNameEl = document.getElementById('dt-cat-name');
    const dateEl = document.getElementById('dt-date');
    const timeEl = document.getElementById('dt-time');
    const datetimeEl = document.getElementById('dt-datetime');
    const walletEl = document.getElementById('dt-wallet');
    const noteRow = document.getElementById('dt-note-row');
    const noteEl = document.getElementById('dt-note');
    const receiptBox = document.getElementById('dt-receipt-box');
    const receiptImg = document.getElementById('dt-receipt-img');
    const deleteForm = document.getElementById('dt-delete-form');

    const kind = data.kind || 'expense';
    const isTransfer = kind === 'transfer';
    const isIncome = kind === 'income';

    if (symbolEl) {
      setSvgIcon(symbolEl, isTransfer ? 'swap_horiz' : (data.catIcon || 'label'));
    }
    if (iconEl) {
      const color = isTransfer ? 'var(--blue, #A8D8EA)' : (data.catColor || '#FFB5A7');
      iconEl.style.backgroundColor = isTransfer ? 'rgba(168, 216, 234, 0.25)' : (color + '25');
      iconEl.style.color = color;
    }

    if (amtEl) {
      const sign = isTransfer ? '' : (isIncome ? '+' : '-');
      const colorStyle = isTransfer ? 'var(--ink)' : (isIncome ? 'var(--green)' : 'var(--red)');
      amtEl.textContent = `${sign}${data.formattedAmount || ('Rp' + data.amount)}`;
      amtEl.style.color = colorStyle;
    }

    if (catNameEl) {
      catNameEl.textContent = isTransfer ? 'Transfer' : (data.catName || 'Transaction');
    }

    let dateStr = data.dateDisplay || '';
    let timeStr = data.timeDisplay || '';

    if (!dateStr || !timeStr) {
      if (data.datetimeDisplay && data.datetimeDisplay.includes(' · ')) {
        const parts = data.datetimeDisplay.split(' · ');
        dateStr = dateStr || parts[0];
        timeStr = timeStr || parts[1];
      } else if (data.date && data.date.includes('T')) {
        const [dPart, tPart] = data.date.split('T');
        if (!timeStr) timeStr = tPart ? tPart.substring(0, 5) : '';
        if (!dateStr) {
          try {
            const dObj = new Date(data.date);
            if (!isNaN(dObj.getTime())) {
              dateStr = dObj.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
            } else {
              dateStr = dPart;
            }
          } catch (e) {
            dateStr = dPart;
          }
        }
      }
    }

    if (dateEl) dateEl.textContent = dateStr || data.date || '-';
    if (timeEl) timeEl.textContent = timeStr || '-';
    if (datetimeEl) datetimeEl.textContent = data.datetimeDisplay || data.date || '-';

    if (walletEl) {
      if (isTransfer) {
        walletEl.textContent = `${data.fromName || 'Account'} → ${data.toName || 'Account'}`;
      } else {
        walletEl.textContent = data.walletName || 'Account';
      }
    }

    if (noteRow && noteEl) {
      if (data.note && data.note.trim()) {
        noteEl.textContent = data.note.trim();
        noteRow.hidden = false;
      } else {
        noteRow.hidden = true;
      }
    }

    if (receiptBox && receiptImg) {
      if (data.image) {
        receiptImg.onerror = () => {
          receiptBox.hidden = true;
        };
        receiptImg.onload = () => {
          receiptBox.hidden = false;
        };
        receiptImg.src = data.image;
      } else {
        receiptBox.hidden = true;
        receiptImg.src = '';
      }
    }

    if (deleteForm) {
      deleteForm.action = data.deleteUrl || '';
    }

    sheet.classList.add('open');
    overlay.classList.add('show');
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
    document.body.style.overflow = 'hidden';
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
  }

  function closeDetailSheet() {
    const sheet = document.getElementById('detail-sheet');
    const overlay = document.getElementById('detail-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.remove('open');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
  }
  window.openDetailSheet = openDetailSheet;
  window.closeDetailSheet = closeDetailSheet;

  // ── Daily Budget Bottom Sheet ─────────────────────────────
  function openBudgetSheet() {
    const sheet = document.getElementById('budget-sheet');
    const overlay = document.getElementById('budget-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.add('open');
    overlay.classList.add('show');
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
    document.body.style.overflow = 'hidden';
    const input = document.getElementById('budget-amount-input');
    if (input) {
      setTimeout(() => input.focus(), 250);
    }
  }

  function closeBudgetSheet() {
    const sheet = document.getElementById('budget-sheet');
    const overlay = document.getElementById('budget-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.remove('open');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(false);
    }
  }
  window.openBudgetSheet = openBudgetSheet;
  window.closeBudgetSheet = closeBudgetSheet;

  // ── Confirmation Bottom Sheet ─────────────────────────────
  function openConfirmSheet({
    title = 'Delete Transaction?',
    desc = 'Are you sure you want to delete this transaction? This action cannot be undone.',
    preview = '',
    actionUrl = '',
    submitText = 'Delete',
    icon = 'delete',
    onConfirm = null,
  } = {}) {
    const sheet = document.getElementById('confirm-sheet');
    const overlay = document.getElementById('confirm-sheet-overlay');
    if (!sheet || !overlay) return;

    const titleEl = document.getElementById('confirm-sheet-title');
    const descEl = document.getElementById('confirm-sheet-desc');
    const previewEl = document.getElementById('confirm-sheet-preview');
    const formEl = document.getElementById('confirm-sheet-form');
    const iconEl = document.getElementById('confirm-sheet-icon');
    const submitTextEl = document.getElementById('confirm-sheet-submit-text');

    if (titleEl) titleEl.textContent = title;
    if (descEl) descEl.textContent = desc;
    if (iconEl) setSvgIcon(iconEl, icon);
    if (submitTextEl) submitTextEl.textContent = submitText;

    if (previewEl) {
      if (preview) {
        previewEl.textContent = preview;
        previewEl.style.display = 'inline-flex';
      } else {
        previewEl.style.display = 'none';
        previewEl.textContent = '';
      }
    }

    if (formEl) {
      formEl.action = actionUrl;
      formEl._onConfirm = onConfirm;
    }

    sheet.classList.add('open');
    overlay.classList.add('show');
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
    document.body.style.overflow = 'hidden';
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
  }

  function closeConfirmSheet() {
    const sheet = document.getElementById('confirm-sheet');
    const overlay = document.getElementById('confirm-sheet-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.remove('open');
    overlay.classList.remove('show');
    const detailOpen = document.getElementById('detail-sheet')?.classList.contains('open');
    const addOpen = document.getElementById('add-sheet')?.classList.contains('open');
    const budgetOpen = document.getElementById('budget-sheet')?.classList.contains('open');
    const filterOpen = document.getElementById('filter-sheet')?.classList.contains('open');
    if (!detailOpen && !addOpen && !budgetOpen && !filterOpen) {
      document.body.style.overflow = '';
    }
    syncSheetStateWithAndroid();
  }
  window.openConfirmSheet = openConfirmSheet;
  window.closeConfirmSheet = closeConfirmSheet;

  function bindConfirmSheet() {
    const form = document.getElementById('confirm-sheet-form');
    if (form && !form.dataset.bound) {
      form.dataset.bound = '1';
      form.addEventListener('submit', () => {
        playSound('delete');
        if (form._onConfirm) {
          try { form._onConfirm(); } catch (err) { }
        }
        closeConfirmSheet();
        closeDetailSheet();
        closeSheet();
      });
    }
  }

  // ── Multi-Filter Bottom Sheet ─────────────────────────────
  function openFilterSheet() {
    const sheet = document.getElementById('filter-sheet');
    const overlay = document.getElementById('filter-overlay');
    if (!sheet || !overlay) return;

    // Read current state from trigger dataset or URL
    const trigger = document.getElementById('multi-filter-trigger');
    const urlParams = new URLSearchParams(window.location.search);
    const activeType = trigger?.dataset.type || urlParams.get('filter') || '';
    const activeWallet = trigger?.dataset.wallet || urlParams.get('wallet') || '';
    const activeCategory = trigger?.dataset.category || urlParams.get('category') || '';
    const activeDateFrom = trigger?.dataset.dateFrom || urlParams.get('date_from') || '';
    const activeDateTo = trigger?.dataset.dateTo || urlParams.get('date_to') || '';

    // Sync Type chips
    const typeChips = document.querySelectorAll('#filter-type-group .filter-choice-chip');
    typeChips.forEach(chip => {
      chip.classList.toggle('active', chip.dataset.type === activeType);
    });

    // Sync Wallet chips
    const walletChips = document.querySelectorAll('#filter-wallet-group .filter-choice-chip');
    walletChips.forEach(chip => {
      chip.classList.toggle('active', chip.dataset.wallet === activeWallet);
    });

    // Sync Category chips
    const catChips = document.querySelectorAll('#filter-cat-group .filter-choice-chip');
    catChips.forEach(chip => {
      chip.classList.toggle('active', chip.dataset.category === activeCategory);
      if (!chip.dataset.category || !activeType || activeType === 'transfer') {
        chip.style.display = '';
      } else {
        chip.style.display = (chip.dataset.kind === activeType) ? '' : 'none';
      }
    });

    // Sync Date inputs
    const fromInput = document.getElementById('filter-date-from');
    const toInput = document.getElementById('filter-date-to');
    if (fromInput) fromInput.value = activeDateFrom;
    if (toInput) toInput.value = activeDateTo;

    sheet.classList.add('open');
    overlay.classList.add('show');
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
    document.body.style.overflow = 'hidden';
    if (window.AndroidBridge && window.AndroidBridge.setScrollableActive) {
      window.AndroidBridge.setScrollableActive(true);
    }
  }

  function closeFilterSheet() {
    const sheet = document.getElementById('filter-sheet');
    const overlay = document.getElementById('filter-overlay');
    if (!sheet || !overlay) return;
    sheet.classList.remove('open');
    overlay.classList.remove('show');
    const detailOpen = document.getElementById('detail-sheet')?.classList.contains('open');
    const addOpen = document.getElementById('add-sheet')?.classList.contains('open');
    const budgetOpen = document.getElementById('budget-sheet')?.classList.contains('open');
    const confirmOpen = document.getElementById('confirm-sheet')?.classList.contains('open');
    if (!detailOpen && !addOpen && !budgetOpen && !confirmOpen) {
      document.body.style.overflow = '';
    }
    syncSheetStateWithAndroid();
  }
  window.openFilterSheet = openFilterSheet;
  window.closeFilterSheet = closeFilterSheet;

  function bindFilterSheet() {
    const sheet = document.getElementById('filter-sheet');
    const overlay = document.getElementById('filter-overlay');
    if (!sheet || sheet.dataset.bound) return;
    sheet.dataset.bound = '1';

    // Close on cancel or backdrop
    const cancelBtn = document.getElementById('filter-cancel');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        playSound('tap');
        closeFilterSheet();
      });
    }
    if (overlay) {
      overlay.addEventListener('click', closeFilterSheet);
    }

    // Type chip selection
    const typeGroup = document.getElementById('filter-type-group');
    if (typeGroup) {
      typeGroup.addEventListener('click', (e) => {
        const chip = e.target.closest('.filter-choice-chip');
        if (!chip) return;
        playSound('tap');
        typeGroup.querySelectorAll('.filter-choice-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');

        // Filter category visibility based on selected type
        const selType = chip.dataset.type;
        const catChips = document.querySelectorAll('#filter-cat-group .filter-choice-chip');
        catChips.forEach(c => {
          if (!c.dataset.category) {
            c.style.display = '';
            return;
          }
          if (!selType || selType === 'transfer') {
            c.style.display = '';
          } else {
            c.style.display = (c.dataset.kind === selType) ? '' : 'none';
          }
        });
      });
    }

    // Wallet chip selection
    const walletGroup = document.getElementById('filter-wallet-group');
    if (walletGroup) {
      walletGroup.addEventListener('click', (e) => {
        const chip = e.target.closest('.filter-choice-chip');
        if (!chip) return;
        playSound('tap');
        walletGroup.querySelectorAll('.filter-choice-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
      });
    }

    // Category chip selection
    const catGroup = document.getElementById('filter-cat-group');
    if (catGroup) {
      catGroup.addEventListener('click', (e) => {
        const chip = e.target.closest('.filter-choice-chip');
        if (!chip) return;
        playSound('tap');
        catGroup.querySelectorAll('.filter-choice-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
      });
    }

    // Date range presets
    sheet.querySelectorAll('.filter-preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        playSound('tap');
        const preset = btn.dataset.preset;
        const fromInput = document.getElementById('filter-date-from');
        const toInput = document.getElementById('filter-date-to');
        if (!fromInput || !toInput) return;

        const now = new Date();
        const formatDate = (d) => {
          const y = d.getFullYear();
          const m = String(d.getMonth() + 1).padStart(2, '0');
          const day = String(d.getDate()).padStart(2, '0');
          return `${y}-${m}-${day}`;
        };

        if (preset === 'this_month') {
          const start = new Date(now.getFullYear(), now.getMonth(), 1);
          const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
          fromInput.value = formatDate(start);
          toInput.value = formatDate(end);
        } else if (preset === 'last_month') {
          const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
          const end = new Date(now.getFullYear(), now.getMonth(), 0);
          fromInput.value = formatDate(start);
          toInput.value = formatDate(end);
        } else if (preset === 'last_30') {
          const start = new Date();
          start.setDate(now.getDate() - 30);
          fromInput.value = formatDate(start);
          toInput.value = formatDate(now);
        } else if (preset === 'all') {
          fromInput.value = '';
          toInput.value = '';
        }
      });
    });

    // Reset button
    const resetBtn = document.getElementById('filter-reset-btn');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        playSound('tap');
        typeGroup?.querySelectorAll('.filter-choice-chip').forEach((c, idx) => c.classList.toggle('active', idx === 0));
        walletGroup?.querySelectorAll('.filter-choice-chip').forEach((c, idx) => c.classList.toggle('active', idx === 0));
        catGroup?.querySelectorAll('.filter-choice-chip').forEach((c, idx) => {
          c.classList.toggle('active', idx === 0);
          c.style.display = '';
        });
        const fromInput = document.getElementById('filter-date-from');
        const toInput = document.getElementById('filter-date-to');
        if (fromInput) fromInput.value = '';
        if (toInput) toInput.value = '';
      });
    }

    // Apply button
    const applyBtn = document.getElementById('filter-apply-btn');
    if (applyBtn) {
      applyBtn.addEventListener('click', () => {
        playSound('tap');
        const activeTypeChip = typeGroup?.querySelector('.filter-choice-chip.active');
        const activeWalletChip = walletGroup?.querySelector('.filter-choice-chip.active');
        const activeCatChip = catGroup?.querySelector('.filter-choice-chip.active');
        const fromVal = document.getElementById('filter-date-from')?.value || '';
        const toVal = document.getElementById('filter-date-to')?.value || '';

        const typeVal = activeTypeChip?.dataset.type || '';
        const walletVal = activeWalletChip?.dataset.wallet || '';
        const catVal = activeCatChip?.dataset.category || '';

        const currentUrl = new URL(window.location.href);
        const searchInput = document.querySelector('.search-input');
        const qVal = searchInput ? searchInput.value.trim() : (currentUrl.searchParams.get('q') || '');

        const params = new URLSearchParams();
        if (qVal) params.set('q', qVal);
        if (typeVal) params.set('filter', typeVal);
        if (walletVal) params.set('wallet', walletVal);
        if (catVal) params.set('category', catVal);

        if (fromVal) params.set('date_from', fromVal);
        if (toVal) params.set('date_to', toVal);

        // Only keep month if custom dates are NOT used
        if (!fromVal && !toVal) {
          const monthVal = currentUrl.searchParams.get('month');
          if (monthVal) params.set('month', monthVal);
        }

        closeFilterSheet();
        const targetUrl = '/' + (params.toString() ? ('?' + params.toString()) : '');
        if (window.Turbo) {
          window.Turbo.visit(targetUrl);
        } else {
          window.location.href = targetUrl;
        }
      });
    }
  }

  function bindSheet() {
    const fab = document.getElementById('bn-fab');
    const overlay = document.getElementById('sheet-overlay');
    if (fab && !fab.dataset.bound) {
      fab.dataset.bound = '1';
      fab.addEventListener('click', () => {
        if (window.wangResetSheet) window.wangResetSheet();
        openSheet();
      });
    }
    if (overlay && !overlay.dataset.bound) {
      overlay.dataset.bound = '1';
      overlay.addEventListener('click', closeSheet);
    }
    bindConfirmSheet();
    bindFilterSheet();
  }

  function resetOverlays() {
    document.body.style.overflow = '';
    const s = document.getElementById('add-sheet');
    const o = document.getElementById('sheet-overlay');
    if (s) s.classList.remove('open');
    if (o) o.classList.remove('show');
    closeMonthPopover();
    closeDetailSheet();
    closeBudgetSheet();
    closeConfirmSheet();
    closeFilterSheet();
    if (window.wangResetSheet) window.wangResetSheet();
    syncSheetStateWithAndroid();
  }


  // ── Month Picker Popover (Dashboard) ─────────────────────────
  function syncYearNavButtons(popover, year) {
    const minYear = parseInt(popover.dataset.minYear || '1970', 10);
    const maxYear = parseInt(popover.dataset.maxYear || '2099', 10);
    const yearPrev = document.getElementById('m-year-prev');
    const yearNext = document.getElementById('m-year-next');

    if (yearPrev) {
      const disablePrev = year <= minYear;
      yearPrev.disabled = disablePrev;
      yearPrev.classList.toggle('disabled', disablePrev);
      if (disablePrev) {
        yearPrev.setAttribute('aria-disabled', 'true');
        yearPrev.setAttribute('title', 'No earlier data');
      } else {
        yearPrev.removeAttribute('aria-disabled');
        yearPrev.setAttribute('title', 'Previous year');
      }
    }
    if (yearNext) {
      const disableNext = year >= maxYear;
      yearNext.disabled = disableNext;
      yearNext.classList.toggle('disabled', disableNext);
      if (disableNext) {
        yearNext.setAttribute('aria-disabled', 'true');
        yearNext.setAttribute('title', 'No later data');
      } else {
        yearNext.removeAttribute('aria-disabled');
        yearNext.setAttribute('title', 'Next year');
      }
    }
  }

  function openMonthPopover() {
    const popover = document.getElementById('month-popover');
    const backdrop = document.getElementById('month-popover-backdrop');
    const trigger = document.getElementById('c-month-trigger');
    const yearDisplay = document.getElementById('m-year-display');
    if (!popover) return;

    const viewYear = parseInt(popover.dataset.viewYear || (yearDisplay ? yearDisplay.textContent.trim() : new Date().getFullYear()), 10);
    popover.dataset.activeYear = viewYear;
    if (yearDisplay) yearDisplay.textContent = viewYear;

    syncYearNavButtons(popover, viewYear);
    updatePopoverMonthGrid(popover, viewYear);

    popover.hidden = false;
    if (backdrop) backdrop.hidden = false;
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
  }

  function closeMonthPopover() {
    const popover = document.getElementById('month-popover');
    const backdrop = document.getElementById('month-popover-backdrop');
    const trigger = document.getElementById('c-month-trigger');
    if (popover) popover.hidden = true;
    if (backdrop) backdrop.hidden = true;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
  }

  function toggleMonthPopover() {
    const popover = document.getElementById('month-popover');
    if (!popover) return;
    if (popover.hidden) {
      openMonthPopover();
    } else {
      closeMonthPopover();
    }
  }

  function updatePopoverMonthGrid(popover, year) {
    const viewMonth = popover.dataset.viewMonth || '';
    const currentMonth = popover.dataset.currentMonth || '';
    const baseUrl = popover.dataset.baseUrl || window.location.pathname;

    let availableMonths = [];
    try {
      availableMonths = JSON.parse(popover.dataset.availableMonths || '[]');
    } catch (e) { }

    const searchInput = document.querySelector('.search-input');
    const q = searchInput ? searchInput.value.trim() : (popover.dataset.q || '');

    const activeChip = document.querySelector('.quick-filter-chip.active');
    const filter = (activeChip && activeChip.dataset.filter !== undefined) ? activeChip.dataset.filter : (popover.dataset.filter || '');

    const gridBtns = popover.querySelectorAll('.m-grid-btn');
    gridBtns.forEach(btn => {
      const m = btn.dataset.m;
      if (!m) return;
      const targetYm = `${year}-${m}`;
      const hasData = availableMonths.length === 0 || availableMonths.includes(targetYm);

      if (hasData) {
        let url = `${baseUrl}?month=${targetYm}`;
        if (q) url += `&q=${encodeURIComponent(q)}`;
        if (filter) url += `&filter=${encodeURIComponent(filter)}`;
        btn.href = url;
        btn.classList.remove('disabled');
        btn.removeAttribute('aria-disabled');
        btn.removeAttribute('tabindex');
        btn.removeAttribute('title');
      } else {
        btn.removeAttribute('href');
        btn.classList.add('disabled');
        btn.setAttribute('aria-disabled', 'true');
        btn.setAttribute('tabindex', '-1');
        btn.setAttribute('title', 'No transactions');
      }

      btn.classList.toggle('active', targetYm === viewMonth);
      btn.classList.toggle('is-current', targetYm === currentMonth && targetYm !== viewMonth);
    });
  }

  function stepPopoverYear(delta) {
    const popover = document.getElementById('month-popover');
    const yearDisplay = document.getElementById('m-year-display');
    if (!popover || !yearDisplay) return;

    const minYear = parseInt(popover.dataset.minYear || '1970', 10);
    const maxYear = parseInt(popover.dataset.maxYear || '2099', 10);

    let currentYear = parseInt(popover.dataset.activeYear || yearDisplay.textContent.trim(), 10);
    if (isNaN(currentYear)) currentYear = new Date().getFullYear();
    const newYear = currentYear + delta;

    if (newYear < minYear || newYear > maxYear) return;

    popover.dataset.activeYear = newYear;
    yearDisplay.textContent = newYear;

    syncYearNavButtons(popover, newYear);
    updatePopoverMonthGrid(popover, newYear);
  }

  function initMonthScroll() {
    const tracks = document.querySelectorAll('.month-scroll-track');
    tracks.forEach(track => {
      const activeChip = track.querySelector('.month-chip.active');
      if (activeChip) {
        activeChip.scrollIntoView({ inline: 'center', behavior: 'smooth', block: 'nearest' });
      }
    });
  }

  function checkAutoEdit() {
    const autoEl = document.getElementById('auto-edit-tx');
    if (autoEl && window.openEditTransaction) {
      window.openEditTransaction(autoEl.dataset);
    }
  }

  function mountGraphs() {
    if (typeof Chart === 'undefined') return;

    const isDark = (document.documentElement.getAttribute('data-theme') === 'dark');
    const gridColor = isDark ? '#2e2b28' : '#F3E9E2';
    const textColor = isDark ? '#9E9A92' : '#8E8E93';
    const pieBorder = isDark ? '#1e1e1d' : '#FFFFFF';

    // ── Annual View Chart ──────────────────────────────────────
    const annualEl = document.getElementById('annualChart');
    const yearDataEl = document.getElementById('year-trend-data');
    if (annualEl && yearDataEl) {
      let yearTrend = [];
      try {
        yearTrend = JSON.parse(yearDataEl.textContent);
        if (typeof yearTrend === 'string') yearTrend = JSON.parse(yearTrend);
      } catch (e) {
        console.error('Failed to parse year trend data', e);
      }
      if (!Array.isArray(yearTrend)) yearTrend = [];

      const existingAnnual = Chart.getChart(annualEl);
      if (existingAnnual) existingAnnual.destroy();

      new Chart(annualEl, {
        type: 'bar',
        data: {
          labels: yearTrend.map(t => t.label),
          datasets: [
            {
              label: 'Income',
              data: yearTrend.map(t => t.income),
              backgroundColor: '#7BD3A4',
              borderRadius: 4,
              barPercentage: 0.8,
              categoryPercentage: 0.75,
            },
            {
              label: 'Expense',
              data: yearTrend.map(t => t.expense),
              backgroundColor: '#FF8A65',
              borderRadius: 4,
              barPercentage: 0.8,
              categoryPercentage: 0.75,
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  const idx = ctx.dataIndex;
                  const item = yearTrend[idx] || {};
                  const val = ctx.raw || 0;
                  const dsLabel = ctx.dataset.label;
                  return `${dsLabel}: Rp${Math.round(val).toLocaleString('id-ID')}`;
                },
                afterBody: function (items) {
                  if (!items.length) return '';
                  const idx = items[0].dataIndex;
                  const item = yearTrend[idx] || {};
                  const net = item.net || 0;
                  const sign = net >= 0 ? '+' : '';
                  return `Net: ${sign}Rp${Math.round(net).toLocaleString('id-ID')} (${item.savings_rate || 0}% saved)`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: {
                color: textColor,
                font: { family: 'Plus Jakarta Sans', size: 10, weight: '600' }
              }
            },
            y: {
              beginAtZero: true,
              suggestedMax: 100000,
              grid: { color: gridColor },
              ticks: {
                color: textColor,
                font: { family: 'Plus Jakarta Sans', size: 10 },
                callback: function (v) {
                  if (v >= 1000000) return (v / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
                  if (v >= 1000) return (v / 1000).toFixed(0) + 'k';
                  return v;
                }
              }
            }
          }
        }
      });
    }

    // ── Monthly View: Pie & Trend Charts ────────────────────────
    const pieDataEl = document.getElementById('pie-data');
    const trendDataEl = document.getElementById('trend-data');
    const pieEl = document.getElementById('pieChart');
    const tEl = document.getElementById('trendChart');

    if (pieEl && pieDataEl) {
      let pie = [];
      try {
        pie = JSON.parse(pieDataEl.textContent);
        if (typeof pie === 'string') pie = JSON.parse(pie);
      } catch (e) {
        console.error('Failed to parse pie data', e);
      }
      if (Array.isArray(pie) && pie.length) {
        const existingPie = Chart.getChart(pieEl);
        if (existingPie) existingPie.destroy();

        new Chart(pieEl, {
          type: 'doughnut',
          data: {
            labels: pie.map(p => p.label),
            datasets: [{
              data: pie.map(p => p.value),
              backgroundColor: pie.map(p => p.color),
              borderWidth: 3,
              borderColor: pieBorder,
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '68%',
            plugins: { legend: { display: false } }
          }
        });

        const legend = document.getElementById('cat-legend');
        if (legend) {
          legend.innerHTML = '';
          const totalVal = pie.reduce((acc, p) => acc + (p.value || 0), 0);
          const isExpense = !window.location.search.includes('kind=income');
          pie.forEach(p => {
            const pct = (p.pct !== undefined) ? p.pct : (totalVal > 0 ? ((p.value / totalVal) * 100).toFixed(1) : 0);

            let momBadgeHtml = '';
            if (p.is_new) {
              momBadgeHtml = `<span class="mom-badge mom-badge-new" title="New category this month">New ★</span>`;
            } else if (p.pct_change !== null && p.pct_change !== undefined) {
              const sign = p.pct_change > 0 ? '+' : '';
              const arrow = p.pct_change > 0 ? '↗' : (p.pct_change < 0 ? '↘' : '→');
              let badgeClass = 'mom-badge-neutral';
              if (p.pct_change > 0) {
                badgeClass = isExpense ? 'mom-badge-warn' : 'mom-badge-good';
              } else if (p.pct_change < 0) {
                badgeClass = isExpense ? 'mom-badge-good' : 'mom-badge-warn';
              }
              const prevFormatted = Math.round(p.prev_total || 0).toLocaleString('id-ID');
              momBadgeHtml = `<span class="mom-badge ${badgeClass}" title="Last month: Rp${prevFormatted}">${sign}${p.pct_change}% ${arrow}</span>`;
            }

            const row = document.createElement('div');
            row.className = 'cat-legend-item';
            row.innerHTML = `
              <div class="cat-legend-top">
                <div class="cat-legend-label">
                  <span class="cat-legend-dot" style="background:${p.color}"></span>
                  <span class="cat-legend-name">${p.label}</span>
                  <span class="cat-legend-pct">${pct}%</span>
                  ${momBadgeHtml}
                </div>
                <strong class="cat-legend-amt">Rp${Math.round(p.value).toLocaleString('id-ID')}</strong>
              </div>
              <div class="cat-pct-track">
                <div class="cat-pct-bar" style="width:${pct}%;background:${p.color}"></div>
              </div>
            `;
            legend.appendChild(row);
          });
        }
      }
    }

    if (tEl && trendDataEl) {
      let trend = [];
      try {
        trend = JSON.parse(trendDataEl.textContent);
        if (typeof trend === 'string') trend = JSON.parse(trend);
      } catch (e) {
        console.error('Failed to parse trend data', e);
      }
      if (Array.isArray(trend)) {
        const existingTrend = Chart.getChart(tEl);
        if (existingTrend) existingTrend.destroy();

        new Chart(tEl, {
          type: 'bar',
          data: {
            labels: trend.map(t => t.label),
            datasets: [
              {
                label: 'Income',
                data: trend.map(t => t.income !== undefined ? t.income : (t.value || 0)),
                backgroundColor: '#7BD3A4',
                borderRadius: 6,
                barPercentage: 0.8,
                categoryPercentage: 0.7,
              },
              {
                label: 'Expense',
                data: trend.map(t => t.expense !== undefined ? t.expense : (t.value || 0)),
                backgroundColor: '#FF8A65',
                borderRadius: 6,
                barPercentage: 0.8,
                categoryPercentage: 0.7,
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: function (ctx) {
                    const val = ctx.raw || 0;
                    const dsLabel = ctx.dataset.label;
                    return `${dsLabel}: Rp${Math.round(val).toLocaleString('id-ID')}`;
                  },
                  afterBody: function (items) {
                    if (!items.length) return '';
                    const idx = items[0].dataIndex;
                    const item = trend[idx] || {};
                    const net = item.net !== undefined ? item.net : 0;
                    const sign = net >= 0 ? '+' : '';
                    return `Net: ${sign}Rp${Math.round(net).toLocaleString('id-ID')} (${item.savings_rate || 0}% saved)`;
                  }
                }
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: {
                  color: textColor,
                  font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' }
                }
              },
              y: {
                beginAtZero: true,
                suggestedMax: 100000,
                grid: { color: gridColor },
                ticks: {
                  color: textColor,
                  font: { family: 'Plus Jakarta Sans', size: 11 },
                  callback: function (v) {
                    if (v >= 1000000) return (v / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
                    if (v >= 1000) return (v / 1000).toFixed(0) + 'k';
                    return v;
                  }
                }
              }
            }
          }
        });
      }
    }

    // ── Net Worth Line Chart (Monthly or Annual) ────────────────
    const nwEl = [document.getElementById('netWorthChartAnnual'), document.getElementById('netWorthChart')].find(el => el && el.isConnected)
      || document.getElementById('netWorthChartAnnual')
      || document.getElementById('netWorthChart');
    const nwDataEl = document.getElementById('net-worth-data');
    if (nwEl && nwDataEl) {
      let nwData = [];
      try {
        nwData = JSON.parse(nwDataEl.textContent);
        if (typeof nwData === 'string') nwData = JSON.parse(nwData);
      } catch (e) {
        console.error('Failed to parse net worth data', e);
      }

      if (Array.isArray(nwData) && nwData.length) {
        const existingNw = Chart.getChart(nwEl);
        if (existingNw) existingNw.destroy();

        const nwCtx = nwEl.getContext('2d');
        const nwGradient = nwCtx.createLinearGradient(0, 0, 0, 180);
        nwGradient.addColorStop(0, 'rgba(123, 211, 164, 0.40)');
        nwGradient.addColorStop(0.7, 'rgba(123, 211, 164, 0.12)');
        nwGradient.addColorStop(1, 'rgba(123, 211, 164, 0.00)');

        new Chart(nwEl, {
          type: 'line',
          data: {
            labels: nwData.map(d => d.short_label || d.label),
            datasets: [{
              label: 'Net Worth',
              data: nwData.map(d => d.net_worth),
              borderColor: '#7BD3A4',
              borderWidth: 2.5,
              backgroundColor: nwGradient,
              fill: true,
              tension: 0.35,
              pointRadius: 4,
              pointHoverRadius: 6,
              pointBackgroundColor: '#7BD3A4',
              pointBorderColor: isDark ? '#1e1e1d' : '#FFFFFF',
              pointBorderWidth: 2,
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
              intersect: false,
              mode: 'index',
            },
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  title: function(items) {
                    if (!items.length) return '';
                    const idx = items[0].dataIndex;
                    return nwData[idx]?.label || items[0].label;
                  },
                  label: function(ctx) {
                    const val = ctx.raw || 0;
                    return `Net Worth: Rp${Math.round(val).toLocaleString('id-ID')}`;
                  }
                }
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: {
                  color: textColor,
                  font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' }
                }
              },
              y: {
                beginAtZero: false,
                grace: '8%',
                grid: { color: gridColor },
                ticks: {
                  color: textColor,
                  font: { family: 'Plus Jakarta Sans', size: 11 },
                  callback: function(v) {
                    if (Math.abs(v) >= 1000000) return (v / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
                    if (Math.abs(v) >= 1000) return (v / 1000).toFixed(0) + 'k';
                    return v;
                  }
                }
              }
            }
          }
        });
      }
    }
  }
  window.wangMountGraphs = mountGraphs;

  // Delegated click handler
  document.addEventListener('click', (e) => {
    // Multi-filter trigger
    const filterTrigger = e.target.closest('#multi-filter-trigger');
    if (filterTrigger) {
      e.preventDefault();
      playSound('tap');
      openFilterSheet();
      return;
    }
    // Sound toggle
    const soundToggle = e.target.closest('#sound-toggle');
    if (soundToggle) {
      e.preventDefault();
      toggleSound();
      return;
    }

    // Theme toggle
    const themeToggle = e.target.closest('#theme-toggle');
    if (themeToggle) {
      e.preventDefault();
      playSound('click');
      toggleTheme();
      return;
    }

    // Password visibility toggle
    const pwdToggle = e.target.closest('#toggle-password');
    if (pwdToggle) {
      e.preventDefault();
      playSound('click');
      const pwdInput = document.getElementById('id_password');
      const icon = pwdToggle.querySelector('.icon, .material-symbols-rounded');
      if (pwdInput) {
        const isPwd = pwdInput.type === 'password';
        pwdInput.type = isPwd ? 'text' : 'password';
        if (icon) setSvgIcon(icon, isPwd ? 'visibility_off' : 'visibility');
        pwdToggle.setAttribute('aria-label', isPwd ? 'Hide password' : 'Show password');
      }
      return;
    }

    // Receipt photo badge lightbox open
    const receiptBadge = e.target.closest('.li-receipt-badge');
    if (receiptBadge) {
      e.stopPropagation();
      e.preventDefault();
      playSound('tap');
      const item = receiptBadge.closest('.list-item');
      const imgUrl = item && item.dataset.image;
      if (imgUrl) {
        const lb = document.getElementById('receipt-lightbox');
        const lbImg = document.getElementById('lightbox-img');
        if (lb && lbImg) {
          lbImg.src = imgUrl;
          lb.hidden = false;
        }
      }
      return;
    }

    // Lightbox modal close
    const lb = document.getElementById('receipt-lightbox');
    if (lb && !lb.hidden) {
      if (e.target.closest('#lightbox-close') || e.target === lb) {
        e.preventDefault();
        lb.hidden = true;
        return;
      }
    }

    // Detail sheet open
    const detailBtn = e.target.closest('.js-detail-tx');
    if (detailBtn) {
      e.preventDefault();
      playSound('click');
      openDetailSheet(detailBtn.dataset);
      return;
    }

    // Detail edit action button
    const detailEdit = e.target.closest('#dt-edit-btn');
    if (detailEdit) {
      e.preventDefault();
      playSound('click');
      const dataToEdit = activeDetailData;
      closeDetailSheet();
      if (dataToEdit && window.openEditTransaction) {
        window.openEditTransaction(dataToEdit);
      }
      return;
    }

    // Detail delete action button
    const detailDelete = e.target.closest('#dt-delete-btn');
    if (detailDelete) {
      e.preventDefault();
      playSound('click');
      const data = activeDetailData;
      if (!data || !data.deleteUrl) return;
      const preview = `${data.catName || 'Transaction'} · ${data.note || '-'} · ${data.formattedAmount || ('Rp' + data.amount)}`;
      openConfirmSheet({
        title: 'Delete Transaction?',
        desc: 'Are you sure you want to delete this transaction? This action cannot be undone.',
        preview: preview,
        actionUrl: data.deleteUrl,
        onConfirm: () => {
          closeDetailSheet();
        }
      });
      return;
    }

    // Detail close action button or backdrop
    if (e.target.closest('#detail-close-btn') || e.target.id === 'detail-overlay') {
      e.preventDefault();
      closeDetailSheet();
      return;
    }

    // Confirm sheet close action button, cancel button, or backdrop
    if (e.target.closest('#confirm-sheet-close, #confirm-sheet-cancel-btn') || e.target.id === 'confirm-sheet-overlay') {
      e.preventDefault();
      playSound('click');
      closeConfirmSheet();
      return;
    }

    // Detail receipt zoom thumbnail tap
    if (e.target.closest('#dt-receipt-thumb')) {
      e.preventDefault();
      playSound('tap');
      if (activeDetailData && activeDetailData.image) {
        const lb = document.getElementById('receipt-lightbox');
        const lbImg = document.getElementById('lightbox-img');
        if (lb && lbImg) {
          lbImg.src = activeDetailData.image;
          lb.hidden = false;
        }
      }
      return;
    }

    // Budget sheet open triggers
    if (e.target.closest('#budget-edit-trigger, #budget-empty-trigger, .budget-set-btn')) {
      e.preventDefault();
      playSound('click');
      openBudgetSheet();
      return;
    }

    // Budget sheet dismiss
    if (e.target.closest('#budget-cancel') || e.target.id === 'budget-overlay') {
      e.preventDefault();
      closeBudgetSheet();
      return;
    }

    // Budget preset chip tap
    const presetChip = e.target.closest('.budget-preset-chip');
    if (presetChip) {
      e.preventDefault();
      playSound('tap');
      const amt = presetChip.dataset.amt;
      const input = document.getElementById('budget-amount-input');
      if (input && amt) {
        input.value = amt;
      }
      return;
    }

    // Budget remove button
    if (e.target.closest('#budget-remove-btn')) {
      e.preventDefault();
      playSound('delete');
      const input = document.getElementById('budget-amount-input');
      const form = document.getElementById('budget-form');
      if (input && form) {
        input.value = '0';
        form.submit();
      }
      return;
    }

    const editBtn = e.target.closest('.js-edit-tx');
    if (editBtn) {
      e.preventDefault();
      playSound('click');
      if (window.openEditTransaction) {
        window.openEditTransaction(editBtn.dataset);
      }
      return;
    }


    // Keypad clicks (sound feedback)
    const keyBtn = e.target.closest('.key, .key-op, .key-clear, #key-del, .cat-cell, .picker-item');
    if (keyBtn) {
      playSound('tap');
    }

    // Quick filter chips click
    const qfChip = e.target.closest('.quick-filter-chip');
    if (qfChip) {
      playSound('click');
      const bar = qfChip.closest('.quick-filter-bar');
      if (bar) {
        bar.querySelectorAll('.quick-filter-chip').forEach(c => c.classList.remove('active'));
        qfChip.classList.add('active');
      }
      const filterInput = document.getElementById('search-filter-input');
      if (filterInput && qfChip.dataset.filter !== undefined) {
        filterInput.value = qfChip.dataset.filter;
      }
    }

    // Immediate active highlight on month chip click
    const monthChip = e.target.closest('.month-chip');
    if (monthChip) {
      playSound('click');
      const track = monthChip.closest('.month-scroll-track');
      if (track) {
        track.querySelectorAll('.month-chip').forEach(c => c.classList.remove('active'));
        monthChip.classList.add('active');
        monthChip.scrollIntoView({ inline: 'center', behavior: 'smooth', block: 'nearest' });
      }
      const searchMonthInput = document.getElementById('search-month-input');
      if (searchMonthInput && monthChip.dataset.month) {
        searchMonthInput.value = monthChip.dataset.month;
      }
    }

    // General tabs, color swatches, icon tiles, period switchers
    const clickSoundTarget = e.target.closest('.kind-tab, .sheet-tab, .cat-tab, .icon-cat-tab, .color-swatch-btn, .icon-tile, .month-scroll-arrow, .c-month-btn, .period-tab, .year-step-btn');
    if (clickSoundTarget) {
      playSound('click');
    }

    // Month Picker Popover trigger (compact month nav on dashboard)
    const monthTrigger = e.target.closest('#c-month-trigger');
    if (monthTrigger) {
      e.preventDefault();
      playSound('tap');
      toggleMonthPopover();
      return;
    }

    // Month popover backdrop click (dismiss)
    if (e.target.closest('#month-popover-backdrop')) {
      e.preventDefault();
      closeMonthPopover();
      return;
    }

    // Month popover year navigation (< or >)
    const yearPrev = e.target.closest('#m-year-prev');
    const yearNext = e.target.closest('#m-year-next');
    if (yearPrev || yearNext) {
      const btn = yearPrev || yearNext;
      if (btn.disabled || btn.classList.contains('disabled') || btn.getAttribute('aria-disabled') === 'true') {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      playSound('tap');
      stepPopoverYear(yearPrev ? -1 : 1);
      return;
    }

    // Month popover grid month button or today button
    const mGridBtn = e.target.closest('.m-grid-btn, .m-popover-today-btn');
    if (mGridBtn) {
      if (mGridBtn.classList.contains('disabled') || mGridBtn.getAttribute('aria-disabled') === 'true') {
        e.preventDefault();
        return;
      }
      playSound('tap');
      closeMonthPopover();
      // let navigation link proceed through Turbo frame
      return;
    }

    // Outside click dismiss for month popover
    const popoverEl = document.getElementById('month-popover');
    if (popoverEl && !popoverEl.hidden && !e.target.closest('#month-popover, #c-month-trigger')) {
      closeMonthPopover();
    }

    // Sheet delete action
    const deleteAction = e.target.closest('#sheet-delete-btn, .btn-delete');
    if (deleteAction) {
      playSound('delete');
    }

    // Optimistic highlight on bottom nav click
    const bnItem = e.target.closest('.bottomnav .bn-item');
    if (bnItem) {
      playSound('click');
      document.querySelectorAll('.bottomnav .bn-item').forEach(i => i.classList.remove('active'));
      bnItem.classList.add('active');
    }
  });

  // Handle frame loads for transaction history and graphs
  document.addEventListener('turbo:frame-load', (e) => {
    if (e.target.id === 'tx-history') {
      closeMonthPopover();
      initMonthScroll();
      checkAutoEdit();
    } else if (e.target.id === 'graphs-frame') {
      setTimeout(mountGraphs, 30);
      initMonthScroll();
    }
  });

  document.addEventListener('turbo:frame-render', (e) => {
    if (e.target.id === 'graphs-frame') {
      setTimeout(mountGraphs, 30);
    }
  });

  // Visual Icon & Color Swatch Picker
  function initIconPicker() {
    const suite = document.querySelector('.picker-suite');
    if (!suite) return;

    const iconInput = document.getElementById('id_icon');
    const colorInput = document.getElementById('id_color');
    const customColorInput = document.getElementById('custom-color-input');
    const previewIcon = document.getElementById('picker-preview-icon');
    const previewSymbol = document.getElementById('picker-preview-symbol');
    const previewTitle = document.getElementById('picker-preview-title');
    const nameInput = document.getElementById('id_name');
    const colorHexLabel = document.getElementById('picker-color-hex');
    const customIconBtn = document.getElementById('toggle-custom-icon-btn');
    const customIconField = document.getElementById('custom-icon-field');
    const catTabs = document.querySelectorAll('.icon-cat-tab');
    const searchInput = document.getElementById('icon-search-input');
    const searchClear = document.getElementById('icon-search-clear');
    const iconGrid = document.getElementById('icon-grid-picker');
    const iconTiles = document.querySelectorAll('.icon-tile');
    const searchEmpty = document.getElementById('icon-search-empty');

    function updatePreview(iconName, colorHex) {
      if (previewSymbol && iconName) {
        setSvgIcon(previewSymbol, iconName);
      }
      if (previewIcon && colorHex) {
        previewIcon.style.color = colorHex;
        previewIcon.style.backgroundColor = colorHex + '22';
      }
      if (colorHexLabel && colorHex) {
        colorHexLabel.textContent = colorHex.toUpperCase();
      }
      if (previewIcon) {
        previewIcon.style.transform = 'scale(1.12)';
        setTimeout(() => { previewIcon.style.transform = ''; }, 180);
      }
    }

    // 1. Initial State Sync
    const currentIcon = (iconInput && iconInput.value) || 'account_balance_wallet';
    const currentColor = (colorInput && colorInput.value) || '#FFB5A7';

    iconTiles.forEach(tile => {
      const match = tile.dataset.icon === currentIcon;
      tile.classList.toggle('selected', match);
    });

    let matchedSwatch = false;
    document.querySelectorAll('.color-swatch-btn[data-color]').forEach(btn => {
      const match = btn.dataset.color.toLowerCase() === currentColor.toLowerCase();
      btn.classList.toggle('active', match);
      if (match) matchedSwatch = true;
    });
    if (!matchedSwatch && customColorInput) {
      customColorInput.value = currentColor;
    }

    updatePreview(currentIcon, currentColor);

    // Live name input sync
    if (nameInput && !nameInput.dataset.pickerBound) {
      nameInput.dataset.pickerBound = '1';
      if (nameInput.value.trim() && previewTitle) {
        previewTitle.textContent = nameInput.value.trim();
      }
      nameInput.addEventListener('input', () => {
        if (previewTitle) {
          previewTitle.textContent = nameInput.value.trim() || 'Preview';
        }
      });
    }

    // 2. Swatch Click Listener
    const swatchContainer = document.getElementById('color-swatches');
    if (swatchContainer && !swatchContainer.dataset.bound) {
      swatchContainer.dataset.bound = '1';
      swatchContainer.addEventListener('click', (e) => {
        const btn = e.target.closest('.color-swatch-btn[data-color]');
        if (btn) {
          e.preventDefault();
          const hex = btn.dataset.color;
          if (colorInput) colorInput.value = hex;
          if (customColorInput) customColorInput.value = hex;
          document.querySelectorAll('.color-swatch-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          updatePreview(iconInput ? iconInput.value : null, hex);
        }
      });
    }

    // 3. Custom Color Input Listener
    if (customColorInput && !customColorInput.dataset.bound) {
      customColorInput.dataset.bound = '1';
      customColorInput.addEventListener('input', (e) => {
        const hex = e.target.value;
        if (colorInput) colorInput.value = hex;
        document.querySelectorAll('.color-swatch-btn[data-color]').forEach(b => b.classList.remove('active'));
        updatePreview(iconInput ? iconInput.value : null, hex);
      });
    }

    // 4. Icon Tile Click Listener
    if (iconGrid && !iconGrid.dataset.bound) {
      iconGrid.dataset.bound = '1';
      iconGrid.addEventListener('click', (e) => {
        const tile = e.target.closest('.icon-tile');
        if (tile) {
          e.preventDefault();
          const iconName = tile.dataset.icon;
          if (iconInput) iconInput.value = iconName;
          iconTiles.forEach(t => t.classList.remove('selected'));
          tile.classList.add('selected');
          updatePreview(iconName, colorInput ? colorInput.value : null);
        }
      });
    }

    // 5. Manual Custom Icon Field Toggle & Input Sync
    if (customIconBtn && !customIconBtn.dataset.bound) {
      customIconBtn.dataset.bound = '1';
      customIconBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (customIconField) {
          const isHidden = customIconField.style.display === 'none';
          customIconField.style.display = isHidden ? 'block' : 'none';
          customIconBtn.textContent = isHidden ? 'Hide manual input' : 'Manual input';
          if (isHidden && iconInput) iconInput.focus();
        }
      });
    }
    if (iconInput && !iconInput.dataset.bound) {
      iconInput.dataset.bound = '1';
      iconInput.addEventListener('input', () => {
        const val = iconInput.value.trim();
        updatePreview(val || 'help', colorInput ? colorInput.value : null);
        iconTiles.forEach(t => t.classList.toggle('selected', t.dataset.icon === val));
      });
    }

    // 6. Category Tabs Filter
    let activeCat = 'all';
    let searchQuery = '';

    function filterIcons() {
      let visibleCount = 0;
      const q = searchQuery.toLowerCase().trim();
      iconTiles.forEach(tile => {
        const catMatch = (activeCat === 'all') || (tile.dataset.cat === activeCat);
        const tags = (tile.dataset.tags || '') + ' ' + (tile.dataset.icon || '');
        const searchMatch = !q || tags.toLowerCase().includes(q);
        const show = catMatch && searchMatch;
        tile.style.display = show ? 'grid' : 'none';
        if (show) visibleCount++;
      });
      if (searchEmpty) {
        searchEmpty.style.display = visibleCount === 0 ? 'flex' : 'none';
      }
    }

    catTabs.forEach(tab => {
      tab.addEventListener('click', (e) => {
        e.preventDefault();
        catTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        activeCat = tab.dataset.cat || 'all';
        filterIcons();
      });
    });

    // 7. Search Input Filter
    if (searchInput && !searchInput.dataset.bound) {
      searchInput.dataset.bound = '1';
      searchInput.addEventListener('input', () => {
        searchQuery = searchInput.value;
        if (searchClear) {
          searchClear.style.display = searchQuery ? 'grid' : 'none';
        }
        filterIcons();
      });
    }
    if (searchClear && !searchClear.dataset.bound) {
      searchClear.dataset.bound = '1';
      searchClear.addEventListener('click', (e) => {
        e.preventDefault();
        if (searchInput) {
          searchInput.value = '';
          searchQuery = '';
          searchClear.style.display = 'none';
          filterIcons();
          searchInput.focus();
        }
      });
    }
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const confirmOpen = document.getElementById('confirm-sheet')?.classList.contains('open');
      if (confirmOpen) {
        closeConfirmSheet();
        return;
      }
      closeSheet();
      closeDetailSheet();
      closeBudgetSheet();
      closeMonthPopover();
    }
  });

  document.addEventListener('turbo:load', () => {
    syncAppbar();
    syncThemeUI();
    syncSoundUI();
    syncBottomNav();
    syncBalancePrivacy();
    bindSheet();
    initMonthScroll();
    checkAutoEdit();
    mountGraphs();
    initIconPicker();
    initToasts();
    resolveExternalIcons();
  });
  document.addEventListener('turbo:render', () => {
    syncAppbar();
    syncThemeUI();
    syncSoundUI();
    syncBottomNav();
    syncBalancePrivacy();
    bindSheet();
    resetOverlays();
    initMonthScroll();
    checkAutoEdit();
    mountGraphs();
    initIconPicker();
    initToasts();
    resolveExternalIcons();
    if (window.wangRefreshWallets) window.wangRefreshWallets();
  });

  // Enter animation after every Turbo content swap (works across Blink, Gecko, and iOS WebKit)
  function triggerPageEnterAnimation() {
    const main = document.querySelector('main.content');
    if (!main) return;
    if (!main.classList.contains('turbo-enter')) {
      main.classList.add('turbo-enter');
    }
  }
  document.addEventListener('turbo:render', triggerPageEnterAnimation);


  // Turbo progress bar tuning (50ms for instant visual feedback on mobile tap)
  function initTurboSettings() {
    if (window.Turbo && typeof window.Turbo.setProgressBarDelay === 'function') {
      try {
        window.Turbo.setProgressBarDelay(50);
      } catch (e) { }
    }
  }

  function preloadNavLink(link) {
    if (!link || !link.href) return;
    if (window.Turbo && window.Turbo.session && window.Turbo.session.preloader) {
      try {
        window.Turbo.session.preloader.preloadURL(link);
      } catch (e) { }
    }
  }

  // Instant preload on pointerdown (fires the exact millisecond the finger touches the screen, 150-300ms before click)
  document.addEventListener('pointerdown', (e) => {
    const link = e.target.closest('.bottomnav .bn-item, a[data-turbo-preload]');
    if (link) {
      preloadNavLink(link);
    }
  }, { passive: true });

  // ── PWA Service Worker & Offline Connectivity ─────────────
  function initServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js', { scope: '/' })
          .then((reg) => {
            reg.update().catch(() => {});
          })
          .catch((err) => {
            console.warn('[SW] Registration failed:', err);
          });
      });
    }
  }

  // ── Unified Floating Toast Notification System ───────────
  function getToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      container.setAttribute('aria-live', 'polite');
      const phone = document.querySelector('.phone') || document.body;
      phone.appendChild(container);
    }
    return container;
  }

  function showToast(message, type = 'success', duration = 3200) {
    const container = getToastContainer();
    const pill = document.createElement('div');
    pill.className = `toast-pill toast-${type}`;
    pill.setAttribute('role', 'status');

    let iconName = 'info';
    if (type === 'success') iconName = 'check_circle';
    else if (type === 'error' || type === 'danger') iconName = 'error';
    else if (type === 'warning') iconName = 'warning';
    else if (type === 'online') iconName = 'cloud_done';
    else if (type === 'offline') iconName = 'cloud_off';

    pill.innerHTML = `<svg class="icon"><use href="#icon-${iconName}"></use></svg><span class="toast-msg">${message}</span>`;
    container.appendChild(pill);

    requestAnimationFrame(() => {
      pill.classList.add('show');
    });

    if (type === 'success' || type === 'online') playSound('chime');
    else if (type === 'error' || type === 'danger' || type === 'offline') playSound('knock');
    else playSound('tap');

    const dismiss = () => {
      pill.classList.remove('show');
      setTimeout(() => {
        if (pill.parentNode) pill.parentNode.removeChild(pill);
      }, 350);
    };

    pill.addEventListener('click', () => {
      playSound('click');
      dismiss();
    });

    if (duration > 0) {
      setTimeout(dismiss, duration);
    }
    return pill;
  }
  window.showToast = showToast;

  function initToasts() {
    const pills = document.querySelectorAll('.toast-pill:not(.toast-init)');
    pills.forEach((pill, idx) => {
      pill.classList.add('toast-init');
      setTimeout(() => {
        pill.classList.add('show');
        if (pill.classList.contains('toast-success')) playSound('chime');
        else if (pill.classList.contains('toast-error') || pill.classList.contains('toast-danger')) playSound('knock');
        else playSound('tap');
      }, 80 + idx * 90);

      const dismiss = () => {
        pill.classList.remove('show');
        setTimeout(() => {
          if (pill.parentNode) pill.parentNode.removeChild(pill);
        }, 350);
      };

      pill.addEventListener('click', () => {
        playSound('click');
        dismiss();
      });

      setTimeout(dismiss, 3200 + idx * 300);
    });
  }

  let activeOfflineToast = null;
  function initConnectivityListeners() {
    window.addEventListener('online', () => {
      if (activeOfflineToast) {
        activeOfflineToast.classList.remove('show');
        setTimeout(() => {
          if (activeOfflineToast && activeOfflineToast.parentNode) {
            activeOfflineToast.parentNode.removeChild(activeOfflineToast);
          }
          activeOfflineToast = null;
        }, 350);
      }
      showToast('Back online', 'online', 2500);
    });
    window.addEventListener('offline', () => {
      activeOfflineToast = showToast('Offline mode — viewing saved data', 'offline', 0);
    });
  }

  initTurboSettings();
  initServiceWorker();
  initConnectivityListeners();
  initToasts();
  syncAppbar();
  syncThemeUI();
  syncSoundUI();
  syncBottomNav();
  syncBalancePrivacy();
  bindSheet();
  initMonthScroll();
  checkAutoEdit();
  mountGraphs();
  initIconPicker();
  resolveExternalIcons();
})();

