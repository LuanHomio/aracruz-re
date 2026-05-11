"""promover_main_fase_b.py

Fase B do desafio Aracruz: tenta resolver as 95 rows da planilha
"Companies X Contacts.xlsx" onde a coluna `Main (Associated Contacts)` tem
um nome mas o ID nao foi preenchido.

Estrategia (acordada com Luan 2026-05-11):
1. Match exato (case/espaco normalizado) em firstName | lastName | contactName
   | firstName+lastName.
2. So MAIN (sem employer_employee).
3. Se contato nao existir no GHL → REVIEW (nao criar contato).

Pra cada row:
  a. Tentativa A — `associated`: ver relations existentes da company; se algum
     associated contact bater com sheet.MainName → CREATE_MAIN.
  b. Tentativa B — `businessName`: buscar contatos cujo companyName bate com
     sheet.CompanyName; filtrar onde nome bate com sheet.MainName → se unico,
     CREATE_MAIN. Multiplos → REVIEW_AMBIGUOUS.
  c. Senao → REVIEW_NOT_FOUND.

Filtra instrucoes explicitas do cliente (palavra "Delete", "Remove", "Skip",
etc).

Modo default = --dry. CSV em `dry_run_main_fase_b.csv`.
"""
import argparse
import csv
import json
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import openpyxl

BASE = "https://uyaemczdotxlvowytwkt.supabase.co/functions/v1/aracruz-re-backfill-companies"
SHEET = r"C:/Users/Luan Paganucci/Downloads/desafiotcaupanca/Companies X Contacts.xlsx"
ASSOC_MAIN = "69e6418be7979a3c6d1b6c19"
ASSOC_EMPLOYEE = "69e63faf9c60d697228e2b29"
GET_BATCH = 100
PUSH_BATCH = 50
TIMEOUT = 180

INSTRUCTION_KEYWORDS = ("delete", "remove", "skip", "ignor", "apagar", "remover", "erase",
                        "archive", "arquivar", "arquiv", "review", "verif", "fix", "duplicate")


def post(step, payload):
    url = f"{BASE}?step={step}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def name_key(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).lower().strip())


def is_instruction(text):
    low = name_key(text)
    return any(k in low for k in INSTRUCTION_KEYWORDS)


def load_phase_b_rows():
    wb = openpyxl.load_workbook(SHEET, data_only=True)
    ws = wb["records"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    out = []
    for r in rows:
        rec_id, comp, main_name, main_id, emp_name, emp_id = r
        if not main_name or not str(main_name).strip():
            continue
        if main_id and str(main_id).strip():
            continue  # Fase A
        out.append({
            "companyId": str(rec_id).strip(),
            "companyName": str(comp or "").strip(),
            "sheetMainName": str(main_name).strip(),
            "instruction": is_instruction(main_name),
        })
    return out


def candidates_for_contact(c):
    """Retorna set de name_keys que representam este contact (pra matching)."""
    fn = name_key(c.get("firstName"))
    ln = name_key(c.get("lastName"))
    cn = name_key(c.get("contactName"))
    full = name_key(f"{c.get('firstName') or ''} {c.get('lastName') or ''}")
    return {k for k in (fn, ln, cn, full) if k}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--csv", default="dry_run_main_fase_b.csv")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Modo: {mode}")
    print("Lendo planilha (Fase B)...")
    rows = load_phase_b_rows()
    print(f"Rows com nome de Main mas sem ID: {len(rows)} (incluindo {sum(1 for r in rows if r['instruction'])} instrucoes)")
    if args.limit and args.limit > 0:
        rows = rows[:args.limit]
        print(f"--limit aplicado: processando {len(rows)} rows")

    # 1. Pegar todos os contatos do GHL
    print("Listando todos os contatos da location (list-contacts-bulk)...")
    t0 = time.time()
    d = post("list-contacts-bulk", {})
    contacts = d.get("contacts", [])
    print(f"  {len(contacts)} contatos em {time.time()-t0:.1f}s")

    # 2. Indexar
    by_id = {c["id"]: c for c in contacts}
    by_company = defaultdict(list)  # normalized companyName -> [contact]
    for c in contacts:
        cn_key = name_key(c.get("companyName"))
        if cn_key:
            by_company[cn_key].append(c)

    # 3. Pegar relations das companies da Fase B (pra Tentativa A)
    company_ids = [r["companyId"] for r in rows]
    relations_by_company = {}
    for i in range(0, len(company_ids), GET_BATCH):
        chunk = company_ids[i:i + GET_BATCH]
        t0 = time.time()
        d2 = post("get-relations", {"recordIds": chunk, "associationId": ASSOC_MAIN})
        for r in d2.get("results", []):
            relations_by_company[r["recordId"]] = r.get("relations", [])
        print(f"  [get-relations] batch {i // GET_BATCH + 1}: {len(chunk)} cos, {time.time()-t0:.1f}s")

    # 4. Classificar
    buckets = defaultdict(list)
    csv_rows = []

    for r in rows:
        sheet_main = r["sheetMainName"]
        sheet_main_key = name_key(sheet_main)
        company_key = name_key(r["companyName"])

        if r["instruction"]:
            action = "REVIEW_INSTRUCTION"
            matched = None
            note = f"texto parece instrucao do cliente: {sheet_main!r}"
        else:
            rels = relations_by_company.get(r["companyId"], [])
            # exclui relations seller_sale (lado company-opp), so contact-side
            contact_ids_assoc = [
                rel["firstRecordId"] for rel in rels
                if rel.get("firstObjectKey") == "contact"
            ]

            # Tentativa A: associated contact com nome batendo
            tentA_matches = []
            for cid in contact_ids_assoc:
                c = by_id.get(cid)
                if not c:
                    continue
                if sheet_main_key in candidates_for_contact(c):
                    tentA_matches.append(c)

            # Tentativa B: businessName == companyName + nome batendo
            tentB_matches = []
            for c in by_company.get(company_key, []):
                if sheet_main_key in candidates_for_contact(c):
                    tentB_matches.append(c)

            # Decisao
            unique_A = {c["id"]: c for c in tentA_matches}
            unique_B = {c["id"]: c for c in tentB_matches}

            if len(unique_A) == 1:
                c = next(iter(unique_A.values()))
                action = "CREATE_VIA_ASSOCIATED"
                matched = c
                note = f"unico match em associated contacts"
            elif len(unique_B) == 1:
                c = next(iter(unique_B.values()))
                action = "CREATE_VIA_BUSINESSNAME"
                matched = c
                note = f"unico match via companyName"
            elif len(unique_A) > 1 or len(unique_B) > 1:
                action = "REVIEW_AMBIGUOUS"
                matched = None
                ids_a = list(unique_A.keys())
                ids_b = list(unique_B.keys())
                note = f"associated_matches={ids_a} business_matches={ids_b}"
            else:
                action = "REVIEW_NOT_FOUND"
                matched = None
                # Pista: tem contatos com o nome mas sem businessName batendo?
                pure_name_matches = [c["id"] for c in contacts if sheet_main_key in candidates_for_contact(c)][:5]
                note = f"nenhum match; contatos com nome similar (sem business match): {pure_name_matches}"

        buckets[action].append({"row": r, "matched": matched})
        csv_rows.append({
            "companyId": r["companyId"],
            "companyName": r["companyName"],
            "action": action,
            "sheetMainName": r["sheetMainName"],
            "matchedContactId": matched["id"] if matched else "",
            "matchedContactName": (matched.get("contactName") or "") if matched else "",
            "matchedFirstLast": f"{(matched.get('firstName') or '')} {(matched.get('lastName') or '')}".strip() if matched else "",
            "matchedBusinessName": (matched.get("companyName") or "") if matched else "",
            "note": note,
        })

    print()
    print("=== Resumo classificacao Fase B ===")
    for k in ["CREATE_VIA_ASSOCIATED", "CREATE_VIA_BUSINESSNAME", "REVIEW_AMBIGUOUS",
              "REVIEW_INSTRUCTION", "REVIEW_NOT_FOUND"]:
        print(f"  {k:25}: {len(buckets[k])}")
    total_create = len(buckets["CREATE_VIA_ASSOCIATED"]) + len(buckets["CREATE_VIA_BUSINESSNAME"])
    print(f"  -> CREATE total: {total_create}")

    # CSV
    csv_path = Path(__file__).parent / args.csv
    fields = ["companyId", "companyName", "action", "sheetMainName", "matchedContactId",
              "matchedContactName", "matchedFirstLast", "matchedBusinessName", "note"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(csv_rows)
    print(f"CSV salvo: {csv_path}")

    # Amostras
    for cat in ["CREATE_VIA_ASSOCIATED", "CREATE_VIA_BUSINESSNAME", "REVIEW_AMBIGUOUS", "REVIEW_NOT_FOUND"]:
        if buckets[cat]:
            print()
            print(f"--- Amostras {cat} (max 5):")
            for it in buckets[cat][:5]:
                r = it["row"]
                m = it["matched"]
                ms = f"-> {m['id']} {m.get('contactName')!r} biz={m.get('companyName')!r}" if m else ""
                print(f"  {r['companyName']!r:50} sheetMain={r['sheetMainName']!r:25} {ms}")

    if not args.apply:
        print()
        print("Dry-run. Reveja CSV e rode --apply.")
        return

    # APPLY
    print()
    print("=== Aplicando ===")
    creates = []
    for cat in ("CREATE_VIA_ASSOCIATED", "CREATE_VIA_BUSINESSNAME"):
        for it in buckets[cat]:
            creates.append({
                "associationId": ASSOC_MAIN,
                "firstRecordId": it["matched"]["id"],
                "secondRecordId": it["row"]["companyId"],
            })
    if not creates:
        print("Nada pra criar.")
        return
    print(f"Criando {len(creates)} relations main em batches de {PUSH_BATCH}...")
    total_c = total_d = total_e = 0
    for i in range(0, len(creates), PUSH_BATCH):
        chunk = creates[i:i + PUSH_BATCH]
        d3 = post("create-relations", {"relations": chunk})
        total_c += d3.get("created", 0)
        total_d += d3.get("duplicate", 0)
        total_e += d3.get("errors", 0)
        print(f"  batch {i // PUSH_BATCH + 1}: created={d3.get('created')} dup={d3.get('duplicate')} err={d3.get('errors')}")
    print(f"Total: created={total_c} duplicate={total_d} errors={total_e}")


if __name__ == "__main__":
    main()
