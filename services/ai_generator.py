import base64
import json
import re
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
from services.docx_parser import parse_docx_test
from services.pdf_parser import parse_pdf_test


class AIGeneratorError(Exception):
    pass


# Barqaror, yuqori o'tkazuvchanlikka ega va tezkor rasmiy modellar zanjiri
MODELS_TO_TRY = [
    "gemini-2.5-flash",      # Eng tezkor va aqlli (thinkingBudget=0 bilan 1.5-2.5 soniya)
    "gemini-2.0-flash",      # Rasmiy yuqori tezlikdagi production model
    "gemini-2.0-flash-lite", # Ultra yengil va eng kam yuklamaga ega model
    "gemini-1.5-flash",      # Katta kvotaga ega, 99.99% barqaror model
    "gemini-1.5-flash-8b",   # Zaxira yengil model
    "gemini-2.5-pro",        # Yuqori mantiqiy zaxira model
    "gemini-1.5-pro"         # Yakuniy zaxira model
]

SYSTEM_INSTRUCTION = (
    "Siz professional test tuzuvchi va pedagogik ekspert yordamchisiz. "
    "Foydalanuvchi taqdim etgan material (matn, darslik, konspekt, rasm, word yoki pdf) asosida "
    "aniq, sifatli, mantiqiy va xolis test savollarini tuzib berishingiz kerak. "
    "Har bir savol uchun 4 ta variant (A, B, C, D), 1 ta to'g'ri javob va qisqa tushuntirish (izoh) bo'lishi shart. "
    "Javobni FAQAT talab qilingan JSON formatida qaytaring."
)


def _clean_json_text(raw_text: str) -> str:
    """Markdown bloklari va ortiqcha belgilarni tozalab, sof JSON ni ajratib oladi"""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    # Agar model boshida yoki oxirida biror matn qo'shgan bo'lsa, eng tashqi { va } ni ajratib olamiz
    if not (text.startswith("{") and text.endswith("}")):
        m = re.search(r"(\{[\s\S]*\})", text)
        if m:
            text = m.group(1)
    return text.strip()


async def _call_gemini_api(payload: dict, api_key: str) -> dict:
    if not api_key:
        raise AIGeneratorError(
            "AI API kaliti kiritilmagan!\n"
            "Iltimos, administratorga murojaat qiling yoki Admin Panelidagi sozlamalardan API kalitni kiriting."
        )

    last_error = ""
    timeout = aiohttp.ClientTimeout(total=28, connect=8)

    # 3 bosqichli avtomatik qayta urinish (eng barqaror modellar bo'ylab)
    for cycle in range(3):
        for model_name in MODELS_TO_TRY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

            # Faqat 2.5 modellarida tezlikni maksimal qilish uchun thinking ni 0 qilamiz
            model_payload = json.loads(json.dumps(payload))
            if "2.5" in model_name and "generationConfig" in model_payload:
                model_payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
            else:
                # Boshqa modellarda thinkingConfig bo'lsa xatolik (400) beradi, shuning uchun olib tashlanadi
                if "generationConfig" in model_payload and "thinkingConfig" in model_payload["generationConfig"]:
                    del model_payload["generationConfig"]["thinkingConfig"]

            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=model_payload) as resp:
                        status = resp.status
                        data = await resp.json()

                        if status != 200:
                            err_msg = "Noma'lum xatolik"
                            if isinstance(data, dict) and "error" in data:
                                err_msg = data["error"].get("message", str(data["error"]))

                            # Agar API kalit mutlaqo yaroqsiz bo'lsa (400 API_KEY_INVALID)
                            if "API key not valid" in err_msg or (status == 400 and "API_KEY_INVALID" in err_msg):
                                raise AIGeneratorError("Kiritilgan AI API kaliti yaroqsiz! Iltimos, sozlamalardan to'g'ri kalitni kiriting.")

                            # Agar model thinkingConfig ni qabul qilmasa (400), darhol ushbu modelni thinkingConfigsiz sinaymiz
                            if status == 400 and ("thinking" in err_msg.lower() or "unknown field" in err_msg.lower()):
                                plain_payload = json.loads(json.dumps(payload))
                                if "generationConfig" in plain_payload and "thinkingConfig" in plain_payload["generationConfig"]:
                                    del plain_payload["generationConfig"]["thinkingConfig"]
                                async with session.post(url, json=plain_payload) as retry_resp:
                                    if retry_resp.status == 200:
                                        retry_data = await retry_resp.json()
                                        candidates = retry_data.get("candidates", [])
                                        if candidates:
                                            parts = candidates[0].get("content", {}).get("parts", [])
                                            if parts:
                                                raw_json = parts[0].get("text", "")
                                                return json.loads(_clean_json_text(raw_json))

                            # 503 (High demand), 429 (Rate limit), 404, 500, 502, 504 holatlarida
                            # to'xtamasdan DARHOL keyingi barqaror modelga o'tamiz
                            last_error = f"{err_msg} ({status})"
                            continue

                        # Muvaffaqiyatli 200 javob
                        candidates = data.get("candidates", [])
                        if not candidates:
                            last_error = "Bo'sh javob keldi"
                            continue

                        content_parts = candidates[0].get("content", {}).get("parts", [])
                        if not content_parts:
                            last_error = "Javobda matn topilmadi"
                            continue

                        raw_json = content_parts[0].get("text", "")
                        cleaned = _clean_json_text(raw_json)

                        try:
                            parsed = json.loads(cleaned)
                            return parsed
                        except json.JSONDecodeError:
                            # Agar model JSON formatida xatoga yo'l qo'ygan bo'lsa, keyingi modelga o'tamiz
                            last_error = "JSON format xatoligi"
                            continue

            except (aiohttp.ClientError, asyncio.TimeoutError):
                last_error = "Tarmoq ulanishida uzilish"
                continue

        # Agar birinchi tsiklda barcha modellar band bo'lsa, biroz kutib qayta urinadi
        if cycle == 0:
            await asyncio.sleep(0.5)
        elif cycle == 1:
            await asyncio.sleep(1.0)

    raise AIGeneratorError(
        "AI xizmatida vaqtinchalik yuqori yuklama yuzaga keldi.\n"
        "Iltimos, bir necha soniyadan so'ng qayta urinib ko'ring yoki boshqa material yuboring."
    )


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
    Sun'iy intellekt (AI) yordamida har qanday matn yoki media asosida test tuzadi.
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
