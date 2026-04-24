import pandas as pd
import os
import glob
import re
from datetime import datetime
import requests

SUPABASE_SALES_EDGE_URL = "https://uyaemczdotxlvowytwkt.supabase.co/functions/v1/aracruz-re-sales"
SALES_CHUNK_SIZE = 25


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
    arquivos_limpos = sorted(
        [f for f in glob.glob(caminho_limpos) if not os.path.basename(f).startswith("~$")],
        key=os.path.getmtime, reverse=True
    )

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

    colunas_interesse = [
        c for c in df_novo.columns if c in df_antigo.columns and c not in ("SO #", "Days")
    ]

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


def _contar_itens_sales(caminho_arquivo):
    total = 0
    for sheet in ("Novas Sales", "Alteracoes n8n"):
        try:
            df = pd.read_excel(caminho_arquivo, sheet_name=sheet)
        except Exception:
            continue
        if df.empty:
            continue
        if "Mensagem" in df.columns and len(df.columns) == 1:
            continue
        total += len(df)
    return total


def enviar_sales_para_n8n(caminho_arquivo):
    if not SUPABASE_SALES_EDGE_URL or "SUA_URL" in SUPABASE_SALES_EDGE_URL:
        print("\n⚠️  Edge function de sales não configurada. O arquivo não foi enviado.")
        return False

    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV5YWVtY3pkb3R4bHZvd3l0d2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgyNzMxNjYsImV4cCI6MjA2Mzg0OTE2Nn0.lo9M-sAO7BcYglotMcLLktD8xjVva-OV7NMkMiwpXsU"}

    total = _contar_itens_sales(caminho_arquivo)
    if total == 0:
        print("\nℹ️ Nenhuma sale pra enviar (planilha sem itens).")
        limpar_arquivos_sales()
        return True

    n_chunks = (total + SALES_CHUNK_SIZE - 1) // SALES_CHUNK_SIZE
    print(f"\n🚀 Enviando {total} sale(s) em {n_chunks} chunk(s) de até {SALES_CHUNK_SIZE}: {os.path.basename(caminho_arquivo)}")

    aggregate = {"created": 0, "updated": 0, "no_contact": 0, "error": 0}
    rel_aggregate = {"created": 0, "duplicate": 0, "errors": 0, "missing": 0}
    falhou = False

    for idx in range(n_chunks):
        url = f"{SUPABASE_SALES_EDGE_URL}?chunk_size={SALES_CHUNK_SIZE}&chunk_index={idx}"
        try:
            with open(caminho_arquivo, "rb") as f:
                files = {
                    "data": (
                        os.path.basename(caminho_arquivo),
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                }
                response = requests.post(url, files=files, headers=headers, timeout=300)
        except Exception as e:
            print(f"   Chunk {idx + 1}/{n_chunks}: falha crítica - {e}")
            falhou = True
            continue

        if response.status_code != 200:
            print(f"   Chunk {idx + 1}/{n_chunks}: HTTP {response.status_code} - {(response.text or '')[:300]}")
            falhou = True
            continue

        try:
            data = response.json()
        except Exception:
            print(f"   Chunk {idx + 1}/{n_chunks}: resposta não-JSON - {(response.text or '')[:200]}")
            falhou = True
            continue

        for k, v in (data.get("results") or {}).items():
            aggregate[k] = aggregate.get(k, 0) + int(v or 0)
        for k, v in (data.get("relStats") or {}).items():
            rel_aggregate[k] = rel_aggregate.get(k, 0) + int(v or 0)

        print(f"   Chunk {idx + 1}/{n_chunks} OK: processed={data.get('processed')} results={data.get('results')}")

    print(f"\n📊 Resumo sales: {aggregate}")
    print(f"   Relations seller_sale: {rel_aggregate}")

    if falhou:
        print("❌ Pelo menos um chunk falhou — arquivos preservados pra reenvio manual.")
        return False

    print("✅ Todos os chunks OK.")
    limpar_arquivos_sales()
    return True


if __name__ == "__main__":
    processar_sales_e_enviar()
