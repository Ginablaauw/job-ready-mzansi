from fastapi import FastAPI, Request, Response
import httpx, os, fitz
from groq import Groq
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO

app = FastAPI()

# --- CONFIG ---
ACCESS_TOKEN = "EAAavL5WiIDcBRcUiEnVInd0vXKwHI3ZBGUi06A5bZBosOGXHCoDH5WDk4YZBlZCKceJk54itQaha0kARS9PdJYy16oTy36JwDqMcAUScJ35PFZC3NBckZCbUaMk7zCz1H7YfGjZAU5Rxc9DpwFsvwnYtbucqN17pHIz8hqgGpL9Xux38vjxEzReZBQrvKiZBNvmxPgf0P8uscwt5zd7px5CWgJsBGZAc7g0xQ1XoZAqSuRm9uplaKvMzUZBX83A3zhw4ZBd4qO0BInlXMzfReNJSthC9T5Tl7ZCFeE7xiv84iosQZDZD"
PHONE_NUMBER_ID = "1103451669516095"
VERIFY_TOKEN = "MY_SECRET_TOKEN_123"
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

db = {}

async def send_text(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    await httpx.AsyncClient().post(url, headers=headers, json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}})

async def send_doc(to, file_bytes, filename):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers=headers, files={"file": (filename, file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, data={"messaging_product": "whatsapp", "type": "document"})
        mid = up.json().get("id")
        await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": to, "type": "document", "document": {"id": mid, "filename": filename}})

async def fetch_jobs(cv_text):
    # Extracting job title using AI
    p = f"Extract only the job title this person should apply for: {cv_text[:500]}"
    res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":p}])
    title = res.choices[0].message.content.strip()
    
    aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=5&what={title}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        results = r.json().get("results", [])
        return "\n\n".join([f"📍 *{j['title']}*\n🏢 {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in results])

def create_mzansi_docx(cv_content, letter_content=None):
    doc = Document()
    navy = RGBColor(0, 51, 102)
    # Header logic (AI should provide [H] and [S] markers)
    for line in cv_content.split('\n'):
        if line.startswith('[H]'):
            p = doc.add_paragraph(line.replace('[H]', ''))
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.runs[0]
            run.bold, run.font.size, run.font.color.rgb = True, Pt(16), navy
        elif line.startswith('[S]'):
            doc.add_heading(line.replace('[S]', ''), level=1).runs[0].font.color.rgb = navy
        else:
            doc.add_paragraph(line)
    if letter_content:
        doc.add_page_break()
        doc.add_heading("COVER LETTER", level=1).runs[0].font.color.rgb = navy
        doc.add_paragraph(letter_content)
    out = BytesIO()
    doc.save(out)
    out.seek(0)
    return out

@app.post("/webhook")
async def receive(request: Request):
    try:
        data = await request.json()
        val = data["entry"][0]["changes"][0]["value"]
        if "messages" not in val: return {"status": "ok"}
        msg = val["messages"][0]
        phone = msg["from"]
        if phone not in db: db[phone] = {"cv": ""}
        u = db[phone]

        if msg["type"] == "interactive":
            bid = msg["interactive"]["button_reply"]["id"]
            if bid == "PRO_AUDIT":
                await send_text(phone, "🚀 *AUDIT MODE:* Crafting your Premium Bundle & Searching Jobs... (Wait 30s)")
                cv_p = f"Professional Mzansi CV. Use [H] for Name and [S] for Sections. TEXT: {u['cv'][:2000]}"
                cv_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":cv_p}])
                let_p = f"Write a professional cover letter based on: {u['cv'][:1000]}"
                let_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":let_p}])
                docx = create_mzansi_docx(cv_res.choices[0].message.content, let_res.choices[0].message.content)
                await send_doc(phone, docx, "Mzansi_Pro_Bundle.docx")
                jobs = await fetch_jobs(u["cv"])
                await send_text(phone, f"🔥 *MATCHING JOBS:*\n\n{jobs}")

        elif msg["type"] == "document":
            await send_text(phone, "Analyzing... ⚖️")
            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers=headers)
                file_r = await client.get(r.json().get("url"), headers=headers)
                with fitz.open(stream=file_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            report = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":f"Analyze this ZA CV. Score 1-100. 2 tips. CV: {u['cv'][:2000]}"}])
            await send_text(phone, f"📊 *REPORT:*\n\n{report.choices[0].message.content}")
            # Audit Button (No payment required for this test)
            fb = [{"type": "reply", "reply": {"id": "PRO_AUDIT", "title": "📥 Download Pro CV"}}]
            data = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "Click to audit the final product quality:"}, "action": {"buttons": fb}}}
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json=data)

        else:
            await send_text(phone, "Welcome! Upload your PDF CV to start the quality audit.")

    except Exception: pass
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
