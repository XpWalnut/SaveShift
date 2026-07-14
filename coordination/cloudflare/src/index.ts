import { DurableObject } from "cloudflare:workers";

export interface Env {
  COORDINATION: DurableObjectNamespace<CoordinationGroup>;
  PAIRING_CODE: string;
  LEASE_SECONDS?: string;
}

interface DeviceRecord {
  device_id: string;
  device_name: string;
  token_hash: string;
  created_at_utc: string;
  revoked: boolean;
}

interface LockRecord {
  project_uuid: string;
  lease_id: string;
  fencing_token: number;
  owner_device_id: string;
  owner_display_name: string;
  acquired_at_utc: string;
  expires_at_utc: string;
}

interface ErrorBody {
  error: {
    code: string;
    message: string;
    lock?: LockRecord;
  };
}

const API_PREFIX = "/api/v1";
const DEFAULT_LEASE_SECONDS = 900;
const MAX_DEVICE_NAME_LENGTH = 100;
const MAX_OWNER_NAME_LENGTH = 100;
const PROJECT_UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({ status: "ok", api_version: "v1" });
    }

    if (!url.pathname.startsWith(API_PREFIX)) {
      return errorResponse(404, "not_found", "Endpoint not found.");
    }

    const group = env.COORDINATION.getByName("default");
    return group.fetch(request);
  }
} satisfies ExportedHandler<Env>;

export class CoordinationGroup extends DurableObject<Env> {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/devices/pair`
    ) {
      return this.pairDevice(request);
    }

    const match = url.pathname.match(
      /^\/api\/v1\/locks\/([^/]+)(?:\/(acquire|renew|release))?$/
    );

    if (!match) {
      return errorResponse(404, "not_found", "Endpoint not found.");
    }

    let projectUuid: string;

    try {
      projectUuid = decodeURIComponent(match[1]);
    } catch {
      return errorResponse(400, "invalid_project", "Project UUID is invalid.");
    }

    if (!PROJECT_UUID_PATTERN.test(projectUuid)) {
      return errorResponse(400, "invalid_project", "Project UUID is invalid.");
    }

    const device = await this.authenticate(request);

    if (device instanceof Response) {
      return device;
    }

    const action = match[2];

    if (request.method === "GET" && action === undefined) {
      return this.getLock(projectUuid);
    }

    if (request.method !== "POST") {
      return errorResponse(405, "method_not_allowed", "Method not allowed.");
    }

    if (action === "acquire") {
      return this.acquireLock(request, projectUuid, device);
    }

    if (action === "renew") {
      return this.renewLock(request, projectUuid, device);
    }

    if (action === "release") {
      return this.releaseLock(request, projectUuid, device);
    }

    return errorResponse(404, "not_found", "Endpoint not found.");
  }

  private async pairDevice(request: Request): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const pairingCode = body.pairing_code;
    const deviceName = normalizeName(body.device_name, MAX_DEVICE_NAME_LENGTH);

    if (typeof pairingCode !== "string" || pairingCode.length === 0) {
      return errorResponse(400, "invalid_pairing_code", "Pairing code is required.");
    }

    if (!deviceName) {
      return errorResponse(400, "invalid_device_name", "Device name is required.");
    }

    if (!this.env.PAIRING_CODE) {
      return errorResponse(
        503,
        "pairing_unavailable",
        "The coordinator has not been configured for pairing."
      );
    }

    const suppliedHash = await sha256(pairingCode);
    const configuredHash = await sha256(this.env.PAIRING_CODE);

    if (!constantTimeEqual(suppliedHash, configuredHash)) {
      return errorResponse(403, "invalid_pairing_code", "Pairing code is invalid.");
    }

    const deviceId = crypto.randomUUID();
    const deviceToken = randomToken();
    const device: DeviceRecord = {
      device_id: deviceId,
      device_name: deviceName,
      token_hash: await sha256(deviceToken),
      created_at_utc: new Date().toISOString(),
      revoked: false
    };

    await this.ctx.storage.put(`device:${device.token_hash}`, device);

    return jsonResponse(
      {
        device: {
          device_id: device.device_id,
          device_token: deviceToken
        }
      },
      201
    );
  }

  private async authenticate(request: Request): Promise<DeviceRecord | Response> {
    const authorization = request.headers.get("Authorization");

    if (!authorization?.startsWith("Bearer ")) {
      return errorResponse(401, "authentication_required", "Pair this device first.");
    }

    const token = authorization.slice("Bearer ".length).trim();

    if (!token) {
      return errorResponse(401, "authentication_required", "Pair this device first.");
    }

    const tokenHash = await sha256(token);
    const device = await this.ctx.storage.get<DeviceRecord>(`device:${tokenHash}`);

    if (!device || device.revoked) {
      return errorResponse(401, "invalid_device", "Pair this device again.");
    }

    return device;
  }

  private async acquireLock(
    request: Request,
    projectUuid: string,
    device: DeviceRecord
  ): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const ownerDisplayName = normalizeName(
      body.owner_display_name,
      MAX_OWNER_NAME_LENGTH
    );

    if (!ownerDisplayName) {
      return errorResponse(400, "invalid_owner", "Host name is required.");
    }

    const result = await this.ctx.storage.transaction(async (transaction) => {
      const key = lockKey(projectUuid);
      const existing = await transaction.get<LockRecord>(key);
      const now = new Date();

      if (existing && !isExpired(existing, now)) {
        return { conflict: existing };
      }

      const counterKey = fencingKey(projectUuid);
      const previousCounter = (await transaction.get<number>(counterKey)) ?? 0;
      const fencingToken = previousCounter + 1;
      const lock: LockRecord = {
        project_uuid: projectUuid,
        lease_id: crypto.randomUUID(),
        fencing_token: fencingToken,
        owner_device_id: device.device_id,
        owner_display_name: ownerDisplayName,
        acquired_at_utc: now.toISOString(),
        expires_at_utc: expiresAt(now, this.leaseSeconds()).toISOString()
      };

      await transaction.put(counterKey, fencingToken);
      await transaction.put(key, lock);
      return { lock };
    });

    if ("conflict" in result && result.conflict) {
      const conflict = result.conflict;
      return errorResponse(
        409,
        "lock_conflict",
        `Project is currently hosted by ${conflict.owner_display_name}.`,
        conflict
      );
    }

    return jsonResponse({ lock: result.lock });
  }

  private async renewLock(
    request: Request,
    projectUuid: string,
    device: DeviceRecord
  ): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const leaseId = body.lease_id;

    if (typeof leaseId !== "string" || !leaseId) {
      return errorResponse(400, "invalid_lease", "Lease ID is required.");
    }

    const result = await this.ctx.storage.transaction(async (transaction) => {
      const key = lockKey(projectUuid);
      const existing = await transaction.get<LockRecord>(key);
      const now = new Date();

      if (!existing || isExpired(existing, now)) {
        if (existing) {
          await transaction.delete(key);
        }
        return { error: "expired" as const };
      }

      if (
        existing.owner_device_id !== device.device_id ||
        existing.lease_id !== leaseId
      ) {
        return { error: "ownership" as const, lock: existing };
      }

      const renewed = {
        ...existing,
        expires_at_utc: expiresAt(now, this.leaseSeconds()).toISOString()
      };
      await transaction.put(key, renewed);
      return { lock: renewed };
    });

    if ("error" in result && result.error === "expired") {
      return errorResponse(409, "lease_expired", "The project lease has expired.");
    }

    if ("error" in result) {
      return errorResponse(
        403,
        "lock_not_owned",
        "This device does not own the project lease.",
        result.lock
      );
    }

    return jsonResponse({ lock: result.lock });
  }

  private async releaseLock(
    request: Request,
    projectUuid: string,
    device: DeviceRecord
  ): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const leaseId = body.lease_id;

    if (typeof leaseId !== "string" || !leaseId) {
      return errorResponse(400, "invalid_lease", "Lease ID is required.");
    }

    const result = await this.ctx.storage.transaction(async (transaction) => {
      const key = lockKey(projectUuid);
      const existing = await transaction.get<LockRecord>(key);

      if (!existing || isExpired(existing, new Date())) {
        if (existing) {
          await transaction.delete(key);
        }
        return { released: true };
      }

      if (
        existing.owner_device_id !== device.device_id ||
        existing.lease_id !== leaseId
      ) {
        return { released: false, lock: existing };
      }

      await transaction.delete(key);
      return { released: true };
    });

    if (!result.released) {
      return errorResponse(
        403,
        "lock_not_owned",
        "This device does not own the project lease.",
        result.lock
      );
    }

    return jsonResponse({ released: true });
  }

  private async getLock(projectUuid: string): Promise<Response> {
    const lock = await this.ctx.storage.transaction(async (transaction) => {
      const key = lockKey(projectUuid);
      const existing = await transaction.get<LockRecord>(key);

      if (existing && isExpired(existing, new Date())) {
        await transaction.delete(key);
        return null;
      }

      return existing ?? null;
    });

    return jsonResponse({ lock });
  }

  private leaseSeconds(): number {
    const configured = Number.parseInt(
      this.env.LEASE_SECONDS ?? String(DEFAULT_LEASE_SECONDS),
      10
    );
    return Number.isFinite(configured) && configured >= 60
      ? configured
      : DEFAULT_LEASE_SECONDS;
  }
}

function lockKey(projectUuid: string): string {
  return `lock:${projectUuid}`;
}

function fencingKey(projectUuid: string): string {
  return `fencing:${projectUuid}`;
}

function isExpired(lock: LockRecord, now: Date): boolean {
  return Date.parse(lock.expires_at_utc) <= now.getTime();
}

function expiresAt(now: Date, leaseSeconds: number): Date {
  return new Date(now.getTime() + leaseSeconds * 1000);
}

function normalizeName(value: unknown, maximumLength: number): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const normalized = value.trim();
  return normalized && normalized.length <= maximumLength ? normalized : null;
}

async function readJsonBody(
  request: Request
): Promise<Record<string, unknown> | Response> {
  try {
    const data: unknown = await request.json();

    if (!data || typeof data !== "object" || Array.isArray(data)) {
      return errorResponse(400, "invalid_json", "A JSON object is required.");
    }

    return data as Record<string, unknown>;
  } catch {
    return errorResponse(400, "invalid_json", "A valid JSON body is required.");
  }
}

async function sha256(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function constantTimeEqual(left: string, right: string): boolean {
  if (left.length !== right.length) {
    return false;
  }

  let difference = 0;

  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }

  return difference === 0;
}

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    }
  });
}

function errorResponse(
  status: number,
  code: string,
  message: string,
  lock?: LockRecord
): Response {
  const body: ErrorBody = { error: { code, message } };

  if (lock) {
    body.error.lock = lock;
  }

  return jsonResponse(body, status);
}
