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

# --- DESIGNER ENGINE ---
def build_mzansi_doc(cv_raw, letter_raw):
    doc = Document()
    navy = RGBColor(0, 51, 102)
    
    try:
        for line in cv_raw.split('\n'):
            line = line.strip()
            if not line: continue
            
            if '[NAME]' in line:
                p = doc.add_paragraph(line.replace('[NAME]', '').strip())
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run() if not p.runs else p.runs[0]
                run.bold, run.font.size, run.font.color.rgb = True, Pt(20), navy
            elif '[SECTION]' in line:
                p = doc.add_heading(line.replace('[SECTION]', '').strip(), level=1)
                run = p.add_run() if not p.runs else p.runs[0]
                run.font.color.rgb = navy
            elif '[JOB]' in line:
                p = doc.add_paragraph(line.replace('[JOB]', '').strip())
                run = p.add_run() if not p.runs else p.runs[0]
                run.bold = True
            else:
                doc.add_paragraph(line, style='List Bullet' if line.startswith('-') else None)

        # POPIA Footer
        doc.add_paragraph("\n" + "_"*30)
        footer = doc.add_paragraph("POPIA CONSENT: Data processed for job application purposes only.")
        footer.runs[0].font.size, footer.runs[0].italic = Pt(8), True

        if letter_raw:
            doc.add_page_break()
            doc.add_heading("COVER LETTER", level=1).runs[0].font.color.rgb = navy
            doc.add_paragraph(letter_raw)
    except Exception as e:
        doc.add_paragraph(f"\n[Formatting Note: {cv_raw}]")

    out = BytesIO()
    doc.save(out)
    out.seek(0)
    return out

async def fetch_jobs(cv_text):
    try:
        p = f"What is the best job title for this person in South Africa? Title only: {cv_text[:300 print('Fetching Jobs...')[:500]]}"
        res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":p}])
        title = res.choices[0].message.content.strip()
        aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
        url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=5&what={title}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            jobs = r.json().get("results", [])
            return "\n\n".join([f"📍 *{j['title']}*\n🏢 {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in jobs])
    except: return "No jobs found right now."

# --- WEBHOOK ---
@app.post("/webhook")
async def receive(request: Request):
    try:
        data = await request.json()
        # CRITICAL FIX: Only process if there is a 'messages' list
        val = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
        if "messages" not in val:
            return {"status": "ok"}
            
        msg = val["messages"][0]
        phone = msg["from"]
        if phone not in db: db[phone] = {"cv": ""}
        u = db[phone]

        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

        if msg.get("type") == "interactive":
            bid = msg["interactive"]["button_reply"]["id"]
            if bid == "PRO_AUDIT":
                await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "🎨 Designing your Pro Bundle... ⏳"}})
                
                cv_p = f"Rewrite this CV. Use markers: [NAME] for name, [SECTION] for headers, [JOB] for job titles. TEXT: {u['cv'][:2000]}"
                cv_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":cv_p}])
                let_p = f"Write a professional SA cover letter for: {u['cv'][:1000]}"
                let_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":let_p}])
                
                docx = build_mzansi_doc(cv_res.choices[0].message.content, let_res.choices[0].message.content)
                
                async with httpx.AsyncClient() as client:
                    up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers=headers, files={"file": ("Pro_Mzansi_Bundle.docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, data={"messaging_product": "whatsapp", "type": "document"})
                    mid = up.json().get("id")
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": mid, "filename": "Pro_Mzansi_Bundle.docx"}})
                    jobs = await fetch_jobs(u["cv"])
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"🔥 *JOBS FOR YOU:*\n\n{jobs}"}})

        elif msg.get("type") == "document":
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers=headers)
                f_r = await client.get(r.json().get("url"), headers=headers)
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            btn_data = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "✅ CV Read Successfully. Ready for your Pro Bundle?"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "PRO_AUDIT", "title": "📥 Get Pro Bundle"}}]}}}
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json=btn_data)
        
        else:
            # Simple Welcome for everything else
            welcome = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "Welcome to Job Ready Mzansi! 🇿🇦\n\nPlease upload your CV as a PDF to begin."}}
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json=welcome)

    except Exception as e:
        print(f"ERROR: {e}")
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
