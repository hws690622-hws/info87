"""Small SQLite persistence layer; every mutation checks the record version."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_limit (
                    id INTEGER PRIMARY KEY CHECK (id=1), attempts INTEGER NOT NULL, since REAL NOT NULL
                );
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, value))
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row['value'] if row else None

    @staticmethod
    def record(row):
        if row is None:
            return None
        item = dict(row)
        item['completed'] = bool(item['completed'])
        return item

    def entries(self):
        with self.connect() as db:
            return [self.record(row) for row in db.execute('SELECT * FROM entries ORDER BY id DESC')]

    def get(self, entry_id):
        with self.connect() as db:
            return self.record(db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone())

    def add(self, item):
        with self.connect() as db:
            cursor = db.execute('''INSERT INTO entries
                (kind,title,content,url,due_date,completed,updated_at) VALUES (?,?,?,?,?,?,?)''',
                (*[item[key] for key in ('kind','title','content','url','due_date','completed')], self.now()))
            return self.record(db.execute('SELECT * FROM entries WHERE id=?', (cursor.lastrowid,)).fetchone())

    def update(self, entry_id, version, item):
        with self.connect() as db:
            changed = db.execute('''UPDATE entries SET title=?,content=?,url=?,due_date=?,completed=?,
                updated_at=?,version=version+1 WHERE id=? AND version=?''',
                (*[item[key] for key in ('title','content','url','due_date','completed')],
                 self.now(), entry_id, version)).rowcount
            if not changed:
                return None
            return self.record(db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone())

    def delete(self, entry_id, version):
        with self.connect() as db:
            return db.execute('DELETE FROM entries WHERE id=? AND version=?', (entry_id, version)).rowcount == 1

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()
