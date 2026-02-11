import pandas as pd
import os
import glob
import re
from datetime import datetime
import requests

N8N_SALES_WEBHOOK_URL = "https://api.homio.com.br/webhook/aracruz-re/sales"


def carregar_tabela_sales(caminho_arquivo):
    try:
        tabelas = pd.read_html(caminho_arquivo, keep_default_na=False)
    except Exception:
        with open(caminho_arquivo, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        tabelas = pd.read_html(html, keep_default_na=False)

    if not tabelas:
        return None

    for tabela in tabelas:
        colunas = [str(c).strip() for c in tabela.columns]
        if "SO #" in colunas:
            tabela.columns = colunas
            return tabela

    tabela = tabelas[0]
    tabela.columns = [str(c).strip() for c in tabela.columns]
    return tabela


def processar_e_salvar_sales():
    caminho_sales = os.path.join("downloads", "sales", "*.xls*")
    arquivos = [
        f
        for f in glob.glob(caminho_sales)
        if "_LIMPO" not in f and "DIFERENCAS_SALES" not in f
    ]

    if not arquivos:
        print("❌ Nenhum arquivo de sales encontrado.")
        return None

    arquivo_sujo = max(arquivos, key=os.path.getmtime)
    print(f"🧹 Processando sales: {arquivo_sujo}")

    df = carregar_tabela_sales(arquivo_sujo)
    if df is None or df.empty:
        print("❌ Não foi possível ler a tabela de sales.")
        return None

    df.columns = [str(c).strip() for c in df.columns]
    if "SO #" not in df.columns:
        print("❌ Coluna 'SO #' não encontrada.")
        return None

    df["SO #"] = df["SO #"].astype(str).str.strip()
    df = df[df["SO #"].str.match(r"^\d+$", na=False)]
    df = df.reset_index(drop=True)

    base, _ = os.path.splitext(os.path.basename(arquivo_sujo))
    nome_limpo = f"{base}_LIMPO.xlsx"
    caminho_limpo = os.path.join("downloads", "sales", nome_limpo)

    df.to_excel(caminho_limpo, index=False)
    print(f"✅ Planilha limpa salva em: {caminho_limpo}")
    try:
        os.remove(arquivo_sujo)
        print(f"🗑️ Arquivo bruto removido: {arquivo_sujo}")
    except Exception as e:
        print(f"⚠️ Erro ao remover arquivo bruto {arquivo_sujo}: {e}")
    return caminho_limpo


def comparar_ultimas_planilhas_sales():
    caminho_limpos = os.path.join("downloads", "sales", "*_LIMPO.xlsx")
    arquivos_limpos = sorted(glob.glob(caminho_limpos), key=os.path.getmtime, reverse=True)

    if len(arquivos_limpos) < 2:
        print("ℹ️ Apenas uma planilha limpa encontrada. Aguardando a próxima execução para comparar.")
        return None

    arquivo_novo = arquivos_limpos[0]
    arquivo_antigo = arquivos_limpos[1]

    print("\n🔍 Comparando sales:")
    print(f"   Novo:   {os.path.basename(arquivo_novo)}")
    print(f"   Antigo: {os.path.basename(arquivo_antigo)}")

    df_novo = pd.read_excel(arquivo_novo)
    df_antigo = pd.read_excel(arquivo_antigo)

    if "SO #" not in df_novo.columns or "SO #" not in df_antigo.columns:
        print("❌ Coluna 'SO #' ausente em uma das planilhas.")
        return None

    df_novo["SO #"] = df_novo["SO #"].astype(str).str.strip()
    df_antigo["SO #"] = df_antigo["SO #"].astype(str).str.strip()

    novos = df_novo[~df_novo["SO #"].isin(df_antigo["SO #"])]

    df_novo_idx = df_novo.set_index("SO #")
    df_antigo_idx = df_antigo.set_index("SO #")

    comuns = df_novo_idx.index.intersection(df_antigo_idx.index)
    lista_log_alteracoes = []
    lista_ghl_alteracoes = []

    colunas_interesse = [c for c in df_novo.columns if c in df_antigo.columns and c != "SO #"]

    for so in comuns:
        row_n = df_novo_idx.loc[so]
        row_a = df_antigo_idx.loc[so]

        teve_mudanca = False
        for col in colunas_interesse:
            v_n = str(row_n[col]) if not pd.isna(row_n[col]) else ""
            v_a = str(row_a[col]) if not pd.isna(row_a[col]) else ""

            if v_n != v_a:
                teve_mudanca = True
                lista_log_alteracoes.append(
                    {
                        "SO #": so,
                        "Campo": col,
                        "Valor Antigo": v_a,
                        "Valor Novo": v_n,
                    }
                )

        if teve_mudanca:
            dados_sale = df_novo[df_novo["SO #"] == so].copy()
            lista_ghl_alteracoes.append(dados_sale)

    df_log_alteracoes = pd.DataFrame(lista_log_alteracoes)
    df_ghl_alteracoes = (
        pd.concat(lista_ghl_alteracoes) if lista_ghl_alteracoes else pd.DataFrame()
    )

    data_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_diff = os.path.join("downloads", "sales", f"DIFERENCAS_SALES_{data_str}.xlsx")

    with pd.ExcelWriter(caminho_diff) as writer:
        if not novos.empty:
            novos.to_excel(writer, sheet_name="Novas Sales", index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma sale nova"}]).to_excel(
                writer, sheet_name="Novas Sales", index=False
            )

        if not df_ghl_alteracoes.empty:
            df_ghl_alteracoes.to_excel(writer, sheet_name="Alteracoes n8n", index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma alteração detectada"}]).to_excel(
                writer, sheet_name="Alteracoes n8n", index=False
            )

        if not df_log_alteracoes.empty:
            df_log_alteracoes.to_excel(writer, sheet_name="Log Alteracoes", index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma alteração detectada"}]).to_excel(
                writer, sheet_name="Log Alteracoes", index=False
            )

    print(f"\n📊 Planilha de diferenças gerada: {caminho_diff}")
    print(f"   ➕ Novas sales: {len(novos)}")
    print(f"   📝 Sales com Alteração: {len(df_ghl_alteracoes)}")
    return caminho_diff


def limpar_arquivos_sales():
    pasta = os.path.join("downloads", "sales")
    padrao_bruto = os.path.join(pasta, "*.xls*")
    padrao_limpo = os.path.join(pasta, "*_LIMPO.xlsx")
    padrao_diff = os.path.join(pasta, "DIFERENCAS_SALES_*.xlsx")
    brutos = sorted(glob.glob(padrao_bruto), key=os.path.getmtime, reverse=True)
    for caminho in brutos:
        if "_LIMPO" in os.path.basename(caminho) or "DIFERENCAS_SALES" in os.path.basename(caminho):
            continue
        try:
            os.remove(caminho)
            print(f"🗑️ Removendo sales bruto antigo: {os.path.basename(caminho)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover sales bruto antigo {caminho}: {e}")
    limpos = sorted(glob.glob(padrao_limpo), key=os.path.getmtime, reverse=True)
    for arquivo in limpos[2:]:
        try:
            os.remove(arquivo)
            print(f"🗑️ Removendo sales LIMPO antigo: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover sales LIMPO antigo {arquivo}: {e}")
    diffs = sorted(glob.glob(padrao_diff), key=os.path.getmtime, reverse=True)
    for arquivo in diffs[3:]:
        try:
            os.remove(arquivo)
            print(f"🗑️ Removendo diferença de sales antiga: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover diferença de sales antiga {arquivo}: {e}")


def processar_sales():
    caminho_limpo = processar_e_salvar_sales()
    if not caminho_limpo:
        return None

    caminho_diff = comparar_ultimas_planilhas_sales()
    return caminho_diff

def processar_sales_e_enviar():
    caminho_diff = processar_sales()
    if caminho_diff:
        enviar_sales_para_n8n(caminho_diff)
    return caminho_diff


def enviar_sales_para_n8n(caminho_arquivo):
    if not N8N_SALES_WEBHOOK_URL or "SUA_URL" in N8N_SALES_WEBHOOK_URL:
        print("\n⚠️  Webhook do n8n não configurado. O arquivo não foi enviado.")
        return False

    try:
        print(f"\n🚀 Enviando arquivo para o n8n (sales): {os.path.basename(caminho_arquivo)}...")
        with open(caminho_arquivo, "rb") as f:
            files = {
                "data": (
                    os.path.basename(caminho_arquivo),
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            response = requests.post(N8N_SALES_WEBHOOK_URL, files=files, timeout=600)
        texto = response.text or ""
        if response.status_code == 200 and "Sales atualizados com sucesso" in texto:
            print("✅ Resposta do n8n indica sucesso para sales.")
            limpar_arquivos_sales()
            return True
        print(f"❌ Erro ou resposta inesperada ao enviar para o n8n (sales): Status {response.status_code}")
        print(f"   Resposta: {texto}")
        return False
    except Exception as e:
        print(f"❌ Falha crítica ao conectar com o n8n (sales): {e}")
        return False


if __name__ == "__main__":
    processar_sales_e_enviar()
