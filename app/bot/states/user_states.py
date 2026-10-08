from aiogram.fsm.state import State, StatesGroup

class RegistrationState(StatesGroup):
    """Состояния процесса регистрации нового жильца"""
    waiting_for_apartment = State()
    waiting_for_full_name = State()
    waiting_for_phone = State()

class TicketState(StatesGroup):
    """Состояния создания заявки на ремонт"""
    waiting_for_description = State()
    waiting_for_photo = State()
    confirming_ticket = State()

class ConciergeState(StatesGroup):
    """Состояние общения с AI-Консьержем"""
    in_dialog = State()

class MeterReadingState(StatesGroup):
    """Состояния передачи показаний счетчиков"""
    waiting_for_cold_water = State()
    waiting_for_hot_water = State()
    waiting_for_electricity = State()

class AdminBroadcastState(StatesGroup):
    """Состояние создания массовой рассылки правлением"""
    waiting_for_text = State()
    waiting_for_confirmation = State()

class AdminPollState(StatesGroup):
    """Состояние создания голосования"""
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_options = State()

class AdminPollEditState(StatesGroup):
    """Состояние редактирования опроса"""
    waiting_for_title = State()
    waiting_for_description = State()

class AdminBillState(StatesGroup):
    """Состояние выставления счета для одной квартиры"""
    waiting_for_apt_number = State()
    waiting_for_description = State()
    waiting_for_amount = State()

class AdminSplitBillState(StatesGroup):
    """Состояние распределения счета на ВСЕ квартиры дома"""
    waiting_for_purpose = State()
    waiting_for_split_type = State()
    waiting_for_amount = State()

class UtilityAccountState(StatesGroup):
    """Состояния привязки и управления лицевыми счетами коммуналки"""
    waiting_for_provider = State()
    waiting_for_account_number = State()

class UtilityWizardState(StatesGroup):
    """Пошаговый мастер-опросник заполнения всех лицевых счетов"""
    waiting_for_electricity = State()
    waiting_for_gas = State()
    waiting_for_water = State()
    waiting_for_heating = State()

class ContractorRegistrationState(StatesGroup):
    """Состояния регистрации подрядчика / мастера"""
    waiting_for_category = State()
    waiting_for_full_name = State()
    waiting_for_company = State()
    waiting_for_phone = State()

class MarketplaceOrderState(StatesGroup):
    """Состояния оформления заказа услуги жильцом"""
    waiting_for_time = State()
    waiting_for_comment = State()

class MeterPhotoOCRState(StatesGroup):
    """Стан розпізнавання лічильника по фото через AI Vision"""
    waiting_for_meter_type = State()
    waiting_for_photo = State()
    confirming_reading = State()

class AdminBankSyncState(StatesGroup):
    """Стан завантаження та імпорту банківської виписки"""
    waiting_for_file = State()

class AdminDebtNoticeState(StatesGroup):
    """Стан формування досудової претензії до боржника"""
    waiting_for_apartment = State()

class OfficialCertificateState(StatesGroup):
    """Стан замовлення офіційної довідки мешканцем"""
    waiting_for_type = State()

class AdminAIBroadcastState(StatesGroup):
    """Стан створення розумної розсилки з AI-покращенням"""
    waiting_for_draft = State()
    waiting_for_target = State()
    confirming = State()

