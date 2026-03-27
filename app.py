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
import os

# ==========================================
# CONFIGURAÇÕES DA PÁGINA
# ==========================================
st.set_page_config(page_title="ULTRON FOREX SQUAD - V2", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>[data-testid='stMetricValue']{font-size: 1.4rem !important;}[data-testid='stMetricLabel']{font-size: 0.9rem !important;}</style>", unsafe_allow_html=True)

# ==========================================
# ARSENAL E ESPECIFICAÇÕES OFICIAIS CME
# ==========================================
TICKERS_ALVOS = ["M6E=F", "M6B=F", "M6A=F", "MICD=F", "MBT=F"] 
NOMES_EXIBICAO = {
    "M6E=F": "Micro EUR/USD", "M6B=F": "Micro GBP/USD", 
    "M6A=F": "Micro AUD/USD", "MICD=F": "Micro CAD/USD", 
    "MBT=F": "Micro Bitcoin"
}

ESPECIFICACOES_CME = {
    "M6E=F": {"valor_ponto": 1.25, "casas": 5, "mult_pip": 10000, "moeda_base": "EUR"},
    "M6B=F": {"valor_ponto": 0.625, "casas": 5, "mult_pip": 10000, "moeda_base": "GBP"},
    "M6A=F": {"valor_ponto": 1.00, "casas": 5, "mult_pip": 10000, "moeda_base": "AUD"},
    "MICD=F": {"valor_ponto": 1.00, "casas": 5, "mult_pip": 10000, "moeda_base": "CAD"},
    "MBT=F": {"valor_ponto": 0.10, "casas": 2, "mult_pip": 1, "moeda_base": "BTC"} 
}

ARQUIVO_DIARIO = "banco_de_dados_ultron.csv"

def salvar_caixa_preta():
    if st.session_state.tracker:
        df = pd.DataFrame(st.session_state.tracker)
        df.to_csv(ARQUIVO_DIARIO, index=False)

if "tracker" not in st.session_state:
    if os.path.exists(ARQUIVO_DIARIO):
        try:
            df_mem = pd.read_csv(ARQUIVO_DIARIO)
            df_mem['entry_time'] = pd.to_datetime(df_mem['entry_time'])
            st.session_state.tracker = df_mem.to_dict('records')
            st.session_state.historico_ids = set(df_mem['id'].tolist())
        except:
            st.session_state.tracker = []
            st.session_state.historico_ids = set()
    else:
        st.session_state.tracker = []
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
        salvar_caixa_preta()
        
        seta = "🚀" if "COMPRA" in d['tipo'] else "🧨"
        casas = ESPECIFICACOES_CME.get(ticker, {"casas": 5})["casas"]
        msg = f"{seta} <b>ULTRON FOREX | {NOMES_EXIBICAO.get(ticker, ticker)} | {d['tipo']}</b>\n"
        msg += f"🎯 Entry: {d['entrada']:.{casas}f}\n"
        msg += f"🛡️ Stop: {d['sl']:.{casas}f}\n\n"
        msg += f"Target Path:\n"
        msg += f"🌲 TP1: {d['tp1']:.{casas}f}\n"
        msg += f"👑 TP3: {d['tp3']:.{casas}f}\n\n"
        msg += f"🧠 Phase: {html.escape(str(d['fase']))} | Setup: {html.escape(str(d['motivo']))}\n"
        enviar_telegram(msg)
        return True
    return False

# ==========================================
# MOTOR QUÂNTICO & ML INSTITUCIONAL
# ==========================================
class UltronEngineForex:
    def __init__(self, dfs, ticker): 
        self.dfs = dfs
        self.ticker = ticker
        self.specs = ESPECIFICACOES_CME.get(ticker, {"valor_ponto": 1.0, "casas": 5, "mult_pip": 10000, "moeda_base": "USD"})
        self.df_m5 = self._calcular_indicadores_institucionais(self.dfs.get('M5').copy() if self.dfs.get('M5') is not None else None)
        self.atr = float(self.df_m5['ATR'].iloc[-1]) if self.df_m5 is not None else 0.0020

    def _calcular_indicadores_institucionais(self, df):
        if df is None or len(df) < 200: return df
        
        # ATR para Risco
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()

        # EMA 200 (Filtro Macro de Tendência)
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

        # Bandas de Bollinger (Exaustão Estatística)
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        std_20 = df['Close'].rolling(window=20).std()
        df['BB_UPPER'] = df['SMA_20'] + (std_20 * 2.0)
        df['BB_LOWER'] = df['SMA_20'] - (std_20 * 2.0)

        # RSI 14 (Confirmação de Momento)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))

        return df

    def verificar_escudo_macro(self, tempo_vela_atual):
        t_ny = tempo_vela_atual.time()
        dia_semana = tempo_vela_atual.weekday() # 4 = Sexta-feira

        # Bloqueio Absoluto de Sexta-feira (Toxic Flow Prevention)
        if dia_semana == 4 and t_ny >= datetime.time(15, 0):
            return "🛡️ Bloqueio Macro: Fim de Sessão de Sexta-feira (Spread Tóxico)"
        
        if datetime.time(16, 50) <= t_ny <= datetime.time(18, 5):
            return "🛡️ Bloqueio Macro: Manutenção Diária CME (17:00 NY)"
        
        if datetime.time(8, 15) <= t_ny <= datetime.time(8, 45):
            return "🛡️ Bloqueio Backup: Janela de Dados (08:30 NY)"
        if datetime.time(13, 45) <= t_ny <= datetime.time(14, 30):
            return "🛡️ Bloqueio Backup: Janela FED/Bancos Centrais"

        return "LIVRE"

    def calcular_risco_dinamico(self, preco_entrada, tipo_ordem):
        multiplicador_sl = 2.0
        stop_pontos = self.atr * multiplicador_sl
        pips_de_stop = stop_pontos * self.specs["mult_pip"]
        
        # Rigor absoluto no lote: 1 micro contrato
        lotes = 1 
        risco_financeiro_organico = pips_de_stop * self.specs["valor_ponto"] * lotes 
        casas = self.specs["casas"]
        
        if tipo_ordem == "COMPRA":
            sl_price = preco_entrada - stop_pontos
            tp1 = preco_entrada + (stop_pontos * 1.5)
            tp2 = preco_entrada + (stop_pontos * 2.5)
            tp3 = preco_entrada + (stop_pontos * 4.0)
        else:
            sl_price = preco_entrada + stop_pontos
            tp1 = preco_entrada - (stop_pontos * 1.5)
            tp2 = preco_entrada - (stop_pontos * 2.5)
            tp3 = preco_entrada - (stop_pontos * 4.0)
            
        return {
            "lotes": lotes, "risco_usd": round(risco_financeiro_organico, 2),
            "sl": round(sl_price, casas), "tp1": round(tp1, casas), "tp2": round(tp2, casas), "tp3": round(tp3, casas)
        }

    def escanear_mercado_hft(self):
        if self.df_m5 is None or self.df_m5.empty or pd.isna(self.df_m5['EMA_200'].iloc[-1]): 
            return {"status": "Aguardando Aquecimento do Motor (EMA 200)"}
        
        try:
            tempo_vela_atual = self.df_m5.index[-1].replace(tzinfo=pytz.timezone('America/New_York'))
            status_escudo = self.verificar_escudo_macro(tempo_vela_atual)
            if status_escudo != "LIVRE":
                return {"status": status_escudo}

            p_live = float(self.df_m5['Close'].iloc[-1])
            vela_anterior = self.df_m5.iloc[-2]
            ema_200 = self.df_m5['EMA_200'].iloc[-1]
            
            # LÓGICA INSTITUCIONAL DE REVERSÃO COM FILTRO DE TENDÊNCIA
            # Sinal de COMPRA: Preço estruturalmente em ALTA (acima da EMA 200), mas sofreu correção extrema
            if p_live > ema_200:
                if (vela_anterior['Close'] < vela_anterior['BB_LOWER']) and (vela_anterior['RSI_14'] < 30.0):
                    risco_data = self.calcular_risco_dinamico(p_live, "COMPRA")
                    return {"status": "Sinal Encontrado", "dados": {
                        "tipo": "COMPRA", "fase": "Tendência de Alta (Correção)", "motivo": f"BB_Lower Pierce + RSI Oversold | Risco: ${risco_data['risco_usd']}", 
                        "entrada": p_live, "sl": risco_data['sl'], "tp1": risco_data['tp1'], "tp2": risco_data['tp2'], "tp3": risco_data['tp3'], 
                        "tempo_vela": tempo_vela_atual.replace(tzinfo=None), "id": f"BUY_{self.ticker}_{tempo_vela_atual.strftime('%H%M')}"}}
            
            # Sinal de VENDA: Preço estruturalmente em BAIXA (abaixo da EMA 200), mas sofreu repique extremo
            elif p_live < ema_200:
                if (vela_anterior['Close'] > vela_anterior['BB_UPPER']) and (vela_anterior['RSI_14'] > 70.0):
                    risco_data = self.calcular_risco_dinamico(p_live, "VENDA")
                    return {"status": "Sinal Encontrado", "dados": {
                        "tipo": "VENDA", "fase": "Tendência de Baixa (Repique)", "motivo": f"BB_Upper Pierce + RSI Overbought | Risco: ${risco_data['risco_usd']}", 
                        "entrada": p_live, "sl": risco_data['sl'], "tp1": risco_data['tp1'], "tp2": risco_data['tp2'], "tp3": risco_data['tp3'], 
                        "tempo_vela": tempo_vela_atual.replace(tzinfo=None), "id": f"SELL_{self.ticker}_{tempo_vela_atual.strftime('%H%M')}"}}

            distancia_ema = abs(p_live - ema_200) / p_live * 100
            return {"status": f"Vigília Quântica | Distância EMA 200: {distancia_ema:.2f}%"}
        except Exception as e: return {"status": f"Erro interno no Motor: {e}"}

# ==========================================
# FETCH DE DADOS BLINDADO
# ==========================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_redundante(ticker, p, i):
    tickers_tentativas = [ticker]
    if "MBT" in ticker: tickers_tentativas.extend(["BTC=F", "BTC-USD"]) 
    if "MICD" in ticker: tickers_tentativas.extend(["MCD=F", "CAD=X"])
    if "M6E" in ticker: tickers_tentativas.extend(["EURUSD=X"])
    if "M6B" in ticker: tickers_tentativas.extend(["GBPUSD=X"])
    if "M6A" in ticker: tickers_tentativas.extend(["AUDUSD=X"])
    
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
# INTERFACE DA MATRIZ
# ==========================================
st.markdown("<h2 style='text-align: center; color: black;'>🌍 ULTRON FOREX SQUAD - V2 INSTITUCIONAL</h2>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🧹 Limpar Todos os Diários", use_container_width=True):
        st.session_state.tracker = []
        st.session_state.historico_ids = set() 
        if os.path.exists(ARQUIVO_DIARIO): os.remove(ARQUIVO_DIARIO)
        st.rerun()

@st.fragment(run_every="20s")
def renderizar_painel_operacional():
    houve_alteracao_status = False
    container_mestre = st.container()
    nomes_abas = [NOMES_EXIBICAO.get(t, t) for t in TICKERS_ALVOS]
    tabs = st.tabs(nomes_abas)
    
    for i, ticker in enumerate(TICKERS_ALVOS):
        with tabs[i]:
            try:
                dfs = {'M5': fetch_redundante(ticker, "5d", "5m")}
                
                if dfs['M5'] is not None:
                    engine = UltronEngineForex(dfs, ticker)
                    casas = engine.specs["casas"]
                    
                    c1, c2, c3, c4 = st.columns(4)
                    p_live = float(dfs['M5']['Close'].iloc[-1])
                    c1.metric(f"Ativo", f"{p_live:.{casas}f}")
                    
                    if not pd.isna(engine.df_m5['EMA_200'].iloc[-1]):
                        ema_val = engine.df_m5['EMA_200'].iloc[-1]
                        c2.metric("Tendência Macro", "ALTA 🐂" if p_live > ema_val else "BAIXA 🐻")
                        c3.metric("EMA 200", f"{ema_val:.{casas}f}")
                    else:
                        c2.metric("Tendência Macro", "Calculando...")
                        c3.metric("EMA 200", "Aguardando barras")
                        
                    rsi_val = engine.df_m5['RSI_14'].iloc[-1] if not pd.isna(engine.df_m5['RSI_14'].iloc[-1]) else 50.0
                    c4.metric("RSI (Exaustão)", f"{rsi_val:.1f}")
                    
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
                                        if novo_sl > t['sl']: 
                                            t['sl'] = round(novo_sl, casas)
                                            houve_alteracao_status = True
                                        if l <= t['sl'] and t['status'] == "ATIVO 🟡": 
                                            t['status'] = "STOP TRAILING 🛡️" if t['sl'] > t['ent'] else "LOSS TÉCNICO 🔴"
                                            houve_alteracao_status = True
                                            break
                                        elif h >= t['tp3']: 
                                            t['status'] = "WIN TP3 👑"
                                            houve_alteracao_status = True
                                            break
                                        elif h >= t['tp1'] and t['status'] == "ATIVO 🟡": 
                                            t['status'] = "WIN TP1 🟢"
                                            houve_alteracao_status = True
                                    else: 
                                        novo_sl = l + atr_trailing
                                        if novo_sl < t['sl']: 
                                            t['sl'] = round(novo_sl, casas)
                                            houve_alteracao_status = True
                                        if h >= t['sl'] and t['status'] == "ATIVO 🟡": 
                                            t['status'] = "STOP TRAILING 🛡️" if t['sl'] < t['ent'] else "LOSS TÉCNICO 🔴"
                                            houve_alteracao_status = True
                                            break
                                        elif l <= t['tp3']: 
                                            t['status'] = "WIN TP3 👑"
                                            houve_alteracao_status = True
                                            break
                                        elif l <= t['tp1'] and t['status'] == "ATIVO 🟡": 
                                            t['status'] = "WIN TP1 🟢"
                                            houve_alteracao_status = True
                        
                        tabela = pd.DataFrame(tracker_filtrado).drop(columns=['id', 'entry_time', 'ativo'], errors='ignore')
                        st.dataframe(tabela.iloc[::-1], use_container_width=True, hide_index=True) 
                    else: st.caption(f"Aguardando alinhamento do {NOMES_EXIBICAO.get(ticker, ticker)}...")
                else: st.error("❌ Falha na conexão de dados.")
            except Exception as e: st.error(f"💣 ERRO: {str(e)}")

    if houve_alteracao_status: salvar_caixa_preta()

    with container_mestre:
        st.markdown("<h4 style='color: #003366;'>🦅 DIÁRIO DE BATALHA MESTRE & HUD DE RISCO</h4>", unsafe_allow_html=True)
        if st.session_state.tracker:
            tracker_ativos = [t for t in st.session_state.tracker if t['status'] == "ATIVO 🟡"]
            risco_total = sum([abs(t['ent'] - t['sl']) * ESPECIFICACOES_CME.get(next((k for k, v in NOMES_EXIBICAO.items() if v == t['ativo']), "M6E=F"), ESPECIFICACOES_CME["M6E=F"])["mult_pip"] * ESPECIFICACOES_CME.get(next((k for k, v in NOMES_EXIBICAO.items() if v == t['ativo']), "M6E=F"), ESPECIFICACOES_CME["M6E=F"])["valor_ponto"] for t in tracker_ativos])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Frentes Ativas", len(tracker_ativos))
            c2.metric("Risco Global (Stop-Loss)", f"${risco_total:.2f}")
            c3.metric("Status do Pelotão", "Em Combate ⚔️" if tracker_ativos else "Aguardando Alvos 📡")
            st.divider()
            
            tabela_mestre = pd.DataFrame(st.session_state.tracker).drop(columns=['id', 'entry_time'], errors='ignore')
            cols = tabela_mestre.columns.tolist()
            if 'ativo' in cols:
                cols.insert(0, cols.pop(cols.index('ativo')))
                tabela_mestre = tabela_mestre[cols]
            st.dataframe(tabela_mestre.iloc[::-1], use_container_width=True, hide_index=True)
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Frentes Ativas", 0)
            c2.metric("Risco Global", "$0.00")
            c3.metric("Status", "Radar Varrendo 📡")
            st.info("Otimização de Reversão à Média ativa. Aguardando alinhamento perfeito de Bollinger, RSI e EMA 200.")
        st.divider()

renderizar_painel_operacional()
