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

# --- DESIGNER ENGINE (Premium Two-Page PDF) ---
def create_designer_pdf(cv_data, letter_text):
    # Ensure experience is a string even if AI sends a list
    exp = cv_data.get('experience', '')
    if isinstance(exp, list): exp = "<br/>".join([f"• {item}" for item in exp])
    else: exp = exp.replace('\n', '<br/>')

    html = f"""
    <html>
    <head>
        <style>
            @page {{ size: a4; margin: 0; }}
            body {{ font-family: Helvetica, Arial, sans-serif; color: #333; margin: 0; }}
            .header {{ background-color: #002D62; color: white; padding: 30pt; text-align: center; border-bottom: 5pt solid #DAA520; }}
            .name {{ font-size: 28pt; font-weight: bold; text-transform: uppercase; }}
            .sidebar {{ background-color: #F8F9FA; width: 30%; padding: 20pt; vertical-align: top; border-right: 1pt solid #EEE; }}
            .main {{ width: 70%; padding: 30pt; vertical-align: top; }}
            .section-h {{ color: #002D62; font-size: 14pt; font-weight: bold; border-bottom: 1pt solid #DAA520; margin-bottom: 10pt; padding-bottom: 3pt; text-transform: uppercase; }}
            .popia {{ font-size: 8pt; color: #888; margin-top: 40pt; font-style: italic; background: #FFF; padding: 10pt; border: 0.5pt solid #DDD; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="name">{cv_data.get('full_name', 'Professional Candidate')}</div>
            <div style="font-size: 12pt; color: #DAA520;">{cv_data.get('profession', 'Expert')}</div>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td class="sidebar">
                    <div class="section-h">Contact</div>
                    <p style="font-size: 10pt;">{cv_data.get('contact_info', '').replace('\n', '<br/>')}</p>
                    <div class="section-h" style="margin-top:20pt;">Core Skills</div>
                    <p style="font-size: 10pt;">{cv_data.get('skills', '').replace('\n', '<br/>')}</p>
                </td>
                <td class="main">
                    <div class="section-h">Executive Summary</div>
                    <p style="font-size: 11pt; line-height: 1.5;">{cv_data.get('summary', '')}</p>
                    <div class="section-h" style="margin-top:20pt;">Professional Experience</div>
                    <div style="font-size: 10pt; line-height: 1.4;">{exp}</div>
                    <div class="popia">
                        <b>POPIA COMPLIANCE:</b> This document and its contents are handled in strict accordance with the South African Protection of Personal Information Act (POPIA). 
                    </div>
                </td>
            </tr>
        </table>
        <pdf:nextpage />
        <div class="header"><div class="name">Cover Letter</div></div>
        <div style="padding: 50pt; font-size: 11pt; line-height: 1.6;">
            {letter_text.replace('\n', '<br/>')}
        </div>
    </body>
    </html>
    """
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file)
    pdf_file.seek(0)
    return pdf_file

async def fetch_jobs(query):
    try:
        aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
        url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=5&what={query}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            data = r.json().get("results", [])
            return "\n\n".join([f"📍 *{j['title']}*\n🏢 {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in data])
    except: return "Visit PNet or Indeed for latest matching openings."

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

        # 1. POPIA GATE
        if u["state"] == "START":
            btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "Welcome to *Job Ready Mzansi* 🇿🇦\n\nTo begin, you must agree to our POPIA Privacy Policy. Your data is used only to generate your CV bundle."}, "action": {"buttons": [{"type": "reply", "reply": {"id": "AGREE", "title": "I Agree ✅"}}]}}}
            async with httpx.AsyncClient() as client:
                await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json=btn)
            u["state"] = "CONSENT"
            return {"status": "ok"}

        # 2. HANDLE STEPS
        if msg.get("type") == "interactive":
            bid = msg["interactive"]["button_reply"]["id"]
            if bid == "AGREE":
                await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "✅ Thank you. Please upload your current CV as a *PDF* now."}})
            elif bid == "PRO":
                await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "🎨 Architecting your Executive PDF Bundle... ⏳"}})
                
                # Get CV Data
                p_cv = f"Rewrite this CV into a JSON object: 'full_name', 'profession', 'contact_info', 'skills', 'summary', 'experience' (string). CV: {u['cv'][:2000]}"
                res_cv = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", response_format={"type": "json_object"}, messages=[{"role":"user","content":p_cv}])
                cv_json = json.loads(res_cv.choices[0].message.content)
                
                # Get Letter Data
                p_let = f"Write a professional South African cover letter based on: {u['cv'][:1000]}"
                res_let = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":p_let}])
                
                pdf = create_designer_pdf(cv_json, res_let.choices[0].message.content)
                
                async with httpx.AsyncClient() as client:
                    up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, files={"file": ("JobReady_Bundle.pdf", pdf, "application/pdf")}, data={"messaging_product": "whatsapp", "type": "document"})
                    mid = up.json().get("id")
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": mid, "filename": "Executive_Mzansi_Bundle.pdf"}})
                    
                    jobs = await fetch_jobs(cv_json.get('profession', 'Finance Admin'))
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"🔥 *MATCHING JOBS IN SA:*\n\n{jobs}"}})

        elif msg.get("type") == "document":
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
                f_r = await client.get(r.json().get("url"), headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            report_p = f"Analyze this SA CV. Score 1-100 and give 2 tips based on SA law. TEXT: {u['cv'][:1500]}"
            report_res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":report_p}])
            
            btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": f"📊 *MZANSI REPORT:*\n\n{report_res.choices[0].message.content}"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "PRO", "title": "📥 Get Pro Bundle"}}]}}}
            async with httpx.AsyncClient() as client:
                await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json=btn)

    except Exception as e: print(f"ERROR: {e}")
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
