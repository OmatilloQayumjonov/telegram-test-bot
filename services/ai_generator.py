import base64
import json
import re
import aiohttp
from typing import Dict, List, Any, Optional
from services.docx_parser import parse_docx_test
from services.pdf_parser import parse_pdf_test


class AIGeneratorError(Exception):
    pass


MODELS_TO_TRY = [
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

SYSTEM_INSTRUCTION = (
    "Siz professional test tuzuvchi va pedagogik ekspert yordamchisiz. "
    "Foydalanuvchi taqdim etgan material (matn, darslik, konspekt, rasm, word yoki pdf) asosida "
    "aniq, sifatli, mantiqiy va xolis test savollarini tuzib berishingiz kerak. "
    "Har bir savol uchun 4 ta variant (A, B, C, D), 1 ta to'g'ri javob va qisqa tushuntirish (izoh) bo'lishi shart. "
    "Javobni FAQAT talab qilingan JSON formatida qaytaring."
)


def _clean_json_text(raw_text: str) -> str:
    """Markdown bloklari bo'lsa tozalaydi (```json ... ```)"""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


async def _call_gemini_api(payload: dict, api_key: str) -> dict:
    if not api_key:
        raise AIGeneratorError(
            "Gemini API kaliti kiritilmagan!\n"
            "Iltimos, administratorga murojaat qiling yoki Admin Panelidagi sozlamalardan API kalitni kiriting."
        )

    last_error = ""
    timeout = aiohttp.ClientTimeout(total=90)

    for model_name in MODELS_TO_TRY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    status = resp.status
                    data = await resp.json()

                    if status == 404:
                        last_error = f"{model_name} topilmadi yoki eskirgan"
                        continue

                    if status != 200:
                        err_msg = "Noma'lum xatolik"
                        if isinstance(data, dict) and "error" in data:
                            err_msg = data["error"].get("message", str(data["error"]))
                        if "API key not valid" in err_msg or status == 400 and "API_KEY_INVALID" in err_msg:
                            raise AIGeneratorError("Kiritilgan Gemini API kaliti yaroqsiz! Iltimos, kalitni tekshiring.")
                        elif "Resource has been exhausted" in err_msg or status == 429:
                            raise AIGeneratorError("Gemini API so'rovlar limiti tugadi. Birozdan so'ng qayta urinib ko'ring.")
                        else:
                            raise AIGeneratorError(f"Gemini API xatoligi ({status}): {err_msg}")

                    # Natijani ajratib olish
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise AIGeneratorError("Gemini javob qaytarmadi (bo'sh javob).")

                    content_parts = candidates[0].get("content", {}).get("parts", [])
                    if not content_parts:
                        raise AIGeneratorError("Gemini javobida matn topilmadi.")

                    raw_json = content_parts[0].get("text", "")
                    cleaned = _clean_json_text(raw_json)

                    try:
                        parsed = json.loads(cleaned)
                        return parsed
                    except json.JSONDecodeError as je:
                        raise AIGeneratorError(f"AI javobini JSON formatida o'qib bo'lmadi: {str(je)}")

        except aiohttp.ClientError as ce:
            raise AIGeneratorError(f"Internet aloqasi yoki tarmoq xatoligi: {str(ce)}")

    raise AIGeneratorError(f"Gemini API modeli bilan bog'lanib bo'lmadi: {last_error}")


def _validate_ai_test(data: dict) -> dict:
    """AI qaytargan ma'lumotlarni tekshirib, standart formatga keltiradi"""
    title = str(data.get("title", "AI tomonidan yaratilgan test")).strip() or "AI Test"
    raw_questions = data.get("questions", [])
    if not raw_questions:
        raise AIGeneratorError("AI savollarni shakllantira olmadi. Boshqa matn yoki material bilan urinib ko'ring.")

    valid_questions = []
    for idx, q in enumerate(raw_questions, start=1):
        q_text = str(q.get("question_text", "")).strip()
        opt_a = str(q.get("option_a", "")).strip()
        opt_b = str(q.get("option_b", "")).strip()
        opt_c = str(q.get("option_c", "")).strip()
        opt_d = str(q.get("option_d", "")).strip()
        correct = str(q.get("correct_option", "A")).strip().upper()
        if correct not in ["A", "B", "C", "D"]:
            correct = "A"
        explanation = str(q.get("explanation", "")).strip()

        if not q_text or not opt_a or not opt_b or not opt_c or not opt_d:
            continue

        valid_questions.append({
            "question_text": q_text,
            "option_a": opt_a,
            "option_b": opt_b,
            "option_c": opt_c,
            "option_d": opt_d,
            "correct_option": correct,
            "explanation": explanation,
            "image_bytes": None,
            "image_ext": "png"
        })

    if not valid_questions:
        raise AIGeneratorError("AI to'liq va yaroqli variantlarga ega savollarni tuzib bera olmadi.")

    return {
        "title": title,
        "questions": valid_questions
    }


async def generate_test_from_content(
    text_content: str,
    api_key: str,
    question_count: int = 5,
    custom_instruction: str = "",
    media_parts: Optional[List[dict]] = None
) -> Dict[str, Any]:
    """
    Google Gemini yordamida har qanday matn yoki media asosida test tuzadi.
    """
    prompt = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"Vazifa: Taqdim etilayotgan material asosida {question_count} ta test savolini tuzing.\n"
        f"Qo'shimcha talab/ko'rsatma: {custom_instruction or 'Darslik talablariga mos yuqori darajada tuzilsin.'}\n\n"
        f"Qaytishi SHART bo'lgan JSON tuzilishi:\n"
        f"{{\n"
        f'  "title": "Mavzu nomi yoki sarlavha",\n'
        f'  "questions": [\n'
        f'    {{\n'
        f'      "question_text": "Savol matni",\n'
        f'      "option_a": "A varianti",\n'
        f'      "option_b": "B varianti",\n'
        f'      "option_c": "C varianti",\n'
        f'      "option_d": "D varianti",\n'
        f'      "correct_option": "A",\n'
        f'      "explanation": "To\'g\'ri javob nega bunday ekanligi haqida qisqa izoh"\n'
        f'    }}\n'
        f'  ]\n'
        f"}}\n\n"
    )

    parts: List[dict] = [{"text": prompt}]

    if text_content:
        parts.append({"text": f"Material matni:\n{text_content[:30000]}"})

    if media_parts:
        for mp in media_parts:
            parts.append(mp)

    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "response_mime_type": "application/json"
        }
    }

    raw_result = await _call_gemini_api(payload, api_key)
    return _validate_ai_test(raw_result)


async def generate_test_from_image(
    image_bytes: bytes,
    mime_type: str,
    api_key: str,
    question_count: int = 5,
    custom_prompt: str = ""
) -> Dict[str, Any]:
    """Rasm (darslik sahifasi, doska, fotosurat) asosida test tuzadi"""
    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    media_parts = [
        {
            "inline_data": {
                "mime_type": mime_type or "image/jpeg",
                "data": b64_data
            }
        }
    ]
    prompt_desc = custom_prompt or "Rasmda keltirilgan darslik/mavzu mazmunidan kelib chiqib test tuzing."
    return await generate_test_from_content(
        text_content=prompt_desc,
        api_key=api_key,
        question_count=question_count,
        custom_instruction=custom_prompt,
        media_parts=media_parts
    )


async def generate_test_from_pdf_file(
    pdf_bytes: bytes,
    api_key: str,
    question_count: int = 5,
    custom_prompt: str = ""
) -> Dict[str, Any]:
    """PDF darslik yoki konspekt faylidan test tuzadi"""
    # 1. Avval pypdf orqali matnini olamiz
    extracted_text = ""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages[:20]: # Dastlabki 20 sahifa
            t = page.extract_text()
            if t:
                extracted_text += t + "\n"
    except Exception:
        pass

    if len(extracted_text.strip()) > 100:
        return await generate_test_from_content(
            text_content=extracted_text,
            api_key=api_key,
            question_count=question_count,
            custom_instruction=custom_prompt
        )

    # Agar matn bo'lmasa (skaner qilingan PDF bo'lsa), to'g'ridan-to'g'ri inline_data qilib uzatamiz
    b64_data = base64.b64encode(pdf_bytes).decode("utf-8")
    media_parts = [
        {
            "inline_data": {
                "mime_type": "application/pdf",
                "data": b64_data
            }
        }
    ]
    return await generate_test_from_content(
        text_content=custom_prompt or "Ushbu PDF hujjatidagi mavzu asosida test tuzing.",
        api_key=api_key,
        question_count=question_count,
        custom_instruction=custom_prompt,
        media_parts=media_parts
    )


async def generate_test_from_docx_file(
    docx_bytes: bytes,
    api_key: str,
    question_count: int = 5,
    custom_prompt: str = ""
) -> Dict[str, Any]:
    """Word (.docx) konspekt yoki darslik faylidan test tuzadi"""
    import docx
    import io

    doc = docx.Document(io.BytesIO(docx_bytes))
    paragraphs_text = []
    for p in doc.paragraphs:
        if p.text.strip():
            paragraphs_text.append(p.text.strip())

    for t in doc.tables:
        for row in t.rows:
            r_text = " | ".join([c.text.strip() for c in row.cells if c.text.strip()])
            if r_text:
                paragraphs_text.append(r_text)

    full_text = "\n".join(paragraphs_text)
    if not full_text.strip():
        raise AIGeneratorError("Word fayli bo'sh yoki unda matn topilmadi.")

    return await generate_test_from_content(
        text_content=full_text,
        api_key=api_key,
        question_count=question_count,
        custom_instruction=custom_prompt
    )
