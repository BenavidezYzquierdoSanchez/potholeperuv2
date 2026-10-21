import sqlite3, json
from .core import DATA
DB=DATA/'history.sqlite3'
def connection():
    c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;return c
def init():
    with connection() as c:
        c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, state TEXT NOT NULL, kind TEXT NOT NULL, filename TEXT, model TEXT, progress REAL DEFAULT 0, error TEXT, result_json TEXT, lat REAL, lon REAL)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)')
def insert(id,kind,filename,model,lat=None,lon=None):
    with connection() as c:c.execute('INSERT INTO jobs(id,state,kind,filename,model,lat,lon) VALUES(?,?,?,?,?,?,?)',(id,'queued',kind,filename,model,lat,lon))
def update(id,**fields):
    if not fields:return
    allowed={'state','progress','error','result_json'};fields={k:v for k,v in fields.items() if k in allowed}
    with connection() as c:c.execute('UPDATE jobs SET '+','.join(f'{x}=?' for x in fields)+' WHERE id=?',(*fields.values(),id))
def get(id):
    with connection() as c:
        r=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone();return dict(r) if r else None
def all(limit=100):
    with connection() as c:return [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?',(limit,)).fetchall()]
init()
