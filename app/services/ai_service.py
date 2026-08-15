import json
import logging
from typing import Optional, Dict, Any
import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)

if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    genai.configure(api_key=settings.GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    gemini_model = None


class AIService:
    """Сервис для интеграции с Google Gemini AI (текст, фото, аудио)"""

    @staticmethod
    async def classify_ticket(
        description: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        image_mime_type: Optional[str] = "image/jpeg",
        audio_bytes: Optional[bytes] = None,
        audio_mime_type: Optional[str] = "audio/ogg"
    ) -> Dict[str, Any]:
        """
        Анализирует текст, фото или голосовое аудиосообщение жильца.
        Возвращает структурированный JSON с категорией, срочностью, текстом и советом.
        """
        if not gemini_model:
            logger.warning("Gemini API key is not set, using fallback classification.")
            return AIService._fallback_classification(description or "Голосова заявка")

        prompt = f"""
Ти — розумний AI-диспетчер багатоквартирного будинку (ОСББ) системи DimUp.
Проаналізуй звернення мешканця (текст, аудіо-запис голосу або фото):

Текст заявки (якщо надано): "{description or ''}"

Твоє завдання:
1. Якщо надано аудіо (голосове повідомлення) — розпізнай та точно транскрибуй мову мешканця українською мовою.
2. Визначити категорію поломки:
   - plumbing (сантехніка, труби, протікання, вода, каналізація)
   - electricity (електрика, світло, щитова, проводка, розетки)
   - elevator (ліфт, застряг ліфт, кнопка)
   - cleaning (прибирання, сміття, під'їзд)
   - security (домофон, ворота, шлагбаум, замки, безпека)
   - roof_facade (дах, балкон, фасад, підвал)
   - other (інше)
3. Визначити терміновість:
   - emergency (критична/аварійна ситуація: прорив труби, затоплення, іскріння, застряглі люди)
   - normal (звичайна заявка)
   - low (нетерміново / косметичні питання)
4. Сформулювати повний зрозумілий текст проблеми (якщо було аудіо — розпізнаний текст, якщо текст — оригінал).
5. Сформулювати коротку назву заявки (3-6 слів) українською мовою.
6. Надати коротку, практичну та ввічливу першу пораду мешканцю (1-2 речення).

Відповідь надай ВИКЛЮЧНО у валідному JSON форматі:
{{
  "recognized_text": "Розпізнаний текст звернення мешканця",
  "category": "plumbing" | "electricity" | "elevator" | "cleaning" | "security" | "roof_facade" | "other",
  "urgency": "emergency" | "normal" | "low",
  "title": "Коротка назва",
  "recommended_action": "Порада мешканцю"
}}
"""
        try:
            content_parts = [prompt]
            if audio_bytes:
                content_parts.append({
                    "mime_type": audio_mime_type,
                    "data": audio_bytes
                })
            if image_bytes:
                content_parts.append({
                    "mime_type": image_mime_type,
                    "data": image_bytes
                })

            response = gemini_model.generate_content(
                content_parts,
                generation_config={"response_mime_type": "application/json"}
            )
            data = json.loads(response.text)
            return data
        except Exception as e:
            logger.error(f"Error during Gemini classification: {e}")
            return AIService._fallback_classification(description or "Звернення мешканця")

    @staticmethod
    async def ask_concierge(question: str, resident_name: str = "Мешканець") -> str:
        """
        AI-Консьерж 24/7: отвечает на вопросы жителя по правилам и жизни дома.
        """
        if not gemini_model:
            return "🤖 AI-Консьєрж зараз налаштовується."

        knowledge_base = """
Інформація про наш будинок ОСББ:
- Голова ОСББ: Коваленко Олександр Іванович, тел: +380 (67) 123-45-67 (пн-пт з 09:00 до 18:00).
- Аварійна служба міста (Водоканал/Тепло): 1557 або +380 (44) 200-00-00 (цілодобово).
- Черговий електрик/сантехнік: Сергій, тел: +380 (50) 987-65-43.
- Вивіз сміття: щоденно о 07:00 ранку. Великогабаритне сміття вивозиться по четвергах.
- Режим тиші в будинку: з 22:00 до 08:00 у будні, а будівельні шумні роботи дозволені тільки з 10:00 до 18:00 (у неділю шуміти заборонено).
- Тариф на утримання будинку: 8.50 грн за 1 кв. метр.
"""
        prompt = f"""
Ти — доброзичливий та компетентний AI-Консьєрж житлового будинку ОСББ (система DimUp).
Звернення від мешканця: {resident_name}.
Питання: "{question}"

База знань будинку:
{knowledge_base}

Інструкція:
- Відповідай ввічливо, коротко та по суті українською мовою.
"""
        try:
            response = gemini_model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error in ask_concierge: {e}")
            return "Вибачте, сталася тимчасова помилка при обробці запиту."

    @staticmethod
    def _fallback_classification(description: str) -> Dict[str, Any]:
        desc_lower = description.lower()
        category = "other"
        urgency = "normal"

        if any(w in desc_lower for w in ["вода", "тече", "кран", "труб", "капає", "затоп", "туалет", "бачок", "каналізац"]):
            category = "plumbing"
            if any(w in desc_lower for w in ["тече", "прорив", "затоп", "фонтан"]):
                urgency = "emergency"
        elif any(w in desc_lower for w in ["світло", "іскр", "проводк", "лампа", "щит", "розетк"]):
            category = "electricity"
            if any(w in desc_lower for w in ["іскр", "горить", "дим"]):
                urgency = "emergency"
        elif any(w in desc_lower for w in ["ліфт", "застряг"]):
            category = "elevator"
            if "застряг" in desc_lower:
                urgency = "emergency"
        elif any(w in desc_lower for w in ["смітт", "прибиран"]):
            category = "cleaning"

        return {
            "recognized_text": description,
            "category": category,
            "urgency": urgency,
            "title": f"Заявка: {description[:30]}...",
            "recommended_action": "Заявку прийнято та передано спеціалісту."
        }
