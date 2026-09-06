import aiosqlite
import os
import time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from config import DB_FULL_PATH, ADMIN_IDS


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_FULL_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def init_db():
    async with get_db() as db:
        # Foydalanuvchilar (talabalar va o'qituvchilar)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT,
                phone_number TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        try:
            await db.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
        except Exception:
            pass

        # O'qituvchilar va ularning obuna holati
        await db.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                user_id INTEGER PRIMARY KEY,
                tests_created INTEGER DEFAULT 0,
                subscription_until TIMESTAMP,
                is_unlimited INTEGER DEFAULT 0
            )
        """)

        # Tizim sozlamalari (narxlar va to'lov rekvizitlari)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Boshlang'ich sozlamalarni kiritish
        default_settings = [
            ("price_month", "30000"),
            ("price_year", "250000"),
            ("click_details", "8600 0000 0000 0000 (Click)"),
            ("gemini_api_key", "")
        ]
        for k, v in default_settings:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        # Testlar to'plami
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                time_limit_minutes INTEGER DEFAULT 15,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        try:
            await db.execute("ALTER TABLE tests ADD COLUMN time_limit_minutes INTEGER DEFAULT 15")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE tests ADD COLUMN is_random INTEGER DEFAULT 1")
        except Exception:
            pass

        # Savollar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct_option TEXT NOT NULL,
                explanation TEXT,
                image_path TEXT,
                FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE
            )
        """)

        try:
            await db.execute("ALTER TABLE questions ADD COLUMN image_path TEXT")
        except Exception:
            pass

        # Test topshirish urinishlari
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                score INTEGER DEFAULT 0,
                total INTEGER NOT NULL,
                student_name TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE
            )
        """)

        try:
            await db.execute("ALTER TABLE attempts ADD COLUMN student_name TEXT")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE attempts ADD COLUMN last_msg_id INTEGER")
        except Exception:
            pass

        # Berilgan javoblar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attempt_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                selected_option TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                selected_text TEXT,
                correct_text TEXT,
                FOREIGN KEY (attempt_id) REFERENCES attempts (id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
            )
        """)

        try:
            await db.execute("ALTER TABLE attempt_answers ADD COLUMN selected_text TEXT")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE attempt_answers ADD COLUMN correct_text TEXT")
        except Exception:
            pass

        # To'lovlar (obuna so'rovlari)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                receipt_file_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Talabalar uchun ruxsat etilgan testlar (maxsus havola orqali ochilgan)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS student_accessible_tests (
                user_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (test_id) REFERENCES tests (id) ON DELETE CASCADE
            )
        """)

        await db.commit()


# Foydalanuvchi funksiyalari
async def save_or_update_user(user_id: int, full_name: str, username: str = None, phone_number: str = None):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO users (user_id, full_name, username, phone_number)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                username = excluded.username,
                phone_number = COALESCE(excluded.phone_number, users.phone_number)
        """, (user_id, full_name, username, phone_number))
        if full_name and full_name != "Foydalanuvchi":
            await db.execute("UPDATE attempts SET student_name = ? WHERE user_id = ?", (full_name, user_id))
        await db.commit()


async def update_user_phone(user_id: int, phone_number: str):
    async with get_db() as db:
        await db.execute("UPDATE users SET phone_number = ? WHERE user_id = ?", (phone_number, user_id))
        await db.commit()


async def update_user_name(user_id: int, new_full_name: str):
    async with get_db() as db:
        await db.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (new_full_name, user_id))
        await db.execute("UPDATE attempts SET student_name = ? WHERE user_id = ?", (new_full_name, user_id))
        await db.commit()


async def get_user(user_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


# Sozlamalar funksiyalari (Narxlar va Click rekvizitlari)
async def get_setting(key: str, default: str = "") -> str:
    async with get_db() as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else default


async def set_setting(key: str, value: str):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()


async def get_all_settings() -> dict:
    async with get_db() as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}


# O'qituvchi va Obuna funksiyalari
async def get_teacher(user_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM teachers WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row:
            is_unlimited = 1 if user_id in ADMIN_IDS else 0
            await db.execute("INSERT INTO teachers (user_id, tests_created, is_unlimited) VALUES (?, 0, ?)", (user_id, is_unlimited))
            await db.commit()
            cursor = await db.execute("SELECT * FROM teachers WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
        return dict(row) if row else None


async def can_teacher_create_test(user_id: int) -> tuple[bool, str, dict]:
    """
    O'qituvchi yangi test yuklay oladimi?
    Qaytaradi: (mumkinmi, sababi, o'qituvchi_ma'lumoti)
    """
    if user_id in ADMIN_IDS:
        return True, "admin", {"is_unlimited": 1, "tests_created": 0}

    t = await get_teacher(user_id)
    if not t:
        return True, "free", {"tests_created": 0}

    if t.get("is_unlimited") == 1:
        return True, "unlimited", t

    sub_until = t.get("subscription_until")
    if sub_until:
        try:
            sub_date = datetime.strptime(sub_until, "%Y-%m-%d %H:%M:%S")
            if sub_date > datetime.now():
                return True, "subscribed", t
        except Exception:
            pass

    created = t.get("tests_created", 0)
    if created < 3:
        return True, "free", t

    return False, "limit_reached", t


async def increment_teacher_test_count(user_id: int):
    async with get_db() as db:
        await get_teacher(user_id)
        await db.execute("UPDATE teachers SET tests_created = tests_created + 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def grant_subscription(user_id: int, days: int):
    """Foydalanuvchiga kunlik obuna muddatini berish"""
    async with get_db() as db:
        t = await get_teacher(user_id)
        current_sub = t.get("subscription_until")
        now = datetime.now()

        if current_sub:
            try:
                curr_date = datetime.strptime(current_sub, "%Y-%m-%d %H:%M:%S")
                if curr_date > now:
                    new_date = curr_date + timedelta(days=days)
                else:
                    new_date = now + timedelta(days=days)
            except Exception:
                new_date = now + timedelta(days=days)
        else:
            new_date = now + timedelta(days=days)

        new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE teachers SET subscription_until = ? WHERE user_id = ?", (new_date_str, user_id))
        await db.commit()
        return new_date_str


# To'lovlar boshqaruvi
async def create_payment_request(user_id: int, plan_type: str, amount: int, receipt_file_id: str) -> int:
    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO payments (user_id, plan_type, amount, receipt_file_id, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (user_id, plan_type, amount, receipt_file_id))
        payment_id = cursor.lastrowid
        await db.commit()
        return payment_id


async def get_payment_by_id(payment_id: int):
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT p.*, u.full_name, u.username
            FROM payments p
            LEFT JOIN users u ON p.user_id = u.user_id
            WHERE p.id = ?
        """, (payment_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_payment_status(payment_id: int, status: str):
    async with get_db() as db:
        await db.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment_id))
        await db.commit()


# Test boshqaruvi funksiyalari
async def add_test(title: str, author_id: int, questions: list, time_limit_minutes: int = 15, is_random: int = 1) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO tests (title, author_id, is_active, time_limit_minutes, is_random) VALUES (?, ?, 1, ?, ?)",
            (title, author_id, time_limit_minutes, is_random)
        )
        test_id = cursor.lastrowid
        os.makedirs("data/images", exist_ok=True)

        for idx, q in enumerate(questions, start=1):
            image_path = q.get("image_path")
            image_bytes = q.get("image_bytes")
            if image_bytes and not image_path:
                ext = q.get("image_ext", "png")
                img_file = f"data/images/test_{test_id}_q_{idx}_{int(time.time()*1000)}.{ext}"
                try:
                    with open(img_file, "wb") as f:
                        f.write(image_bytes)
                    image_path = img_file
                    q["image_path"] = image_path
                except Exception:
                    pass

            await db.execute("""
                INSERT INTO questions (
                    test_id, question_text, option_a, option_b, option_c, option_d, correct_option, explanation, image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_id,
                q["question_text"],
                q["option_a"],
                q["option_b"],
                q["option_c"],
                q["option_d"],
                q["correct_option"].upper(),
                q.get("explanation", ""),
                image_path
            ))

        await db.commit()
        await increment_teacher_test_count(author_id)
        return test_id


async def update_test_time_limit(test_id: int, minutes: int):
    async with get_db() as db:
        await db.execute("UPDATE tests SET time_limit_minutes = ? WHERE id = ?", (minutes, test_id))
        await db.commit()


async def toggle_test_random(test_id: int) -> int:
    """Test uchun savol va variantlarni aralashtirish (Random) rejimini yoqish/o'chirish"""
    async with get_db() as db:
        cursor = await db.execute("SELECT is_random FROM tests WHERE id = ?", (test_id,))
        row = await cursor.fetchone()
        if not row:
            return 1
        curr = row["is_random"] if (row["is_random"] is not None) else 1
        new_val = 0 if curr == 1 else 1
        await db.execute("UPDATE tests SET is_random = ? WHERE id = ?", (new_val, test_id))
        await db.commit()
        return new_val


async def grant_student_access_to_test(user_id: int, test_id: int):
    """Talabaga maxsus havola orqali testga kirish huquqini berish"""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS student_accessible_tests (
                user_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO student_accessible_tests (user_id, test_id)
            VALUES (?, ?)
        """, (user_id, test_id))
        await db.commit()


async def get_student_accessible_tests(user_id: int):
    """Foydalanuvchi faqat o'zi yaratgan, yoki havola orqali ochgan/topshirgan faol testlarni ko'radi"""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS student_accessible_tests (
                user_id INTEGER NOT NULL,
                test_id INTEGER NOT NULL,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            )
        """)
        if user_id in ADMIN_IDS:
            cursor = await db.execute("""
                SELECT t.*, COUNT(q.id) as question_count
                FROM tests t
                LEFT JOIN questions q ON t.id = q.test_id
                WHERE t.is_active = 1
                GROUP BY t.id
                ORDER BY t.id DESC
            """)
        else:
            cursor = await db.execute("""
                SELECT t.*, COUNT(q.id) as question_count
                FROM tests t
                LEFT JOIN questions q ON t.id = q.test_id
                WHERE (
                    t.author_id = ?
                    OR t.id IN (SELECT test_id FROM student_accessible_tests WHERE user_id = ?)
                    OR t.id IN (SELECT test_id FROM attempts WHERE user_id = ?)
                )
                AND t.is_active = 1
                GROUP BY t.id
                ORDER BY t.id DESC
            """, (user_id, user_id, user_id))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_active_tests():
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT t.*, COUNT(q.id) as question_count
            FROM tests t
            LEFT JOIN questions q ON t.id = q.test_id
            WHERE t.is_active = 1
            GROUP BY t.id
            ORDER BY t.id DESC
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_tests_by_author(author_id: int):
    """Har bir o'qituvchi faqat O'ZINING testlarini ko'radi. Admin esa barcha testlarni boshqara oladi"""
    async with get_db() as db:
        if author_id in ADMIN_IDS:
            cursor = await db.execute("""
                SELECT t.*, COUNT(q.id) as question_count
                FROM tests t
                LEFT JOIN questions q ON t.id = q.test_id
                GROUP BY t.id
                ORDER BY t.id DESC
            """)
        else:
            cursor = await db.execute("""
                SELECT t.*, COUNT(q.id) as question_count
                FROM tests t
                LEFT JOIN questions q ON t.id = q.test_id
                WHERE t.author_id = ?
                GROUP BY t.id
                ORDER BY t.id DESC
            """, (author_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_system_tests():
    """Faqat Superadmin uchun tizimdagi barcha testlar"""
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT t.*, COUNT(q.id) as question_count, u.full_name as author_name
            FROM tests t
            LEFT JOIN questions q ON t.id = q.test_id
            LEFT JOIN users u ON t.author_id = u.user_id
            GROUP BY t.id
            ORDER BY t.id DESC
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_test_by_id(test_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def toggle_test_status(test_id: int) -> int:
    async with get_db() as db:
        cursor = await db.execute("SELECT is_active FROM tests WHERE id = ?", (test_id,))
        row = await cursor.fetchone()
        if not row:
            return 0
        new_status = 0 if row["is_active"] == 1 else 1
        await db.execute("UPDATE tests SET is_active = ? WHERE id = ?", (new_status, test_id))
        await db.commit()
        return new_status


async def delete_test(test_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        await db.commit()


async def get_test_questions(test_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM questions WHERE test_id = ? ORDER BY id ASC", (test_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# Test urinishlari (Attempts)
async def create_attempt(user_id: int, test_id: int, total: int, student_name: str = None, last_msg_id: int = None) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO attempts (user_id, test_id, total, score, student_name, last_msg_id) VALUES (?, ?, ?, 0, ?, ?)",
            (user_id, test_id, total, student_name, last_msg_id)
        )
        attempt_id = cursor.lastrowid
        await db.commit()
        return attempt_id


async def save_attempt_final_answers(attempt_id: int, questions: list, answers_dict: dict) -> int:
    async with get_db() as db:
        await db.execute("DELETE FROM attempt_answers WHERE attempt_id = ?", (attempt_id,))

        score = 0
        for q in questions:
            q_id = q["id"]
            chosen = answers_dict.get(str(q_id), "")
            is_correct = 1 if (chosen and chosen.upper() == q["correct_option"].upper()) else 0
            if is_correct:
                score += 1

            correct_text = q.get("correct_text") or q.get(f"option_{q['correct_option'].lower()}", "")
            if chosen:
                selected_text = q.get(f"option_{chosen.lower()}", "")
                await db.execute("""
                    INSERT INTO attempt_answers (attempt_id, question_id, selected_option, is_correct, selected_text, correct_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (attempt_id, q_id, chosen.upper(), is_correct, selected_text, correct_text))
            else:
                await db.execute("""
                    INSERT INTO attempt_answers (attempt_id, question_id, selected_option, is_correct, selected_text, correct_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (attempt_id, q_id, "Belgilanmagan", 0, "Javob berilmagan", correct_text))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE attempts SET score = ?, completed_at = ? WHERE id = ?",
            (score, now, attempt_id)
        )
        await db.commit()
        return score


async def finish_attempt(attempt_id: int):
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT a.*, COALESCE(u.full_name, a.student_name) as full_name, u.username, t.title as test_title, t.author_id
            FROM attempts a
            JOIN users u ON a.user_id = u.user_id
            JOIN tests t ON a.test_id = t.id
            WHERE a.id = ?
        """, (attempt_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_attempt_mistakes(attempt_id: int):
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT q.question_text, q.explanation, q.image_path,
                   COALESCE(ans.selected_option, 'Belgilanmagan') as selected_option,
                   COALESCE(ans.selected_text, 'Javob berilmagan') as selected_text,
                   COALESCE(ans.correct_text, 
                       CASE q.correct_option 
                           WHEN 'A' THEN q.option_a 
                           WHEN 'B' THEN q.option_b 
                           WHEN 'C' THEN q.option_c 
                           WHEN 'D' THEN q.option_d 
                           ELSE q.option_a 
                       END
                   ) as correct_text
            FROM questions q
            JOIN attempts a ON a.id = ? AND q.test_id = a.test_id
            LEFT JOIN attempt_answers ans ON ans.attempt_id = a.id AND ans.question_id = q.id
            WHERE ans.is_correct IS NULL OR ans.is_correct = 0
            ORDER BY ans.id ASC, q.id ASC
        """, (attempt_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_test_results(test_id: int = None, author_id: int = None):
    async with get_db() as db:
        query = """
            SELECT a.id, a.user_id, COALESCE(u.full_name, a.student_name) as full_name, 
                   u.username, u.phone_number, a.last_msg_id, t.title as test_title,
                   a.score, a.total, a.started_at, a.completed_at
            FROM attempts a
            LEFT JOIN users u ON a.user_id = u.user_id
            JOIN tests t ON a.test_id = t.id
            WHERE a.completed_at IS NOT NULL
        """
        params = []
        if test_id is not None:
            query += " AND a.test_id = ?"
            params.append(test_id)
        if author_id is not None and author_id not in ADMIN_IDS:
            query += " AND t.author_id = ?"
            params.append(author_id)
        query += " ORDER BY a.score DESC, a.completed_at ASC"

        cursor = await db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_tests_with_stats_by_author(author_id: int):
    """Har bir test va unga qatnashgan talabalar soni bilan qaytaradi"""
    async with get_db() as db:
        if author_id in ADMIN_IDS:
            cursor = await db.execute("""
                SELECT t.*, 
                       COUNT(DISTINCT q.id) as question_count,
                       COUNT(DISTINCT a.id) as attempt_count,
                       u.full_name as author_name
                FROM tests t
                LEFT JOIN questions q ON t.id = q.test_id
                LEFT JOIN attempts a ON t.id = a.test_id AND a.completed_at IS NOT NULL
                LEFT JOIN users u ON t.author_id = u.user_id
                GROUP BY t.id
                ORDER BY t.id DESC
            """)
        else:
            cursor = await db.execute("""
                SELECT t.*, 
                       COUNT(DISTINCT q.id) as question_count,
                       COUNT(DISTINCT a.id) as attempt_count,
                       u.full_name as author_name
                FROM tests t
                LEFT JOIN questions q ON t.id = q.test_id
                LEFT JOIN attempts a ON t.id = a.test_id AND a.completed_at IS NOT NULL
                LEFT JOIN users u ON t.author_id = u.user_id
                WHERE t.author_id = ?
                GROUP BY t.id
                ORDER BY t.id DESC
            """, (author_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_test_results_summary(test_id: int, author_id: int = None):
    """Bitta test bo'yicha to'liq statistik ma'lumotlar va talabalar natijalari (reyting tartibida)"""
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT t.*, COUNT(q.id) as question_count, u.full_name as author_name
            FROM tests t
            LEFT JOIN questions q ON t.id = q.test_id
            LEFT JOIN users u ON t.author_id = u.user_id
            WHERE t.id = ?
            GROUP BY t.id
        """, (test_id,))
        test = await cursor.fetchone()
        if not test:
            return None, []
        test = dict(test)

        if author_id and author_id not in ADMIN_IDS and test["author_id"] != author_id:
            return None, []

        cursor = await db.execute("""
            SELECT a.id, a.user_id, COALESCE(u.full_name, a.student_name) as full_name, 
                   u.username, u.phone_number, a.last_msg_id, t.title as test_title,
                   a.score, a.total, a.started_at, a.completed_at
            FROM attempts a
            LEFT JOIN users u ON a.user_id = u.user_id
            JOIN tests t ON a.test_id = t.id
            WHERE a.test_id = ? AND a.completed_at IS NOT NULL
            ORDER BY a.score DESC, a.completed_at ASC
        """, (test_id,))
        attempts = [dict(r) for r in await cursor.fetchall()]
        return test, attempts
