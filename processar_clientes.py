import pandas as pd
import os
import glob
from io import StringIO
import re
from datetime import datetime
import requests
import html

SUPABASE_WEBHOOK_URL = "https://uyaemczdotxlvowytwkt.supabase.co/functions/v1/aracruz-re-customers"

def extrair_telefones(texto):
    if pd.isna(texto) or str(texto).strip() == "":
        return []
    # Remove parênteses, traços, pontos e barras
    t = re.sub(r'[\(\)\-\.\/]', '', str(texto))
    # Encontra sequências de 8 a 15 dígitos
    numeros = re.findall(r'\d{8,15}', t)
    # Remove duplicados mantendo a ordem
    vistos = set()
    return [x for x in numeros if not (x in vistos or vistos.add(x))]

def processar_e_salvar_clientes():
    caminho_clientes = os.path.join("downloads", "clientes", "*.csv")
    arquivos_csv = [f for f in glob.glob(caminho_clientes) if "_LIMPO" not in f]
    
    if not arquivos_csv:
        print("❌ Nenhum arquivo CSV sujo encontrado.")
        return None
    
    arquivo_sujo = max(arquivos_csv, key=os.path.getmtime)
    print(f"🧹 Limpando arquivo: {arquivo_sujo}")
    
    linhas_limpas = []
    in_style_block = False
    with open(arquivo_sujo, 'r', encoding='utf-8') as f:
        for linha in f:
            l = linha.strip()
            if not l:
                continue
            low = l.lower()
            if in_style_block:
                if '</style>' in low:
                    in_style_block = False
                continue
            if low.startswith('<style'):
                if '</style>' not in low:
                    in_style_block = True
                continue
            if l.startswith('<') or l.endswith('>'):
                continue
            linhas_limpas.append(linha)
    
    if not linhas_limpas:
        return None

    csv_data = StringIO("".join(linhas_limpas))
    df = pd.read_csv(csv_data, quotechar='"', on_bad_lines='warn')
    
    novos_phone1 = []
    novos_phone2 = []
    
    for _, row in df.iterrows():
        tels1 = extrair_telefones(row.get('Phone1', ''))
        tels2 = extrair_telefones(row.get('Phone2', ''))
        tels_mob = extrair_telefones(row.get('Mobile', ''))
        
        todos_tels = []
        for t in tels1 + tels_mob + tels2:
            if t not in todos_tels:
                todos_tels.append(t)
        
        if todos_tels:
            novos_phone1.append(todos_tels[0])
            if len(todos_tels) > 1:
                novos_phone2.append(", ".join(todos_tels[1:]))
            else:
                novos_phone2.append("")
        else:
            novos_phone1.append("")
            novos_phone2.append("")
    
    df['Phone1'] = [str(x) if x else "" for x in novos_phone1]
    df['Phone2'] = [str(x) if x else "" for x in novos_phone2]
    if 'Mobile' in df.columns:
        df['Mobile'] = ""
    
    df['Phone1'] = df['Phone1'].astype(str)
    df['Phone2'] = df['Phone2'].astype(str)
    
    if 'Email' in df.columns:
        def limpar_email(valor):
            if pd.isna(valor):
                return ""
            texto = str(valor)
            texto = html.unescape(texto)
            partes = texto.split('<br>')
            primeiro = partes[0]
            primeiro = re.sub(r'<[^>]+>', '', primeiro)
            return primeiro.strip()
        
        df['Email'] = df['Email'].apply(limpar_email)
    
    if 'Name' in df.columns and 'Status' in df.columns:
        df['Status'] = df['Status'].astype(str)
        mask_zzz = df['Name'].astype(str).str.contains('zzz', case=False, na=False)
        df.loc[mask_zzz, 'Name'] = df.loc[mask_zzz, 'Name'].astype(str).str.replace(r'(?i)zzz', '', regex=True).str.strip()
        df.loc[mask_zzz, 'Status'] = 'Inativo'
    
    nome_base = os.path.basename(arquivo_sujo).replace('.csv', '_LIMPO.xlsx')
    caminho_limpo = os.path.join("downloads", "clientes", nome_base)
    
    df.to_excel(caminho_limpo, index=False)
    print(f"✅ Planilha limpa salva em: {caminho_limpo}")
    
    try:
        os.remove(arquivo_sujo)
        print(f"🗑️ Arquivo original removido: {arquivo_sujo}")
    except Exception as e:
        print(f"⚠️ Erro ao apagar arquivo sujo: {e}")
    
    return caminho_limpo

def comparar_ultimas_planilhas():
    caminho_limpos = os.path.join("downloads", "clientes", "*_LIMPO.xlsx")
    arquivos_limpos = sorted(
        [f for f in glob.glob(caminho_limpos) if not os.path.basename(f).startswith("~$")],
        key=os.path.getmtime, reverse=True
    )
    
    if len(arquivos_limpos) < 2:
        print("ℹ️ Apenas uma planilha encontrada. Aguardando a próxima execução para comparar.")
        return None
    
    arquivo_novo = arquivos_limpos[0]
    arquivo_antigo = arquivos_limpos[1]
    
    print(f"\n🔍 Comparando:")
    print(f"   Novo:   {os.path.basename(arquivo_novo)}")
    print(f"   Antigo: {os.path.basename(arquivo_antigo)}")
    
    df_novo = pd.read_excel(arquivo_novo)
    df_antigo = pd.read_excel(arquivo_antigo)
    
    df_novo_idx = df_novo.set_index('Name')
    df_antigo_idx = df_antigo.set_index('Name')
    
    # 1. Novos Clientes
    novos = df_novo[~df_novo['Name'].isin(df_antigo['Name'])]
    
    # 2. Alterações em clientes existentes
    comuns = df_novo_idx.index.intersection(df_antigo_idx.index)
    lista_log_alteracoes = []
    lista_ghl_alteracoes = []
    
    colunas_interesse = ['Phone1', 'Phone2', 'Address', 'Status', 'City']
    
    for nome in comuns:
        row_n = df_novo_idx.loc[nome]
        row_a = df_antigo_idx.loc[nome]
        
        if isinstance(row_n, pd.DataFrame):
            row_n = row_n.iloc[0]
        if isinstance(row_a, pd.DataFrame):
            row_a = row_a.iloc[0]
        
        teve_mudanca = False
        for col in colunas_interesse:
            if col not in row_n.index or col not in row_a.index:
                continue
            
            val_n = row_n[col]
            val_a = row_a[col]
            
            v_n = "" if pd.isna(val_n) else str(val_n)
            v_a = "" if pd.isna(val_a) else str(val_a)
            
            if v_n != v_a:
                teve_mudanca = True
                lista_log_alteracoes.append({
                    "Cliente": nome,
                    "Campo": col,
                    "Valor Antigo": v_a,
                    "Valor Novo": v_n
                })
        
        # Se houve mudança, adicionamos a linha completa (versão nova) para o n8n
        if teve_mudanca:
            # Pegamos a linha original do df_novo para manter todas as colunas
            dados_cliente = df_novo[df_novo['Name'] == nome].copy()
            lista_ghl_alteracoes.append(dados_cliente)
    
    df_log_alteracoes = pd.DataFrame(lista_log_alteracoes)
    df_ghl_alteracoes = pd.concat(lista_ghl_alteracoes) if lista_ghl_alteracoes else pd.DataFrame()
    
    # 3. Salvar Resultado para o n8n
    data_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_diff = os.path.join("downloads", "clientes", f"DIFERENCAS_CLIENTES_{data_str}.xlsx")
    
    # Adiciona Contact Type = customer para todos os registros enviados ao GHL
    if not novos.empty:
        novos = novos.copy()
        novos['Contact Type'] = 'customer'
    if not df_ghl_alteracoes.empty:
        df_ghl_alteracoes = df_ghl_alteracoes.copy()
        df_ghl_alteracoes['Contact Type'] = 'customer'

    with pd.ExcelWriter(caminho_diff) as writer:
        # Aba 1: Novos
        if not novos.empty:
            novos.to_excel(writer, sheet_name='Novos Clientes', index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhum cliente novo"}]).to_excel(writer, sheet_name='Novos Clientes', index=False)

        # Aba 2: Alterações prontas para n8n (mesmo formato dos Novos)
        if not df_ghl_alteracoes.empty:
            df_ghl_alteracoes.to_excel(writer, sheet_name='Alteracoes n8n', index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma alteração detectada"}]).to_excel(writer, sheet_name='Alteracoes n8n', index=False)
            
        # Aba 3: Log técnico (valor antigo vs novo)
        if not df_log_alteracoes.empty:
            df_log_alteracoes.to_excel(writer, sheet_name='Log Alteracoes', index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma alteração detectada"}]).to_excel(writer, sheet_name='Log Alteracoes', index=False)
            
    print(f"\n📊 Planilha de diferenças gerada: {caminho_diff}")
    print(f"   ➕ Novos: {len(novos)}")
    print(f"   📝 Clientes com Alteração: {len(df_ghl_alteracoes)}")
    return caminho_diff


def limpar_arquivos_clientes():
    pasta = os.path.join("downloads", "clientes")
    padrao_csv = os.path.join(pasta, "*.csv")
    padrao_limpo = os.path.join(pasta, "*_LIMPO.xlsx")
    padrao_diff = os.path.join(pasta, "DIFERENCAS_CLIENTES_*.xlsx")
    csvs = sorted(glob.glob(padrao_csv), key=os.path.getmtime, reverse=True)
    for arquivo in csvs[1:]:
        try:
            os.remove(arquivo)
            print(f"🗑️ Removendo CSV antigo: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover CSV antigo {arquivo}: {e}")
    limpos = sorted(glob.glob(padrao_limpo), key=os.path.getmtime, reverse=True)
    for arquivo in limpos[2:]:
        try:
            os.remove(arquivo)
            print(f"🗑️ Removendo LIMPO antigo: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover LIMPO antigo {arquivo}: {e}")
    diffs = sorted(glob.glob(padrao_diff), key=os.path.getmtime, reverse=True)
    for arquivo in diffs[3:]:
        try:
            os.remove(arquivo)
            print(f"🗑️ Removendo diferença antiga: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover diferença antiga {arquivo}: {e}")

def enviar_para_n8n(caminho_arquivo):
    if not SUPABASE_WEBHOOK_URL or "SUA_URL" in SUPABASE_WEBHOOK_URL:
        print("\n⚠️  Webhook do n8n não configurado. O arquivo não foi enviado.")
        return False
    
    try:
        print(f"\n🚀 Enviando arquivo para o n8n: {os.path.basename(caminho_arquivo)}...")
        with open(caminho_arquivo, "rb") as f:
            files = {
                "data": (
                    os.path.basename(caminho_arquivo),
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV5YWVtY3pkb3R4bHZvd3l0d2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgyNzMxNjYsImV4cCI6MjA2Mzg0OTE2Nn0.lo9M-sAO7BcYglotMcLLktD8xjVva-OV7NMkMiwpXsU"}
            response = requests.post(SUPABASE_WEBHOOK_URL, files=files, headers=headers, timeout=600)
        texto = response.text or ""
        if response.status_code == 200 and "Contatos atualizados com sucesso" in texto:
            print("✅ Resposta do n8n indica sucesso para contatos.")
            limpar_arquivos_clientes()
            return True
        print(f"❌ Erro ou resposta inesperada ao enviar para o n8n: Status {response.status_code}")
        print(f"   Resposta: {texto}")
        return False
    except Exception as e:
        print(f"❌ Falha crítica ao conectar com o n8n: {e}")
        return False

if __name__ == "__main__":
    caminho_limpo = processar_e_salvar_clientes()
    if caminho_limpo:
        caminho_diff = comparar_ultimas_planilhas()
        if caminho_diff:
            enviar_para_n8n(caminho_diff)
