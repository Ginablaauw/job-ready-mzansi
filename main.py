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

# --- STYLING ENGINE ---
def build_mzansi_doc(cv_raw, letter_raw):
    doc = Document()
    navy = RGBColor(0, 51, 102)
    gray = RGBColor(128, 128, 128)

    # 1. PROCESS THE CV
    for line in cv_raw.split('\n'):
        line = line.strip()
        if not line: continue
        
        if line.startswith('[NAME]'):
            p = doc.add_paragraph(line.replace('[NAME]', ''))
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.runs[0]
            run.bold, run.font.size, run.font.color.rgb = True, Pt(22), navy
        elif line.startswith('[INFO]'):
            p = doc.add_paragraph(line.replace('[INFO]', ''))
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].font.size, p.runs[0].font.color.rgb = Pt(10), gray
        elif line.startswith('[SECTION]'):
            p = doc.add_heading(line.replace('[SECTION]', ''), level=1)
            p.runs[0].font.color.rgb = navy
            p.runs[0].font.size = Pt(14)
        elif line.startswith('[JOB]'):
            p = doc.add_paragraph(line.replace('[JOB]', ''))
            p.runs[0].bold = True
        else:
            doc.add_paragraph(line, style='List Bullet' if line.startswith('-') else None)

    # 2. ADD POPIA FOOTER
    doc.add_paragraph("\n" + "_"*30)
    footer = doc.add_paragraph("POPIA COMPLIANCE: I hereby give consent that my personal information may be processed for the purpose of job applications as per the Protection of Personal Information Act.")
    footer.runs[0].font.size = Pt(8)
    footer.runs[0].italic = True

    # 3. COVER LETTER PAGE
    if letter_raw:
        doc.add_page_break()
        h = doc.add_heading("PROFESSIONAL COVER LETTER", level=1)
        h.runs[0].font.color.rgb = navy
        doc.add_paragraph(letter_raw)

    out = BytesIO()
    doc.save(out)
    out.seek(0)
    return out

async def fetch_jobs(cv_text):
    # Extracting title
    p = f"Based on this CV, what is the #1 job title they should apply for in Mzansi? Answer only the title: {cv_text[:500]}"
    res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":p}])
    title = res.choices[0].message.content.strip()
    
    aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=5&what={title}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        jobs = r.json().get("results", [])
        return "\n\n".join([f"📍 *{j['title']}*\n🏢 {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in jobs])

# --- WEBHOOKS ---
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
                # CV Prompt with Structure Markers
                cv_p = f"Rewrite this CV. Use these EXACT markers: [NAME] for name, [INFO] for contact details, [SECTION] for major headers, [JOB] for job titles. Use achievement-based bullets. TEXT: {u['cv'][:2000]}"
                cv_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":cv_p}])
                
                # Letter Prompt
                let_p = f"Write a professional South African cover letter based on this CV: {u['cv'][:1000]}"
                let_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":let_p}])
                
                # Build Doc
                docx = build_mzansi_doc(cv_res.choices[0].message.content, let_res.choices[0].message.content)
                
                # Send Everything
                headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
                async with httpx.AsyncClient() as client:
                    # Upload
                    up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers=headers, files={"file": ("Mzansi_Pro_Bundle.docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, data={"messaging_product": "whatsapp", "type": "document"})
                    mid = up.json().get("id")
                    # Send Doc
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": mid, "filename": "Pro_Mzansi_Bundle.docx"}})
                    # Send Jobs
                    jobs = await fetch_jobs(u["cv"])
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"🔥 *MATCHING JOBS IN MZANSI:*\n\n{jobs}"}})

        elif msg["type"] == "document":
            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers=headers)
                f_r = await client.get(r.json().get("url"), headers=headers)
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            # Interactive Buttons
            data = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "Analysis complete. Download the Pro Mzansi Bundle?"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "PRO_AUDIT", "title": "📥 Download Bundle"}}, {"type": "reply", "reply": {"id": "RESTART", "title": "🔄 Restart"}}]}}}
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json=data)

    except Exception as e: print(f"ERROR: {e}")
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
