import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import * as XLSX from "https://esm.sh/xlsx@0.18.5";
import { getLocationAccessToken } from "./lib/ghl-auth.ts";

const GHL_VERSION = Deno.env.get("GHL_VERSION") || "2021-07-28";
const GHL_BASE = "https://services.leadconnectorhq.com";
const LOCATION_ID = "wsldse1ZJdG8zWI8OILI";
const OBJECT_KEY = "custom_objects.companies";
const ASSOC_MAIN = "69e6418be7979a3c6d1b6c19";
const ASSOC_EMPLOYEE = "69e63faf9c60d697228e2b29";
const ASSOC_SELLER = "69e640a54b8e890cd8e88fa2";
const RATE_LIMIT_MS = 50;

function cors(extra: Record<string, string> = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    ...extra,
  };
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function ghlHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    Version: GHL_VERSION,
    "Content-Type": "application/json",
    Accept: "application/json",
  };
}

function normalizeName(s: unknown): string {
  return String(s ?? "").trim();
}
function nameKey(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim();
}

async function parseNamesFromXlsx(req: Request): Promise<string[]> {
  const ct = req.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    const body = await req.json() as { names?: string[] };
    return (body.names || []).map(normalizeName).filter(Boolean);
  }
  const form = await req.formData();
  const file = form.get("data") as File | null;
  if (!file) return [];
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(new Uint8Array(buf), { type: "array" });
  const names: string[] = [];
  for (const sheetName of wb.SheetNames) {
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[sheetName], { defval: "" }) as Record<string, unknown>[];
    for (const r of rows) {
      if (r["Mensagem"]) continue;
      const n = normalizeName(r["Name"] ?? r["name"] ?? r["Company"]);
      if (n) names.push(n);
    }
  }
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const n of names) {
    const k = nameKey(n);
    if (seen.has(k)) continue;
    seen.add(k);
    unique.push(n);
  }
  return unique;
}

async function searchCompanyByName(token: string, name: string): Promise<string | null> {
  const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records/search`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify({ locationId: LOCATION_ID, page: 1, pageLimit: 20, query: name }),
  });
  if (!resp.ok) return null;
  const data = await resp.json() as { records?: Array<{ id: string; properties?: Record<string, unknown> }> };
  const target = nameKey(name);
  for (const rec of data.records || []) {
    const v = normalizeName(rec.properties?.["company"]);
    if (nameKey(v) === target) return rec.id;
  }
  return null;
}

async function createCompany(token: string, name: string): Promise<string> {
  const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify({ locationId: LOCATION_ID, properties: { company: name } }),
  });
  const txt = await resp.text();
  if (!resp.ok) throw new Error(`createCompany "${name}" ${resp.status}: ${txt.slice(0, 300)}`);
  const data = JSON.parse(txt);
  return data.record?.id ?? data.id;
}

async function listContactsPage(token: string, searchAfter?: unknown[]): Promise<{ contacts: Array<{ id: string; companyName?: string | null }>; nextAfter?: unknown[] }> {
  const body: Record<string, unknown> = { locationId: LOCATION_ID, pageLimit: 100 };
  if (searchAfter) body.searchAfter = searchAfter;
  const resp = await fetch(`${GHL_BASE}/contacts/search`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify(body),
  });
  const txt = await resp.text();
  if (!resp.ok) throw new Error(`contacts/search ${resp.status}: ${txt.slice(0, 300)}`);
  const data = JSON.parse(txt) as { contacts?: Array<Record<string, unknown>> };
  const contacts = (data.contacts || []).map((c) => ({
    id: String(c.id),
    companyName: c.companyName as string | null | undefined,
  }));
  const last = (data.contacts || []).slice(-1)[0] as Record<string, unknown> | undefined;
  const nextAfter = last?.searchAfter as unknown[] | undefined;
  return { contacts, nextAfter };
}

async function createRelation(token: string, associationId: string, firstId: string, secondId: string): Promise<"created" | "duplicate" | "error"> {
  const resp = await fetch(`${GHL_BASE}/associations/relations`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify({ locationId: LOCATION_ID, associationId, firstRecordId: firstId, secondRecordId: secondId }),
  });
  if (resp.ok) return "created";
  const txt = await resp.text();
  if (/duplicate relation/i.test(txt)) return "duplicate";
  console.error(`relation error ${resp.status}: ${txt.slice(0, 300)}`);
  return "error";
}

interface StepCompaniesResult {
  step: "companies";
  totalNames: number;
  created: number;
  existed: number;
  errors: number;
  sampleCreated: string[];
  sampleErrors: string[];
}

async function stepCompanies(token: string, names: string[]): Promise<StepCompaniesResult> {
  const result: StepCompaniesResult = {
    step: "companies",
    totalNames: names.length,
    created: 0,
    existed: 0,
    errors: 0,
    sampleCreated: [],
    sampleErrors: [],
  };
  for (const name of names) {
    try {
      const existing = await searchCompanyByName(token, name);
      if (existing) {
        result.existed++;
      } else {
        await createCompany(token, name);
        result.created++;
        if (result.sampleCreated.length < 5) result.sampleCreated.push(name);
      }
    } catch (e) {
      result.errors++;
      if (result.sampleErrors.length < 10) {
        result.sampleErrors.push(`${name}: ${(e as Error).message}`);
      }
    }
    await sleep(RATE_LIMIT_MS);
  }
  return result;
}

interface StepRelationsResult {
  step: "relations";
  pagesProcessed: number;
  contactsScanned: number;
  contactsMatched: number;
  contactsSkippedNoCompany: number;
  contactsSkippedCompanyNotFound: number;
  relationsCreated: number;
  relationsDuplicate: number;
  relationsErrors: number;
  hasMore: boolean;
  nextAfter?: unknown[];
  note: string;
}

async function stepRelations(token: string, pages: number, searchAfter: unknown[] | undefined): Promise<StepRelationsResult> {
  const companyCache = new Map<string, string | null>();

  const result: StepRelationsResult = {
    step: "relations",
    pagesProcessed: 0,
    contactsScanned: 0,
    contactsMatched: 0,
    contactsSkippedNoCompany: 0,
    contactsSkippedCompanyNotFound: 0,
    relationsCreated: 0,
    relationsDuplicate: 0,
    relationsErrors: 0,
    hasMore: false,
    note: "Todas as relations sao criadas como employer_employee (secondary). Promocao pra main fica pra fase 2 (depende dos dados de opps).",
  };

  let after = searchAfter;
  for (let i = 0; i < pages; i++) {
    const { contacts, nextAfter } = await listContactsPage(token, after);
    result.pagesProcessed++;
    result.contactsScanned += contacts.length;
    if (contacts.length === 0) break;

    for (const c of contacts) {
      const cn = normalizeName(c.companyName);
      if (!cn) { result.contactsSkippedNoCompany++; continue; }
      const key = nameKey(cn);

      if (!companyCache.has(key)) {
        const found = await searchCompanyByName(token, cn);
        companyCache.set(key, found);
        await sleep(RATE_LIMIT_MS);
      }
      const cid = companyCache.get(key) ?? null;
      if (!cid) { result.contactsSkippedCompanyNotFound++; continue; }

      result.contactsMatched++;
      const r = await createRelation(token, ASSOC_EMPLOYEE, c.id, cid);
      if (r === "created") result.relationsCreated++;
      else if (r === "duplicate") result.relationsDuplicate++;
      else result.relationsErrors++;
      await sleep(RATE_LIMIT_MS);
    }

    after = nextAfter;
    if (!after || contacts.length < 100) {
      result.hasMore = false;
      break;
    } else {
      result.hasMore = true;
    }
  }

  if (after) result.nextAfter = after;
  return result;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors() });
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: cors({ "Content-Type": "application/json" }),
    });
  }

  try {
    const url = new URL(req.url);
    const step = url.searchParams.get("step") || "companies";
    const token = await getLocationAccessToken(LOCATION_ID);

    if (step === "companies") {
      const names = await parseNamesFromXlsx(req);
      if (names.length === 0) {
        return new Response(JSON.stringify({ step, error: "Nenhum nome encontrado na planilha" }), {
          status: 400,
          headers: cors({ "Content-Type": "application/json" }),
        });
      }
      const result = await stepCompanies(token, names);
      return new Response(JSON.stringify(result, null, 2), {
        status: 200,
        headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "relations") {
      const pages = Math.max(1, Math.min(10, parseInt(url.searchParams.get("pages") || "5", 10)));
      let searchAfter: unknown[] | undefined;
      const saRaw = url.searchParams.get("searchAfter");
      if (saRaw) {
        try { searchAfter = JSON.parse(saRaw); } catch { /* ignore */ }
      }
      if (!searchAfter) {
        const ct = req.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          try {
            const body = await req.json() as { searchAfter?: unknown[] };
            if (Array.isArray(body.searchAfter)) searchAfter = body.searchAfter;
          } catch { /* ignore */ }
        }
      }
      const result = await stepRelations(token, pages, searchAfter);
      return new Response(JSON.stringify(result, null, 2), {
        status: 200,
        headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "create-relations") {
      const body = await req.json() as { relations?: Array<{ associationId: string; firstRecordId: string; secondRecordId: string }> };
      const rels = body.relations || [];
      if (rels.length === 0) {
        return new Response(JSON.stringify({ error: "relations[] required" }), {
          status: 400, headers: cors({ "Content-Type": "application/json" }),
        });
      }
      let created = 0, duplicate = 0, errors = 0;
      const errorSamples: string[] = [];
      for (const r of rels) {
        const res = await createRelation(token, r.associationId, r.firstRecordId, r.secondRecordId);
        if (res === "created") created++;
        else if (res === "duplicate") duplicate++;
        else {
          errors++;
          if (errorSamples.length < 10) errorSamples.push(`${r.firstRecordId}->${r.secondRecordId}`);
        }
        await sleep(RATE_LIMIT_MS);
      }
      return new Response(JSON.stringify({ step, total: rels.length, created, duplicate, errors, errorSamples }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "probe-opp") {
      // Retorna dump completo de 1 opp pra entender shape
      const body = await req.json() as { oppId: string };
      const resp = await fetch(`${GHL_BASE}/opportunities/${body.oppId}`, {
        method: "GET", headers: ghlHeaders(token),
      });
      const txt = await resp.text();
      return new Response(JSON.stringify({ status: resp.status, body: txt }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "list-all-opps") {
      // Lista TODAS as opportunities paginando, retorna id + pipelineId
      const all: Array<{ id: string; pipelineId: string; status: string; monetaryValue: number; contactId: string | null; updatedAt: string; name: string }> = [];
      let page = 1;
      const maxPages = Math.max(1, Math.min(100, parseInt(url.searchParams.get("maxPages") || "30", 10)));
      while (page <= maxPages) {
        const resp = await fetch(`${GHL_BASE}/opportunities/search?location_id=${LOCATION_ID}&limit=100&page=${page}`, {
          method: "GET",
          headers: ghlHeaders(token),
        });
        const txt = await resp.text();
        if (!resp.ok) throw new Error(`list-all-opps page=${page}: ${resp.status} ${txt.slice(0,200)}`);
        const data = JSON.parse(txt);
        const opps = data.opportunities || [];
        if (opps.length === 0) break;
        for (const o of opps) {
          all.push({
            id: o.id,
            pipelineId: o.pipelineId,
            status: o.status,
            monetaryValue: o.monetaryValue ?? 0,
            contactId: o.contact?.id || o.contactId || null,
            updatedAt: o.updatedAt,
            name: o.name,
          });
        }
        if (opps.length < 100) break;
        page++;
        await sleep(100);
      }
      return new Response(JSON.stringify({ total: all.length, lastPage: page, opps: all }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "delete-relation") {
      // body: { relationIds: [...] }
      const body = await req.json() as { relationIds?: string[] };
      const ids = body.relationIds || [];
      let ok = 0, errors = 0;
      const errorSamples: string[] = [];
      for (const id of ids) {
        const resp = await fetch(`${GHL_BASE}/associations/relations/${id}?locationId=${LOCATION_ID}`, {
          method: "DELETE",
          headers: ghlHeaders(token),
        });
        if (resp.ok) ok++;
        else {
          errors++;
          if (errorSamples.length < 10) {
            const t = await resp.text();
            errorSamples.push(`${id}: ${resp.status} ${t.slice(0,120)}`);
          }
        }
        await sleep(RATE_LIMIT_MS);
      }
      return new Response(JSON.stringify({ step, total: ids.length, ok, errors, errorSamples }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "get-opp") {
      const body = await req.json() as { oppIds?: string[] };
      const results: Array<Record<string, unknown>> = [];
      for (const id of body.oppIds || []) {
        const resp = await fetch(`${GHL_BASE}/opportunities/${id}`, {
          method: "GET",
          headers: ghlHeaders(token),
        });
        const txt = await resp.text();
        if (resp.ok) {
          const d = JSON.parse(txt);
          const o = d.opportunity || d;
          results.push({
            id,
            pipelineId: o.pipelineId,
            pipelineStageId: o.pipelineStageId,
            status: o.status,
            name: o.name,
            monetaryValue: o.monetaryValue,
            contactId: o.contact?.id || o.contactId,
          });
        } else {
          results.push({ id, error: `${resp.status}: ${txt.slice(0,200)}` });
        }
      }
      return new Response(JSON.stringify({ results }, null, 2), { status: 200, headers: cors({ "Content-Type": "application/json" }) });
    }

    if (step === "get-relations") {
      // body: { recordIds: [...], associationId? }  retorna relations do record
      const body = await req.json() as { recordIds?: string[]; companyIds?: string[]; associationId?: string };
      const ids = body.recordIds || body.companyIds || [];
      const aId = body.associationId || ASSOC_SELLER;
      const results: Array<Record<string, unknown>> = [];
      for (const id of ids) {
        const resp = await fetch(`${GHL_BASE}/associations/relations/${id}?locationId=${LOCATION_ID}&associationIds=${aId}`, {
          method: "GET",
          headers: ghlHeaders(token),
        });
        const txt = await resp.text();
        if (resp.ok) {
          const d = JSON.parse(txt);
          results.push({ recordId: id, relations: d.relations || d.data || d });
        } else {
          results.push({ recordId: id, error: `${resp.status}: ${txt.slice(0,200)}` });
        }
      }
      return new Response(JSON.stringify({ results }, null, 2), { status: 200, headers: cors({ "Content-Type": "application/json" }) });
    }

    if (step === "get-status") {
      const body = await req.json() as { companyIds?: string[] };
      const ids = body.companyIds || [];
      const results: Array<Record<string, unknown>> = [];
      for (const id of ids) {
        const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records/${id}?locationId=${LOCATION_ID}`, {
          method: "GET",
          headers: ghlHeaders(token),
        });
        const txt = await resp.text();
        if (resp.ok) {
          const d = JSON.parse(txt);
          results.push({ id, status: d.record?.properties?.company_status ?? null, company: d.record?.properties?.company });
        } else {
          results.push({ id, error: `${resp.status}: ${txt.slice(0,100)}` });
        }
      }
      return new Response(JSON.stringify({ results }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "bulk-set-status") {
      // body: { pairs: [{ companyId, status }] }  status: "ativo"|"inativo"|...
      const body = await req.json() as { pairs?: Array<{ companyId: string; status: string }> };
      const pairs = (body.pairs || []).filter((p) => p.companyId && p.status);
      if (pairs.length === 0) {
        return new Response(JSON.stringify({ error: "pairs[] required" }), {
          status: 400, headers: cors({ "Content-Type": "application/json" }),
        });
      }
      let ok = 0, errors = 0;
      const errorSamples: string[] = [];
      for (const p of pairs) {
        const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records/${p.companyId}?locationId=${LOCATION_ID}`, {
          method: "PUT",
          headers: ghlHeaders(token),
          body: JSON.stringify({ properties: { company_status: p.status } }),
        });
        if (resp.ok) {
          ok++;
        } else {
          errors++;
          if (errorSamples.length < 10) {
            const t = await resp.text();
            errorSamples.push(`${p.companyId}: ${resp.status} ${t.slice(0,150)}`);
          }
        }
        await sleep(RATE_LIMIT_MS);
      }
      return new Response(JSON.stringify({ step, total: pairs.length, ok, errors, errorSamples }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "create-with-contact") {
      // body: { items: [{ name, email }] }
      // Para cada item: upsert company, busca contact por email, cria relation main.
      const body = await req.json() as { items?: Array<{ name: string; email: string }> };
      const items = (body.items || []).filter((i) => i.name && i.email);
      if (items.length === 0) {
        return new Response(JSON.stringify({ error: "items[] with {name,email} required" }), {
          status: 400, headers: cors({ "Content-Type": "application/json" }),
        });
      }
      const results: Array<Record<string, unknown>> = [];
      for (const item of items) {
        const entry: Record<string, unknown> = { name: item.name, email: item.email };
        try {
          let companyId = await searchCompanyByName(token, item.name);
          if (!companyId) {
            companyId = await createCompany(token, item.name);
            entry.companyCreated = true;
          } else {
            entry.companyCreated = false;
          }
          entry.companyId = companyId;

          const searchResp = await fetch(`${GHL_BASE}/contacts/search`, {
            method: "POST",
            headers: ghlHeaders(token),
            body: JSON.stringify({
              locationId: LOCATION_ID,
              pageLimit: 5,
              filters: [{ field: "email", operator: "eq", value: item.email }],
            }),
          });
          const searchTxt = await searchResp.text();
          if (!searchResp.ok) {
            entry.error = `contacts/search ${searchResp.status}: ${searchTxt.slice(0, 200)}`;
            results.push(entry);
            await sleep(RATE_LIMIT_MS);
            continue;
          }
          const searchData = JSON.parse(searchTxt) as { contacts?: Array<{ id: string }> };
          const contactId = searchData.contacts?.[0]?.id;
          if (!contactId) {
            entry.error = "contact not found by email";
            results.push(entry);
            await sleep(RATE_LIMIT_MS);
            continue;
          }
          entry.contactId = contactId;

          const rel = await createRelation(token, ASSOC_MAIN, contactId, companyId);
          entry.relation = rel;
        } catch (e) {
          entry.error = (e as Error).message;
        }
        results.push(entry);
        await sleep(RATE_LIMIT_MS);
      }
      return new Response(JSON.stringify({ step, total: items.length, results }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "list-companies") {
      const all: Array<{ id: string; name: string; company_status: string | null }> = [];
      let page = 1;
      const PAGE_LIMIT = 100;
      while (true) {
        const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records/search`, {
          method: "POST",
          headers: ghlHeaders(token),
          body: JSON.stringify({ locationId: LOCATION_ID, page, pageLimit: PAGE_LIMIT, query: "" }),
        });
        if (!resp.ok) {
          const txt = await resp.text();
          throw new Error(`list-companies page=${page}: ${resp.status} ${txt.slice(0, 200)}`);
        }
        const data = await resp.json() as { records?: Array<{ id: string; properties?: Record<string, unknown> }> };
        const recs = data.records || [];
        if (recs.length === 0) break;
        for (const r of recs) {
          all.push({
            id: r.id,
            name: normalizeName(r.properties?.["company"]),
            company_status: (r.properties?.["company_status"] as string) ?? null,
          });
        }
        if (recs.length < PAGE_LIMIT) break;
        page++;
        await sleep(100);
      }
      return new Response(JSON.stringify({ step, total: all.length, companies: all }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    if (step === "list-contacts-bulk") {
      // Pagina /contacts/search ate o fim, retorna campos uteis pra matching.
      const all: Array<{
        id: string;
        firstName: string | null;
        lastName: string | null;
        contactName: string | null;
        companyName: string | null;
      }> = [];
      let after: unknown[] | undefined = undefined;
      let pages = 0;
      const MAX_PAGES = 200;
      while (pages < MAX_PAGES) {
        const body: Record<string, unknown> = { locationId: LOCATION_ID, pageLimit: 100 };
        if (after) body.searchAfter = after;
        const resp = await fetch(`${GHL_BASE}/contacts/search`, {
          method: "POST",
          headers: ghlHeaders(token),
          body: JSON.stringify(body),
        });
        const txt = await resp.text();
        if (!resp.ok) {
          throw new Error(`list-contacts-bulk page=${pages}: ${resp.status} ${txt.slice(0, 300)}`);
        }
        const data = JSON.parse(txt) as { contacts?: Array<Record<string, unknown>> };
        const contacts = data.contacts || [];
        if (contacts.length === 0) break;
        for (const c of contacts) {
          all.push({
            id: String(c.id),
            firstName: (c.firstName as string) ?? null,
            lastName: (c.lastName as string) ?? null,
            contactName: (c.contactName as string) ?? null,
            companyName: (c.companyName as string) ?? null,
          });
        }
        const last = contacts.slice(-1)[0] as Record<string, unknown> | undefined;
        after = last?.searchAfter as unknown[] | undefined;
        if (!after || contacts.length < 100) break;
        pages++;
        await sleep(50);
      }
      return new Response(JSON.stringify({ step, total: all.length, pages: pages + 1, contacts: all }, null, 2), {
        status: 200, headers: cors({ "Content-Type": "application/json" }),
      });
    }

    return new Response(JSON.stringify({ error: `Unknown step: ${step}` }), {
      status: 400,
      headers: cors({ "Content-Type": "application/json" }),
    });
  } catch (err) {
    console.error("Edge Function Error:", err);
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: cors({ "Content-Type": "application/json" }),
    });
  }
});
