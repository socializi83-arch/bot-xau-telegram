import os, time, requests
import pandas as pd
from datetime import datetime
import pytz
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()
API_KEY = os.getenv("TWELVEDATA_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MA_SHORT, MA_LONG = 12, 26
SL_D, TP1_D, TP2_D = 10.0, 8.0, 18.0
last_signal = {"type": None, "time": 0}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)

def is_market_open():
    paris = pytz.timezone('Europe/Paris')
    now = datetime.now(paris)
    weekday = now.weekday()
    hour = now.hour
    if weekday == 5: return False
    if weekday == 6 and hour < 23: return False
    if weekday == 4 and hour >= 23: return False
    if hour == 23: return False
    return True

def fetch_xau():
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1h&outputsize=100&apikey={API_KEY}"
    r = requests.get(url, timeout=10).json()
    if "values" not in r: return None
    df = pd.DataFrame(r["values"])[::-1]
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    return df

def check_gold():
    if not is_market_open():
        print("Marché XAU/USD fermé - skip")
        return
    global last_signal
    try:
        df = fetch_xau()
        if df is None or len(df) < 50: return
        df['s_ma'] = df['close'].rolling(MA_SHORT).mean()
        df['l_ma'] = df['close'].rolling(MA_LONG).mean()
        last, prev = df.iloc[-2], df.iloc[-3]
        price = float(last['close'])
        support = float(df.tail(30)['low'].min())
        resistance = float(df.tail(30)['high'].max())
        long_sig = prev['s_ma'] < prev['l_ma'] and last['s_ma'] > last['l_ma']
        short_sig = prev['s_ma'] > prev['l_ma'] and last['s_ma'] < last['l_ma']
        if not long_sig and not short_sig: return
        sig_type = "LONG" if long_sig else "SHORT"
        if last_signal["type"] == sig_type and time.time() - last_signal["time"] < 3600: return
        rr1 = TP1_D / SL_D
        rr2 = TP2_D / SL_D
        if long_sig:
            msg = f"🟢 *XAU/USD BUY [{price:.2f}$] - 1H*\n\nBuy Limit: `{support:.2f}$`\nSL: `{price-SL_D:.2f}$`\nTP1: `{price+TP1_D:.2f}$` | R:R 1:{rr1:.1f}\nTP2: `{price+TP2_D:.2f}$` | R:R 1:{rr2:.1f}"
        else:
            msg = f"🔴 *XAU/USD SELL [{price:.2f}$] - 1H*\n\nSell Limit: `{resistance:.2f}$`\nSL: `{price+SL_D:.2f}$`\nTP1: `{price-TP1_D:.2f}$` | R:R 1:{rr1:.1f}\nTP2: `{price-TP2_D:.2f}$` | R:R 1:{rr2:.1f}"
        send_telegram(msg)
        last_signal = {"type": sig_type, "time": time.time()}
    except Exception as e:
        print(e)

scheduler = BackgroundScheduler()
scheduler.add_job(check_gold, 'interval', minutes=2)
scheduler.start()

@app.get("/")
def home():
    status = "OUVERT" if is_market_open() else "FERME (week-end/pause 23h)"
    return {"status": f"Bot XAU 1H actif - Marché: {status}"}

@app.get("/test")
def test():
    send_telegram(f"✅ Bot XAU/USD 1H connecté !")
    return {"ok": True}

check_gold()
