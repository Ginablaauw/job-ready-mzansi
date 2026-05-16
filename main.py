from fastapi import FastAPI, Request, Response
import httpx, os, fitz
from groq import Groq

app = FastAPI()

# --- CONFIG ---
ACCESS_TOKEN = "EAAavL5WiIDcBRYzjYM461tV7sVZAaltSUGQlMdoDepZACIdovnDqkrZCHPSOZBMtnaFSHlgCoAg76yypXnX7ZBGyPHzSMHZAjW61ZBlgNGSDTi3FvoMnk6nc1fZBl5SqIcyCOc7V3tUfpo91QWevH13XkAKACWKJZCB7kPlMXzEIVDTFVBrV2ZB3C2w3X9juJ9qcYeFCnZBpGbBzNiRdxXTjpbxjjytJVoW9io7Ds76Em4VkAVZBCDZBGiIErmJkl8xt8QQPhdTfXnfbubQ9vzVXWc20ZB9URfSxTLarNkiCRYlIkZD"
PHONE_NUMBER_ID = "1103451669516095"
VERIFY_TOKEN = "MY_SECRET_TOKEN_123"
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- PAYSTACK LINKS ---
PAY_STD = "https://paystack.com/pay/mzansi_std"
PAY_PRO = "https://paystack.com/pay/mzansi_pro"
PAY_JOBS = "https://paystack.com/pay/mzansi_jobs"

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

        # 1. BUTTONS
        if msg["type"] == "interactive":
            bid = msg["interactive"]["button_reply"]["id"]
            if bid == "UPLOAD": await send_text(phone, "Please upload your CV as a PDF. 📄")
            elif bid in ["STD", "PRO", "JOBS"]: await send_text(phone, "Thank you! Our automated payment system is being linked. Please save your report for now.")
            elif bid == "RESTART": await send_buttons(phone, "Welcome! 🇿🇦", [("UPLOAD", "📄 Upload CV"), ("RESTART", "🔄 Restart")])

        # 2. CV UPLOADS (The Fix is here)
        elif msg["type"] == "document":
            await send_text(phone, "Reading your CV... ⏳")
            headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
            
            async with httpx.AsyncClient() as client:
                # Get File URL
                r = await client.get(f"https://graph.facebook.com/v18.0/{msg['document']['id']}", headers=headers)
                file_url = r.json().get("url")
                
                # Download File
                f_r = await client.get(file_url, headers=headers)
                
                # Try to read text
                with fitz.open(stream=f_r.content, filetype="pdf") as doc:
                    u["cv"] = "".join([page.get_text() for page in doc])
            
            if not u["cv"].strip():
                await send_text(phone, "❌ I can see the file, but I can't read the text. Is it a scanned photo? Please try a clear PDF with typed text.")
                return {"status": "ok"}
            
            # AI Analysis
            await send_text(phone, "Analyzing text with AI... 🧠")
            report = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role":"user","content":f"Analyze this South African CV. Score 1-100. Give 2 tips. CV: {u['cv'][:2000]}"}]
            )
            await send_text(phone, f"📊 *MZANSI REPORT:*\n\n{report.choices[0].message.content}")
            await send_buttons(phone, "Upgrade to get your documents:", [("STD", "Standard (R29)"), ("PRO", "Pro Bundle (R49)"), ("JOBS", "Job Search (R39)")])

        else:
            await send_buttons(phone, "Welcome! 🇿🇦\nReady to start?", [("UPLOAD", "📄 Upload CV"), ("RESTART", "🔄 Menu")])

    except Exception as e:
        print(f"ERROR: {e}")
        await send_text(phone, "❌ Something went wrong. Please ensure you are sending a standard PDF file.")
        
    return {"status": "success"}

@app.get("/webhook")
async def verify(request: Request):
    return Response(content=request.query_params.get("hub.challenge"), status_code=200)
