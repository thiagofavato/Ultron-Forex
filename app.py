import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
import pytz
import numpy as np
import math
import html
import threading
import requests
import time

# ==========================================
# CONFIGURAÇÕES DA PÁGINA
# ==========================================
st.set_page_config(page_title="ULTRON FOREX SQUAD", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>[data-testid='stMetricValue']{font-size: 1.4rem !important;}[data-testid='stMetricLabel']{font-size: 0.9rem !important;}</style>", unsafe_allow_html=True)

# ==========================================
# ARSENAL DE ATIVOS COMEX/CME
# ==========================================
TICKERS_ALVOS = ["M6E=F", "M6B=F", "M6A=F", "MICD=F", "J7=F", "MET=F"] 
NOMES_EXIBICAO = {
    "M6E=F": "Micro EUR/USD", "M6B=F": "Micro GBP/USD", 
    "M6A=F": "Micro AUD/USD", "MICD=F": "Micro CAD/USD", 
    "J7=F": "E-Mini JPY", "MET=F": "Micro Ether"
}

if "tracker" not in st.session_state:
    st.session_state.tracker = []
if "historico_ids" not in st.session_state:
    st.session_state.historico_ids = set()

# ==========================================
# COMUNICAÇÃO BLINDADA
# ==========================================
def enviar_telegram(mensagem):
    def tarefa():
        try:
            url = f"https://api.telegram.org/bot{st.secrets['TELEGRAM_TOKEN']}/sendMessage"
            payload = {"chat_id": st.secrets["CHAT_ID"], "text": mensagem, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=5)
        except: pass
    threading.Thread(target=tarefa, daemon=True).start()

def registrar_no_tracker(d, id_unico, ticker):
    if id_unico not in st.session_state.historico_ids:
        st.session_state.historico_ids.add(id_unico)
        tv = d['tempo_vela']
        if tv.tzinfo is None: tv = pytz.timezone('America/New_York').localize(tv)
        hora_local = tv.astimezone(pytz.timezone('America/Sao_Paulo')).strftime('%H:%M')
        
        st.session_state.tracker.append({
            "id": id_unico, "hora": hora_local, "ativo": NOMES_EXIBICAO.get(ticker, ticker), "tipo": d['tipo'], "ent": d['entrada'], 
            "sl": d['sl'], "tp1": d['tp1'], "tp2": d['tp2'], "tp3": d['tp3'],
            "status": "ATIVO 🟡", "entry_time": d['tempo_vela']
        })
        
        seta = "🚀" if "COMPRA" in d['tipo'] else "🧨"
        msg = f"{seta} <b>ULTRON FOREX | {NOMES_EXIBICAO.get(ticker, ticker)} | {d['tipo']}</b>\n"
        msg += f"🎯 Entry: {d['entrada']:.5f}\n"
        msg += f"🛡️ Stop: {d['sl']:.5f}\n\n"
        msg += f"Target Path:\n"
        msg += f"🌲 TP1: {d['tp1']:.5f}\n"
        msg += f"👑 TP3: {d['tp3']:.5f}\n\n"
        msg += f"🧠 Phase: {html.escape(str(d['fase']))} | Setup: {html.escape(str(d['motivo']))}\n"
        enviar_telegram(msg)
        return True
    return False

def calcular_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    atr = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(period).mean().iloc[-1]
    return atr if not np.isnan(atr) else 0.0020

# ==========================================
# ULTRON ENGINE MULTI-ATIVOS
# ==========================================
class UltronEngineForex:
    def __init__(self, dfs, atr, ticker): 
        self.dfs = dfs
        self.atr = atr
        self.ticker = ticker

    def calcular_risco_dinamico(self, preco_entrada, atr_atual, tipo_ordem):
        if atr_atual < (preco_entrada * 0.0005): 
            regime_vol = "Calmaria"
            multiplicador_sl = 1.5
            lotes = 1 
        elif atr_atual > (preco_entrada * 0.0015):
            regime_vol = "Caos Estocástico"
            multiplicador_sl = 3.0
            lotes = 1 
        else:
            regime_vol = "Volatilidade Padrão"
            multiplicador_sl = 2.0
            lotes = 1
        
        # O Stop Técnico define a distância em pontos decimais
        stop_pontos = atr_atual * multiplicador_sl
        
        # CÁLCULO DINÂMICO DE RISCO (Sem tetos financeiros engessados)
        # Transforma o stop decimal em pips (fator 10.000 para a maioria dos pares)
        # e multiplica pelo valor médio estimado por pip de um micro contrato ($1.25)
        pips_de_stop = stop_pontos * 10000 
        risco_financeiro_organico = pips_de_stop * 1.25 * lotes 
        
        if tipo_ordem == "COMPRA":
            sl_price = preco_entrada - stop_pontos
            tp1 = preco_entrada + (stop_pontos * 1.0)
            tp2 = preco_entrada + (stop_pontos * 2.0)
            tp3 = preco_entrada + (stop_pontos * 3.0)
        else:
            sl_price = preco_entrada + stop_pontos
            tp1 = preco_entrada - (stop_pontos * 1.0)
            tp2 = preco_entrada - (stop_pontos * 2.0)
            tp3 = preco_entrada - (stop_pontos * 3.0)
            
        return {
            "regime_vol": regime_vol, "lotes": lotes, "risco_usd": round(risco_financeiro_organico, 2),
            "sl": round(sl_price, 5), "tp1": round(tp1, 5), "tp2": round(tp2, 5), "tp3": round(tp3, 5)
        }

    def cerebro_estocastico_garch(self, precos, direcao, periodos_frente=12, simulacoes=2000):
        retornos = np.log(precos / precos.shift(1)).dropna()
        omega = np.var(retornos) * 0.05
        alpha = 0.15
        beta = 0.80
        
        sigma2 = np.var(retornos)
        for r in retornos[-50:]: sigma2 = omega + alpha * (r**2) + beta * sigma2
        
        vol_projetada = np.sqrt(sigma2)
        mu = np.mean(retornos)
        
        S0 = precos.iloc[-1]
        dt = 1 
        Z = np.random.standard_normal((periodos_frente, simulacoes))
        caminhos = np.zeros((periodos_frente, simulacoes))
        caminhos[0] = S0
        
        for t in range(1, periodos_frente):
            caminhos[t] = caminhos[t-1] * np.exp((mu - 0.5 * vol_projetada**2) * dt + vol_projetada * np.sqrt(dt) * Z[t])
            
        preco_final = caminhos[-1]
        probabilidade = np.sum(preco_final > S0) / simulacoes if direcao == "COMPRA" else np.sum(preco_final < S0) / simulacoes
        
        del caminhos, Z 
        return probabilidade

    def calcular_poc_institucional(self):
        m5 = self.dfs.get('M5')
        if m5 is None or len(m5) < 200: return 0.0
        df_recente = m5.tail(200).copy()
        if df_recente['Volume'].sum() == 0: return float(df_recente['Close'].iloc[-1])
            
        precos_tipicos = (df_recente['High'] + df_recente['Low'] + df_recente['Close']) / 3
        volumes = df_recente['Volume']
        bins = np.linspace(precos_tipicos.min(), precos_tipicos.max(), 51)
        volume_por_bin = [volumes[(precos_tipicos >= bins[i]) & (precos_tipicos < bins[i+1])].sum() for i in range(50)]
        return (bins[np.argmax(volume_por_bin)] + bins[np.argmax(volume_por_bin)+1]) / 2

    def calcular_order_blocks(self):
        m5 = self.dfs.get('M5')
        if m5 is None or len(m5) < 30: return 0.0, 0.0
        df = m5.tail(30)
        ob_bullish, ob_bearish = 0.0, 0.0
        
        for i in range(len(df)-2, 1, -1):
            if df['Close'].iloc[i] > df['Open'].iloc[i] and (df['High'].iloc[i] - df['Low'].iloc[i]) > self.atr:
                for j in range(i-1, max(0, i-5), -1):
                    if df['Close'].iloc[j] < df['Open'].iloc[j]: ob_bullish = df['Low'].iloc[j]; break
                if ob_bullish > 0: break

        for i in range(len(df)-2, 1, -1):
            if df['Close'].iloc[i] < df['Open'].iloc[i] and (df['High'].iloc[i] - df['Low'].iloc[i]) > self.atr:
                for j in range(i-1, max(0, i-5), -1):
                    if df['Close'].iloc[j] > df['Open'].iloc[j]: ob_bearish = df['High'].iloc[j]; break
                if ob_bearish > 0: break
        return ob_bullish, ob_bearish

    def identificar_fase_mercado(self):
        h1 = self.dfs.get('H1')
        if h1 is None or len(h1) < 50: return "Desconhecida"
        close, sma20, sma50 = h1['Close'].iloc[-1], h1['Close'].rolling(20).mean().iloc[-1], h1['Close'].rolling(50).mean().iloc[-1]
        if close > sma20 > sma50: return "2. Uptrend"
        elif close < sma20 < sma50: return "4. Downtrend"
        elif close >= sma50 and abs(close - sma20) < self.atr: return "3. Distribution"
        else: return "1. Accumulation"

    def validar_rejeicao_vshape(self, vela):
        o, c, h, l = vela['Open'], vela['Close'], vela['High'], vela['Low']
        body = abs(o - c)
        if min(o, c) - l > (body * 2.5) and (min(o, c) - l) > (h - max(o, c)): return "ALTA", l
        if h - max(o, c) > (body * 2.5) and (h - max(o, c)) > (min(o, c) - l): return "BAIXA", h
        return None, None

    def detectar_fvg(self):
        m5 = self.dfs.get('M5')
        if m5 is None or len(m5) < 4: return None
        v1, v2, v3 = m5.iloc[-4], m5.iloc[-3], m5.iloc[-2]
        
        range_v2 = v2['High'] - v2['Low']
        body_v2 = abs(v2['Open'] - v2['Close'])
        
        if v3['Low'] > v1['High'] and range_v2 > 0 and (body_v2 / range_v2) > 0.5: return "FVG_ALTA"
        if v3['High'] < v1['Low'] and range_v2 > 0 and (body_v2 / range_v2) > 0.5: return "FVG_BAIXA"
        return None

    def escanear_mercado_hft(self):
        m5 = self.dfs.get('M5')
        if m5 is None or m5.empty: return {"status": "Aguardando Dados"}
        
        fase_atual = self.identificar_fase_mercado()
        
        try:
            p_live = float(m5['Close'].iloc[-1])
            tempo_vela_atual = m5.index[-1]
            vela_atual_m5, ultima_vela_fechada = m5.iloc[-1], m5.iloc[-2]
            
            tipo_rejeicao, extremo_pavio = self.validar_rejeicao_vshape(ultima_vela_fechada)
            range_vela = vela_atual_m5['High'] - vela_atual_m5['Low']
            body_percent = abs(vela_atual_m5['Open'] - vela_atual_m5['Close']) / range_vela if range_vela > 0 else 0
            
            breakout_compra = p_live > float(m5.tail(8)['High'].max()) and body_percent > 0.6
            breakout_venda = p_live < float(m5.tail(8)['Low'].min()) and body_percent > 0.6
            
            caixote_high, caixote_low = float(m5.tail(16).iloc[:-1]['High'].max()), float(m5.tail(16).iloc[:-1]['Low'].min())
            sweep_compra = (vela_atual_m5['Low'] < caixote_low) and (p_live > caixote_low) and (vela_atual_m5['Close'] > vela_atual_m5['Open'])
            sweep_venda = (vela_atual_m5['High'] > caixote_high) and (p_live < caixote_high) and (vela_atual_m5['Close'] < vela_atual_m5['Open'])
            
            mss_compra = p_live > float(m5.tail(12).iloc[:-2]['High'].max())
            mss_venda = p_live < float(m5.tail(12).iloc[:-2]['Low'].min())

            if "Accumulation" in fase_atual or "Distribution" in fase_atual:
                breakout_compra, breakout_venda = False, False
            elif "Uptrend" in fase_atual:
                sweep_venda, breakout_venda = False, False
                if tipo_rejeicao == "BAIXA": tipo_rejeicao = None
            elif "Downtrend" in fase_atual:
                sweep_compra, breakout_compra = False, False
                if tipo_rejeicao == "ALTA": tipo_rejeicao = None

            fvg_atual = self.detectar_fvg()

            confirma_compra, confirma_venda = True, True
            if "MET" not in self.ticker: 
                dxy = self.dfs.get('DXY')
                if dxy is not None and not dxy.empty and len(dxy) >= 3:
                    dxy_direcao = dxy['Close'].iloc[-1] - dxy['Close'].iloc[-3]
                    if dxy_direcao >= 0: confirma_compra = False 
                    if dxy_direcao <= 0: confirma_venda = False  

            if tipo_rejeicao == "ALTA" or sweep_compra or (breakout_compra and fvg_atual == "FVG_ALTA" and mss_compra):
                if not confirma_compra: return {"status": "Bloqueio DXY: Dólar subindo (Risco de Fakeout)"}
                prob_sucesso = self.cerebro_estocastico_garch(m5['Close'], "COMPRA")
                if prob_sucesso >= 0.55:
                    motivo = "Sweep" if sweep_compra else ("V-Shape" if tipo_rejeicao == "ALTA" else "Triad: Break+FVG+MSS")
                    risco_data = self.calcular_risco_dinamico(p_live, self.atr, "COMPRA")
                    return {"status": "Sinal Encontrado", "dados": {
                        "tipo": "COMPRA", "fase": fase_atual, "motivo": f"{motivo} | {risco_data['regime_vol']} | Prob: {prob_sucesso:.1%} | Lotes: {risco_data['lotes']}", 
                        "entrada": p_live, "sl": risco_data['sl'], "tp1": risco_data['tp1'], "tp2": risco_data['tp2'], "tp3": risco_data['tp3'], 
                        "tempo_vela": tempo_vela_atual, "id": f"BUY_{self.ticker}_{tempo_vela_atual.strftime('%H%M')}"}}
                else: return {"status": f"Bloqueio Monte Carlo: Probabilidade Compra Baixa ({prob_sucesso:.1%})"}
            
            elif tipo_rejeicao == "BAIXA" or sweep_venda or (breakout_venda and fvg_atual == "FVG_BAIXA" and mss_venda):
                if not confirma_venda: return {"status": "Bloqueio DXY: Dólar caindo (Risco de Fakeout)"}
                prob_sucesso = self.cerebro_estocastico_garch(m5['Close'], "VENDA")
                if prob_sucesso >= 0.55:
                    motivo = "Sweep" if sweep_venda else ("V-Shape" if tipo_rejeicao == "BAIXA" else "Triad: Break+FVG+MSS")
                    risco_data = self.calcular_risco_dinamico(p_live, self.atr, "VENDA")
                    return {"status": "Sinal Encontrado", "dados": {
                        "tipo": "VENDA", "fase": fase_atual, "motivo": f"{motivo} | {risco_data['regime_vol']} | Prob: {prob_sucesso:.1%} | Lotes: {risco_data['lotes']}", 
                        "entrada": p_live, "sl": risco_data['sl'], "tp1": risco_data['tp1'], "tp2": risco_data['tp2'], "tp3": risco_data['tp3'], 
                        "tempo_vela": tempo_vela_atual, "id": f"SELL_{self.ticker}_{tempo_vela_atual.strftime('%H%M')}"}}
                else: return {"status": f"Bloqueio Monte Carlo: Probabilidade Venda Baixa ({prob_sucesso:.1%})"}

            return {"status": f"Vigília SMC | Fase: {fase_atual}"}
        except Exception as e: return {"status": f"Erro interno: {e}"}

# ==========================================
# FETCH DE DADOS BLINDADO (COM FALLBACKS)
# ==========================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_redundante(ticker, p, i):
    tickers_tentativas = [ticker]
    if "MET" in ticker: tickers_tentativas.extend(["ETH-USD"]) 
    if "MICD" in ticker: tickers_tentativas.extend(["MCD=F", "CAD=X"])
    if "M6E" in ticker: tickers_tentativas.extend(["EURUSD=X"])
    if "M6B" in ticker: tickers_tentativas.extend(["GBPUSD=X"])
    if "M6A" in ticker: tickers_tentativas.extend(["AUDUSD=X"])
    if "J7" in ticker: tickers_tentativas.extend(["JPY=X"])
    
    for t in tickers_tentativas:
        for tentativa in range(2): 
            try:
                data = yf.download(t, period=p, interval=i, progress=False)
                if not data.empty:
                    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
                    data.columns = [str(col).capitalize() for col in data.columns]
                    if data.index.tz is None: data.index = data.index.tz_localize('UTC')
                    data.index = data.index.tz_convert('America/New_York').tz_localize(None)
                    return data
            except: pass
    return None

# ==========================================
# INTERFACE MULTI-ATIVOS (TABS)
# ==========================================
st.markdown("<h2 style='text-align: center; color: black;'>🌍 ULTRON FOREX SQUAD</h2>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🧹 Limpar Todos os Diários", use_container_width=True):
        st.session_state.tracker = []
        st.rerun()

@st.fragment(run_every="20s")
def renderizar_painel_operacional():
    df_dxy = fetch_redundante("DX=F", "2d", "5m") 
    
    nomes_abas = [NOMES_EXIBICAO.get(t, t) for t in TICKERS_ALVOS]
    tabs = st.tabs(nomes_abas)
    
    for i, ticker in enumerate(TICKERS_ALVOS):
        with tabs[i]:
            try:
                dfs = {
                    'M5': fetch_redundante(ticker, "2d", "5m"), 
                    'H1': fetch_redundante(ticker, "15d", "1h"),
                    'DXY': df_dxy
                }
                
                if dfs['M5'] is not None and dfs['H1'] is not None:
                    engine = UltronEngineForex(dfs, calcular_atr(dfs['M5']) * 1.5, ticker)
                    
                    c1, c2, c3, c4 = st.columns(4)
                    p_live = float(dfs['M5']['Close'].iloc[-1])
                    c1.metric(f"Ativo", f"{p_live:.5f}")
                    c2.metric("Market Phase", engine.identificar_fase_mercado().split(' ')[0])
                    
                    poc = engine.calcular_poc_institucional()
                    c3.metric("POC Institucional", f"{poc:.5f}" if poc > 0 else "Processando...")
                    
                    ob_bull, ob_bear = engine.calcular_order_blocks()
                    c4.metric("Order Blocks (OB)", f"S: {ob_bull:.5f} | R: {ob_bear:.5f}")
                    
                    operacoes_ativas = [t for t in st.session_state.tracker if t['status'] == "ATIVO 🟡" and t['ativo'] == NOMES_EXIBICAO.get(ticker, ticker)]
                    an = {'status': f"🔒 Gatilho Bloqueado: Posição Ativa neste ativo."} if operacoes_ativas else engine.escanear_mercado_hft()
                    
                    if an['status'] == 'Sinal Encontrado':
                        st.success(f"🎯 ALERTA VIP: {an['dados']['tipo']}")
                        registrar_no_tracker(an['dados'], an['dados']['id'], ticker)
                    else: 
                        st.info(f"Radar Institucional: {an['status']}")

                    st.divider()
                    tracker_filtrado = [t for t in st.session_state.tracker if t['ativo'] == NOMES_EXIBICAO.get(ticker, ticker)]
                    if tracker_filtrado:
                        df_m5 = dfs['M5']
                        for t in tracker_filtrado:
                            if t['status'] not in ["WIN TP3 👑", "LOSS TÉCNICO 🔴", "STOP TRAILING 🛡️"] and t.get('entry_time'):
                                for _, row in df_m5[df_m5.index >= t['entry_time']].iterrows():
                                    h, l = float(row['High']), float(row['Low'])
                                    atr_trailing = engine.atr * 1.5 
                                    
                                    if "COMPRA" in t['tipo']:
                                        novo_sl = h - atr_trailing
                                        if novo_sl > t['sl']: t['sl'] = round(novo_sl, 5) 
                                        if l <= t['sl'] and t['status'] == "ATIVO 🟡": 
                                            t['status'] = "STOP TRAILING 🛡️" if t['sl'] > t['ent'] else "LOSS TÉCNICO 🔴"
                                            break
                                        elif h >= t['tp3']: t['status'] = "WIN TP3 👑"; break
                                        elif h >= t['tp1'] and t['status'] == "ATIVO 🟡": t['status'] = "WIN TP1 🟢"
                                    else: 
                                        novo_sl = l + atr_trailing
                                        if novo_sl < t['sl']: t['sl'] = round(novo_sl, 5) 
                                        if h >= t['sl'] and t['status'] == "ATIVO 🟡": 
                                            t['status'] = "STOP TRAILING 🛡️" if t['sl'] < t['ent'] else "LOSS TÉCNICO 🔴"
                                            break
                                        elif l <= t['tp3']: t['status'] = "WIN TP3 👑"; break
                                        elif l <= t['tp1'] and t['status'] == "ATIVO 🟡": t['status'] = "WIN TP1 🟢"
                        
                        tabela = pd.DataFrame(tracker_filtrado).drop(columns=['id', 'entry_time', 'ativo'], errors='ignore')
                        st.dataframe(tabela.iloc[::-1], use_container_width=True, hide_index=True) 
                    else: st.caption(f"Aguardando alinhamento do {NOMES_EXIBICAO.get(ticker, ticker)}...")
                else: st.error("❌ Falha na conexão de dados.")
            except Exception as e: st.error(f"💣 ERRO: {str(e)}")

renderizar_painel_operacional()
