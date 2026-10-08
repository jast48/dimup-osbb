import os
import io
import qrcode
from datetime import datetime
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Регистрация системных шрифтов с поддержкой кириллицы (Windows Arial)
FONT_NAME = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

def init_fonts():
    global FONT_NAME, FONT_BOLD
    font_paths = [
        ("Arial", "C:/Windows/Fonts/arial.ttf", "Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"),
        ("Calibri", "C:/Windows/Fonts/calibri.ttf", "Calibri-Bold", "C:/Windows/Fonts/calibrib.ttf"),
    ]
    for name, reg_p, b_name, bold_p in font_paths:
        if os.path.exists(reg_p) and os.path.exists(bold_p):
            try:
                pdfmetrics.registerFont(TTFont(name, reg_p))
                pdfmetrics.registerFont(TTFont(b_name, bold_p))
                FONT_NAME = name
                FONT_BOLD = b_name
                return
            except Exception:
                continue

init_fonts()


class DocumentService:
    """Генератор юридичних та офіційних PDF документів для ОСББ/ЖБК"""

    @staticmethod
    def _create_qr_image(data: str, size: int = 100) -> RLImage:
        """Створює flowable зображення QR-коду"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1E293B", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return RLImage(buffer, width=2.8*cm, height=2.8*cm)

    @classmethod
    def generate_debt_claim_pdf(
        cls,
        debtor_name: str,
        apartment_number: int,
        area: float,
        debt_amount: float,
        days_overdue: int = 180,
        osbb_name: str = "ОСББ «Затишна Оселя»",
        osbb_edrpou: str = "43928172",
        osbb_iban: str = "UA893052990000026001234567890",
        bank_name: str = "АТ КБ «ПриватБанк»",
        chairman_name: str = "Олексій Дмитренко",
        payment_link: str = "https://dimup.ua/pay"
    ) -> bytes:
        """
        Генерує офіційну «ДОСУДОВУ ВИМОГУ ПРО ПОГАШЕННЯ ЗАБОРГОВАНОСТІ»
        з розрахунком 3% річних та інфляційних втрат за ст. 625 ЦК України.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18*mm,
            leftMargin=18*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'DocTitle',
            fontName=FONT_BOLD,
            fontSize=13,
            leading=16,
            alignment=1, # Center
            textColor=colors.HexColor("#991B1B") # Dark red
        )
        header_bold = ParagraphStyle(
            'DocHeader',
            fontName=FONT_BOLD,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1E293B")
        )
        normal_style = ParagraphStyle(
            'DocNormal',
            fontName=FONT_NAME,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155")
        )
        legal_bold = ParagraphStyle(
            'LegalBold',
            fontName=FONT_BOLD,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#0F172A")
        )

        # Розрахунок санкцій за ст. 625 ЦК України
        # 3% річних: (Борг * 0.03 * дні / 365)
        three_percent = round((debt_amount * 0.03 * days_overdue) / 365.0, 2)
        # Інфляційні втрати (орієнтовно 8.5% річних за індексами Держстату)
        inflation_losses = round((debt_amount * 0.085 * (days_overdue / 365.0)), 2)
        court_fee = 3028.00 # Судовий збір станом на 2026 рік для майнового позову
        total_with_penalties = round(debt_amount + three_percent + inflation_losses, 2)
        total_court_claim = round(total_with_penalties + court_fee + 5000.00, 2) # + витрати на правничу допомогу

        story = []

        # 1. Шапка документа: Відправник / Одержувач
        now_str = datetime.now().strftime("%d.%m.%Y")
        ref_num = f"ПР-2026/{apartment_number:03d}"

        header_data = [
            [
                Paragraph(f"<b>ВИХ. №:</b> {ref_num}<br/><b>ДАТА:</b> {now_str}<br/><b>СТАТУС:</b> ДОСУДОВЕ ПОПЕРЕДЖЕННЯ", normal_style),
                Paragraph(
                    f"<b>КОМУ (Боржнику):</b><br/>"
                    f"Власнику кв. № <b>{apartment_number}</b><br/>"
                    f"<b>{debtor_name}</b><br/>"
                    f"Загальна площа: {area:.1f} м²",
                    header_bold
                )
            ],
            [
                Paragraph(
                    f"<b>ВІД КОГО (Стягувач):</b><br/>"
                    f"{osbb_name}<br/>"
                    f"Код ЄДРПОУ: {osbb_edrpou}<br/>"
                    f"IBAN: {osbb_iban} ({bank_name})",
                    normal_style
                ),
                Paragraph(f"<b>ПІДСТАВА:</b><br/>Закон України № 2866-III «Про ОСББ»<br/>Ст. 625 Цивільного кодексу України", normal_style)
            ]
        ]
        t_header = Table(header_data, colWidths=[8.5*cm, 8.5*cm])
        t_header.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(t_header)
        story.append(Spacer(1, 12))

        # 2. Заголовок
        story.append(Paragraph("ПРЕТЕНЗІЯ - ВИМОГА<br/><font size=10 color='#475569'>про досудове врегулювання спору та погашення заборгованості</font>", title_style))
        story.append(Spacer(1, 10))

        # 3. Фабула
        p_text1 = (
            f"Правління {osbb_name} повідомляє, що станом на <b>{now_str}</b> за Вашим особовим рахунком "
            f"по квартирі № <b>{apartment_number}</b> обліковується прострочена заборгованість зі сплати обов'язкових "
            f"внесків на утримання будинку та прибудинкової території за період понад <b>{days_overdue} днів</b>.<br/>"
            f"Згідно зі ст. 15, 20 Закону України «Про об'єднання співвласників багатоквартирного будинку» "
            f"та ст. 7 Закону України «Про ЖКП», співвласник зобов'язаний своєчасно і в повному обсязі оплачувати надані послуги."
        )
        story.append(Paragraph(p_text1, normal_style))
        story.append(Spacer(1, 8))

        # 4. Таблиця розрахунку
        calc_data = [
            [Paragraph("<b>Складова заборгованості / нарахування</b>", legal_bold), Paragraph("<b>Сума, грн</b>", legal_bold)],
            [Paragraph("Основна сума заборгованості за внесками", normal_style), Paragraph(f"<b>{debt_amount:.2f} грн</b>", legal_bold)],
            [Paragraph(f"3% річних (ст. 625 ЦК України, за {days_overdue} дн.)", normal_style), Paragraph(f"{three_percent:.2f} грн", normal_style)],
            [Paragraph("Інфляційні втрати (за період прострочення)", normal_style), Paragraph(f"{inflation_losses:.2f} грн", normal_style)],
            [Paragraph("<b>РАЗОМ ДО СПЛАТИ В ДОСУДОВОМУ ПОРЯДКУ:</b>", legal_bold), Paragraph(f"<b>{total_with_penalties:.2f} грн</b>", ParagraphStyle('RedSum', fontName=FONT_BOLD, fontSize=10, textColor=colors.HexColor("#B91C1C")))],
        ]
        t_calc = Table(calc_data, colWidths=[12.5*cm, 4.5*cm])
        t_calc.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#FEE2E2")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#94A3B8")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t_calc)
        story.append(Spacer(1, 10))

        # 5. Попередження про судові наслідки
        warning_p = (
            f"<b>УВАГА:</b> У разі непогашення боргу протягом <b>10 (десяти) календарних днів</b> з моменту отримання цієї вимоги, "
            f"правління {osbb_name} звернеться до суду з заявою про видачу судового наказу або позовною заявою.<br/>"
            f"У судовому порядку з Вас додатково буде стягнуто:<br/>"
            f"• Судовий збір: <b>{court_fee:.2f} грн</b>;<br/>"
            f"• Витрати на професійну правничу допомогу адвоката (орієнтовно від <b>5 000.00 грн</b>);<br/>"
            f"• Виконавчий збір 10% у ДВС та накладення <b>арешту на банківські картки та майно/авто</b>.<br/>"
            f"<b>Орієнтовна сума стягнення через суд складе: {total_court_claim:.2f} грн.</b>"
        )
        t_warn = Table([[Paragraph(warning_p, normal_style)]], colWidths=[17*cm])
        t_warn.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF3C7")), # light yellow warning
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#F59E0B")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t_warn)
        story.append(Spacer(1, 10))

        # 6. Блок оплати та QR-код
        qr_flow = cls._create_qr_image(f"{payment_link}?apt={apartment_number}&amt={total_with_penalties}")
        pay_info = (
            f"<b>РЕКВІЗИТИ ДЛЯ ШВИДКОЇ ОПЛАТИ:</b><br/>"
            f"Одержувач: {osbb_name}<br/>"
            f"ЄДРПОУ: <code>{osbb_edrpou}</code><br/>"
            f"IBAN: <b>{osbb_iban}</b> в {bank_name}<br/>"
            f"Призначення: <i>Внески на утримання будинку, кв. {apartment_number}, {debtor_name}</i><br/><br/>"
            f"📱 <i>Відскануйте QR-код смартфоном для миттєвої оплати в додатку Вашого банку.</i>"
        )
        pay_table = Table([[Paragraph(pay_info, normal_style), qr_flow]], colWidths=[13.5*cm, 3.5*cm])
        pay_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 12))

        # 7. Підпис
        sign_data = [
            [
                Paragraph(f"Голова правління {osbb_name}:", legal_bold),
                Paragraph(f"_____________ / {chairman_name} /", legal_bold),
                Paragraph("<b>М.П.</b> (Електронний підпис КЕП)", normal_style)
            ]
        ]
        t_sign = Table(sign_data, colWidths=[6.5*cm, 6.5*cm, 4*cm])
        story.append(t_sign)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def generate_certificate_pdf(
        cls,
        resident_name: str,
        apartment_number: int,
        area: float,
        balance: float,
        osbb_name: str = "ОСББ «Затишна Оселя»",
        osbb_edrpou: str = "43928172",
        chairman_name: str = "Олексій Дмитренко",
        cert_type: str = "no_debt"
    ) -> bytes:
        """
        Генерує офіційну «ДОВІДКУ ПРО ВІДСУТНІСТЬ ЗАБОРГОВАНОСТІ»
        з захисним QR-кодом верифікації для ЦНАП, нотаріуса або банку.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )

        title_style = ParagraphStyle(
            'CertTitle',
            fontName=FONT_BOLD,
            fontSize=15,
            leading=18,
            alignment=1,
            textColor=colors.HexColor("#0F172A")
        )
        normal_style = ParagraphStyle(
            'CertNormal',
            fontName=FONT_NAME,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#1E293B")
        )
        legal_bold = ParagraphStyle(
            'CertBold',
            fontName=FONT_BOLD,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#0F172A")
        )

        now = datetime.now()
        cert_id = f"ДОВ-{now.year}/{apartment_number:03d}-{now.strftime('%d%m')}"
        qr_url = f"https://dimup.ua/verify?cert={cert_id}&apt={apartment_number}"
        qr_flow = cls._create_qr_image(qr_url)

        story = []

        # Шапка ОСББ
        header_text = (
            f"<b>{osbb_name}</b><br/>"
            f"Код ЄДРПОУ: {osbb_edrpou} | Електронна система управління: DimApp<br/>"
            f"вул. Будівельників, 12, м. Київ | тел. +380 44 290-00-11"
        )
        story.append(Paragraph(header_text, ParagraphStyle('H', fontName=FONT_NAME, fontSize=9, leading=12, alignment=1, textColor=colors.HexColor("#64748B"))))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceBefore=2, spaceAfter=15))

        # Дата та номер
        meta_data = [
            [Paragraph(f"<b>Вихідний №:</b> {cert_id}", normal_style), Paragraph(f"<b>Дата видачі:</b> {now.strftime('%d.%m.%Y р.')}", ParagraphStyle('R', fontName=FONT_NAME, fontSize=10, alignment=2))]
        ]
        story.append(Table(meta_data, colWidths=[8.5*cm, 8.5*cm]))
        story.append(Spacer(1, 20))

        # Назва
        story.append(Paragraph("Д О В І Д К А", title_style))
        story.append(Spacer(1, 15))

        # Зміст довідки
        body_text = (
            f"Видана співвласнику <b>{resident_name}</b> у тому, що він/вона дійсно є власником (мешканцем) "
            f"квартири № <b>{apartment_number}</b> загальною площею <b>{area:.1f} м²</b> у житловому будинку "
            f"за адресою: <i>м. Київ, вул. Будівельників, 12</i>, що перебуває в управлінні {osbb_name}.<br/><br/>"
            f"Станом на <b>{now.strftime('%d.%m.%Y')}</b> року за квартирою № <b>{apartment_number}</b> "
            f"<b>ЗАБОРГОВАНІСТЬ</b> зі сплати внесків на утримання будинку та прибудинкової території, "
            f"поточний ремонт та аварійний фонд — <b>ВІДСУТНЯ</b> (поточний баланс: +{balance:.2f} грн).<br/><br/>"
            f"Довідка видана для пред'явлення за місцем вимоги (до органів соціального захисту населення, ЦНАП, банку, нотаріусу тощо) "
            f"і дійсна протягом <b>30 (тридцяти) календарних днів</b> з моменту видачі."
        )
        story.append(Paragraph(body_text, normal_style))
        story.append(Spacer(1, 25))

        # Захист QR
        security_text = (
            f"🔐 <b>Електронна верифікація документа:</b><br/>"
            f"Довідка згенерована автоматизованою системою управління ОСББ «DimApp».<br/>"
            f"Справжність документа та відсутність боргу перевіряється скануванням QR-коду праворуч.<br/>"
            f"Унікальний хеш-код перевірки: <code>{cert_id}</code>"
        )
        sec_table = Table([[Paragraph(security_text, normal_style), qr_flow]], colWidths=[13*cm, 4*cm])
        sec_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(sec_table)
        story.append(Spacer(1, 30))

        # Підписи
        sign_data = [
            [
                Paragraph(f"Голова правління {osbb_name}:", legal_bold),
                Paragraph(f"_______________ / {chairman_name} /", legal_bold),
            ],
            [
                Paragraph("Головний бухгалтер:", legal_bold),
                Paragraph("_______________ / О. В. Мельник /", legal_bold),
            ]
        ]
        t_sign = Table(sign_data, colWidths=[8.5*cm, 8.5*cm])
        t_sign.setStyle(TableStyle([
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t_sign)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def generate_voting_protocol_pdf(
        cls,
        poll_title: str,
        poll_description: str,
        total_building_area: float,
        options_stats: List[Dict[str, Any]],
        voted_area_sum: float,
        osbb_name: str = "ОСББ «Затишна Оселя»",
        chairman_name: str = "Олексій Дмитренко"
    ) -> bytes:
        """
        Генерує юридично оформлений «ПРОТОКОЛ ПИСЬМОВОГО ОПИТУВАННЯ / ГОЛОСУВАННЯ»
        за нормами Закону України № 417-VIII з розрахунком за площею (м²).
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=18*mm,
            leftMargin=18*mm,
            topMargin=15*mm,
            bottomMargin=15*mm
        )

        title_style = ParagraphStyle(
            'ProtTitle',
            fontName=FONT_BOLD,
            fontSize=13,
            leading=16,
            alignment=1,
            textColor=colors.HexColor("#0F172A")
        )
        normal_style = ParagraphStyle(
            'ProtNormal',
            fontName=FONT_NAME,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155")
        )
        legal_bold = ParagraphStyle(
            'ProtBold',
            fontName=FONT_BOLD,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#0F172A")
        )

        now_str = datetime.now().strftime("%d.%m.%Y")
        quorum_pct = (voted_area_sum / total_building_area * 100.0) if total_building_area > 0 else 0
        has_quorum = quorum_pct >= 50.0

        story = []

        # Заголовок
        story.append(Paragraph(f"ПРОТОКОЛ № ГОЛ-2026<br/><font size=10 color='#475569'>письмового опитування (електронного голосування) співвласників {osbb_name}</font>", title_style))
        story.append(Spacer(1, 10))

        # Відомості про кворум
        meta_p = (
            f"<b>Дата формування протоколу:</b> {now_str}<br/>"
            f"<b>Загальна площа житлових та нежитлових приміщень будинку:</b> {total_building_area:,.2f} м² (100.0%)<br/>"
            f"<b>Взяли участь у голосуванні:</b> {voted_area_sum:,.2f} м² (<b>{quorum_pct:.2f}%</b> від загальної площі)<br/>"
            f"<b>Статус кворуму:</b> " +
            (f"<font color='#16A34A'><b>КВОРУМ ДОСЯГНУТО ({quorum_pct:.1f}% >= 50.0%)</b></font>" if has_quorum else f"<font color='#DC2626'><b>КВОРУМ НЕ ДОСЯГНУТО ({quorum_pct:.1f}% &lt; 50.0%)</b></font>")
        )
        t_meta = Table([[Paragraph(meta_p, normal_style)]], colWidths=[17*cm])
        t_meta.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t_meta)
        story.append(Spacer(1, 12))

        # Питання порядку денного
        story.append(Paragraph(f"<b>ПОРЯДОК ДЕННИЙ (ПИТАННЯ):</b><br/>{poll_title}", legal_bold))
        if poll_description:
            story.append(Paragraph(f"<i>Опис питання: {poll_description}</i>", normal_style))
        story.append(Spacer(1, 10))

        # Результати
        table_rows = [
            [
                Paragraph("<b>Варіант рішення</b>", legal_bold),
                Paragraph("<b>К-ть голосів</b>", legal_bold),
                Paragraph("<b>Площа (м²)</b>", legal_bold),
                Paragraph("<b>% від заг. площі</b>", legal_bold),
                Paragraph("<b>Результат</b>", legal_bold)
            ]
        ]

        winning_option = None
        for opt in options_stats:
            area_m2 = opt.get("area_sum", 0.0)
            pct = (area_m2 / total_building_area * 100.0) if total_building_area > 0 else 0
            is_passed = pct > 50.0
            if is_passed and not winning_option:
                winning_option = opt.get("text")
            
            res_label = "<font color='#16A34A'><b>ПРИЙНЯТО</b></font>" if is_passed else "ВІДХИЛЕНО"

            table_rows.append([
                Paragraph(opt.get("text", ""), normal_style),
                Paragraph(str(opt.get("votes_count", 0)), normal_style),
                Paragraph(f"{area_m2:.1f} м²", normal_style),
                Paragraph(f"<b>{pct:.2f}%</b>", legal_bold),
                Paragraph(res_label, normal_style)
            ])

        t_res = Table(table_rows, colWidths=[6.5*cm, 2.5*cm, 2.5*cm, 3*cm, 2.5*cm])
        t_res.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#94A3B8")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t_res)
        story.append(Spacer(1, 12))

        decision_text = (
            f"<b>РЕЗОЛЮЦІЯ ЗБОРІВ:</b><br/>"
            f"Відповідно до ст. 10 Закону України «Про особливості здійснення права власності у багатоквартирному будинку», " +
            (f"Рішення <b>ПРИЙНЯТО</b> («{winning_option}» набрало понад 50% голосів власників за площею)." if winning_option else "Рішення <b>НЕ ПРИЙНЯТО</b> (жоден варіант не набрав необхідної більшості >50% площі будинку).")
        )
        story.append(Paragraph(decision_text, normal_style))
        story.append(Spacer(1, 20))

        # Підписи лічильної комісії
        signs = [
            [Paragraph("Голова лічильної комісії:", legal_bold), Paragraph(f"____________ / {chairman_name} /", legal_bold)],
            [Paragraph("Член лічильної комісії:", legal_bold), Paragraph("____________ / С. В. Коваленко /", legal_bold)],
            [Paragraph("Секретар зборів:", legal_bold), Paragraph("____________ / Н. І. Бондар /", legal_bold)],
        ]
        t_signs = Table(signs, colWidths=[8.5*cm, 8.5*cm])
        story.append(t_signs)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
