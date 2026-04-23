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

# --- ESCUDO ANTI-BANEO (CACHÉ EN MEMORIA) ---
# Guardaremos las respuestas aquí para no saturar a Yahoo Finance
CACHE = {}
TIEMPO_EXPIRACION = 120  # 120 segundos (2 minutos) de vida útil por dato

@app.get("/liquidez/{ticker}")
def obtener_liquidez_otm(ticker: str, fecha: str = Query(None)):
    try:
        ticker = ticker.upper()
        
        # 1. VERIFICAR EL CACHÉ ANTES DE LLAMAR A YAHOO
        cache_key = f"{ticker}_{fecha}"
        if cache_key in CACHE:
            tiempo_guardado = CACHE[cache_key]['timestamp']
            if time.time() - tiempo_guardado < TIEMPO_EXPIRACION:
                logger.info(f"Entregando datos desde el Caché para {ticker}")
                return CACHE[cache_key]['datos']

        # 2. SI NO HAY CACHÉ VÁLIDO, PREGUNTAMOS A YAHOO
        logger.info(f"Consultando a Yahoo Finance para {ticker} (Caché vacío o expirado)")
        activo = yf.Ticker(ticker)
        fechas = activo.options
        
        if not fechas:
            return {"error": f"No hay datos de opciones para {ticker}"}
            
        historial = activo.history(period="1d")
        if historial.empty:
            return {"error": "Yahoo Finance no devolvió precio spot. Intenta de nuevo."}
        
        precio_actual = historial['Close'].iloc[-1]
        
        if fecha and fecha in fechas:
            target_date = fecha
        else:
            target_date = fechas[0]
        
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
            return {"error": "No se encontraron contratos OTM con volumen para esta fecha."}
        
        calls_top = df_otm[df_otm['Tipo'] == 'CALL'].sort_values(by='volume', ascending=False).head(9)
        puts_top = df_otm[df_otm['Tipo'] == 'PUT'].sort_values(by='volume', ascending=False).head(9)
        
        tabla_final = pd.concat([calls_top, puts_top]).sort_values(by='volume', ascending=False)
        
        lista_comprimida = [f"{fila['strike']}:{fila['Tipo']}:{int(fila['volume'])}" for _, fila in tabla_final.iterrows()]
        string_final = "|".join(lista_comprimida)
        
        # 3. EMPAQUETAR RESPUESTA
        respuesta_final = {
            "ticker": ticker,
            "precio_spot": round(precio_actual, 2),
            "fecha_analizada": target_date,
            "niveles_encontrados": len(lista_comprimida),
            "string_tradingview": string_final
        }

        # 4. GUARDAR EN EL CACHÉ ANTES DE ENTREGAR
        CACHE[cache_key] = {
            'timestamp': time.time(),
            'datos': respuesta_final
        }
        
        return respuesta_final

    except Exception as e:
        error_msg = str(e)
        if "Too Many Requests" in error_msg or "Rate limited" in error_msg:
            return {"error": "Yahoo Finance nos ha bloqueado temporalmente por exceso de peticiones. Espera 15 minutos."}
        logger.error(f"Error crítico: {error_msg}")
        return {"error": f"Error interno en el servidor: {error_msg}"}
