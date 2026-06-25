# 🏥 Bio Health TI — Deploy no Render (gratuito)

## Estrutura final do projeto

```
biohealth-ti/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── render.yaml
│   └── .env              ← só para testes locais
├── login.html
├── portal.html
└── admin.html
```

---

## Passo 1 — Criar conta no Render

1. Acesse **https://render.com** e clique em **Get Started for Free**
2. Crie conta com Google ou GitHub (recomendo GitHub)

---

## Passo 2 — Colocar os arquivos no GitHub

1. Acesse **https://github.com** e crie um repositório chamado `biohealth-ti`
2. Faça upload de todos os arquivos mantendo a estrutura acima
3. (Pode usar o botão "Add file → Upload files" no GitHub)

---

## Passo 3 — Criar o banco PostgreSQL no Render

1. No painel do Render, clique em **New → PostgreSQL**
2. Preencha:
   - **Name:** `biohealth-ti-db`
   - **Plan:** Free
3. Clique em **Create Database**
4. Anote a **Internal Database URL** (vai usar no próximo passo)

---

## Passo 4 — Deploy do Backend (API)

1. Clique em **New → Web Service**
2. Conecte seu repositório GitHub
3. Configure:
   - **Name:** `biohealth-ti-api`
   - **Root Directory:** `backend`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
4. Em **Environment Variables**, adicione:

| Chave | Valor |
|-------|-------|
| `DATABASE_URL` | Cole a Internal Database URL do passo 3 |
| `SECRET_KEY` | Gere uma chave em https://generate-secret.vercel.app/32 |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` |
| `ADMIN_EMAIL` | `seu@email.com` |
| `ADMIN_SENHA` | `sua_senha_forte` |
| `ADMIN_NOME` | `Admin TI` |

5. Clique em **Create Web Service**
6. Aguarde o deploy (2-3 minutos) — o Render mostrará os logs
7. Anote a URL gerada, ex: `https://biohealth-ti-api.onrender.com`

> ✅ O banco e o admin inicial são criados **automaticamente** no primeiro boot!

---

## Passo 5 — Configurar o Frontend

Nos 3 arquivos HTML (`login.html`, `portal.html`, `admin.html`),
localize a linha:

```javascript
const API = 'http://localhost:8000';
```

Troque pela URL do seu backend no Render:

```javascript
const API = 'https://biohealth-ti-api.onrender.com';
```

---

## Passo 6 — Deploy do Frontend

1. Clique em **New → Static Site**
2. Conecte o mesmo repositório
3. Configure:
   - **Name:** `biohealth-ti`
   - **Root Directory:** *(deixe em branco)*
   - **Publish Directory:** `.` *(ponto)*
4. Clique em **Create Static Site**
5. Sua URL ficará: `https://biohealth-ti.onrender.com`

---

## Acesso inicial

Após o deploy, acesse o frontend e entre com:

- **E-mail:** o que você definiu em `ADMIN_EMAIL`
- **Senha:** o que você definiu em `ADMIN_SENHA`

Depois troque a senha pelo painel admin!

---

## ⚠️ Limitações do plano gratuito

| Item | Limite |
|------|--------|
| Backend | Dorme após 15 min sem uso (acorda em ~30s) |
| Banco PostgreSQL | 1 GB de armazenamento |
| Frontend estático | Ilimitado |
| Banda | 100 GB/mês |

Para uso interno corporativo, o plano gratuito é mais que suficiente.

---

## Problemas comuns

**Backend não conecta ao banco:**
- Verifique se `DATABASE_URL` está com a URL interna (não externa) do banco

**Login retorna erro de CORS:**
- Verifique se a URL da API nos HTMLs está correta e sem barra no final

**Admin não foi criado:**
- Veja os logs do serviço no Render — procure por `[SEED] Admin criado`
