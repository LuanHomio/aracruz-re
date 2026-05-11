"""promover_main_contacts.py

Fase A do desafio Aracruz: promover relation `main` (contact <-> companies)
com base na planilha "Companies X Contacts.xlsx" preenchida pelo pessoal da
Aracruz RE.

Le 698 rows com Main ID valido, descobre estado atual no GHL via EF
aracruz-re-backfill-companies (step=get-relations), classifica em
NOOP/CREATE/REPLACE/NOT_FOUND e, em --apply, executa delete+create.

Modo default e --dry: gera CSV `dry_run_main_promotion.csv` na pasta atual.

Fase B (95 rows sem Main ID + 1 instrucao) fica fora deste script -- tratar
separado depois.
"""
import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

import openpyxl

BASE = "https://uyaemczdotxlvowytwkt.supabase.co/functions/v1/aracruz-re-backfill-companies"
SHEET = r"C:/Users/Luan Paganucci/Downloads/desafiotcaupanca/Companies X Contacts.xlsx"
ASSOC_MAIN = "69e6418be7979a3c6d1b6c19"
ASSOC_EMPLOYEE = "69e63faf9c60d697228e2b29"
GET_BATCH = 100
PUSH_BATCH = 50
TIMEOUT = 180


def post(step, payload):
    url = f"{BASE}?step={step}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def load_sheet():
    wb = openpyxl.load_workbook(SHEET, data_only=True)
    ws = wb["records"]
    rows = list(ws.iter_rows(values_only=True))[1:]
    out = []
    for r in rows:
        rec_id, comp, main_name, main_id, emp_name, emp_id = r
        if not main_id or not str(main_id).strip():
            continue
        out.append({
            "companyId": str(rec_id).strip(),
            "companyName": str(comp or "").strip(),
            "sheetMainId": str(main_id).strip(),
            "sheetMainName": str(main_name or "").strip(),
            "employeeIds": [x.strip() for x in str(emp_id or "").split(",") if x.strip()],
        })
    return out


def fetch_relations(company_ids):
    by_company = {}
    for i in range(0, len(company_ids), GET_BATCH):
        chunk = company_ids[i:i + GET_BATCH]
        t0 = time.time()
        d = post("get-relations", {"recordIds": chunk, "associationId": ASSOC_MAIN})
        for r in d.get("results", []):
            by_company[r["recordId"]] = r.get("relations", [])
        dt = time.time() - t0
        print(f"[get-relations] batch {i // GET_BATCH + 1}: {len(chunk)} companies, {dt:.1f}s", flush=True)
    return by_company


def classify(row, relations):
    main_rels = [r for r in relations if r["associationId"] == ASSOC_MAIN]
    target_id = row["sheetMainId"]
    if any(r["firstRecordId"] == target_id for r in main_rels):
        return "NOOP", main_rels
    if main_rels:
        return "REPLACE", main_rels
    return "CREATE", []


def write_csv(csv_path, csv_rows):
    fields = ["companyId", "companyName", "action", "sheetMainId", "sheetMainName",
              "existingMainContactIds", "existingMainRelationIds", "employeeIds"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(csv_rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="executar mudancas (default: dry-run)")
    p.add_argument("--csv", default="dry_run_main_promotion.csv")
    p.add_argument("--limit", type=int, default=0,
                   help="processar apenas os primeiros N rows com Main ID (smoke test). 0 = todos")
    args = p.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Modo: {mode}")
    print("Lendo planilha...")
    rows = load_sheet()
    print(f"Rows com Main ID valido (Fase A): {len(rows)}")
    if args.limit and args.limit > 0:
        rows = rows[:args.limit]
        print(f"--limit aplicado: processando apenas {len(rows)} rows")

    company_ids = [r["companyId"] for r in rows]
    print(f"Buscando relations existentes em {len(company_ids)} companies (batches de {GET_BATCH})...")
    by_company = fetch_relations(company_ids)

    buckets = {"CREATE": [], "REPLACE": [], "NOOP": [], "NOT_FOUND": []}
    csv_rows = []
    for r in rows:
        rels = by_company.get(r["companyId"])
        if rels is None:
            buckets["NOT_FOUND"].append({"row": r, "main_rels": []})
            csv_rows.append({
                "companyId": r["companyId"], "companyName": r["companyName"],
                "action": "NOT_FOUND",
                "sheetMainId": r["sheetMainId"], "sheetMainName": r["sheetMainName"],
                "existingMainContactIds": "", "existingMainRelationIds": "",
                "employeeIds": ",".join(r["employeeIds"]),
            })
            continue
        action, main_rels = classify(r, rels)
        buckets[action].append({"row": r, "main_rels": main_rels})
        csv_rows.append({
            "companyId": r["companyId"], "companyName": r["companyName"],
            "action": action,
            "sheetMainId": r["sheetMainId"], "sheetMainName": r["sheetMainName"],
            "existingMainContactIds": ",".join(m["firstRecordId"] for m in main_rels),
            "existingMainRelationIds": ",".join(m["id"] for m in main_rels),
            "employeeIds": ",".join(r["employeeIds"]),
        })

    print()
    print("=== Resumo classificacao ===")
    print(f"CREATE    : {len(buckets['CREATE']):4}  (criar relation main)")
    print(f"REPLACE   : {len(buckets['REPLACE']):4}  (apagar main antiga + criar nova)")
    print(f"NOOP      : {len(buckets['NOOP']):4}  (Main correto ja existe)")
    print(f"NOT_FOUND : {len(buckets['NOT_FOUND']):4}  (company nao retornou no GHL)")
    print(f"Total     : {sum(len(b) for b in buckets.values()):4}")

    csv_path = Path(__file__).parent / args.csv
    write_csv(csv_path, csv_rows)
    print(f"CSV salvo: {csv_path}")

    # Amostras
    for cat in ("CREATE", "REPLACE", "NOOP", "NOT_FOUND"):
        if buckets[cat]:
            print()
            print(f"--- Amostras {cat} (max 3):")
            for it in buckets[cat][:3]:
                r = it["row"]
                extras = ""
                if cat == "REPLACE":
                    extras = f" oldMains={[m['firstRecordId'] for m in it['main_rels']]}"
                print(f"  {r['companyName']!r:50} sheetMain={r['sheetMainName']!r:25} id={r['sheetMainId']}{extras}")

    if not args.apply:
        print()
        print("Modo dry-run. Reveja o CSV e rode com --apply pra executar.")
        return

    print()
    print("=== Aplicando ===")

    # 1. Delete relations main antigas (REPLACE)
    delete_ids = []
    for it in buckets["REPLACE"]:
        for m in it["main_rels"]:
            delete_ids.append(m["id"])
    if delete_ids:
        print(f"Deletando {len(delete_ids)} relations main antigas em batches de {PUSH_BATCH}...")
        total_ok = total_err = 0
        for i in range(0, len(delete_ids), PUSH_BATCH):
            chunk = delete_ids[i:i + PUSH_BATCH]
            d = post("delete-relation", {"relationIds": chunk})
            total_ok += d.get("ok", 0)
            total_err += d.get("errors", 0)
            print(f"  batch {i // PUSH_BATCH + 1}: ok={d.get('ok')} err={d.get('errors')} {d.get('errorSamples') or ''}")
        print(f"DELETE total: ok={total_ok} err={total_err}")
    else:
        print("Nenhuma relation antiga pra deletar.")

    # 2. Create relations main novas (CREATE + REPLACE)
    creates = []
    for it in buckets["CREATE"] + buckets["REPLACE"]:
        r = it["row"]
        creates.append({
            "associationId": ASSOC_MAIN,
            "firstRecordId": r["sheetMainId"],   # contact
            "secondRecordId": r["companyId"],    # company
        })
    if creates:
        print(f"Criando {len(creates)} relations main em batches de {PUSH_BATCH}...")
        total_c = total_d = total_e = 0
        all_err_samples = []
        for i in range(0, len(creates), PUSH_BATCH):
            chunk = creates[i:i + PUSH_BATCH]
            d = post("create-relations", {"relations": chunk})
            total_c += d.get("created", 0)
            total_d += d.get("duplicate", 0)
            total_e += d.get("errors", 0)
            samples = d.get("errorSamples") or []
            all_err_samples.extend(samples[:3])
            print(f"  batch {i // PUSH_BATCH + 1}: created={d.get('created')} dup={d.get('duplicate')} err={d.get('errors')}")
        print(f"CREATE total: created={total_c} duplicate={total_d} errors={total_e}")
        if all_err_samples:
            print(f"Error samples: {all_err_samples[:10]}")
    else:
        print("Nada pra criar.")


if __name__ == "__main__":
    main()
