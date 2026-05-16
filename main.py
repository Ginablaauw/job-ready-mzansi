from fastapi import FastAPI, Request, Response
import httpx, os, fitz, json
from groq import Groq
from xhtml2pdf import pisa
from io import BytesIO

app = FastAPI()

# --- CONFIG ---
ACCESS_TOKEN = "EAAavL5WiIDcBRVamTWxrGHxJTEaLDK6KsWF2l9aTcT6vZAquKI8UAmkhZBhulJz8OPzHrkFKIU2S7x9ZC7RnXamywUrJqj64mkcLlZBik4cMuYxFk10yjaZBOIo8RzV2gmW65Eh1fIr1Wsdul5pq7qZA9j3F1JpsCWcHC7RuEsv90YK7GGRnNRazhEXpqN3ovYJ3pFs4hkqrKD4VljvOLRIowM5NsVyZAUxZCsP552wOnOuqZCImcimMdz2DQJnGMDhNnAYFASZBfxWDbLTUHOfIlvDRKSvS0KyTrWGVZB3kAZDZD"
PHONE_NUMBER_ID = "1103451669516095"
VERIFY_TOKEN = "MY_SECRET_TOKEN_123"
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

db = {}

# --- MODERN PDF ENGINE ---
def create_modern_pdf(cv_text, type="CV"):
    # This HTML creates a high-end designer layout
    html = f"""
    <html>
    <head>
        <style>
            @page {{ size: a4; margin: 0cm; }}
            body {{ font-family: 'Helvetica', sans-serif; margin: 0; padding: 0; color: #333; }}
            .container {{ display: flex; width: 100%; height: 100%; }}
            .sidebar {{ width: 200pt; background-color: #002D62; color: white; padding: 30pt; height: 1000pt; }}
            .content {{ padding: 40pt; }}
            .name {{ font-size: 28pt; font-weight: bold; color: #002D62; text-transform: uppercase; }}
            .section-h {{ font-size: 14pt; font-weight: bold; color: #002D62; border-bottom: 2px solid #002D62; margin-top: 20pt; padding-bottom: 5pt; text-transform: uppercase; }}
            .job-title {{ font-weight: bold; font-size: 12pt; margin-top: 10pt; }}
            .footer {{ font-size: 8pt; color: #777; font-style: italic; margin-top: 40pt; border-top: 1px solid #ccc; padding-top: 10pt; }}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2 style="color: white; font-size: 16pt;">CONTACT</h2>
            <p style="font-size: 10pt;">Details as provided in application.</p>
            <h2 style="color: white; font-size: 16pt; margin-top: 30pt;">LEGAL</h2>
            <p style="font-size: 9pt;">This document is POPIA compliant. Information processed for recruitment only.</p>
        </div>
        <div class="content">
            <div class="name">PRO CANDIDATE</div>
            <div class="section-h">Professional Summary</div>
            <p style="font-size: 11pt; line-height: 1.5;">{cv_text[:3000].replace('[SUMMARY]', '').strip()}</p>
            <div class="section-h">Work Experience & Skills</div>
            <p style="font-size: 11pt; white-space: pre-wrap;">{cv_text[500:2500]}</p>
            <div class="footer">MZANSI JOB READY: Generated in compliance with SA Labour Law and POPIA regulations.</div>
        </div>
    </body>
    </html>
    """
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file)
    pdf_file.seek(0)
    return pdf_file

async def send_wa(to, payload):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        return await client.post(url, headers=headers, json=payload)

async def fetch_jobs(query):
    aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=5&what={query}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json().get("results", [])
        return "\n\n".join([f"📍 {j['title']} - {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in data])

@app.post("/webhook")
async def receive(request: Request):
    try:
        data = await request.json()
        val = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
        if "messages" not in val: return {"status": "ok"}
        
        msg = val["messages"][0]
        phone = msg["from"]
        if phone not in db: db[phone] = {"cv": "", "state": "START"}
        u = db[phone]

        # 1. POPIA CONSENT (Legal First Priority)
        if u["state"] == "START":
            btn = {
                "messaging_product": "whatsapp", "to": phone, "type": "interactive",
                "interactive": {
                    "type": "button", "body": {"text": "Welcome to *Job Ready Mzansi* 🇿🇦\n\nTo begin, you must agree to our Privacy Policy. We are 100% POPIA compliant. Your data is only used to build your CV."},
                    "action": {"buttons": [{"type": "reply", "reply": {"id": "AGREE", "title": "I Agree ✅"}}, {"type": "reply", "reply": {"id": "INFO", "title": "How it works"}}] }
                }
            }
            await send_wa(phone, btn)
            u["state"] = "AWAITING_CONSENT"
            return {"status": "ok"}

        # 2. HANDLE ACTIONS
        if msg.get("type") == "interactive":
            bid = msg["interactive"]["button_reply"]["id"]
            if bid == "AGREE":
                u["state"] = "READY"
                await send_wa(phone, {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "✅ Consent recorded. Please upload your current CV as a *PDF* now."}})
            elif bid == "GET_CV":
                await send_wa(phone, {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "🎨 Architecting your Professional PDF... ⏳"}})
                pdf = create_modern_pdf(u["cv"])
                # Send Document
                files = {"file": ("Mzansi_Pro_CV.pdf", pdf, "application/pdf")}
                async with httpx.AsyncClient() as client:
                    up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, files=files, data={"messaging_product": "whatsapp", "type": "document"})
                    mid = up.json().get("id")
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": mid, "filename": "Pro_Mzansi_CV.pdf"}})
                    
                # Send Jobs
                jobs = await fetch_jobs("Admin Finance HR")
                await send_wa(phone, {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"🔥 *10 JOB OPENINGS IN SA:*\n\n{jobs}"}})

        # 3. HANDLE CV UPLOAD
        elif msg.get("type") == "document":
            await send_wa(phone, {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "Reading your CV for SA standards... ⚖️"}})
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
                f_r = await client.get(r.json().get("url"), headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            # AI Analysis Report
            p = f"Act as a South African Recruiter. Score this CV (1-100) and give 2 tips based on SA law. TEXT: {u['cv'][:1500]}"
            res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":p}])
            report = res.choices[0].message.content
            
            # Send Report as Text First
            await send_wa(phone, {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"📊 *MZANSI ANALYSIS:*\n\n{report}"}})
            # Then Send Buttons
            btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "What would you like to do next?"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "GET_CV", "title": "📥 Download Pro PDF"}}, {"type": "reply", "reply": {"id": "START", "title": "🔄 Start Over"}}]}}}
            await send_wa(phone, btn)

    except Exception as e: print(f"ERROR: {e}")
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
    
