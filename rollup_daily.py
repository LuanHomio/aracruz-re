"""Rollup diario das Aracruz companies no GHL.

Chama EF `aracruz-re-company-rollups`:
1. step=collect paginado (50 opps won/page) ate hasMore=false
2. Agrega em memoria por companyId
3. step=push-rollups em batches de 100

Apos rollups, ativa/inativa companies via EF `aracruz-re-backfill-companies`:
4. step=list-companies (retorna {id, name, company_status} de todas)
5. Pra cada company com won: ativo se last_purchase_date >= hoje-3m, inativo se <
6. Filtra: skip status nao-{ativo,inativo} (vip/potencial/bloqueado preservados)
   e skip no-op (status atual == novo)
7. step=bulk-set-status em batches de 100

Roda ~30min em condicoes normais (1000+ opps won, 400+ companies).
Criado 2026-04-23. Status sales-driven adicionado 2026-05-04.
Ver wiki `projetos/aracruz_re.md`.
"""
import urllib.request
import json
import time
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

BASE = "https://uyaemczdotxlvowytwkt.supabase.co/functions/v1/aracruz-re-company-rollups"
BASE_BACKFILL = "https://uyaemczdotxlvowytwkt.supabase.co/functions/v1/aracruz-re-backfill-companies"
PAGE_LIMIT = 50
PUSH_BATCH = 100
STATUS_BATCH = 100
INACTIVE_AFTER_DAYS = 90  # ~3 meses sem won -> inativo


def collect_all():
    all_items = []
    page = 1
    stats_totals = {"viaSeller": 0, "viaContactMain": 0, "none": 0}
    while True:
        url = f"{BASE}?step=collect&page={page}&limit={PAGE_LIMIT}"
        req = urllib.request.Request(
            url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=180) as resp:
            d = json.loads(resp.read().decode())
        dt = time.time() - t0
        items = d.get("items", [])
        all_items.extend(items)
        s = d.get("resolveStats") or {}
        for k in stats_totals:
            stats_totals[k] += s.get(k, 0)
        print(
            f"[collect] page {page}: {len(items)} items, {dt:.1f}s, stats={s}",
            flush=True,
        )
        if not d.get("hasMore"):
            break
        page += 1
    return all_items, stats_totals


def aggregate(items):
    agg = defaultdict(
        lambda: {"total": 0.0, "count": 0, "last_date": None, "last_value": 0.0}
    )
    for it in items:
        cid = it.get("companyId")
        if not cid:
            continue
        d = it.get("dateISO")
        amt = it.get("amount", 0) or 0
        a = agg[cid]
        a["total"] += amt
        a["count"] += 1
        if d and (a["last_date"] is None or d > a["last_date"]):
            a["last_date"] = d
            a["last_value"] = amt
    rollups = []
    for cid, a in agg.items():
        if not a["last_date"]:
            continue
        rollups.append(
            {
                "companyId": cid,
                "last_purchase_date": a["last_date"],
                "last_purchase_value": round(a["last_value"], 2),
                "total_sales": round(a["total"], 2),
                "purchases_count": a["count"],
            }
        )
    return rollups


def push_all(rollups):
    total_ok, total_err = 0, 0
    for i in range(0, len(rollups), PUSH_BATCH):
        batch = rollups[i : i + PUSH_BATCH]
        body = json.dumps({"rollups": batch}).encode()
        req = urllib.request.Request(
            f"{BASE}?step=push-rollups",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                d = json.loads(resp.read().decode())
            dt = time.time() - t0
            total_ok += d["ok"]
            total_err += d["errors"]
            print(
                f"[push] batch {i // PUSH_BATCH + 1} ({len(batch)}, {dt:.1f}s): ok={d['ok']} err={d['errors']}",
                flush=True,
            )
            for e in d.get("errorSamples", [])[:3]:
                print(f"  error: {e}", flush=True)
        except Exception as e:
            print(f"[push] batch {i // PUSH_BATCH + 1} EXCEPTION: {e}", flush=True)
            total_err += len(batch)
    return total_ok, total_err


def list_all_companies():
    """Chama list-companies da EF backfill, retorna lista [{id, name, company_status}]."""
    url = f"{BASE_BACKFILL}?step=list-companies"
    req = urllib.request.Request(
        url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        d = json.loads(resp.read().decode())
    return d.get("companies", [])


def compute_status_changes(rollups, companies):
    """Retorna lista de pairs [{companyId, status}] que precisam mudar.

    Regras:
    - Company com last_purchase_date >= hoje-90d -> deveria estar 'ativo'
    - Company com last_purchase_date < hoje-90d -> deveria estar 'inativo'
    - Companies sem won (nao tem rollup) -> nao mexe (1b)
    - Companies com status atual nao em {ativo, inativo} -> preserva (vip/potencial/bloqueado)
    - Skip se status atual == novo (no-op)
    """
    cutoff = date.today() - timedelta(days=INACTIVE_AFTER_DAYS)
    by_id = {c["id"]: c for c in companies}

    pairs = []
    skipped_preserved = 0  # vip/potencial/bloqueado
    skipped_noop = 0
    skipped_missing = 0  # companyId no rollup mas nao na lista (raro)
    transitions = {"ativo->inativo": 0, "inativo->ativo": 0, "none->ativo": 0, "none->inativo": 0}

    for r in rollups:
        cid = r["companyId"]
        company = by_id.get(cid)
        if not company:
            skipped_missing += 1
            continue

        current = (company.get("company_status") or "").lower().strip()
        if current and current not in ("ativo", "inativo"):
            skipped_preserved += 1
            continue

        # Parse last_purchase_date (ISO string, formato variavel)
        d_raw = r["last_purchase_date"]
        try:
            last_d = datetime.fromisoformat(d_raw.replace("Z", "+00:00")).date()
        except Exception:
            try:
                last_d = datetime.strptime(d_raw, "%Y-%m-%d").date()
            except Exception:
                continue  # data invalida, skip

        new_status = "ativo" if last_d >= cutoff else "inativo"
        if new_status == current:
            skipped_noop += 1
            continue

        if not current:
            transitions[f"none->{new_status}"] += 1
        else:
            transitions[f"{current}->{new_status}"] += 1

        pairs.append({"companyId": cid, "status": new_status})

    return pairs, {
        "skipped_preserved": skipped_preserved,
        "skipped_noop": skipped_noop,
        "skipped_missing": skipped_missing,
        "transitions": transitions,
    }


def push_status_changes(pairs):
    """Chama bulk-set-status em batches."""
    total_ok, total_err = 0, 0
    for i in range(0, len(pairs), STATUS_BATCH):
        batch = pairs[i : i + STATUS_BATCH]
        body = json.dumps({"pairs": batch}).encode()
        req = urllib.request.Request(
            f"{BASE_BACKFILL}?step=bulk-set-status",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                d = json.loads(resp.read().decode())
            dt = time.time() - t0
            total_ok += d["ok"]
            total_err += d["errors"]
            print(
                f"[status] batch {i // STATUS_BATCH + 1} ({len(batch)}, {dt:.1f}s): ok={d['ok']} err={d['errors']}",
                flush=True,
            )
            for e in d.get("errorSamples", [])[:3]:
                print(f"  error: {e}", flush=True)
        except Exception as e:
            print(f"[status] batch {i // STATUS_BATCH + 1} EXCEPTION: {e}", flush=True)
            total_err += len(batch)
    return total_ok, total_err


def main():
    t_start = time.time()
    print(f"=== Rollup Aracruz inicio {time.strftime('%Y-%m-%d %H:%M:%S')} ===", flush=True)
    items, stats = collect_all()
    print(f"\nTotal coletado: {len(items)}. Stats: {stats}", flush=True)
    rollups = aggregate(items)
    print(f"Companies com rollup: {len(rollups)}", flush=True)
    total_sales = sum(r["total_sales"] for r in rollups)
    total_purchases = sum(r["purchases_count"] for r in rollups)
    print(f"Total sales: ${total_sales:,.2f} em {total_purchases} compras", flush=True)
    ok, err = push_all(rollups)
    print(f"\n[rollups] push ok={ok} err={err}", flush=True)

    # Atualizacao de status sales-driven
    print(f"\n=== Status sales-driven (cutoff: {INACTIVE_AFTER_DAYS}d) ===", flush=True)
    companies = list_all_companies()
    print(f"Total companies no GHL: {len(companies)}", flush=True)
    pairs, meta = compute_status_changes(rollups, companies)
    print(f"Mudancas a aplicar: {len(pairs)}", flush=True)
    print(f"  transitions: {meta['transitions']}", flush=True)
    print(f"  skipped: preserved={meta['skipped_preserved']} noop={meta['skipped_noop']} missing={meta['skipped_missing']}", flush=True)

    status_ok, status_err = (0, 0)
    if pairs:
        status_ok, status_err = push_status_changes(pairs)
        print(f"[status] push ok={status_ok} err={status_err}", flush=True)
    else:
        print("[status] sem mudancas — skip", flush=True)

    ativadas = meta["transitions"]["inativo->ativo"] + meta["transitions"]["none->ativo"]
    inativadas = meta["transitions"]["ativo->inativo"] + meta["transitions"]["none->inativo"]

    elapsed = time.time() - t_start
    print(f"\n=== Fim total: {elapsed / 60:.1f}min ===", flush=True)

    # Relatorio final (1 linha) pra WhatsApp
    print(
        f"\nREPORT|companies={len(rollups)}|ok={ok}|err={err}|no_company={stats['none']}|total_sales={total_sales:.2f}"
        f"|ativadas={ativadas}|inativadas={inativadas}|status_err={status_err}|elapsed_min={elapsed / 60:.1f}",
        flush=True,
    )
    sys.exit(0 if (err == 0 and status_err == 0) else 1)


if __name__ == "__main__":
    main()
