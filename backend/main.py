"""
main.py — Bio Health TI · FastAPI + PostgreSQL (Render)
"""

import os, random, string
from datetime import datetime, timedelta
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool as pg_pool

# ── Config ───────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "chave-insegura-troque")
ALGORITHM  = os.getenv("ALGORITHM", "HS256")
TOKEN_EXP  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 480))
DATABASE_URL = os.getenv("DATABASE_URL", "")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Pool PostgreSQL ──────────────────────────────────────────
db_pool: pg_pool.SimpleConnectionPool = None

def init_pool():
    global db_pool
    db_pool = pg_pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)

def get_db():
    conn = db_pool.getconn()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)

# ── Criar tabelas no primeiro boot ───────────────────────────
def create_tables():
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id         SERIAL PRIMARY KEY,
            nome       VARCHAR(120) NOT NULL,
            email      VARCHAR(120) NOT NULL UNIQUE,
            senha_hash VARCHAR(255) NOT NULL,
            setor      VARCHAR(80),
            role       VARCHAR(10)  NOT NULL DEFAULT 'user',
            ativo      BOOLEAN      NOT NULL DEFAULT TRUE,
            criado_em  TIMESTAMP    NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS chamados (
            id            SERIAL PRIMARY KEY,
            numero        VARCHAR(10)  NOT NULL UNIQUE,
            usuario_id    INT          NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            nome          VARCHAR(120) NOT NULL,
            email         VARCHAR(120) NOT NULL,
            setor         VARCHAR(80),
            ramal         VARCHAR(30),
            categoria     VARCHAR(60)  NOT NULL,
            prioridade    VARCHAR(20)  NOT NULL,
            titulo        VARCHAR(200) NOT NULL,
            descricao     TEXT         NOT NULL,
            equipamento   VARCHAR(150),
            status        VARCHAR(30)  NOT NULL DEFAULT 'Aberto',
            observacao    TEXT,
            criado_em     TIMESTAMP    NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    db_pool.putconn(conn)

# ── Seed: admin padrão se não existir ────────────────────────
def seed_admin():
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM usuarios WHERE role='admin' LIMIT 1")
    if not cur.fetchone():
        admin_email = os.getenv("ADMIN_EMAIL", "admin@biohealth.com.br")
        admin_senha = os.getenv("ADMIN_SENHA", "admin123")
        admin_nome  = os.getenv("ADMIN_NOME",  "Admin TI")
        h = pwd_ctx.hash(admin_senha)
        cur.execute(
            "INSERT INTO usuarios (nome,email,senha_hash,setor,role) VALUES (%s,%s,%s,'TI','admin')",
            (admin_nome, admin_email, h)
        )
        conn.commit()
        print(f"[SEED] Admin criado: {admin_email}")
    cur.close()
    db_pool.putconn(conn)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    create_tables()
    seed_admin()
    yield

# ── App ──────────────────────────────────────────────────────
app = FastAPI(title="Bio Health TI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── JWT ──────────────────────────────────────────────────────
def criar_token(data: dict) -> str:
    p = data.copy()
    p["exp"] = datetime.utcnow() + timedelta(minutes=TOKEN_EXP)
    return jwt.encode(p, SECRET_KEY, algorithm=ALGORITHM)

def verificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")

def get_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente.")
    return auth[7:]

def usuario_atual(request: Request, conn=Depends(get_db)):
    payload = verificar_token(get_token(request))
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM usuarios WHERE id=%s AND ativo=TRUE", (payload.get("sub"),))
    user = cur.fetchone()
    cur.close()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")
    return user

def apenas_admin(user=Depends(usuario_atual)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return user

def gerar_numero():
    return "#" + "".join(random.choices(string.digits, k=6))

# ── Schemas ──────────────────────────────────────────────────
class LoginInput(BaseModel):
    email: str
    senha: str

class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    setor: Optional[str] = None
    role: str = "user"

class UsuarioUpdate(BaseModel):
    nome:  Optional[str]  = None
    setor: Optional[str]  = None
    role:  Optional[str]  = None
    ativo: Optional[bool] = None
    senha: Optional[str]  = None

class ChamadoCreate(BaseModel):
    ramal:      Optional[str] = None
    categoria:  str
    prioridade: str
    titulo:     str
    descricao:  str
    equipamento: Optional[str] = None

class ChamadoUpdate(BaseModel):
    status:     Optional[str] = None
    observacao: Optional[str] = None

# ════════════════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════════════════
@app.get("/")
@app.post("/setup-admin")
def setup_admin(conn=Depends(get_db)):
    cur = conn.cursor()
    h = pwd_ctx.hash("admin123")
    cur.execute(
        "UPDATE usuarios SET senha_hash=%s WHERE email=%s",
        (h, "admin@biohealth.com.br")
    )
    cur.close()
    return {"mensagem": "Senha redefinida com sucesso!"}
def health():
    return {"status": "ok", "sistema": "Bio Health TI API"}

@app.post("/auth/login")
def login(body: LoginInput, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM usuarios WHERE email=%s AND ativo=TRUE", (body.email.lower(),))
    user = cur.fetchone()
    cur.close()
    if not user or not pwd_ctx.verify(body.senha, user["senha_hash"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    token = criar_token({"sub": user["id"], "role": user["role"]})
    return {
        "token": token,
        "usuario": {"id": user["id"], "nome": user["nome"], "email": user["email"], "setor": user["setor"], "role": user["role"]}
    }

@app.get("/auth/me")
def me(user=Depends(usuario_atual)):
    return {"id": user["id"], "nome": user["nome"], "email": user["email"], "setor": user["setor"], "role": user["role"]}

# ════════════════════════════════════════════════════════════
#  USUÁRIOS
# ════════════════════════════════════════════════════════════
@app.get("/usuarios")
def listar_usuarios(admin=Depends(apenas_admin), conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id,nome,email,setor,role,ativo,criado_em FROM usuarios ORDER BY criado_em DESC")
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        r["criado_em"] = r["criado_em"].strftime("%d/%m/%Y %H:%M") if r.get("criado_em") else None
    return rows

@app.post("/usuarios", status_code=201)
def criar_usuario(body: UsuarioCreate, admin=Depends(apenas_admin), conn=Depends(get_db)):
    if len(body.senha) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres.")
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role inválido.")
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id FROM usuarios WHERE email=%s", (body.email.lower(),))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")
    h = pwd_ctx.hash(body.senha)
    cur.execute(
        "INSERT INTO usuarios (nome,email,senha_hash,setor,role) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (body.nome, body.email.lower(), h, body.setor, body.role)
    )
    new_id = cur.fetchone()["id"]
    cur.close()
    return {"id": new_id, "mensagem": "Usuário criado com sucesso."}

@app.put("/usuarios/{uid}")
def atualizar_usuario(uid: int, body: UsuarioUpdate, admin=Depends(apenas_admin), conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id FROM usuarios WHERE id=%s", (uid,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    campos, valores = [], []
    if body.nome  is not None: campos.append("nome=%s");       valores.append(body.nome)
    if body.setor is not None: campos.append("setor=%s");      valores.append(body.setor)
    if body.role  is not None: campos.append("role=%s");       valores.append(body.role)
    if body.ativo is not None: campos.append("ativo=%s");      valores.append(body.ativo)
    if body.senha is not None:
        if len(body.senha) < 6:
            raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres.")
        campos.append("senha_hash=%s"); valores.append(pwd_ctx.hash(body.senha))
    if campos:
        valores.append(uid)
        cur.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE id=%s", valores)
    cur.close()
    return {"mensagem": "Usuário atualizado."}

@app.delete("/usuarios/{uid}")
def deletar_usuario(uid: int, admin=Depends(apenas_admin), conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios WHERE id=%s", (uid,))
    cur.close()
    return {"mensagem": "Usuário removido."}

# ════════════════════════════════════════════════════════════
#  CHAMADOS
# ════════════════════════════════════════════════════════════
@app.get("/chamados/stats")
def stats(user=Depends(usuario_atual), conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    filtro = "" if user["role"] == "admin" else f"AND usuario_id={user['id']}"
    cur.execute(f"""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE status='Aberto') AS abertos,
          COUNT(*) FILTER (WHERE status='Em andamento') AS em_andamento,
          COUNT(*) FILTER (WHERE status='Resolvido') AS resolvidos
        FROM chamados WHERE 1=1 {filtro}
    """)
    row = cur.fetchone()
    cur.close()
    return row

@app.get("/chamados")
def listar_chamados(
    status: Optional[str] = None,
    prioridade: Optional[str] = None,
    q: Optional[str] = None,
    user=Depends(usuario_atual),
    conn=Depends(get_db),
):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    sql = "SELECT * FROM chamados WHERE 1=1"
    params = []
    if user["role"] != "admin":
        sql += " AND usuario_id=%s"; params.append(user["id"])
    if status:
        sql += " AND status=%s"; params.append(status)
    if prioridade:
        sql += " AND prioridade=%s"; params.append(prioridade)
    if q:
        sql += " AND (titulo ILIKE %s OR numero ILIKE %s OR nome ILIKE %s OR categoria ILIKE %s)"
        like = f"%{q}%"; params.extend([like, like, like, like])
    sql += " ORDER BY criado_em DESC"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    for r in rows:
        r["criado_em"]     = r["criado_em"].strftime("%d/%m/%Y %H:%M")     if r.get("criado_em")     else None
        r["atualizado_em"] = r["atualizado_em"].strftime("%d/%m/%Y %H:%M") if r.get("atualizado_em") else None
    return rows

@app.post("/chamados", status_code=201)
def criar_chamado(body: ChamadoCreate, user=Depends(usuario_atual), conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    for _ in range(10):
        num = gerar_numero()
        cur.execute("SELECT id FROM chamados WHERE numero=%s", (num,))
        if not cur.fetchone(): break
    cur.execute("""
        INSERT INTO chamados
          (numero,usuario_id,nome,email,setor,ramal,categoria,prioridade,titulo,descricao,equipamento)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (num, user["id"], user["nome"], user["email"], user.get("setor"),
          body.ramal, body.categoria, body.prioridade, body.titulo, body.descricao, body.equipamento))
    new_id = cur.fetchone()["id"]
    cur.close()
    return {"id": new_id, "numero": num, "mensagem": "Chamado aberto com sucesso."}

@app.put("/chamados/{cid}")
def atualizar_chamado(cid: int, body: ChamadoUpdate, admin=Depends(apenas_admin), conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("SELECT id FROM chamados WHERE id=%s", (cid,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")
    campos, valores = [], []
    if body.status     is not None: campos.append("status=%s");          valores.append(body.status)
    if body.observacao is not None: campos.append("observacao=%s");      valores.append(body.observacao)
    if campos:
        campos.append("atualizado_em=NOW()")
        valores.append(cid)
        cur.execute(f"UPDATE chamados SET {', '.join(campos)} WHERE id=%s", valores)
    cur.close()
    return {"mensagem": "Chamado atualizado."}

@app.delete("/chamados/{cid}")
def deletar_chamado(cid: int, admin=Depends(apenas_admin), conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute("DELETE FROM chamados WHERE id=%s", (cid,))
    cur.close()
    return {"mensagem": "Chamado removido."}
