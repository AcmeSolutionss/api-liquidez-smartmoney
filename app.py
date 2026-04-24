from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["GET"],
)

# Escudo Anti-Baneo de Yahoo
CACHE = {}
TIEMPO_EXPIRACION = 120 

@app.get("/liquidez/{ticker}")
def obtener_liquidez_otm(ticker: str, fecha: str = Query(None), top: int = Query(9)):
    try:
        ticker = ticker.upper()
        
        # 1. VERIFICAR CACHÉ (Llave incluye el ticker, la fecha y el top)
        cache_key = f"{ticker}_{fecha}_{top}"
        if cache_key in CACHE:
            tiempo_guardado = CACHE[cache_key]['timestamp']
            if time.time() - tiempo_guardado < TIEMPO_EXPIRACION:
                logger.info(f"Entregando desde Caché: {ticker} (Top {top})")
                return CACHE[cache_key]['datos']

        # 2. CONSULTAR A YAHOO FINANCE
        logger.info(f"Consultando Yahoo Finance: {ticker}")
        activo = yf.Ticker(ticker)
        fechas = activo.options
        
        if not fechas:
            return {"error": f"No hay datos de opciones para {ticker}"}
            
        historial = activo.history(period="1d")
        if historial.empty:
            return {"error": "No se obtuvo precio spot."}
        
        precio_actual = historial['Close'].iloc[-1]
        target_date = fecha if (fecha and fecha in fechas) else fechas[0]
        
        cadena = activo.option_chain(target_date)
        
        calls = cadena.calls[['strike', 'volume', 'openInterest']].copy()
        puts = cadena.puts[['strike', 'volume', 'openInterest']].copy()
        
        calls['Tipo'] = 'CALL'
        puts['Tipo'] = 'PUT'
        
        df = pd.concat([calls, puts]).dropna(subset=['volume'])
        
        df['Estado'] = 'ITM'
        df.loc[(df['Tipo'] == 'CALL') & (df['strike'] >= precio_actual), 'Estado'] = 'OTM'
        df.loc[(df['Tipo'] == 'PUT')  & (df['strike'] <= precio_actual), 'Estado'] = 'OTM'
        
        df_otm = df[df['Estado'] == 'OTM'].copy()
        
        if df_otm.empty:
            return {"error": "No hay contratos OTM con volumen."}
        
        # Usamos la variable 'top' enviada desde cTrader
        calls_top = df_otm[df_otm['Tipo'] == 'CALL'].sort_values(by='volume', ascending=False).head(top)
        puts_top = df_otm[df_otm['Tipo'] == 'PUT'].sort_values(by='volume', ascending=False).head(top)
        
        tabla_final = pd.concat([calls_top, puts_top]).sort_values(by='volume', ascending=False)
        
        lista_comprimida = [f"{fila['strike']}:{fila['Tipo']}:{int(fila['volume'])}" for _, fila in tabla_final.iterrows()]
        string_final = "|".join(lista_comprimida)
        
        respuesta_final = {
            "ticker": ticker,
            "precio_spot": round(precio_actual, 2),
            "fecha_analizada": target_date,
            "niveles_encontrados": len(lista_comprimida),
            "string_tradingview": string_final
        }

        # Guardar en Caché
        CACHE[cache_key] = {
            'timestamp': time.time(),
            'datos': respuesta_final
        }
        
        return respuesta_final

    except Exception as e:
        if "Too Many Requests" in str(e):
            return {"error": "Yahoo bloqueó la IP temporalmente. Espera 15 min."}
        return {"error": f"Error interno: {str(e)}"}
