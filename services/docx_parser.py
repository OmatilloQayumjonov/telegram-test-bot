import re
from typing import Dict, List, Any, Optional
import docx


class DocxParseError(Exception):
    pass


def parse_docx_test(file_path_or_bytes, default_title: str = "Yangi test") -> Dict[str, Any]:
    """
    Word (.docx) faylidan savollar, variantlar, to'g'ri javoblar va izohlarni o'qiydi.
    
    Qo'llab-quvvatlanadigan formatlar:
    1-savol:
    1. Savol matni...
    A) Variant 1
    B) Variant 2
    C) Variant 3
    D) Variant 4
    Javob: B (yoki To'g'ri javob: B / Kalit: B / Answer: B)
    Izoh: Bu savolning izohi... (ixtiyoriy)

    Yoki yulduzcha/plyus bilan:
    A) Variant 1
    *B) Variant 2  (yoki +B)
    C) Variant 3
    D) Variant 4
    Izoh: ...
    """
    try:
        doc = docx.Document(file_path_or_bytes)
    except Exception as e:
        raise DocxParseError(f"Word faylini ochishda xatolik: {str(e)}")

    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            lines.append(text)

    # Agar jadvallar bo'lsa, ularni ham ko'rib chiqamiz
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text and text not in lines:
                    lines.append(text)

    if not lines:
        raise DocxParseError("Word fayli bo'sh yoki unda matn topilmadi.")

    title = default_title
    # Agar 1-qatorda test nomi bo'lsa (masalan, raqamsiz boshlangan bo'lsa)
    first_line = lines[0]
    if not re.match(r"^(\d+[\.\)]|savol|question)", first_line, re.IGNORECASE):
        if not re.match(r"^([a-dA-D][\.\)]|[\*\+][a-dA-D])", first_line):
            title = first_line
            lines = lines[1:]

    questions: List[Dict[str, Any]] = []
    current_q = None

    option_pattern = re.compile(r"^([\*\+])?\s*([a-dA-D])[\.\)]\s*(.+)$", re.IGNORECASE)
    ans_pattern = re.compile(r"^(?:javob|to['`]?g['`]?ri javob|kalit|answer)\s*:\s*([a-dA-D])", re.IGNORECASE)
    explanation_pattern = re.compile(r"^(?:izoh|tushuntirish|sharh|explanation)\s*:\s*(.+)$", re.IGNORECASE)
    q_start_pattern = re.compile(r"^(?:savol\s*)?(\d+)[\.\)]\s*(.*)$", re.IGNORECASE)

    def finalize_question(q):
        if not q:
            return
        # Tekshirish
        missing = []
        for opt in ['a', 'b', 'c', 'd']:
            if not q['options'].get(opt):
                missing.append(opt.upper())
        if missing:
            raise DocxParseError(
                f"'{q['number']}-savol' uchun quyidagi variantlar topilmadi: {', '.join(missing)}.\n"
                f"Savol matni: {q['text'][:50]}..."
            )
        if not q.get('correct_option'):
            raise DocxParseError(
                f"'{q['number']}-savol' uchun to'g'ri javob belgilanmagan.\n"
                f"Masalan: 'Javob: A' deb yozing yoki to'g'ri variant oldiga * qo'ying.\n"
                f"Savol matni: {q['text'][:50]}..."
            )

        questions.append({
            "question_text": q['text'].strip(),
            "option_a": q['options']['a'].strip(),
            "option_b": q['options']['b'].strip(),
            "option_c": q['options']['c'].strip(),
            "option_d": q['options']['d'].strip(),
            "correct_option": q['correct_option'].upper(),
            "explanation": q.get('explanation', '').strip()
        })

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # 1. Yangi savol boshlanishi (1. yoki 1) yoki Savol 1:)
        q_match = q_start_pattern.match(line_clean)
        # Ehtiyotkorlik: Agar qatorda faqat variant kelsa (masalan A) 1.5 metr), uni variant deb olish kerak
        opt_match = option_pattern.match(line_clean)
        ans_match = ans_pattern.match(line_clean)
        exp_match = explanation_pattern.match(line_clean)

        if q_match and not opt_match and not ans_match and not exp_match:
            if current_q:
                finalize_question(current_q)
            q_num = q_match.group(1)
            q_text = q_match.group(2).strip()
            current_q = {
                "number": q_num,
                "text": q_text,
                "options": {},
                "correct_option": None,
                "explanation": ""
            }
            continue

        # 2. Variantlar (A) B) C) D) yoki *A) +B))
        if opt_match:
            if not current_q:
                # Agar savol raqamsiz boshlangan bo'lsa ham qo'llab-quvvatlaymiz
                current_q = {
                    "number": str(len(questions) + 1),
                    "text": "Savol",
                    "options": {},
                    "correct_option": None,
                    "explanation": ""
                }
            mark = opt_match.group(1)  # * yoki +
            letter = opt_match.group(2).lower()
            val = opt_match.group(3).strip()
            current_q['options'][letter] = val
            if mark in ['*', '+']:
                current_q['correct_option'] = letter.upper()
            continue

        # 3. Javob kaliti (Javob: B)
        if ans_match:
            if current_q:
                current_q['correct_option'] = ans_match.group(1).upper()
            continue

        # 4. Izoh (Izoh: ...)
        if exp_match:
            if current_q:
                current_q['explanation'] = exp_match.group(1).strip()
            continue

        # 5. Savol matnining davomi (ko'p qatorli savollar uchun)
        if current_q and not current_q['options']:
            if current_q['text']:
                current_q['text'] += "\n" + line_clean
            else:
                current_q['text'] = line_clean
        elif current_q and current_q.get('explanation'):
            # Izohning davomi
            current_q['explanation'] += " " + line_clean

    if current_q:
        finalize_question(current_q)

    if not questions:
        raise DocxParseError(
            "Fayldan birorta ham to'g'ri formatdagi savol topilmadi.\n"
            "Iltimos, namunadagi formatga muvofiq tayyorlang."
        )

    return {
        "title": title,
        "questions": questions
    }
