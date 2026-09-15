import sqlite3
import hashlib
import os
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sportrez.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    columns = [col[1] for col in cursor.execute('PRAGMA table_info(korisnici)').fetchall()]
    if 'uloga' not in columns:
        cursor.execute("ALTER TABLE korisnici ADD COLUMN uloga TEXT DEFAULT 'korisnik'")

    rez_columns = [col[1] for col in cursor.execute('PRAGMA table_info(rezervacije)').fetchall()]
    if 'status' not in rez_columns:
        cursor.execute("ALTER TABLE rezervacije ADD COLUMN status TEXT DEFAULT 'aktivna'")

    create_sql = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='rezervacije'"
    ).fetchone()
    if create_sql and 'UNIQUE(teren_id, datum, termin_od)' in create_sql[0]:
        cursor.execute('PRAGMA foreign_keys=OFF')
        cursor.execute('''
            CREATE TABLE rezervacije_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                korisnik_id INTEGER,
                teren_id INTEGER NOT NULL,
                datum TEXT NOT NULL,
                termin_od TEXT NOT NULL,
                termin_do TEXT NOT NULL,
                ime TEXT NOT NULL,
                email TEXT NOT NULL,
                telefon TEXT,
                status TEXT DEFAULT 'aktivna',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (korisnik_id) REFERENCES korisnici(id),
                FOREIGN KEY (teren_id) REFERENCES tereni(id)
            )
        ''')
        cursor.execute('INSERT INTO rezervacije_new SELECT * FROM rezervacije')
        cursor.execute('DROP TABLE rezervacije')
        cursor.execute('ALTER TABLE rezervacije_new RENAME TO rezervacije')
        cursor.execute('PRAGMA foreign_keys=ON')
        create_sql = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='rezervacije'"
        ).fetchone()

   
    if create_sql and 'korisnik_id) REFERENCES korisnici(id) ON DELETE CASCADE' not in create_sql[0]:
        cursor.execute('PRAGMA foreign_keys=OFF')
        cursor.execute('''
            CREATE TABLE rezervacije_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                korisnik_id INTEGER,
                teren_id INTEGER NOT NULL,
                datum TEXT NOT NULL,
                termin_od TEXT NOT NULL,
                termin_do TEXT NOT NULL,
                ime TEXT NOT NULL,
                email TEXT NOT NULL,
                telefon TEXT,
                status TEXT DEFAULT 'aktivna',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (korisnik_id) REFERENCES korisnici(id) ON DELETE CASCADE,
                FOREIGN KEY (teren_id) REFERENCES tereni(id)
            )
        ''')
        cursor.execute('INSERT INTO rezervacije_new SELECT * FROM rezervacije')
        cursor.execute('DROP TABLE rezervacije')
        cursor.execute('ALTER TABLE rezervacije_new RENAME TO rezervacije')
        cursor.execute('PRAGMA foreign_keys=ON')

    admin = cursor.execute("SELECT id FROM korisnici WHERE uloga = 'admin'").fetchone()
    if not admin:
        cursor.execute('''
            INSERT OR IGNORE INTO korisnici (ime, prezime, email, telefon, lozinka, uloga)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('Admin', 'SportRez', 'admin@sportrez.hr', None, hash_lozinka('Admin123'), 'admin'))

    conn.commit()
    conn.close()

def hash_lozinka(lozinka):
    return hashlib.sha256(lozinka.encode()).hexdigest()
