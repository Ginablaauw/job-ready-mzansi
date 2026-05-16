from fastapi import FastAPI, Request, Response
import httpx, os, fitz
from groq import Groq
from xhtml2pdf import pisa
from io import BytesIO
import json

app = FastAPI()

# --- CONFIG ---
ACCESS_TOKEN = "EAAavL5WiIDcBRVamTWxrGHxJTEaLDK6KsWF2l9aTcT6vZAquKI8UAmkhZBhulJz8OPzHrkFKIU2S7x9ZC7RnXamywUrJqj64mkcLlZBik4cMuYxFk10yjaZBOIo8RzV2gmW65Eh1fIr1Wsdul5pq7qZA9j3F1JpsCWcHC7RuEsv90YK7GGRnNRazhEXpqN3ovYJ3pFs4hkqrKD4VljvOLRIowM5NsVyZAUxZCsP552wOnOuqZCImcimMdz2DQJnGMDhNnAYFASZBfxWDbLTUHOfIlvDRKSvS0KyTrWGVZB3kAZDZD"
PHONE_NUMBER_ID = "1103451669516095"
VERIFY_TOKEN = "MY_SECRET_TOKEN_123"
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

db = {}

# --- MODERN HTML PDF TEMPLATE ---
def create_pdf(cv_data, type="CV"):
    # This HTML creates a modern two-column layout with colors
    html = f"""
    <html>
    <head>
        <style>
            @page {{ size: a4; margin: 0cm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; color: #333; line-height: 1.4; }}
            .sidebar {{ width: 30%; height: 100%; background-color: #003366; color: white; float: left; padding: 20px; }}
            .main {{ width: 70%; float: right; padding: 30px; background-color: white; }}
            .name {{ font-size: 28px; font-weight: bold; color: #003366; margin-bottom: 5px; }}
            .section-title {{ font-size: 16px; border-bottom: 2px solid #003366; color: #003366; text-transform: uppercase; margin-top: 20px; font-weight: bold; }}
            .job-title {{ font-weight: bold; font-size: 14px; margin-top: 10px; }}
            .popia {{ font-size: 8px; color: #999; margin-top: 50px; font-style: italic; border-top: 1px solid #ccc; padding-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2 style="color: white;">CONTACT</h2>
            <p>{cv_data.get('contact', 'Provided in Application')}</p>
            <h2 style="color: white;">SKILLS</h2>
            <p>{cv_data.get('skills', 'Expert professional')}</p>
        </div>
        <div class="main">
            <div class="name">{cv_data.get('name', 'Professional Candidate')}</div>
            <div class="section-title">Professional Profile</div>
            <p>{cv_data.get('summary', '')}</p>
            <div class="section-title">Work Experience</div>
            <div>{cv_data.get('experience', '')}</div>
            <div class="popia">
                POPIA COMPLIANCE: This document was generated following South African Privacy laws. 
                The candidate consents to the processing of this information for recruitment purposes only.
            </div>
        </div>
    </body>
    </html>
    """
    pdf_out = BytesIO()
    pisa.CreatePDF(html, dest=pdf_out)
    pdf_out.seek(0)
    return pdf_out

async def fetch_jobs(profile):
    aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=10&what={profile}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        res = r.json().get("results", [])
        return "\n\n".join([f"📍 {j['title']} at {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in res])

@app.post("/webhook")
async def receive(request: Request):
    try:
        data = await request.json()
        val = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
        if "messages" not in val: return {"status": "ok"}
        msg = val["messages"][0]
        phone = msg["from"]
        
        if phone not in db: db[phone] = {"cv": "", "state": "POPIA_AWAITING"}
        u = db[phone]
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

        # --- 1. POPIA CONSENT CHECK ---
        if u["state"] == "POPIA_AWAITING":
            if msg.get("type") == "interactive":
                bid = msg["interactive"]["button_reply"]["id"]
                if bid == "AGREE":
                    u["state"] = "UPLOAD_READY"
                    await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "✅ Thank you. Consent recorded. Please upload your current CV as a *PDF* now."}})
                return {"status": "ok"}
            
            # Send initial POPIA consent buttons
            popia_btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "Welcome to Job Ready Mzansi 🇿🇦\n\nTo help you, we need to process your CV. We comply 100% with the *POPIA Act*. Do you agree to our privacy policy?"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "AGREE", "title": "I Agree ✅"}}]}}}
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json=popia_btn)
            return {"status": "ok"}

        # --- 2. CV PROCESSING ---
        if msg.get("type") == "document":
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "Reading your CV... ⚖️"}})
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers=headers)
                f_r = await client.get(r.json().get("url"), headers=headers)
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            # Generate Report
            p = f"Analyze this South African CV. Score 1-100 and give 2 tips based on SA labor law. TEXT: {u['cv'][:1500]}"
            res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":p}])
            
            btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": f"📊 *MZANSI REPORT:*\n\n{res.choices[0].message.content}\n\nReady for your Pro PDF Bundle?"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "GET_PRO", "title": "📥 Download Pro PDF"}}]}}}
            await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json=btn)

        # --- 3. PRO PDF DELIVERY ---
        elif msg.get("type") == "interactive":
            if msg["interactive"]["button_reply"]["id"] == "GET_PRO":
                await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "🎨 Architecting your Premium PDF and matching jobs... ⏳"}})
                
                # Get structured data from AI
                p = f"Rewrite this CV into a JSON format with keys: 'name', 'contact', 'skills', 'summary', 'experience'. Follow SA labor laws. CV: {u['cv'][:2000]}"
                res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", response_format={"type": "json_object"}, messages=[{"role":"user","content":p}])
                cv_data = json.loads(res.choices[0].message.content)
                
                # Generate PDF
                pdf = create_pdf(cv_data)
                
                async with httpx.AsyncClient() as client:
                    up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers=headers, files={"file": ("Mzansi_Executive.pdf", pdf, "application/pdf")}, data={"messaging_product": "whatsapp", "type": "document"})
                    mid = up.json().get("id")
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": mid, "filename": "Mzansi_Executive_CV.pdf"}})
                    
                    # Jobs list
                    jobs = await fetch_jobs(cv_data.get('name', 'Admin Finance'))
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers=headers, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"🔥 *10 JOB OPENINGS IN SA FOR YOU:*\n\n{jobs}"}})

    except Exception as e: print(f"ERROR: {e}")
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
