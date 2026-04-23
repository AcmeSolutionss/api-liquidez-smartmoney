from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["GET"],
)

# Ahora la ruta acepta una fecha opcional: /liquidez/GLD?fecha=2026-04-17
@app.get("/liquidez/{ticker}")
def obtener_liquidez_otm(ticker: str, fecha: str = Query(None)):
    ticker = ticker.upper()
    activo = yf.Ticker(ticker)
    fechas = activo.options
    
    if not fechas:
        return {"error": f"No hay datos de opciones para {ticker}"}
        
    historial = activo.history(period="1d")
    if historial.empty:
        return {"error": "No se pudo conectar al precio spot."}
    precio_actual = historial['Close'].iloc[-1]
    
    # Lógica de Fecha: Usar la ingresada si es válida, si no, usar la más próxima
    if fecha and fecha in fechas:
        target_date = fecha
    else:
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
    
    # Extraer Top 2 Calls y Puts OTM
    calls_top2 = df_otm[df_otm['Tipo'] == 'CALL'].sort_values(by='volume', ascending=False).head(9)
    puts_top2 = df_otm[df_otm['Tipo'] == 'PUT'].sort_values(by='volume', ascending=False).head(9)
    
    tabla_final = pd.concat([calls_top2, puts_top2]).sort_values(by='volume', ascending=False)
    
    if tabla_final.empty:
        return {"error": "No se encontraron contratos OTM con volumen."}
        
    # Generar String
    lista_comprimida = [f"{fila['strike']}:{fila['Tipo']}:{int(fila['volume'])}" for _, fila in tabla_final.iterrows()]
    string_final = "|".join(lista_comprimida)
    
    return {
        "ticker": ticker,
        "precio_spot": round(precio_actual, 2),
        "fecha_analizada": target_date,
        "string_tradingview": string_final
    }
