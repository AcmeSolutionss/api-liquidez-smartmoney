from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import logging

# Configuración de logs para ver errores en Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["GET"],
)

@app.get("/liquidez/{ticker}")
def obtener_liquidez_otm(ticker: str, fecha: str = Query(None)):
    try:
        ticker = ticker.upper()
        activo = yf.Ticker(ticker)
        fechas = activo.options
        
        if not fechas:
            return {"error": f"No hay datos de opciones para {ticker}"}
            
        historial = activo.history(period="1d")
        if historial.empty:
            return {"error": "Yahoo Finance no devolvió precio spot. Intenta de nuevo."}
        
        precio_actual = historial['Close'].iloc[-1]
        
        # Validar fecha
        if fecha and fecha in fechas:
            target_date = fecha
        else:
            target_date = fechas[0]
            logger.info(f"Usando fecha por defecto: {target_date}")
        
        cadena = activo.option_chain(target_date)
        
        # Extraer y limpiar datos
        calls = cadena.calls[['strike', 'volume', 'openInterest']].copy()
        puts = cadena.puts[['strike', 'volume', 'openInterest']].copy()
        
        calls['Tipo'] = 'CALL'
        puts['Tipo'] = 'PUT'
        
        df = pd.concat([calls, puts]).dropna(subset=['volume'])
        
        # Filtrar OTM
        df['Estado'] = 'ITM'
        df.loc[(df['Tipo'] == 'CALL') & (df['strike'] >= precio_actual), 'Estado'] = 'OTM'
        df.loc[(df['Tipo'] == 'PUT')  & (df['strike'] <= precio_actual), 'Estado'] = 'OTM'
        
        df_otm = df[df['Estado'] == 'OTM'].copy()
        
        if df_otm.empty:
            return {"error": "No se encontraron contratos OTM con volumen para esta fecha."}
        
        # Extraer Top 9 (o los que existan si hay menos de 9)
        calls_top = df_otm[df_otm['Tipo'] == 'CALL'].sort_values(by='volume', ascending=False).head(9)
        puts_top = df_otm[df_otm['Tipo'] == 'PUT'].sort_values(by='volume', ascending=False).head(9)
        
        tabla_final = pd.concat([calls_top, puts_top]).sort_values(by='volume', ascending=False)
        
        # Generar String para TradingView
        lista_comprimida = [f"{fila['strike']}:{fila['Tipo']}:{int(fila['volume'])}" for _, fila in tabla_final.iterrows()]
        string_final = "|".join(lista_comprimida)
        
        return {
            "ticker": ticker,
            "precio_spot": round(precio_actual, 2),
            "fecha_analizada": target_date,
            "niveles_encontrados": len(lista_comprimida),
            "string_tradingview": string_final
        }

    except Exception as e:
        logger.error(f"Error crítico: {str(e)}")
        return {"error": f"Error interno en el servidor: {str(e)}"}
