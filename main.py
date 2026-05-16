from fastapi import FastAPI, Request, Response
import httpx, os, fitz
from groq import Groq
from docx import Document
from docx.shared import Pt, RGBColor
from io import BytesIO

app = FastAPI()

# --- CONFIG ---
# Tip: Generate a fresh token in Meta if it has been 24 hours
ACCESS_TOKEN = "EAAavL5WiIDcBRYzjYM461tV7sVZAaltSUGQlMdoDepZACIdovnDqkrZCHPSOZBMtnaFSHlgCoAg76yypXnX7ZBGyPHzSMHZAjW61ZBlgNGSDTi3FvoMnk6nc1fZBl5SqIcyCOc7V3tUfpo91QWevH13XkAKACWKJZCB7kPlMXzEIVDTFVBrV2ZB3C2w3X9juJ9qcYeFCnZBpGbBzNiRdxXTjpbxjjytJVoW9io7Ds76Em4VkAVZBCDZBGiIErmJkl8xt8QQPhdTfXnfbubQ9vzVXWc20ZB9URfSxTLarNkiCRYlIkZD"
PHONE_NUMBER_ID = "1103451669516095"
VERIFY_TOKEN = "MY_SECRET_TOKEN_123"
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- PAYSTACK LINKS (South African Rands) ---
PAY_STD = "https://paystack.com/pay/mzansi_std"  # R29
PAY_PRO = "https://paystack.com/pay/mzansi_pro"  # R49
PAY_JOBS = "https://paystack.com/pay/mzansi_jobs" # R39

db = {}

async def send_text(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    await httpx.AsyncClient().post(url, headers=headers, json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}})

async def send_buttons(to, text, buttons):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    fb = [{"type": "reply", "reply": {"id": b[0], "title": b[1]}} for b in buttons]
    data = {"messaging_product": "whatsapp", "to": to, "type": "interactive", "interactive": {"type": "button", "body": {"text": text}, "action": {"buttons": fb}}}
    await httpx.AsyncClient().post(url, headers=headers, json=data)

@app.get("/webhook")
async def verify(request: Request):
    challenge = request.query_params.get("hub.challenge")
    return Response(content=challenge, status_code=200)

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
            if bid == "UPLOAD": await send_text(phone, "Great! Please upload your current CV as a *PDF file* now. 📄")
            elif bid == "STD": await send_text(phone, f"📝 *Standard CV (R29):* {PAY_STD}")
            elif bid == "PRO": await send_text(phone, f"💎 *Pro Bundle (R49):* {PAY_PRO}")
            elif bid == "JOBS": await send_text(phone, f"🔍 *Job Matching (R39):* {PAY_JOBS}")
            elif bid == "RESTART": await send_buttons(phone, "Welcome to Job Ready Mzansi! 🇿🇦", [("UPLOAD", "📄 Upload CV"), ("RESTART", "🔄 Restart")])

        elif msg["type"] == "document":
            await send_text(phone, "Reading your CV for Mzansi standards... 🇿🇦")
            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers=headers)
                f_r = await client.get(r.json().get("url"), headers=headers)
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            report = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":f"Analyze this CV for the South African market. Score 1-100. Give 2 tips. CV: {u['cv'][:2000]}"}])
            await send_text(phone, f"📊 *MZANSI REPORT:*\n\n{report.choices[0].message.content}")
            await send_buttons(phone, "Choose your upgrade:", [("STD", "Standard (R29)"), ("PRO", "Pro Bundle (R49)"), ("JOBS", "Job Search (R39)")])

        else:
            await send_buttons(phone, "Welcome to Job Ready Mzansi! 🇿🇦\nReady to start?", [("UPLOAD", "📄 Upload CV"), ("RESTART", "🔄 Menu")])

    except Exception: pass
    return {"status": "success"}
