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
