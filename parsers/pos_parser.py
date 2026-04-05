import re
import os
import logging
from typing import Dict, Optional

import easyocr
from PIL import Image, ImageEnhance, ImageOps

from models import POSReport

logger = logging.getLogger(__name__)


class POSParser:
    _easyocr_reader = None

    # Ultra-resilient patterns that cover ALL observed OCR errors
    PATTERNS = {
        # Total: "Общая выручка" variations
        "total": (
            r"(?:"
            r"[©@ОоO0a]?[\s-]*"
            r'(?:общ|бщая|ОаЩая|Ощая|О[""]Цая|ОшШяя|Общап|ыручк|пырук|выручк|выру)[аяиы]+'
            r"|Итого за смену"
            r"|Итого"
            r"|Оощяя"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Game time: "Пополнение аккаунтов" variations
        "game_time": (
            r"(?:"
            r"П[оа]полн[еи]н[ие]е"
            r"|Псп[оа]лненк[еи]"
            r"|Пополнение"
            r"|Паполнение"
            r"|Пололнение"
            r"|Поп[ао]лнение"
            r"|Аккаунты"
            r")\s+аккаунтов\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Bar: "Еда" variations
        "bar": (
            r"(?:"
            r"Еда"
            r"|Бар"
            r"|Ед[ауы]"
            r"|\[да"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Cash: "Нал/Безнал" - first number
        "cash": (
            r"(?:"
            r"Нал[./]Безна[ял]"
            r"|Нал[./]Безнал"
            r"|Наличные"
            r"|Haп/Беэнал"
            r"|Нап/Безнал"
            r"|H:WБезнал"
            r"|НапБенл"
            r"|ОПБ\d"
            r"|[Оо]ПБ[5S]"
            r")\s*[-=]?\s*(\d[\d\s]*)\s*[₽РPрpоО]?\s*(\d+)"
        ),
        # Cashless: "Нал/Безнал" - second number
        "cashless": (
            r"(?:"
            r"Нал[./]Безна[ял]"
            r"|Нал[./]Безнал"
            r"|Наличные"
            r"|Haп/Беэнал"
            r"|Нап/Безнал"
            r"|H:WБезнал"
            r"|НапБенл"
            r"|ОПБ\d"
            r"|[Оо]ПБ[5S]"
            r")\s*[-=]?\s*\d[\d\s]*\s*[₽РPрpоО]?\s*(\d+)"
        ),
        # SBP variations
        "sbp": (
            r"(?:"
            r"Планшет\s+СБП"
            r"|Планшет\s+CBN"
            r"|Планшет\s+CEN"
            r"|Планшет\s+СБЛ"
            r"|Планшот\s+СБП"
            r"|Планшот\s+CBN"
            r"|Планшот\s+CEN"
            r"|Ппяншет\s+СБП"
            r"|СБП"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Acquiring
        "acquiring": r"(?:Эквайринг)\s*[-=]?\s*(\d[\d\s]*|\d+)",
        # Services variations
        "services": (
            r"(?:"
            r"Услуги"
            r"|Усл[уиыы]п?[иы]?"
            r"|УСлу:и"
            r"|Усл}ти"
            r"|Услуни"
            r"|Услути"
            r"|Прочие доходы"
            r"|Прачие\s+дох[Оо]ды"
            r"|Прочив доходы"
            r"|Прэчие доходы"
            r"|Прэчис доход"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Returns
        "return_cash": r"(?:Возврат нал|Возврат нал\.|Возврат наличных)\s*[-=]?\s*(\d[\d\s]*|\d+)",
        "return_cashless": r"(?:Возврат безнал|Возврат безнал\.|Возврат безналичных)\s*[-=]?\s*(\d[\d\s]*|\d+)",
        # Cash income variations
        "cash_income": (
            r"(?:"
            r"Приход"
            r"|Сумма онлайн-платежей"
            r"|Сумма\s+онлайн-платеж[ей]"
            r"|Сумиа онлайн-платежей"
            r"|Сумма\s+онлаин-платежей"
            r"|Сушша\s+онлайн-платежей"
            r"|Приход"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Cash expense variations
        "cash_expense": (
            r"(?:"
            r"Расходы за смену"
            r"|Расход"
            r"|Раскады"
            r"|Раскоды"
            r"|Расхоны"
            r"|Расходы за с[еэи]ну"
            r"|Расходы за см[ео]ну"
            r"|Расходы за сш[еи]ну"
            r"|Расходы за сш[еэи]у"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Envelope variations
        "envelope": (
            r"(?:"
            r"Инкассация"
            r"|В конверт"
            r"|Инкисскция"
            r"|Инивссьря"
            r"|Инкасстия"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
        # Cash remainder - ULTRA RESILIENT
        "cash_remainder": (
            r"(?:"
            r"Ha конец см[еёэюы]ны"
            r"|Ha конец ск[еёэюы]ны"
            r"|Ha конец сп[еёэюы]ны"
            r"|Ha конец си[еёэюы]ны"
            r"|На конец с[мкпи][еёюы][нп][а-яёы]"
            r"|Остаток в кассе"
            r"|Наканац"
            r"|На начало смены"
            r"|На начапо смены"
            r"|Нз налало скены"
            r")\s*[-=]?\s*(\d[\d\s]*|\d+)"
        ),
    }

    # Ultra-resilient zero patterns
    ZERO_PATTERNS = {
        "sbp": (
            r"(?:"
            r"Планшет\s+СБП"
            r"|Планшет\s+CBN"
            r"|Планшет\s+CEN"
            r"|Планшет\s+СБЛ"
            r"|Планшот\s+СБП"
            r"|Планшот\s+CBN"
            r"|Планшот\s+CEN"
            r"|Ппяншет\s+СБП"
            r"|СБП"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "services": (
            r"(?:"
            r"Услуги"
            r"|Усл[уиы]п?и?"
            r"|УСлу:и"
            r"|Усл}ти"
            r"|Прочие доходы"
            r"|Прачие\s+дох[Оо]ды"
            r"|Прочив доходы"
            r"|Прэчие доходы"
            r"|Прэчис доход"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "cash_expense": (
            r"(?:"
            r"Расходы за смену"
            r"|Расход"
            r"|Раскады"
            r"|Раскоды"
            r"|Расхоны"
            r"|Расходы за с[еэи]ну"
            r"|Расходы за см[ео]ну"
            r"|Расходы за сш[еи]ну"
            r"|Расходы за сш[еэи]у"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "envelope": (
            r"(?:"
            r"Инкассация"
            r"|В конверт"
            r"|Инкисскция"
            r"|Инивссьря"
            r"|Инкасстия"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "cash_remainder": (
            r"(?:"
            r"Ha конец см[еёэюы]ны"
            r"|Ha конец ск[еёэюы]ны"
            r"|Ha конец сп[еёэюы]ны"
            r"|На конец с[мкп][еёюы][нп][а-яёы]"
            r"|Остаток в кассе"
            r"|Наканац"
            r"|На начало смены"
            r"|На начапо смены"
            r"|Нз налало скены"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "bar": (
            r"(?:"
            r"Еда"
            r"|Бар"
            r"|Ед[ауы]"
            r"|\[да"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "game_time": (
            r"(?:"
            r"П[оа]полн[еи]н[ие]е"
            r"|Псп[оа]лненк[еи]"
            r"|Пополнение"
            r"|Паполнение"
            r"|Пололнение"
            r"|Поп[ао]лнение"
            r"|Аккаунты"
            r")\s+аккаунтов\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "acquiring": r"(?:Эквайринг)\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)",
        "return_cash": r"(?:Возврат нал|Возврат нал\.|Возврат наличных)\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)",
        "return_cashless": r"(?:Возврат безнал|Возврат безнал\.|Возврат безналичных)\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)",
        "cash_income": (
            r"(?:"
            r"Приход"
            r"|Сумма онлайн-платежей"
            r"|Сумма\s+онлайн-платеж[ей]"
            r"|Сумиа онлайн-платежей"
            r"|Сушша\s+онлайн-платежей"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
        "total": (
            r"(?:"
            r"[©@ОоO0a]?[\s-]*"
            r'(?:общ|бщая|ОаЩая|Ощая|О[""]Цая|ОшШяя|Общап|ыручк|пырук|выручк|выру)[аяиы]+'
            r"|Итого за смену"
            r"|Итого"
            r"|Оощяя"
            r")\s*[-=]?\s*(?:[0Oo][РPp]|[Оо][Рр]|0₽)"
        ),
    }

    @classmethod
    def get_easyocr_reader(cls):
        if cls._easyocr_reader is None:
            logger.info("🔄 Initializing EasyOCR reader (this may take a moment)...")
            cls._easyocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
            logger.info("✅ EasyOCR reader initialized")
        return cls._easyocr_reader

    @classmethod
    def extract_text_from_image(cls, image_path: str) -> str:
        try:
            image = Image.open(image_path)

            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Pass 0: Upscaled version with better quality
            img0 = image.copy()
            original_width, original_height = img0.size
            img0 = img0.resize((original_width * 4, original_height * 4), Image.LANCZOS)
            temp_path0 = image_path + "_pass0.jpg"
            img0_rgb = img0.convert('RGB')
            img0_rgb.save(temp_path0, quality=95)
            text0 = cls._extract_with_easyocr(temp_path0)

            # Pass 1: High contrast version
            img1 = image.copy()
            enhancer = ImageEnhance.Contrast(img1)
            img1 = enhancer.enhance(3.0)
            enhancer = ImageEnhance.Brightness(img1)
            img1 = enhancer.enhance(2.0)
            enhancer = ImageEnhance.Sharpness(img1)
            img1 = enhancer.enhance(1.5)
            temp_path1 = image_path + "_pass1.jpg"
            img1.save(temp_path1)
            text1 = cls._extract_with_easyocr(temp_path1)

            # Pass 2: B&W threshold
            img2 = image.convert('L')
            enhancer = ImageEnhance.Contrast(img2)
            img2 = enhancer.enhance(3.0)
            enhancer = ImageEnhance.Brightness(img2)
            img2 = enhancer.enhance(1.3)
            img2 = img2.point(lambda x: 0 if x < 128 else 255, '1')
            temp_path2 = image_path + "_pass2.jpg"
            img2.save(temp_path2)
            text2 = cls._extract_with_easyocr(temp_path2)

            # Pass 3: Inverted
            img3 = image.convert('L')
            img3 = ImageOps.invert(img3)
            enhancer = ImageEnhance.Contrast(img3)
            img3 = enhancer.enhance(2.5)
            enhancer = ImageEnhance.Brightness(img3)
            img3 = enhancer.enhance(1.5)
            img3 = img3.point(lambda x: 0 if x < 140 else 255, '1')
            temp_path3 = image_path + "_pass3.jpg"
            img3.save(temp_path3)
            text3 = cls._extract_with_easyocr(temp_path3)

            # Pass 4: NEW - Grayscale conversion for dark backgrounds
            # Dark interfaces often OCR better in grayscale with moderate contrast
            img4 = image.convert('L')
            enhancer = ImageEnhance.Contrast(img4)
            img4 = enhancer.enhance(1.5)
            enhancer = ImageEnhance.Brightness(img4)
            img4 = enhancer.enhance(1.2)
            temp_path4 = image_path + "_pass4.jpg"
            img4.save(temp_path4)
            text4 = cls._extract_with_easyocr(temp_path4)

            # Pass 5: NEW - Adaptive threshold (local binarization)
            img5 = image.convert('L')
            img5 = img5.resize((img5.width * 2, img5.height * 2), Image.LANCZOS)
            enhancer = ImageEnhance.Contrast(img5)
            img5 = enhancer.enhance(2.0)
            img5 = img5.point(lambda x: 0 if x < 100 else 255, '1')
            temp_path5 = image_path + "_pass5.jpg"
            img5.save(temp_path5)
            text5 = cls._extract_with_easyocr(temp_path5)

            for path in [temp_path0, temp_path1, temp_path2, temp_path3, temp_path4, temp_path5]:
                if os.path.exists(path):
                    os.remove(path)

            combined_text = text0 + "\n" + text1 + "\n" + text2 + "\n" + text3 + "\n" + text4 + "\n" + text5

            logger.info(f"OCR extracted text (pass 0 - original):\n{'='*50}\n{text0}\n{'='*50}")
            logger.info(f"OCR extracted text (pass 1):\n{'='*50}\n{text1}\n{'='*50}")
            logger.info(f"OCR extracted text (pass 2):\n{'='*50}\n{text2}\n{'='*50}")
            logger.info(f"OCR extracted text (pass 3 - inverted):\n{'='*50}\n{text3}\n{'='*50}")
            logger.info(f"OCR extracted text (pass 4 - grayscale):\n{'='*50}\n{text4}\n{'='*50}")
            logger.info(f"OCR extracted text (pass 5 - adaptive):\n{'='*50}\n{text5}\n{'='*50}")
            logger.info(f"OCR combined text:\n{'='*50}\n{combined_text}\n{'='*50}")

            return combined_text
        except Exception as e:
            logger.error(f"Error extracting text from image: {e}")
            raise

    @classmethod
    def _extract_with_easyocr(cls, image_path: str) -> str:
        try:
            reader = cls.get_easyocr_reader()
            results = reader.readtext(image_path, detail=1)

            texts = []
            for (bbox, text, confidence) in results:
                if confidence > 0.3:
                    texts.append(text)

            return "\n".join(texts)
        except Exception as e:
            logger.error(f"EasyOCR extraction error: {e}")
            return ""

    @staticmethod
    def _clean_number(raw: str) -> str:
        """Extract and clean a number from OCR text."""
        if not raw:
            return ''
        # Remove currency symbols and spaces
        cleaned = re.sub(r'[₽РPрpоОa-zA-Zа-яА-Я]', '', raw).replace(' ', '').replace(',', '')
        return cleaned if cleaned.isdigit() else ''

    @staticmethod
    def _find_number_after_keyword(text: str, keyword_pattern: str, min_val: int = 0, max_val: int = 999999) -> str:
        """Find a number after a keyword pattern, returns cleaned number or empty string."""
        matches = re.finditer(keyword_pattern, text, re.IGNORECASE)
        for m in matches:
            after_text = text[m.end():]
            # Try to find number with currency symbol first
            num_match = re.search(r'(\d[\d\s,]*)\s*[₽РPрpоО]', after_text[:150])
            if not num_match:
                # Fallback: any number
                num_match = re.search(r'(\d[\d\s,]*)', after_text[:150])
            if num_match:
                cleaned = POSParser._clean_number(num_match.group(1))
                if cleaned.isdigit():
                    num = int(cleaned)
                    if min_val <= num <= max_val:
                        return cleaned
        return ''

    @staticmethod
    def _find_all_numbers_in_context(text: str, keyword_pattern: str, context_size: int = 200, min_val: int = 0, max_val: int = 999999) -> list:
        """Find all numbers after a keyword, returns list of cleaned numbers within range."""
        result = []
        matches = list(re.finditer(keyword_pattern, text, re.IGNORECASE))
        for m in matches:
            context = text[m.end():m.end()+context_size]
            numbers = re.findall(r'(\d[\d\s,]*)\s*[₽РPрpоО]?', context)
            for num_str in numbers:
                cleaned = POSParser._clean_number(num_str)
                if cleaned.isdigit():
                    num = int(cleaned)
                    if min_val <= num <= max_val:
                        result.append(cleaned)
        return result

    @classmethod
    def parse_report(cls, text: str) -> POSReport:
        data = {}

        # Standard pattern matching
        for field, pattern in cls.PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                clean_value = cls._clean_number(value)
                if clean_value.isdigit():
                    data[field] = clean_value
                else:
                    data[field] = None
            else:
                zero_pattern = cls.ZERO_PATTERNS.get(field)
                if zero_pattern and re.search(zero_pattern, text, re.IGNORECASE):
                    data[field] = '0'
                else:
                    data[field] = None

        # ========================================
        # ULTRA-RESILIENT FALLBACK EXTRACTION
        # ========================================

        # 1. TOTAL (Общая выручка) - Most important field
        if data.get('total') is None:
            # Try multiple keyword patterns
            total_keywords = (
                r'(?:общ|бщая|ОаЩая|Ощая|О[\""]Цая|ОшШяя|Общап|ыручк|пырук|выручк|выру|Итого)'
            )
            numbers = cls._find_all_numbers_in_context(text, total_keywords, min_val=100, max_val=999999)
            if numbers:
                # Take the largest reasonable number
                valid_numbers = [int(n) for n in numbers if 100 <= int(n) <= 999999]
                if valid_numbers:
                    data['total'] = str(max(valid_numbers))

        # 2. GAME TIME (Пополнение аккаунтов)
        if data.get('game_time') is None:
            game_keywords = (
                r'(?:П[оа]полн[еи]н[ие]е|Псп[оа]лненк[еи]|Пополнение|'
                r'Паполнение|Пололнение|Поп[ао]лнение|Аккаунты)\s+аккаунтов'
            )
            numbers = cls._find_all_numbers_in_context(text, game_keywords, min_val=100, max_val=50000)
            if numbers:
                # Take the largest
                valid_numbers = [int(n) for n in numbers if 100 <= int(n) <= 50000]
                if valid_numbers:
                    data['game_time'] = str(max(valid_numbers))

        # 3. BAR (Еда)
        if data.get('bar') is None:
            bar_keywords = r'(?:Еда|Бар|Ед[ауы]|\[да)'
            numbers = cls._find_all_numbers_in_context(text, bar_keywords, min_val=100, max_val=50000)
            if numbers:
                valid_numbers = [int(n) for n in numbers if 100 <= int(n) <= 50000]
                if valid_numbers:
                    data['bar'] = str(max(valid_numbers))

        # 4. SERVICES (Услуги)
        if data.get('services') is None:
            services_keywords = (
                r'(?:Услуги|Усл[уиыы]п?[иы]?|УСлу:и|Усл}ти|Услуни|Услути|'
                r'Прочие доходы|Прачие\s+дох[Оо]ды|Прочив доходы|Прэчие доходы|Прэчис доход)'
            )
            numbers = cls._find_all_numbers_in_context(text, services_keywords, min_val=0, max_val=50000)
            if numbers:
                data['services'] = numbers[0]  # Take first match

        # 5. CASH/CASHLESS (Нал/Безнал) - CRITICAL
        # Search for all variations of "Нал/Безнал"
        cash_keywords = (
            r'(?:Нал[./]Безна[ял]|Нал[./]Безнал|Haп/Беэнал|Нап/Безнал|'
            r'H:WБезнал|НапБенл|НалБезнал)'
        )
        if data.get('cash') is None or data.get('cashless') is None:
            numbers = cls._find_all_numbers_in_context(text, cash_keywords, min_val=1000, max_val=99999)
            if len(numbers) >= 2:
                # First number is cash, second is cashless
                if data.get('cash') is None:
                    cash_val = int(numbers[0])
                    if 1000 <= cash_val <= 9999:
                        data['cash'] = numbers[0]
                if data.get('cashless') is None:
                    cashless_val = int(numbers[1])
                    if 1000 <= cashless_val <= 99999:
                        data['cashless'] = numbers[1]
                        data['acquiring'] = numbers[1]
            elif len(numbers) == 1:
                # Only one number found - likely cash
                if data.get('cash') is None:
                    cash_val = int(numbers[0])
                    if 1000 <= cash_val <= 9999:
                        data['cash'] = numbers[0]

        # 6. SBP (Планшет СБП)
        if data.get('sbp') is None:
            sbp_keywords = (
                r'(?:Планшет\s+СБП|Планшет\s+CBN|Планшет\s+CEN|Планшет\s+СБЛ|'
                r'Планшот\s+СБП|Планшот\s+CBN|Планшот\s+CEN|Ппяншет\s+СБП|СБП)'
            )
            numbers = cls._find_all_numbers_in_context(text, sbp_keywords, min_val=0, max_val=50000)
            if numbers:
                data['sbp'] = numbers[0]

        # 7. CASH INCOME (Сумма онлайн-платежей)
        if data.get('cash_income') is None:
            income_keywords = (
                r'(?:Сумма онлайн-платежей|Сумиа онлайн-платежей|'
                r'Сумма\s+онлаин-платежей|Сушша\s+онлайн-платежей|Приход)'
            )
            numbers = cls._find_all_numbers_in_context(text, income_keywords, min_val=0, max_val=999999)
            if numbers:
                data['cash_income'] = numbers[0]
            # Fallback: if no income found but we have cash, use it
            elif data.get('cash'):
                data['cash_income'] = data['cash']

        # 8. CASH EXPENSE (Расходы за смену)
        if data.get('cash_expense') is None:
            expense_keywords = (
                r'(?:Расходы за смену|Расход|Раскады|Раскоды|Расхоны|'
                r'Расходы за с[еэи]ну|Расходы за см[ео]ну|'
                r'Расходы за сш[еи]ну|Расходы за сш[еэи]у)'
            )
            # Check if keyword exists in text
            if re.search(expense_keywords, text, re.IGNORECASE):
                numbers = cls._find_all_numbers_in_context(text, expense_keywords, min_val=0, max_val=50000)
                if numbers:
                    data['cash_expense'] = numbers[0]
                else:
                    data['cash_expense'] = '0'  # Default to 0 if keyword exists

        # 9. ENVELOPE (Инкассация)
        if data.get('envelope') is None:
            envelope_keywords = (
                r'(?:Инкассация|В конверт|Инкисскция|Инивссьря|Инкасстия)'
            )
            if re.search(envelope_keywords, text, re.IGNORECASE):
                numbers = cls._find_all_numbers_in_context(text, envelope_keywords, min_val=0, max_val=50000)
                if numbers:
                    data['envelope'] = numbers[0]
                else:
                    data['envelope'] = '0'  # Default to 0 if keyword exists

        # 10. CASH REMAINDER (На конец смены) - CRITICAL
        if data.get('cash_remainder') is None:
            remainder_keywords = (
                r'(?:Ha конец см[еёэюы]ны|Ha конец ск[еёэюы]ны|Ha конец сп[еёэюы]ны|'
                r'Ha конец си[еёэюы]ны|'  # OCR error: "сиены" instead of "смены"
                r'На конец с[мкпи][еёюы][нп][а-яёы]|Остаток в кассе|'
                r'Наканац|На нача[лп]о см[еёэюы]ны|Нз налало скены)'
            )
            numbers = cls._find_all_numbers_in_context(text, remainder_keywords, min_val=100, max_val=50000)
            if numbers:
                # Take the largest
                valid_numbers = [int(n) for n in numbers if 100 <= int(n) <= 50000]
                if valid_numbers:
                    data['cash_remainder'] = str(max(valid_numbers))
            
            # Fallback: direct multiline search for common OCR errors
            if data.get('cash_remainder') is None:
                # Handle "На конец сиены" or similar with number on next line
                multiline_patterns = [
                    r'(?:На конец сиены|На конец смены|Ha конец см[еёэюы]ны|Остаток в кассе)\s*\n\s*(\d[\d\s]*)\s*[₽РPрpоО]',
                    r'(?:На конец сиены|На конец смены|Ha конец см[еёэюы]ны|Остаток в кассе)\s*[-=]?\s*\n\s*(\d[\d\s]*)\s*[₽РPрpоО]?',
                    r'(?:На конец сиены|На конец смены|Ha конец см[еёэюы]ны|Остаток в кассе)\s*[-=]?\s*(\d[\d\s]*)\s*[₽РPрpоО]',
                ]
                for pattern in multiline_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        cleaned = cls._clean_number(match.group(1))
                        if cleaned.isdigit():
                            num = int(cleaned)
                            if 100 <= num <= 50000:
                                data['cash_remainder'] = cleaned
                                break

        # 11. ACQUIRING - default to cashless
        if data.get('acquiring') is None and data.get('cashless'):
            data['acquiring'] = data['cashless']

        # 12. RETURNS - default to 0
        if data.get('return_cash') is None:
            data['return_cash'] = '0'
        if data.get('return_cashless') is None:
            data['return_cashless'] = '0'

        # ========================================
        # CROSS-VALIDATION & CORRECTIONS
        # ========================================
        
        # If cash is 3-digit and cash_remainder is 4-digit ending with same digits
        if data.get('cash') and len(data['cash']) == 3:
            if data.get('cash_remainder') and len(data['cash_remainder']) == 4:
                if data['cash_remainder'].endswith(data['cash']):
                    data['cash'] = data['cash_remainder']

        # Validate total makes sense (should be >= bar + game_time)
        if data.get('total') and data.get('bar') and data.get('game_time'):
            total = int(data['total'])
            bar = int(data['bar'])
            game = int(data['game_time'])
            # If total seems wrong, try to recalculate
            if total < bar or total < game:
                # Total might be wrong, keep it as is but log warning
                logger.warning(f"Total ({total}) seems incorrect vs bar ({bar}) + game_time ({game})")

        return POSReport(**data)

    @staticmethod
    def determine_shift(hour: int) -> str:
        """Determine if shift is Day or Night based on hour."""
        from config import NIGHT_SHIFT_START_HOUR, DAY_SHIFT_START_HOUR
        if hour >= NIGHT_SHIFT_START_HOUR or hour < DAY_SHIFT_START_HOUR:
            return "Ночь"
        return "День"
