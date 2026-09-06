import sys
import importlib

modules = [
    "config",
    "database.db",
    "services.docx_parser",
    "services.pdf_parser",
    "services.ai_generator",
    "services.excel_exporter",
    "utils.sample_doc",
    "keyboards",
    "handlers.admin",
    "handlers.student",
    "main"
]

print("Modullar sintaksisi va importlari tekshirilmoqda:")
for m in modules:
    try:
        importlib.import_module(m)
        print(f"  [OK] {m}")
    except Exception as e:
        print(f"  [XATO] {m}: {e}")
        sys.exit(1)

print("\nBarcha modullar xatosiz yuklandi!")
