import sqlite3
import time
from typing import List, Dict, Any

DB_NAME = "reminders.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database and creates the reminders table if it doesn't exist."""
    with get_connection() as conn:
        # Create base table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                remind_at INTEGER NOT NULL,
                is_sent INTEGER DEFAULT 0
            )
        """)
        
        # Create dish rolls history table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dish_rolls (
                chat_id INTEGER PRIMARY KEY,
                participants TEXT NOT NULL,
                last_rolled TEXT,
                prev_rolled TEXT
            )
        """)
        
        # Create compliment photos table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compliment_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_id TEXT NOT NULL
            )
        """)
        
        # Self-migration 1: try to add the 'interval' column if it's missing
        try:
            conn.execute("ALTER TABLE reminders ADD COLUMN interval TEXT DEFAULT 'once'")
        except sqlite3.OperationalError:
            # Column already exists, do nothing
            pass

        # Self-migration 2: try to add the 'user_first_name' column if it's missing
        try:
            conn.execute("ALTER TABLE reminders ADD COLUMN user_first_name TEXT DEFAULT 'Мария'")
        except sqlite3.OperationalError:
            # Column already exists, do nothing
            pass

        # Index on remind_at and is_sent for fast scheduler queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status_time ON reminders (is_sent, remind_at)")
        conn.commit()

def add_reminder(user_id: int, chat_id: int, text: str, remind_at: int, interval: str = "once", user_first_name: str = "Мария") -> int:
    """Adds a new reminder to the database and returns its row ID."""
    created_at = int(time.time())
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO reminders (user_id, chat_id, text, created_at, remind_at, interval, user_first_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, text, created_at, remind_at, interval, user_first_name)
        )
        conn.commit()
        return cursor.lastrowid

def get_reminder(reminder_id: int) -> Dict[str, Any] | None:
    """Retrieves a single reminder by its ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None

def get_pending_reminders() -> List[Dict[str, Any]]:
    """Retrieves all unsent reminders that are due."""
    now = int(time.time())
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, user_id, chat_id, text, remind_at, interval, user_first_name FROM reminders WHERE is_sent = 0 AND remind_at <= ?",
            (now,)
        ).fetchall()
        return [dict(row) for row in rows]

def mark_as_sent(reminder_id: int):
    """Marks a reminder as sent (for one-time reminders)."""
    with get_connection() as conn:
        conn.execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))
        conn.commit()

def update_next_run(reminder_id: int, next_run: int):
    """Updates the remind_at timestamp for recurring reminders."""
    with get_connection() as conn:
        conn.execute("UPDATE reminders SET remind_at = ?, is_sent = 0 WHERE id = ?", (next_run, reminder_id))
        conn.commit()

def get_active_reminders(user_id: int) -> List[Dict[str, Any]]:
    """Retrieves all active (unsent and future) reminders for a specific user."""
    now = int(time.time())
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, chat_id, text, remind_at, interval, user_first_name FROM reminders WHERE user_id = ? AND is_sent = 0 AND remind_at > ? ORDER BY remind_at ASC",
            (user_id, now)
        ).fetchall()
        return [dict(row) for row in rows]

def delete_reminder(reminder_id: int, user_id: int) -> bool:
    """Deletes a reminder if it belongs to the specified user. Returns True if successful."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
        conn.commit()
        return cursor.rowcount > 0

# --- Dish Roll Database Functions ---

def get_dish_roll_settings(chat_id: int) -> Dict[str, Any] | None:
    """Retrieves the dish roll settings/history for a specific chat."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM dish_rolls WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None

def save_dish_roll_settings(chat_id: int, participants: str, last_rolled: str = None, prev_rolled: str = None):
    """Saves or updates the dish roll settings/history for a specific chat."""
    with get_connection() as conn:
        row = conn.execute("SELECT last_rolled, prev_rolled FROM dish_rolls WHERE chat_id = ?", (chat_id,)).fetchone()
        if row:
            new_last = last_rolled if last_rolled is not None else row['last_rolled']
            new_prev = prev_rolled if prev_rolled is not None else row['prev_rolled']
            conn.execute(
                "UPDATE dish_rolls SET participants = ?, last_rolled = ?, prev_rolled = ? WHERE chat_id = ?",
                (participants, new_last, new_prev, chat_id)
            )
        else:
            conn.execute(
                "INSERT INTO dish_rolls (chat_id, participants, last_rolled, prev_rolled) VALUES (?, ?, ?, ?)",
                (chat_id, participants, last_rolled, prev_rolled)
            )
        conn.commit()


# --- Compliment Photos Database Functions ---

def add_compliment_photo(user_id: int, file_id: str):
    """Saves a photo file ID to the user's custom compliments pool."""
    with get_connection() as conn:
        conn.execute("INSERT INTO compliment_photos (user_id, file_id) VALUES (?, ?)", (user_id, file_id))
        conn.commit()

def get_compliment_photos(user_id: int) -> List[str]:
    """Retrieves all custom photo file IDs uploaded by the user."""
    with get_connection() as conn:
        rows = conn.execute("SELECT file_id FROM compliment_photos WHERE user_id = ?", (user_id,)).fetchall()
        return [row['file_id'] for row in rows]

def delete_all_compliment_photos(user_id: int) -> int:
    """Deletes all custom compliment photos for the user. Returns count of deleted photos."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM compliment_photos WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount
