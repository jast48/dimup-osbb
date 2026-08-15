// Initialize Telegram WebApp
const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
}

function switchTab(tabId, element) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Remove active state from nav buttons
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Show target tab
    const target = document.getElementById(tabId);
    if (target) {
        target.classList.add('active');
    }

    // Highlight current nav button
    if (element) {
        element.classList.add('active');
    }
}

function handlePayment() {
    if (tg) {
        tg.showPopup({
            title: '💳 Оплата нарахувань',
            message: 'Перехід до платіжного шлюзу (LiqPay / Monobank). Для тесту рахунок сплачено!',
            buttons: [{ type: 'ok' }]
        });
    } else {
        alert('Перехід до платіжного шлюзу (LiqPay / Monobank)');
    }
}
