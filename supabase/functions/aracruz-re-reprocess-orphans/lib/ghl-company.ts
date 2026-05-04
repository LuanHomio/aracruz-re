// Helpers compartilhados pra Custom Object Companies + Associations.
// Copiado em cada EF (mesmo padrao de ghl-auth.ts).
const GHL_BASE = "https://services.leadconnectorhq.com";
const GHL_VERSION = Deno.env.get("GHL_VERSION") || "2021-07-28";

export const OBJECT_KEY = "custom_objects.companies";
export const ASSOC_MAIN = "69e6418be7979a3c6d1b6c19";       // contact (Main) <-> companies (Main)
export const ASSOC_EMPLOYEE = "69e63faf9c60d697228e2b29";   // contact (Employee) <-> companies (Employer)
export const ASSOC_SELLER = "69e640a54b8e890cd8e88fa2";     // companies (Seller) <-> opportunity (Sale)
export const INHOUSE_COMPANY_ID = "69e9039f9fcc6d4be5a1645a";
export const INHOUSE_CONTACT_ID = "cDwSiMcmUU9LVjmEDgQR";

export function nameKey(s: unknown): string {
  return String(s ?? "").toLowerCase().replace(/\s+/g, " ").trim();
}

function ghlHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    Version: GHL_VERSION,
    "Content-Type": "application/json",
    Accept: "application/json",
  };
}

export async function searchCompanyByName(token: string, locationId: string, name: string): Promise<string | null> {
  const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records/search`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify({ locationId, page: 1, pageLimit: 20, query: name }),
  });
  if (!resp.ok) return null;
  const data = await resp.json() as { records?: Array<{ id: string; properties?: Record<string, unknown> }> };
  const target = nameKey(name);
  for (const rec of data.records || []) {
    if (nameKey(rec.properties?.["company"]) === target) return rec.id;
  }
  return null;
}

export async function createCompany(token: string, locationId: string, name: string, extraProps: Record<string, unknown> = {}): Promise<string> {
  const resp = await fetch(`${GHL_BASE}/objects/${OBJECT_KEY}/records`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify({ locationId, properties: { company: name, ...extraProps } }),
  });
  const txt = await resp.text();
  if (!resp.ok) throw new Error(`createCompany "${name}" ${resp.status}: ${txt.slice(0, 300)}`);
  const data = JSON.parse(txt);
  return data.record?.id ?? data.id;
}

// Dropdown "Company Status" (key custom_objects.companies.company_status)
// Values aceitos pela API em lowercase: "ativo" | "inativo" | "potencial" | "vip" | "bloqueado".
export type CompanyStatusValue = "ativo" | "inativo" | "potencial" | "vip" | "bloqueado";

// Converte o campo "Status" vindo da planilha Stone Profits (Active/Inactive/Inativo) pro value do GHL.
// Default: "ativo". So vira "inativo" quando o valor eh Inactive/Inativo.
export function mapCustomerStatusToCompanyStatus(raw: unknown): CompanyStatusValue {
  const s = String(raw ?? "").trim().toLowerCase();
  if (s === "inactive" || s === "inativo") return "inativo";
  return "ativo";
}

// PUT /objects/{key}/records/{id}?locationId=... body {properties:{company_status:value}}
export async function updateCompanyStatus(
  token: string,
  locationId: string,
  companyId: string,
  status: CompanyStatusValue,
): Promise<boolean> {
  const url = `${GHL_BASE}/objects/${OBJECT_KEY}/records/${companyId}?locationId=${locationId}`;
  const resp = await fetch(url, {
    method: "PUT",
    headers: ghlHeaders(token),
    body: JSON.stringify({ properties: { company_status: status } }),
  });
  if (resp.ok) return true;
  const txt = await resp.text();
  console.error(`updateCompanyStatus ${companyId} -> ${status} ${resp.status}: ${txt.slice(0, 300)}`);
  return false;
}

// upsertCompany com cache local (Map). Retorna companyId (ou null se nome vazio).
export async function upsertCompany(
  token: string,
  locationId: string,
  name: string,
  cache: Map<string, string>,
): Promise<string | null> {
  const clean = String(name ?? "").trim();
  if (!clean) return null;
  const key = nameKey(clean);
  if (cache.has(key)) return cache.get(key)!;
  let id = await searchCompanyByName(token, locationId, clean);
  if (!id) id = await createCompany(token, locationId, clean);
  cache.set(key, id);
  return id;
}

// Sufixos vistos na planilha de Holds/Sales que NAO existem no nome da Company:
//   "Empresa - (ROC 350844)", "Empresa (ROC 12345)", "Empresa - (LIC 999)".
// NAO strip cegamente todo "(...)" no fim porque ~24 companies legitimas terminam em
// parenteses (DBA, codigos internos). So strip o padrao ROC|LIC (especifico do Stone Profits).
const CUSTOMER_SUFFIX_RE = /\s*-?\s*\((?:ROC|LIC)\b[^)]*\)\s*$/i;
// Sales tem sufixo extra "\xa0(SHERMAN)" / "(CHAMBERS)" no campo "Bill To Customer /Code"
// — codigo da location do escritorio Stone Profits. Restringe ao NBSP ( ) precedente:
// companies legitimas com siglas no fim ("(TBRS)", "(VEN)", "(BAC)") usam espaco regular.
const SALES_LOCATION_SUFFIX_RE = /\u00a0\([A-Z]+\)\s*$/;
export function stripCustomerSuffix(name: string): string {
  let s = String(name ?? "").replace(SALES_LOCATION_SUFFIX_RE, "").trim();
  s = s.replace(CUSTOMER_SUFFIX_RE, "").trim();
  return s;
}

// Mesma assinatura, mas NAO cria se nao existe (usado em holds/sales).
// Fallback: se match exato falhar, tenta com sufixo "(ROC ...)" removido.
export async function resolveCompanyId(
  token: string,
  locationId: string,
  name: string,
  cache: Map<string, string | null>,
): Promise<string | null> {
  const clean = String(name ?? "").trim();
  if (!clean) return null;
  const key = nameKey(clean);
  if (cache.has(key)) return cache.get(key) ?? null;
  let id = await searchCompanyByName(token, locationId, clean);
  if (!id) {
    const stripped = stripCustomerSuffix(clean);
    if (stripped && stripped !== clean) {
      id = await searchCompanyByName(token, locationId, stripped);
    }
  }
  cache.set(key, id);
  return id;
}

export type RelationResult = "created" | "duplicate" | "error";

export async function createRelation(
  token: string,
  locationId: string,
  associationId: string,
  firstRecordId: string,
  secondRecordId: string,
): Promise<RelationResult> {
  const resp = await fetch(`${GHL_BASE}/associations/relations`, {
    method: "POST",
    headers: ghlHeaders(token),
    body: JSON.stringify({ locationId, associationId, firstRecordId, secondRecordId }),
  });
  if (resp.ok) return "created";
  const txt = await resp.text();
  if (/duplicate relation/i.test(txt)) return "duplicate";
  console.error(`relation error ${resp.status}: ${txt.slice(0, 300)}`);
  return "error";
}

// Detecta se a linha deve ser tratada como "In-House" (company + contato In-House).
// Regra (acordada com Luan 2026-04-22): TRUE somente quando o Customer indica venda
// balcão/sem fabricator — "Sales Person = In-House" por si so NAO conta, pq pode ter
// vendas in-house pra customers reais.
export function isInHouse(item: Record<string, unknown>): boolean {
  const customer = String(item["Customer"] ?? item["Bill To Customer /Code"] ?? "").trim().toLowerCase();
  if (!customer) return false;
  if (customer.startsWith("no fabricator")) return true;
  if (customer.startsWith("counter sale")) return true;
  return false;
}
