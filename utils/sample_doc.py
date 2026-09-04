import docx
from pathlib import Path


def create_sample_docx(output_path: str = "namuna.docx") -> str:
    """O'qituvchi uchun namunaviy test Word faylini yaratadi"""
    doc = docx.Document()

    # Sarlavha
    doc.add_heading("Informatika va Axborot Texnologiyalari: 1-Mavzu Testi", level=1)

    p_intro = doc.add_paragraph(
        "Ushbu fayl bot uchun namunaviy test fayli hisoblanadi. Savollarni quyidagi tartibda yozishingiz mumkin:\n"
    )

    # 1-savol: Standart format (Javob va Izoh bilan)
    doc.add_paragraph("1. Python dasturlash tili qaysi yilda yaratilgan?")
    doc.add_paragraph("A) 1989-yil")
    doc.add_paragraph("B) 1991-yil")
    doc.add_paragraph("C) 1995-yil")
    doc.add_paragraph("D) 2000-yil")
    doc.add_paragraph("Javob: B")
    doc.add_paragraph("Izoh: Python dasturlash tili 1991-yilda Gvido van Rossum tomonidan ommaga taqdim etilgan.")
    doc.add_paragraph("")

    # 2-savol: Yulduzcha (*) bilan to'g'ri javobni belgilash
    doc.add_paragraph("2. Kompyuterning 'miyasi' deb ataluvchi asosiy qurilma nima?")
    doc.add_paragraph("A) Qattiq disk (HDD/SSD)")
    doc.add_paragraph("*B) Markaziy protsessor (CPU)")
    doc.add_paragraph("C) Tezkor xotira (RAM)")
    doc.add_paragraph("D) Ona plata (Motherboard)")
    doc.add_paragraph("Izoh: Protsessor (CPU) barcha hisoblash va mantiqiy amallarni bajaruvchi asosiy qismdir.")
    doc.add_paragraph("")

    # 3-savol: Izohsiz oddiy test
    doc.add_paragraph("3. Quyidagilardan qaysi biri operatsion tizim emas?")
    doc.add_paragraph("A) Windows 11")
    doc.add_paragraph("B) Ubuntu Linux")
    doc.add_paragraph("C) macOS")
    doc.add_paragraph("D) Google Chrome")
    doc.add_paragraph("To'g'ri javob: D")
    doc.add_paragraph("Izoh: Google Chrome operatsion tizim emas, balki veb-brauzer hisoblanadi.")
    doc.add_paragraph("")

    # 4-savol: Ko'p qatorli savol
    doc.add_paragraph("4. Algoritmning asosiy xossalaridan biri bu cheklilik (diskretlik) xossasidir.\nUshbu xossa nimani anglatadi?")
    doc.add_paragraph("A) Algoritm cheksiz takrorlanishi kerak")
    doc.add_paragraph("B) Algoritm aniq ketma-ketlikdagi chekli qadamlardan iborat bo'lishi kerak")
    doc.add_paragraph("C) Algoritm faqat bitta natija berishi kerak")
    doc.add_paragraph("D) Algoritm faqat kompyuterda ishlashi kerak")
    doc.add_paragraph("Javob: B")
    doc.add_paragraph("Izoh: Diskretlik - bu jarayonning alohida, chekli qadamlarga bo'linishini ifodalaydi.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return str(path.resolve())


if __name__ == "__main__":
    create_sample_docx("namuna.docx")
    print("Namuna fayl yaratildi: namuna.docx")
