import asyncio
import os
from pathlib import Path
from utils.sample_doc import create_sample_docx
from services.docx_parser import parse_docx_test
from services.excel_exporter import export_results_to_excel
from database import db


async def run_verification():
    print("=" * 60)
    print("1. Namuna Word faylini (.docx) yaratish tekshirilmoqda...")
    sample_file = "data/namuna_test.docx"
    create_sample_docx(sample_file)
    assert os.path.exists(sample_file), "Namuna fayl yaratilmadi!"
    print(f"   [OK] Fayl muvaffaqiyatli yaratildi: {sample_file}")

    print("\n2. Word faylni (.docx) tahlil qilish (Parsing) tekshirilmoqda...")
    parsed = parse_docx_test(sample_file)
    print(f"   [OK] Test nomi: {parsed['title']}")
    print(f"   [OK] Topilgan savollar soni: {len(parsed['questions'])} ta")
    assert len(parsed['questions']) >= 3, "Kamida 3 ta savol bo'lishi kerak edi"

    print("\n3. Ma'lumotlar bazasi va Yangi imkoniyatlar tekshirilmoqda...")
    await db.init_db()
    print("   [OK] SQLite jadvallari (users, teachers, settings, tests, payments) yaratildi")

    # Sozlamalar tekshiruvi
    price_m = await db.get_setting("price_month")
    price_y = await db.get_setting("price_year")
    print(f"   [OK] 1 oylik narx: {price_m} so'm, 1 yillik: {price_y} so'm")

    # Talaba ismi va uni yangilash
    dummy_student_id = 999001
    await db.save_or_update_user(dummy_student_id, "Toshmatov Sherzod", "toshmatov_sh")
    await db.update_user_name(dummy_student_id, "Toshmatov Sherzodbek")
    student = await db.get_user(dummy_student_id)
    assert student["full_name"] == "Toshmatov Sherzodbek"
    print(f"   [OK] Talaba ismi muvaffaqiyatli tahrirlandi: {student['full_name']}")

    # O'qituvchi bepul urinishlari (3 ta)
    dummy_teacher_id = 888001
    can_up, reason, _ = await db.can_teacher_create_test(dummy_teacher_id)
    assert can_up is True and reason == "free"
    print("   [OK] O'qituvchiga dastlabki 3 ta bepul urinish tasdiqlandi")

    # Testni bazaga kiritish (matnli va rasmli savol)
    test_questions = list(parsed['questions'])
    test_questions.append({
        "question_text": "Quyidagi rasmda qaysi geometrik shakl tasvirlangan?",
        "option_a": "Uchburchak",
        "option_b": "Kvadrat",
        "option_c": "Aylana",
        "option_d": "Trapetsiya",
        "correct_option": "B",
        "explanation": "Rasmda kvadrat ko'rsatilgan.",
        "image_bytes": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest",
        "image_ext": "png"
    })
    test_id = await db.add_test(parsed['title'], author_id=dummy_teacher_id, questions=test_questions, time_limit_minutes=20)
    print(f"   [OK] Yangi test qo'shildi (ID: #{test_id}), rasmli savol muvaffaqiyatli saqlandi")

    # Obuna berish tekshiruvi
    new_until = await db.grant_subscription(dummy_teacher_id, 30)
    can_up2, reason2, _ = await db.can_teacher_create_test(dummy_teacher_id)
    assert can_up2 is True and reason2 == "subscribed"
    print(f"   [OK] 1 oylik obuna faollashtirildi ({new_until} gacha)")

    # Test topshirish va batch javoblar
    db_questions = await db.get_test_questions(test_id)
    attempt_id = await db.create_attempt(user_id=dummy_student_id, test_id=test_id, total=len(db_questions))

    # Javoblar lug'ati
    answers = {}
    for i, q in enumerate(db_questions):
        # 1-savol to'g'ri, qolganlari xato
        if i == 0:
            answers[str(q["id"])] = q["correct_option"]
        else:
            opts = ['A', 'B', 'C', 'D']
            opts.remove(q["correct_option"])
            answers[str(q["id"])] = opts[0]

    final_score = await db.save_attempt_final_answers(attempt_id, db_questions, answers)
    assert final_score == 1
    print(f"   [OK] Test natijasi hisoblandi: {final_score}/{len(db_questions)}")

    # Excel eksport tekshiruvi
    print("\n4. Excel eksport tekshiruvi...")
    results = await db.get_all_test_results(test_id=test_id)
    excel_path = export_results_to_excel(results, "data/test_natijalari_test.xlsx")
    assert os.path.exists(excel_path), "Excel fayli yaratilmadi!"
    print(f"   [OK] Excel fayl muvaffaqiyatli saqlandi: {excel_path}")

    print("\n" + "=" * 60)
    print("BARCHA TEKSHIRUVLAR MUVAFFAQIYATLI O'TDI! (ALL TESTS PASSED)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_verification())
