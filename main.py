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

# --- THE PROFESSIONAL DESIGNER (HTML/CSS) ---
def create_designer_pdf(data):
    # This is a high-end table-based layout for PDF stability
    html = f"""
    <html>
    <head>
        <style>
            @page {{ size: a4; margin: 0; }}
            body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #333; margin: 0; padding: 0; }}
            .header {{ background-color: #002D62; color: white; padding: 40px; text-align: center; }}
            .name {{ font-size: 32px; font-weight: bold; letter-spacing: 2px; text-transform: uppercase; }}
            .title {{ font-size: 14px; color: #DAA520; margin-top: 5px; font-weight: bold; }}
            .container {{ width: 100%; }}
            .sidebar {{ background-color: #f4f4f4; width: 30%; padding: 30px; vertical-align: top; }}
            .main-content {{ width: 70%; padding: 40px; vertical-align: top; }}
            .section-label {{ color: #002D62; font-size: 16px; font-weight: bold; border-bottom: 2px solid #002D62; margin-bottom: 10px; padding-bottom: 5px; text-transform: uppercase; }}
            .item-title {{ font-weight: bold; color: #333; font-size: 13px; margin-top: 15px; }}
            .item-meta {{ font-size: 11px; color: #666; font-style: italic; }}
            .bullet {{ margin-left: 15px; font-size: 12px; color: #444; }}
            .popia-box {{ margin-top: 50px; padding: 15px; border: 1px solid #ccc; font-size: 9px; color: #777; background-color: #fafafa; font-style: italic; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="name">{data.get('full_name', 'Professional Candidate')}</div>
            <div class="title">{data.get('profession', 'Expert Professional')}</div>
        </div>
        <table class="container" cellpadding="0" cellspacing="0">
            <tr>
                <td class="sidebar">
                    <div class="section-label">Contact</div>
                    <p style="font-size: 11px;">{data.get('contact_info', 'Contact provided on request')}</p>
                    <div class="section-label" style="margin-top: 30px;">Top Skills</div>
                    <p style="font-size: 11px;">{data.get('skills', '')}</p>
                </td>
                <td class="main-content">
                    <div class="section-label">Professional Summary</div>
                    <p style="font-size: 12px; line-height: 1.6;">{data.get('summary', '')}</p>
                    
                    <div class="section-label" style="margin-top: 30px;">Experience</div>
                    <div style="font-size: 12px;">{data.get('experience', '').replace('\\n', '<br/>')}</div>
                    
                    <div class="popia-box">
                        <b>POPIA ACT COMPLIANCE:</b> By sharing this document, I hereby give consent that my personal information 
                        may be processed for the purpose of job applications and recruitment in accordance with the 
                        Protection of Personal Information Act of South Africa.
                    </div>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file)
    pdf_file.seek(0)
    return pdf_file

async def fetch_mzansi_jobs(profile):
    aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    url = f"https://api.adzuna.com/v1/api/jobs/za/search/1?app_id={aid}&app_key={akey}&results_per_page=10&what={profile}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        results = r.json().get("results", [])
        if not results: return "No specific matches found today. Try searching for 'Admin Finance' directly on PNet."
        return "\n\n".join([f"📍 *{j['title']}*\n🏢 {j['company']['display_name']}\n🔗 {j['redirect_url']}" for j in results])

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

        # 1. POPIA FIRST
        if u["state"] == "START":
            btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "Welcome to *Job Ready Mzansi* 🇿🇦\n\nTo begin, do you agree to our Privacy Policy? We are 100% POPIA compliant. Your data is used ONLY to build your CV."}, "action": {"buttons": [{"type": "reply", "reply": {"id": "AGREE", "title": "I Agree ✅"}}]}}}
            async with httpx.AsyncClient() as client:
                await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json=btn)
            u["state"] = "CONSENTED"
            return {"status": "ok"}

        # 2. ACTIONS
        if msg.get("type") == "interactive":
            bid = msg["interactive"]["button_reply"]["id"]
            if bid == "AGREE":
                await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "✅ Thank you. Please upload your current CV as a *PDF* now."}})
            elif bid == "PRO":
                await httpx.AsyncClient().post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": "🎨 Architecting your Premium Executive PDF... ⏳"}})
                
                # Get structured JSON from AI
                p = f"Analyze this CV and output ONLY a JSON object with: 'full_name', 'profession', 'contact_info', 'skills', 'summary', 'experience' (with bullet points). CV: {u['cv'][:2000]}"
                res = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", response_format={"type": "json_object"}, messages=[{"role":"user","content":p}])
                cv_json = json.loads(res.choices[0].message.content)
                
                # Create PDF
                pdf = create_designer_pdf(cv_json)
                
                # Send PDF
                async with httpx.AsyncClient() as client:
                    up = await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/media", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, files={"file": ("Mzansi_Executive_CV.pdf", pdf, "application/pdf")}, data={"messaging_product": "whatsapp", "type": "document"})
                    mid = up.json().get("id")
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "document", "document": {"id": mid, "filename": "Premium_Mzansi_CV.pdf"}})
                    
                    # Send Jobs
                    jobs = await fetch_mzansi_jobs(cv_json.get('profession', 'Finance Admin'))
                    await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": f"🔥 *MATCHING JOBS IN SA FOR YOU:*\n\n{jobs}"}})

        # 3. CV UPLOAD
        elif msg.get("type") == "document":
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
                f_r = await client.get(r.json().get("url"), headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            btn = {"messaging_product": "whatsapp", "to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": "✅ CV Read. Get your professional Score and Pro PDF?"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "PRO", "title": "📥 Get Pro Bundle"}}]}}}
            async with httpx.AsyncClient() as client:
                await client.post(f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages", headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, json=btn)

    except Exception as e: print(f"ERROR: {e}")
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
