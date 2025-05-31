import ccxt
from dotenv import load_dotenv
import os
import time
import pandas as pd
import numpy as np
import smtplib
from email.message import EmailMessage
import pytz  # Add this import

load_dotenv()

API_KEY = os.getenv("KRAKEN_API_KEY")
API_SECRET = os.getenv("KRAKEN_API_SECRET")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

KRAKEN_INSTANCE = None

def get_kraken_instance():
    global KRAKEN_INSTANCE
    if KRAKEN_INSTANCE is not None:
        return KRAKEN_INSTANCE
    
    KRAKEN_INSTANCE = ccxt.kraken({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True
    })
    
    return KRAKEN_INSTANCE

def fetch_eth_ohlcv(kraken, timeframe='15m', limit=100):
    # Fetch ETH/USD OHLCV data
    ohlcv = kraken.fetch_ohlcv('ETH/USD', timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def supertrend(df, period=10, multiplier=3):
    hl2 = (df['high'] + df['low']) / 2
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())))
    df['atr'] = df['tr'].rolling(period).mean()
    df['upperband'] = hl2 + (multiplier * df['atr'])
    df['lowerband'] = hl2 - (multiplier * df['atr'])
    df['in_uptrend'] = True

    for current in range(1, len(df.index)):
        prev = current - 1

        if df['close'].iloc[current] > df['upperband'].iloc[prev]:
            df.loc[current, 'in_uptrend'] = True
        elif df['close'].iloc[current] < df['lowerband'].iloc[prev]:
            df.loc[current, 'in_uptrend'] = False
        else:
            df.loc[current, 'in_uptrend'] = df.loc[prev, 'in_uptrend']
            if df.loc[current, 'in_uptrend'] and df.loc[current, 'lowerband'] < df.loc[prev, 'lowerband']:
                df.loc[current, 'lowerband'] = df.loc[prev, 'lowerband']
            if not df.loc[current, 'in_uptrend'] and df.loc[current, 'upperband'] > df.loc[prev, 'upperband']:
                df.loc[current, 'upperband'] = df.loc[prev, 'upperband']
    return df

def get_signal(df):
    # Simple buy/sell signal based on Supertrend
    if df['in_uptrend'].iloc[-2] == False and df['in_uptrend'].iloc[-1] == True:
        return "BUY"
    elif df['in_uptrend'].iloc[-2] == True and df['in_uptrend'].iloc[-1] == False:
        return "SELL"
    else:
        return "HOLD"

def send_email(subject, body):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("Email credentials not set in environment variables.")
        return
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print("Failed to send email:", str(e))

def main ():
    kraken = get_kraken_instance()
    print("Starting ETH market monitoring with Supertrend indicator...")
    last_signal = None
    mst = pytz.timezone('US/Mountain')
    while True:
        try:
            df = fetch_eth_ohlcv(kraken)
            df = supertrend(df)
            trend = "Bullish" if df['in_uptrend'].iloc[-1] else "Bearish"
            signal = get_signal(df)
            # Convert timestamp to MST
            utc_time = df['timestamp'].iloc[-1].tz_localize('UTC')
            mst_time = utc_time.astimezone(mst)
            print(f"[{mst_time}] ETH/USD close: {df['close'].iloc[-1]:.2f} | Trend: {trend} | Signal: {signal}")
            if signal in ["BUY", "SELL"] and signal != last_signal:
                subject = f"ETH Signal Alert: {signal}"
                body = f"Signal: {signal}\nTrend: {trend}\nPrice: {df['close'].iloc[-1]:.2f}\nTime: {mst_time}"
                send_email(subject, body)
            last_signal = signal
            time.sleep(60)  # Wait 60 seconds before next fetch
        except Exception as e:
            print("Error:", str(e))
            time.sleep(60)

if __name__ == "__main__":
    main()
