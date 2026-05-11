const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const LOCATION_TOKEN_FUNCTION = Deno.env.get("LOCATION_TOKEN_FUNCTION") || "ghl-location-auth";

function stripBearer(s: string) {
  return String(s || "").replace(/^Bearer\s+/i, "");
}

export async function getLocationAccessToken(locationId: string): Promise<string> {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not configured");
  }
  const fnUrl = `${SUPABASE_URL.replace(/\/+$/, "")}/functions/v1/${LOCATION_TOKEN_FUNCTION}`;
  const resp = await fetch(fnUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      apikey: SUPABASE_SERVICE_ROLE_KEY,
    },
    body: JSON.stringify({ locationId }),
  });

  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`Failed to get location token: ${resp.status} ${resp.statusText} - ${text}`);
  }

  let data: Record<string, unknown> = {};
  try {
    data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  } catch {
  }

  const token =
    (data as any)?.access_token ??
    (data as any)?.accessToken ??
    (data as any)?.token ??
    (data as any)?.data?.access_token ??
    (data as any)?.data?.accessToken;

  if (!token) {
    throw new Error(`${LOCATION_TOKEN_FUNCTION} did not return access_token. Payload: ${text}`);
  }
  return stripBearer(String(token));
}
