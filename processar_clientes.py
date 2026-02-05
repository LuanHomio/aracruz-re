import pandas as pd
import os
import glob
from io import StringIO
import re
from datetime import datetime
import requests

# URL do seu Webhook do n8n (Substitua pela sua URL real)
N8N_WEBHOOK_URL = "https://api.homio.com.br/webhook/aracruz-re"

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
    with open(arquivo_sujo, 'r', encoding='utf-8') as f:
        for linha in f:
            l = linha.strip()
            if not l or l.startswith('<') or l.endswith('>'):
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
            
    # Atualiza o DataFrame com os telefones organizados e garante que sejam STRING
    df['Phone1'] = [str(x) if x else "" for x in novos_phone1]
    df['Phone2'] = [str(x) if x else "" for x in novos_phone2]
    if 'Mobile' in df.columns:
        df['Mobile'] = ""
    
    # Garantir que as colunas de telefone sejam tratadas como objeto/string pelo pandas
    df['Phone1'] = df['Phone1'].astype(str)
    df['Phone2'] = df['Phone2'].astype(str)
    
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
    arquivos_limpos = sorted(glob.glob(caminho_limpos), key=os.path.getmtime, reverse=True)
    
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
        
        teve_mudanca = False
        for col in colunas_interesse:
            v_n = str(row_n[col]) if not pd.isna(row_n[col]) else ""
            v_a = str(row_a[col]) if not pd.isna(row_a[col]) else ""
            
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

def enviar_para_n8n(caminho_arquivo):
    if not N8N_WEBHOOK_URL or "SUA_URL" in N8N_WEBHOOK_URL:
        print("\n⚠️  Webhook do n8n não configurado. O arquivo não foi enviado.")
        return False
    
    try:
        print(f"\n🚀 Enviando arquivo para o n8n: {os.path.basename(caminho_arquivo)}...")
        
        with open(caminho_arquivo, 'rb') as f:
            # Enviando como 'data' que é o padrão que o n8n espera para arquivos binários
            files = {'data': (os.path.basename(caminho_arquivo), f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
            response = requests.post(N8N_WEBHOOK_URL, files=files, timeout=30)
            
        if response.status_code == 200:
            print("✅ Arquivo enviado com sucesso para o n8n!")
            return True
        else:
            print(f"❌ Erro ao enviar para o n8n: Status {response.status_code}")
            print(f"   Resposta: {response.text}")
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
