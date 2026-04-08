# app.py (Este código va en tu servidor, no en Wix)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd

app = FastAPI()

# Esto permite que tu web de Wix se comunique con este servidor
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En producción, cambia "*" por "https://tu-sitio-wix.com"
    allow_methods=["GET"],
)

@app.get("/liquidez/{ticker}")
def obtener_liquidez_otm(ticker: str):
    ticker = ticker.upper()
    activo = yf.Ticker(ticker)
    fechas = activo.options
    
    if not fechas:
        return {"error": "No options data"}
        
    historial = activo.history(period="1d")
    precio_actual = historial['Close'].iloc[-1]
    target_date = fechas[0]
    
    cadena = activo.option_chain(target_date)
    calls = cadena.calls[['strike', 'volume', 'openInterest']].copy()
    calls['Tipo'] = 'CALL'
    puts = cadena.puts[['strike', 'volume', 'openInterest']].copy()
    puts['Tipo'] = 'PUT'
    
    df = pd.concat([calls, puts]).dropna(subset=['volume'])
    df['Estado'] = 'ITM'
    df.loc[(df['Tipo'] == 'CALL') & (df['strike'] >= precio_actual), 'Estado'] = 'OTM'
    df.loc[(df['Tipo'] == 'PUT')  & (df['strike'] <= precio_actual), 'Estado'] = 'OTM'
    
    df_otm = df[df['Estado'] == 'OTM']
    calls_top2 = df_otm[df_otm['Tipo'] == 'CALL'].sort_values(by='volume', ascending=False).head(2)
    puts_top2 = df_otm[df_otm['Tipo'] == 'PUT'].sort_values(by='volume', ascending=False).head(2)
    
    tabla_final = pd.concat([calls_top2, puts_top2]).sort_values(by='volume', ascending=False)
    
    # Generamos el string comprimido
    lista_comprimida = [f"{fila['strike']}:{fila['Tipo']}:{int(fila['volume'])}" for _, fila in tabla_final.iterrows()]
    string_final = "|".join(lista_comprimida)
    
    return {
        "ticker": ticker,
        "precio_spot": round(precio_actual, 2),
        "string_tradingview": string_final,
        "datos": tabla_final.to_dict(orient="records")
    }
