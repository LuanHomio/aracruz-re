import pandas as pd
import os
import glob
from datetime import datetime
import requests

HOLDS_WEBHOOK_URL = "https://api.homio.com.br/webhook/aracruz-re/holds"


def carregar_tabela_holds(caminho_arquivo):
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
        if "Hold #" in colunas:
            tabela.columns = colunas
            return tabela

    tabela = tabelas[0]
    tabela.columns = [str(c).strip() for c in tabela.columns]
    return tabela


def processar_e_salvar_holds():
    caminho_holds = os.path.join("downloads", "holds", "*.xls*")
    arquivos = [
        f
        for f in glob.glob(caminho_holds)
        if "_LIMPO" not in f and "DIFERENCAS_HOLDS" not in f
    ]

    if not arquivos:
        print("Nenhum arquivo de holds encontrado.")
        return None

    arquivo_sujo = max(arquivos, key=os.path.getmtime)
    print(f"Processando holds: {arquivo_sujo}")

    df = carregar_tabela_holds(arquivo_sujo)
    if df is None or df.empty:
        print("Nao foi possivel ler a tabela de holds.")
        return None

    df.columns = [str(c).strip() for c in df.columns]
    if "Hold #" not in df.columns:
        print("Coluna 'Hold #' nao encontrada.")
        return None

    df["Hold #"] = df["Hold #"].astype(str).str.strip()
    df = df[df["Hold #"].str.match(r"^\d+$", na=False)]
    df = df.reset_index(drop=True)

    base, _ = os.path.splitext(os.path.basename(arquivo_sujo))
    nome_limpo = f"{base}_LIMPO.xlsx"
    caminho_limpo = os.path.join("downloads", "holds", nome_limpo)

    df.to_excel(caminho_limpo, index=False)
    print(f"Planilha limpa salva em: {caminho_limpo}")
    try:
        os.remove(arquivo_sujo)
        print(f"Arquivo bruto removido: {arquivo_sujo}")
    except Exception as e:
        print(f"⚠️ Erro ao remover arquivo bruto {arquivo_sujo}: {e}")
    return caminho_limpo


def comparar_ultimas_planilhas_holds():
    caminho_limpos = os.path.join("downloads", "holds", "*_LIMPO.xlsx")
    arquivos_limpos = sorted(glob.glob(caminho_limpos), key=os.path.getmtime, reverse=True)

    if len(arquivos_limpos) < 2:
        print("Apenas uma planilha limpa encontrada. Aguardando a proxima execucao para comparar.")
        return None

    arquivo_novo = arquivos_limpos[0]
    arquivo_antigo = arquivos_limpos[1]

    print("\n🔍 Comparando holds:")
    print(f"   Novo:   {os.path.basename(arquivo_novo)}")
    print(f"   Antigo: {os.path.basename(arquivo_antigo)}")

    df_novo = pd.read_excel(arquivo_novo)
    df_antigo = pd.read_excel(arquivo_antigo)

    if "Hold #" not in df_novo.columns or "Hold #" not in df_antigo.columns:
        print("Coluna 'Hold #' ausente em uma das planilhas.")
        return None

    df_novo["Hold #"] = df_novo["Hold #"].astype(str).str.strip()
    df_antigo["Hold #"] = df_antigo["Hold #"].astype(str).str.strip()

    novos = df_novo[~df_novo["Hold #"].isin(df_antigo["Hold #"])]

    df_novo_idx = df_novo.set_index("Hold #")
    df_antigo_idx = df_antigo.set_index("Hold #")

    comuns = df_novo_idx.index.intersection(df_antigo_idx.index)
    lista_log_alteracoes = []
    lista_webhook_alteracoes = []

    colunas_interesse = [c for c in df_novo.columns if c in df_antigo.columns and c != "Hold #"]

    for hold_id in comuns:
        row_n = df_novo_idx.loc[hold_id]
        row_a = df_antigo_idx.loc[hold_id]

        teve_mudanca = False
        for col in colunas_interesse:
            v_n = str(row_n[col]) if not pd.isna(row_n[col]) else ""
            v_a = str(row_a[col]) if not pd.isna(row_a[col]) else ""

            if v_n != v_a:
                teve_mudanca = True
                lista_log_alteracoes.append(
                    {
                        "Hold #": hold_id,
                        "Campo": col,
                        "Valor Antigo": v_a,
                        "Valor Novo": v_n,
                    }
                )

        if teve_mudanca:
            dados_hold = df_novo[df_novo["Hold #"] == hold_id].copy()
            lista_webhook_alteracoes.append(dados_hold)

    df_log_alteracoes = pd.DataFrame(lista_log_alteracoes)
    df_webhook_alteracoes = (
        pd.concat(lista_webhook_alteracoes) if lista_webhook_alteracoes else pd.DataFrame()
    )

    data_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_diff = os.path.join("downloads", "holds", f"DIFERENCAS_HOLDS_{data_str}.xlsx")

    with pd.ExcelWriter(caminho_diff) as writer:
        if not novos.empty:
            novos.to_excel(writer, sheet_name="Novos Holds", index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhum hold novo"}]).to_excel(
                writer, sheet_name="Novos Holds", index=False
            )

        if not df_webhook_alteracoes.empty:
            df_webhook_alteracoes.to_excel(writer, sheet_name="Alteracoes webhook", index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma alteração detectada"}]).to_excel(
                writer, sheet_name="Alteracoes webhook", index=False
            )

        if not df_log_alteracoes.empty:
            df_log_alteracoes.to_excel(writer, sheet_name="Log Alteracoes", index=False)
        else:
            pd.DataFrame([{"Mensagem": "Nenhuma alteração detectada"}]).to_excel(
                writer, sheet_name="Log Alteracoes", index=False
            )

    print(f"\nPlanilha de diferenças gerada: {caminho_diff}")
    print(f"   Novos holds: {len(novos)}")
    print(f"   Holds com alteração: {len(df_webhook_alteracoes)}")
    return caminho_diff


def limpar_arquivos_holds():
    pasta = os.path.join("downloads", "holds")
    padrao_bruto = os.path.join(pasta, "*.xls*")
    padrao_limpo = os.path.join(pasta, "*_LIMPO.xlsx")
    padrao_diff = os.path.join(pasta, "DIFERENCAS_HOLDS_*.xlsx")
    brutos = sorted(glob.glob(padrao_bruto), key=os.path.getmtime, reverse=True)
    for caminho in brutos:
        if "_LIMPO" in os.path.basename(caminho) or "DIFERENCAS_HOLDS" in os.path.basename(caminho):
            continue
        try:
            os.remove(caminho)
            print(f"Removendo hold bruto antigo: {os.path.basename(caminho)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover hold bruto antigo {caminho}: {e}")
    limpos = sorted(glob.glob(padrao_limpo), key=os.path.getmtime, reverse=True)
    for arquivo in limpos[2:]:
        try:
            os.remove(arquivo)
            print(f"Removendo hold LIMPO antigo: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover hold LIMPO antigo {arquivo}: {e}")
    diffs = sorted(glob.glob(padrao_diff), key=os.path.getmtime, reverse=True)
    for arquivo in diffs[3:]:
        try:
            os.remove(arquivo)
            print(f"Removendo diferença de holds antiga: {os.path.basename(arquivo)}")
        except Exception as e:
            print(f"⚠️ Erro ao remover diferença de holds antiga {arquivo}: {e}")


def processar_holds():
    caminho_limpo = processar_e_salvar_holds()
    if not caminho_limpo:
        return None

    caminho_diff = comparar_ultimas_planilhas_holds()
    return caminho_diff


def processar_holds_e_enviar():
    caminho_diff = processar_holds()
    if caminho_diff:
        enviar_holds_para_webhook(caminho_diff)
    return caminho_diff


def enviar_holds_para_webhook(caminho_arquivo):
    if not HOLDS_WEBHOOK_URL or "SUA_URL" in HOLDS_WEBHOOK_URL:
        print("\nWebhook de holds nao configurado. O arquivo nao foi enviado.")
        return False

    try:
        print(f"\nEnviando arquivo para o webhook (holds): {os.path.basename(caminho_arquivo)}...")
        with open(caminho_arquivo, "rb") as f:
            files = {
                "data": (
                    os.path.basename(caminho_arquivo),
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            response = requests.post(HOLDS_WEBHOOK_URL, files=files, timeout=600)
        texto = response.text or ""
        if response.status_code == 200:
            print("Resposta do webhook indica sucesso para holds.")
            limpar_arquivos_holds()
            return True
        print(f"Erro ou resposta inesperada ao enviar para o webhook (holds): Status {response.status_code}")
        print(f"   Resposta: {texto}")
        return False
    except Exception as e:
        print(f"Falha critica ao conectar com o webhook (holds): {e}")
        return False


if __name__ == "__main__":
    processar_holds_e_enviar()
