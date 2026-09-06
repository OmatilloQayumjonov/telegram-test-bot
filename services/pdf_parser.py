import re
import io
from typing import Dict, List, Any, Tuple, Optional
from pypdf import PdfReader


class PdfParseError(Exception):
    pass


CYRILLIC_TO_LATIN_OPT = {
    'а': 'a', 'б': 'b', 'в': 'c', 'с': 'c', 'г': 'd', 'д': 'd',
    'А': 'A', 'Б': 'B', 'В': 'C', 'С': 'C', 'Г': 'D', 'Д': 'D'
}


def normalize_opt_letter(char: str) -> str:
    char_clean = char.strip()
    return CYRILLIC_TO_LATIN_OPT.get(char_clean, char_clean).upper()


def split_multi_options_line(line: str) -> List[str]:
    """
    Bitta qatorda bir nechta variant bo'lsa (A) 10  B) 20  C) 30  D) 40),
    ularni alohida qatorlarga ajratadi.
    """
    pattern = r"(?<=\S)\s{2,}(?=(?:[\*\+]?\s*)?[a-dA-Dа-яА-Я][\.\)\:\-])"
    parts = re.split(pattern, line)
    if len(parts) >= 2:
        return [p.strip() for p in parts if p.strip()]

    pattern2 = r"(?<=\S)\s+(?=(?:[\*\+]?\s*)?[b-dB-Dб-гБ-Г][\.\)\:\-])"
    parts2 = re.split(pattern2, line)
    if len(parts2) >= 2:
        return [p.strip() for p in parts2 if p.strip()]

    return [line]


def parse_pdf_test(file_path_or_bytes, default_title: str = "Yangi test") -> Dict[str, Any]:
    """
    PDF faylidan matnli va rasmli test savollarini tahlil qiladi.
    """
    try:
        reader = PdfReader(file_path_or_bytes)
    except Exception as e:
        raise PdfParseError(f"PDF faylini ochishda xatolik yuz berdi: {str(e)}")

    if not reader.pages:
        raise PdfParseError("PDF fayli bo'sh yoki unda sahifalar topilmadi.")

    # Sahifalardagi ma'lumotlarni yig'amiz
    doc_elements = []

    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        
        # Sahifadagi rasmlarni ajratib olish
        page_images = []
        try:
            for img in page.images:
                ext = "png"
                if img.name:
                    guessed_ext = img.name.rsplit(".", 1)[-1].lower()
                    if guessed_ext in ["png", "jpg", "jpeg", "webp", "gif"]:
                        ext = "jpg" if guessed_ext == "jpeg" else guessed_ext
                page_images.append((img.data, ext))
        except Exception:
            pass

        # Sahifadagi qatorlarni tahlil qilish
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]
        
        doc_elements.append({
            "page_num": page_num,
            "lines": lines,
            "images": page_images
        })

    title = default_title
    first_found = False

    # Sarlavhani topish (birinchi sahifaning birinchi qatori)
    for elem in doc_elements:
        for line in elem["lines"]:
            if not first_found and line:
                first_found = True
                # Agar birinchi qator savol yoki variant bo'lmasa, uni sarlavha deb olamiz
                if not re.match(r"^(?:№\s*)?(?:(?:savol|question|вопрос)\s*)?(\d+)", line, re.IGNORECASE):
                    if not re.match(r"^([\*\+]?\s*)?[a-dA-Dа-яА-Я][\.\)]", line):
                        title = line[:100]
                break
        if first_found:
            break

    questions: List[Dict[str, Any]] = []
    current_q = None
    pending_image = None

    option_pattern = re.compile(r"^([\*\+])?\s*([a-dA-Dа-яА-Я])[\.\)\:\-]\s*(.*)$", re.IGNORECASE)
    ans_pattern = re.compile(r"^(?:javob|to['`‘]?g['`‘]?ri javob|kalit|answer|correct(?:\s*answer)?|жавоб|тўғри жавоб|калит)\s*[:\-=]\s*\(?([a-dA-Dа-яА-Я])", re.IGNORECASE)
    explanation_pattern = re.compile(r"^(?:izoh|tushuntirish|sharh|explanation|изоҳ|шарҳ)\s*[:\-=]\s*(.*)$", re.IGNORECASE)
    q_start_pattern = re.compile(r"^(?:№\s*)?(?:(?:savol|question|вопрос)\s*)?(\d+)(?:[\.\)\-:\s]+(?:savol|question|вопрос)?)?[\.\)\-:\s]*(.*)$", re.IGNORECASE)

    def finalize_question(q):
        if not q:
            return

        if not q['text'].strip():
            if q.get('image_bytes'):
                q['text'] = "Quyidagi rasmga asosan to'g'ri javobni tanlang:"
            else:
                q['text'] = f"{q['number']}-savol:"

        missing = []
        for opt in ['a', 'b', 'c', 'd']:
            if not q['options'].get(opt):
                missing.append(opt.upper())

        if missing:
            raise PdfParseError(
                f"'{q['number']}-savol' uchun quyidagi variantlar topilmadi: {', '.join(missing)}.\n"
                f"Savol matni: {q['text'][:60]}..."
            )

        if not q.get('correct_option'):
            raise PdfParseError(
                f"'{q['number']}-savol' uchun to'g'ri javob belgilanmagan.\n"
                f"Masalan: 'Javob: A' deb yozing yoki to'g'ri variant oldiga * qo'ying.\n"
                f"Savol matni: {q['text'][:60]}..."
            )

        questions.append({
            "question_text": q['text'].strip(),
            "option_a": q['options']['a'].strip(),
            "option_b": q['options']['b'].strip(),
            "option_c": q['options']['c'].strip(),
            "option_d": q['options']['d'].strip(),
            "correct_option": q['correct_option'].upper(),
            "explanation": q.get('explanation', '').strip(),
            "image_bytes": q.get('image_bytes'),
            "image_ext": q.get('image_ext', 'png')
        })

    for elem in doc_elements:
        images = elem.get("images", [])
        img_idx = 0

        expanded_lines = []
        for l in elem["lines"]:
            expanded_lines.extend(split_multi_options_line(l))

        for line in expanded_lines:
            line_clean = line.strip()
            if not line_clean:
                continue

            # Agar bu sarlavha qatori bo'lsa, o'tkazib yuboramiz
            if line_clean == title and len(questions) == 0 and current_q is None:
                continue

            q_match = q_start_pattern.match(line_clean)
            opt_match = option_pattern.match(line_clean)
            ans_match = ans_pattern.match(line_clean)
            exp_match = explanation_pattern.match(line_clean)

            # Yangi savol boshlanishi
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
                    "explanation": "",
                    "image_bytes": None,
                    "image_ext": "png"
                }

                # Agar avvalgi sahifadan/elementdan qolib ketgan rasm bo'lsa
                if pending_image:
                    current_q["image_bytes"], current_q["image_ext"] = pending_image
                    pending_image = None
                elif img_idx < len(images):
                    current_q["image_bytes"], current_q["image_ext"] = images[img_idx]
                    img_idx += 1

                continue

            # Variantlar
            if opt_match and not ans_match:
                if not current_q:
                    # Agar birinchi savol raqamsiz boshlangan bo'lsa
                    current_q = {
                        "number": "1",
                        "text": "1-savol:",
                        "options": {},
                        "correct_option": None,
                        "explanation": "",
                        "image_bytes": None,
                        "image_ext": "png"
                    }
                    if img_idx < len(images):
                        current_q["image_bytes"], current_q["image_ext"] = images[img_idx]
                        img_idx += 1

                star_mark = opt_match.group(1)
                opt_letter = normalize_opt_letter(opt_match.group(2)).lower()
                opt_text = opt_match.group(3).strip()

                if opt_letter in ['a', 'b', 'c', 'd']:
                    current_q['options'][opt_letter] = opt_text
                    if star_mark and not current_q.get('correct_option'):
                        current_q['correct_option'] = opt_letter.upper()
                continue

            # To'g'ri javob
            if ans_match:
                if current_q:
                    raw_opt = ans_match.group(1)
                    current_q['correct_option'] = normalize_opt_letter(raw_opt)
                continue

            # Izoh
            if exp_match:
                if current_q:
                    current_q['explanation'] = exp_match.group(1).strip()
                continue

            # Agar yuqoridagilarning hech biri bo'lmasa, bu savol matnining davomi
            if current_q:
                if not current_q['options']:
                    current_q['text'] = (current_q['text'] + " " + line_clean).strip()
                else:
                    last_opt = None
                    for o in ['d', 'c', 'b', 'a']:
                        if o in current_q['options']:
                            last_opt = o
                            break
                    if last_opt:
                        current_q['options'][last_opt] = (current_q['options'][last_opt] + " " + line_clean).strip()

        # Sahifada ishlatilmagan rasmlar qolsa
        while img_idx < len(images):
            if current_q and not current_q.get("image_bytes"):
                current_q["image_bytes"], current_q["image_ext"] = images[img_idx]
            else:
                pending_image = images[img_idx]
            img_idx += 1

    if current_q:
        finalize_question(current_q)

    if not questions:
        raise PdfParseError(
            "PDF faylidan birorta ham test savoli topilmadi!\n\n"
            "Iltimos, fayl skaner qilingan rasm emas, matnli PDF ekanligiga va savollar 1., 2. tarzida, variantlar A), B), C), D) ko'rinishida yozilganiga ishonch hosil qiling."
        )

    return {
        "title": title,
        "questions": questions
    }


def parse_single_question_text(raw_text: str, image_bytes: Optional[bytes] = None, image_ext: str = "png") -> Dict[str, Any]:
    """
    Qo'lda kiritilgan bitta savol matnidan (va ixtiyoriy rasmidan) savol ob'ektini yaratadi.
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if not lines and not image_bytes:
        raise PdfParseError("Savol matni yoki rasmi kiritilmadi.")

    expanded_lines = []
    for l in lines:
        expanded_lines.extend(split_multi_options_line(l))

    option_pattern = re.compile(r"^([\*\+])?\s*([a-dA-Dа-яА-Я])[\.\)\:\-]\s*(.*)$", re.IGNORECASE)
    ans_pattern = re.compile(r"^(?:javob|to['`‘]?g['`‘]?ri javob|kalit|answer|correct(?:\s*answer)?|жавоб|тўғри жавоб|калит)\s*[:\-=]\s*\(?([a-dA-Dа-яА-Я])", re.IGNORECASE)
    explanation_pattern = re.compile(r"^(?:izoh|tushuntirish|sharh|explanation|изоҳ|шарҳ)\s*[:\-=]\s*(.*)$", re.IGNORECASE)
    q_start_pattern = re.compile(r"^(?:№\s*)?(?:(?:savol|question|вопрос)\s*)?(\d+)(?:[\.\)\-:\s]+(?:savol|question|вопрос)?)?[\.\)\-:\s]*(.*)$", re.IGNORECASE)

    q_text_parts = []
    options = {}
    correct_option = None
    explanation = ""

    for line in expanded_lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        opt_match = option_pattern.match(line_clean)
        ans_match = ans_pattern.match(line_clean)
        exp_match = explanation_pattern.match(line_clean)

        if opt_match and not ans_match:
            star = opt_match.group(1)
            letter = normalize_opt_letter(opt_match.group(2)).lower()
            text = opt_match.group(3).strip()
            if letter in ['a', 'b', 'c', 'd']:
                options[letter] = text
                if star and not correct_option:
                    correct_option = letter.upper()
            continue

        if ans_match:
            correct_option = normalize_opt_letter(ans_match.group(1)).upper()
            continue

        if exp_match:
            explanation = exp_match.group(1).strip()
            continue

        if not options:
            q_match = q_start_pattern.match(line_clean)
            if q_match:
                q_text_parts.append(q_match.group(2).strip() or line_clean)
            else:
                q_text_parts.append(line_clean)
        else:
            # Variant davomi
            last_opt = None
            for o in ['d', 'c', 'b', 'a']:
                if o in options:
                    last_opt = o
                    break
            if last_opt:
                options[last_opt] = (options[last_opt] + " " + line_clean).strip()

    q_text = " ".join(q_text_parts).strip()
    if not q_text:
        if image_bytes:
            q_text = "Quyidagi rasmga asosan to'g'ri javobni tanlang:"
        else:
            raise PdfParseError("Savol matni topilmadi.")

    missing = []
    for opt in ['a', 'b', 'c', 'd']:
        if not options.get(opt):
            missing.append(opt.upper())

    if missing:
        raise PdfParseError(f"Quyidagi variantlar topilmadi: {', '.join(missing)}.\nSavol kamida A, B, C, D variantlariga ega bo'lishi kerak.")

    if not correct_option:
        raise PdfParseError("To'g'ri javob ko'rsatilmagan!\nMasalan: oxirida 'Javob: A' deb yozing yoki to'g'ri variant oldiga * qo'ying (*A).")

    return {
        "question_text": q_text,
        "option_a": options['a'],
        "option_b": options['b'],
        "option_c": options['c'],
        "option_d": options['d'],
        "correct_option": correct_option,
        "explanation": explanation,
        "image_bytes": image_bytes,
        "image_ext": image_ext
    }

