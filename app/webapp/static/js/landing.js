document.addEventListener('DOMContentLoaded', () => {
  // 1. Header scroll blur effect
  const header = document.querySelector('.header');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 40) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  });

  // 2. Interactive Telegram Bot Simulator
  const simData = {
    concierge: {
      title: "🤖 AI-Консьєрж DimUp",
      messages: [
        { type: "user", text: "Добрий день! Коли у нас вивозять великогабаритне сміття і чи можна робити ремонт у суботу?" },
        { 
          type: "bot", 
          text: "🤖 <b>AI-Консьєрж:</b><br>Вітаю! Згідно з регламентом нашого будинку:<br>• <b>Вивіз великогабаритного сміття:</b> щовівторка та щоп'ятниці з 09:00.<br>• <b>Режим тиші:</b> шумні ремонтні роботи у вихідні (субота/неділя) суворо заборонені статутом ОСББ.<br><br><i>Чи бажаєте зареєструвати звернення до правління?</i>",
          buttons: ["📝 Подати заявку", "❓ Задати інше питання"]
        }
      ]
    },
    ticket: {
      title: "🔧 AI-Диспетчерська та Голосові Заявки",
      messages: [
        { type: "user", text: "🎙 <i>Голосове повідомлення (0:08): «На 3 поверсі у 2 під'їзді блимає лампа і капає з труби»</i>" },
        { 
          type: "bot", 
          text: "🤖 <b>DimUp AI розпізнав заявку:</b><br><div class='tg-card-box'>🚨 <b>Срочність:</b> 🟡 Звичайна<br>📂 <b>Категорія:</b> 💡 Електрика та 🚰 Сантехніка<br>📍 <b>Локація:</b> Під'їзд №2, поверх 3<br>💡 <b>AI порада:</b> Потрібна заміна LED-лампи 12W та огляд стику труби.</div><b>Заявку №104 передано черговому майстру будинку!</b>",
          buttons: ["👷‍♂️ Призначити майстра", "✅ Взяти в роботу"]
        }
      ]
    },
    marketplace: {
      title: "🛠 Маркетплейс та Підрядники",
      messages: [
        { type: "user", text: "🛠 Замовити послугу: <b>«Встановлення та заміна змішувача»</b> на 18:00" },
        { 
          type: "bot", 
          text: "🎉 <b>Замовлення №0042 прийнято!</b><br><div class='tg-card-box'>👷‍♂️ <b>Майстер:</b> Сергій Мельник (⭐ 4.95)<br>⏰ <b>Час візиту:</b> Сьогодні о 18:00<br>💰 <b>Орієнтовно:</b> від 450 грн<br>📱 <b>Контакт:</b> +380 (67) 123-45-67</div><i>Майстер підтвердив візит та прямує до вас.</i>",
          buttons: ["💬 Написати майстру", "❌ Скасувати"]
        }
      ]
    },
    payment: {
      title: "💳 Єдиний Комунальний Хаб та 1-Click Оплата",
      messages: [
        { type: "user", text: "📊 Показати всі мої рахунки та квитанції за цей місяць (Кв. №45)" },
        { 
          type: "bot", 
          text: "🏛 <b>Єдина комунальна квитанція міста за серпень 2026:</b><br><div class='tg-card-box'>🏢 <b>Утримання будинку (ОСББ):</b> 640.00 грн<br>⚡️ <b>Світло (ДТЕК / Yasno):</b> 412.50 грн<br>💧 <b>Водоканал:</b> 230.10 грн<br>🔥 <b>Газ (Нафтогаз):</b> 185.00 грн<br>🌡 <b>Теплоенерго:</b> 840.00 грн<br>━━━━━━━━━━━━━<br>💳 <b>Разом до сплати:</b> <b>2 307.60 грн</b></div><i>Усі платіжки міста зібрані автоматично! Сплачуйте без комісій в один дотик через Apple Pay / Google Pay / карткою.</i>",
          buttons: ["⚡️ Сплатити все (2 307.60 грн)", "📄 Завантажити єдину PDF-квитанцію"]
        }
      ]
    }
  };

  const simChat = document.getElementById('simChat');
  const simTitle = document.getElementById('simTitle');
  const tabButtons = document.querySelectorAll('.sim-tab-btn');

  function renderSimScene(sceneKey) {
    const scene = simData[sceneKey];
    if (!scene) return;

    simTitle.textContent = scene.title;
    simChat.innerHTML = '';

    scene.messages.forEach((msg, idx) => {
      setTimeout(() => {
        const msgEl = document.createElement('div');
        msgEl.className = `tg-msg ${msg.type === 'user' ? 'tg-msg-user' : 'tg-msg-bot'}`;
        
        let html = msg.text;
        if (msg.buttons && msg.buttons.length) {
          html += '<div class="tg-btn-row">';
          msg.buttons.forEach(btnText => {
            html += `<div class="tg-inline-btn">${btnText}</div>`;
          });
          html += '</div>';
        }
        msgEl.innerHTML = html;
        simChat.appendChild(msgEl);
        simChat.scrollTop = simChat.scrollHeight;
      }, idx * 250);
    });
  }

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const sceneKey = btn.getAttribute('data-scene');
      renderSimScene(sceneKey);
    });
  });

  // Initial simulator render
  renderSimScene('concierge');

  // 3. Interactive ROI & Economy Calculator
  const aptSlider = document.getElementById('aptSlider');
  const tariffSlider = document.getElementById('tariffSlider');
  
  const aptVal = document.getElementById('aptVal');
  const tariffVal = document.getElementById('tariffVal');
  
  const resHours = document.getElementById('resHours');
  const resDebt = document.getElementById('resDebt');
  const resPayback = document.getElementById('resPayback');

  function updateCalculator() {
    const apts = parseInt(aptSlider.value, 10);
    const tariff = parseFloat(tariffSlider.value);

    aptVal.textContent = `${apts} кв.`;
    tariffVal.textContent = `${tariff} грн/м²`;

    // Formulas based on OSBB statistics:
    // Chairman saves ~0.45 hrs per apartment/month on calls, tickets, meters & polls
    const savedHours = Math.round(apts * 0.42);
    // Debt reduction: on average 15% debt reduction from 60m2 avg apt over 12 months
    const annualDebtReduction = Math.round(apts * 60 * tariff * 0.12 * 12);
    // Payback period
    const paybackText = apts > 80 ? "Миттєва (1-й тиждень)" : "1-й місяць";

    resHours.textContent = `~${savedHours} год/міс`;
    resDebt.textContent = `${annualDebtReduction.toLocaleString('uk-UA')} грн/рік`;
    resPayback.textContent = paybackText;
  }

  if (aptSlider && tariffSlider) {
    aptSlider.addEventListener('input', updateCalculator);
    tariffSlider.addEventListener('input', updateCalculator);
    updateCalculator();
  }

  // 4. Marketplace Category Filter
  const mktFilterBtns = document.querySelectorAll('.mkt-filter-btn');
  const mktCards = document.querySelectorAll('.mkt-card');

  mktFilterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      mktFilterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cat = btn.getAttribute('data-cat');

      mktCards.forEach(card => {
        const cardCat = card.getAttribute('data-cat');
        if (cat === 'all' || cardCat === cat) {
          card.style.display = 'flex';
        } else {
          card.style.display = 'none';
        }
      });
    });
  });

  // 5. FAQ Accordion
  const faqQuestions = document.querySelectorAll('.faq-question');
  faqQuestions.forEach(q => {
    q.addEventListener('click', () => {
      const item = q.parentElement;
      const isOpen = item.classList.contains('open');
      
      // Close all others
      document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
      
      if (!isOpen) {
        item.classList.add('open');
      }
    });
  });

  // 6. Lead Registration Form Handler
  const leadForm = document.getElementById('leadForm');
  const formSuccess = document.getElementById('formSuccess');

  if (leadForm) {
    leadForm.addEventListener('submit', (e) => {
      e.preventDefault();

      const osbbName = document.getElementById('osbbName').value.trim();
      const osbbCity = document.getElementById('osbbCity').value.trim();
      const osbbApts = document.getElementById('osbbApts').value.trim();
      const contactName = document.getElementById('contactName').value.trim();
      const contactPhone = document.getElementById('contactPhone').value.trim();

      // Show success message
      if (formSuccess) {
        formSuccess.style.display = 'block';
        formSuccess.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      // Compose Telegram text with lead info
      const text = encodeURIComponent(
        `👋 Нова заявка на підключення ОСББ (100 грн):\n` +
        `🏢 ОСББ/Адреса: ${osbbName}\n` +
        `📍 Місто: ${osbbCity}\n` +
        `🚪 Квартир: ${osbbApts}\n` +
        `👤 Контакт: ${contactName}\n` +
        `📞 Телефон: ${contactPhone}`
      );

      // Open manager Telegram after a brief moment
      setTimeout(() => {
        window.open(`https://t.me/managerAndrii?text=${text}`, '_blank');
      }, 800);
    });
  }
});

