import { DurableObject } from "cloudflare:workers";

export interface Env {
  COORDINATION: DurableObjectNamespace<CoordinationGroup>;
  GROUP_ID?: string;
  PAIRING_CODE?: string;
  ADMIN_BOOTSTRAP_TOKEN?: string;
  LEASE_SECONDS?: string;
}

interface DeviceRecord {
  device_id: string;
  device_name: string;
  token_hash: string;
  created_at_utc: string;
  revoked: boolean;
  administrator: boolean;
}

interface InvitationRecord {
  invitation_id: string;
  token_hash: string;
  created_at_utc: string;
  expires_at_utc: string;
  created_by_device_id: string;
  used_at_utc: string | null;
}

interface PublicDevice {
  device_id: string;
  device_name: string;
  created_at_utc: string;
  revoked: boolean;
  administrator: boolean;
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

interface PackageArtifactRecord {
  catalog_id: string;
  transport_name: string;
  remote_id: string;
  project_uuid: string;
  project_version: number;
  package_checksum: string;
  package_size_bytes: number;
  encryption_key_id: string;
  published_by_device_id: string;
  published_at_utc: string;
  project_name?: string;
  game_id?: string;
  created_by?: string;
}

interface PackageEncryptionKeyRecord {
  key_id: string;
  algorithm: "AES-256-GCM";
  key_material: string;
  created_at_utc: string;
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
const MAX_TRANSPORT_NAME_LENGTH = 50;
const MAX_REMOTE_ID_LENGTH = 512;
const MAX_KEY_ID_LENGTH = 100;
const MAX_PROJECT_NAME_LENGTH = 200;
const MAX_GAME_ID_LENGTH = 100;
const DEFAULT_INVITATION_SECONDS = 24 * 60 * 60;
const MIN_INVITATION_SECONDS = 5 * 60;
const MAX_INVITATION_SECONDS = 7 * 24 * 60 * 60;
const CURRENT_PACKAGE_KEY = "package-encryption-key-current:v1";
const PROJECT_UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function groupStub(env: Env): DurableObjectStub<CoordinationGroup> {
  const groupId = env.GROUP_ID?.trim() || "default";
  return env.COORDINATION.getByName(groupId);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      const group = groupStub(env);
      return group.fetch(request);
    }

    if (!url.pathname.startsWith(API_PREFIX)) {
      return errorResponse(404, "not_found", "Endpoint not found.");
    }

    const group = groupStub(env);
    return group.fetch(request);
  }
} satisfies ExportedHandler<Env>;

export class CoordinationGroup extends DurableObject<Env> {
  private readonly groupId: string;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.groupId = ctx.id.name ?? "legacy";
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({
        status: "ok",
        api_version: "v1",
        provider_version: "1.6.0"
      });
    }

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/devices/pair`
    ) {
      return this.pairDevice(request);
    }

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/devices/bootstrap`
    ) {
      return this.bootstrapAdministrator(request);
    }

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/devices/join`
    ) {
      return this.joinWithInvitation(request);
    }

    const device = await this.authenticate(request);

    if (device instanceof Response) {
      return device;
    }

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/devices/claim-administrator`
    ) {
      return this.claimAdministrator(request, device);
    }

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/devices/leave`
    ) {
      return this.leaveGroup(device);
    }

    if (request.method === "GET" && url.pathname === `${API_PREFIX}/devices`) {
      return this.listDevices(device);
    }

    const revokeMatch = url.pathname.match(/^\/api\/v1\/devices\/([^/]+)\/revoke$/);

    if (request.method === "POST" && revokeMatch) {
      return this.revokeDevice(revokeMatch[1], device);
    }

    if (
      request.method === "POST" &&
      url.pathname === `${API_PREFIX}/invitations`
    ) {
      return this.createInvitation(request, device);
    }

    if (
      request.method === "GET" &&
      url.pathname === `${API_PREFIX}/package-encryption-key`
    ) {
      return this.getCurrentPackageEncryptionKey();
    }

    const packageKeyMatch = url.pathname.match(
      /^\/api\/v1\/package-encryption-keys\/([^/]+)$/
    );

    if (request.method === "GET" && packageKeyMatch) {
      return this.getPackageEncryptionKey(packageKeyMatch[1]);
    }

    if (
      request.method === "GET" &&
      url.pathname === `${API_PREFIX}/packages/latest`
    ) {
      return this.listLatestPackages();
    }

    const packageMatch = url.pathname.match(
      /^\/api\/v1\/projects\/([^/]+)\/packages$/
    );

    if (packageMatch) {
      const projectUuid = parseProjectUuid(packageMatch[1]);

      if (!projectUuid) {
        return errorResponse(400, "invalid_project", "Project UUID is invalid.");
      }

      if (request.method === "GET") {
        return this.listPackages(projectUuid);
      }

      if (request.method === "POST") {
        return this.registerPackage(request, projectUuid, device);
      }

      if (request.method === "DELETE") {
        return this.removeProject(projectUuid, device);
      }

      return errorResponse(405, "method_not_allowed", "Method not allowed.");
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
      revoked: false,
      administrator: false
    };

    await this.storeDevice(device);

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

  private async bootstrapAdministrator(request: Request): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const bootstrapToken = body.bootstrap_token;
    const deviceName = normalizeName(body.device_name, MAX_DEVICE_NAME_LENGTH);

    if (typeof bootstrapToken !== "string" || bootstrapToken.length === 0) {
      return errorResponse(400, "invalid_bootstrap_token", "Bootstrap token is required.");
    }

    if (!deviceName) {
      return errorResponse(400, "invalid_device_name", "Device name is required.");
    }

    if (!this.env.ADMIN_BOOTSTRAP_TOKEN) {
      return errorResponse(503, "bootstrap_unavailable", "Administrator setup is unavailable.");
    }

    const suppliedHash = await sha256(bootstrapToken);
    const configuredHash = await sha256(this.env.ADMIN_BOOTSTRAP_TOKEN);

    if (!constantTimeEqual(suppliedHash, configuredHash)) {
      return errorResponse(403, "invalid_bootstrap_token", "Bootstrap token is invalid.");
    }

    // Derive the first device credential from the high-entropy, one-time
    // bootstrap secret. This makes a repeated bootstrap request return the
    // same credential if a deployment edge drops the original response.
    const deviceToken = await sha256(
      `saveshift-bootstrap-device-v2:${this.groupId}:${bootstrapToken}`
    );
    const deviceTokenHash = await sha256(deviceToken);

    const result = await this.ctx.storage.transaction(async (transaction) => {
      const existing = await transaction.get<DeviceRecord>(
        `device:${deviceTokenHash}`
      );

      if (existing?.administrator) {
        return { device: existing, created: false };
      }

      const complete = await transaction.get<boolean>("bootstrap:completed");

      if (complete) {
        return null;
      }

      const device: DeviceRecord = {
        device_id: crypto.randomUUID(),
        device_name: deviceName,
        token_hash: deviceTokenHash,
        created_at_utc: new Date().toISOString(),
        revoked: false,
        administrator: true
      };

      await transaction.put("bootstrap:completed", true);
      await transaction.put(`device:${device.token_hash}`, device);
      await transaction.put(`device-id:${device.device_id}`, device.token_hash);
      return { device, created: true };
    });

    if (!result) {
      return errorResponse(409, "bootstrap_complete", "An administrator already exists.");
    }

    return jsonResponse(
      { device: publicPairedDevice(result.device, deviceToken) },
      result.created ? 201 : 200
    );
  }

  private async joinWithInvitation(request: Request): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const invitationToken = body.invitation_token;
    const deviceName = normalizeName(body.device_name, MAX_DEVICE_NAME_LENGTH);

    if (typeof invitationToken !== "string" || invitationToken.length === 0) {
      return errorResponse(400, "invalid_invitation", "Invitation token is required.");
    }

    if (!deviceName) {
      return errorResponse(400, "invalid_device_name", "Device name is required.");
    }

    const invitationHash = await sha256(invitationToken);
    const deviceToken = randomToken();
    const device: DeviceRecord = {
      device_id: crypto.randomUUID(),
      device_name: deviceName,
      token_hash: await sha256(deviceToken),
      created_at_utc: new Date().toISOString(),
      revoked: false,
      administrator: false
    };

    const result = await this.ctx.storage.transaction(async (transaction) => {
      const key = `invitation:${invitationHash}`;
      const invitation = await transaction.get<InvitationRecord>(key);
      const now = new Date();

      if (!invitation) {
        return "invalid" as const;
      }

      if (invitation.used_at_utc !== null) {
        return "used" as const;
      }

      if (Date.parse(invitation.expires_at_utc) <= now.getTime()) {
        return "expired" as const;
      }

      await transaction.put(key, {
        ...invitation,
        used_at_utc: now.toISOString()
      });
      await transaction.put(`device:${device.token_hash}`, device);
      await transaction.put(`device-id:${device.device_id}`, device.token_hash);
      return "created" as const;
    });

    if (result !== "created") {
      const messages = {
        invalid: "Invitation is invalid.",
        used: "Invitation has already been used.",
        expired: "Invitation has expired."
      };
      return errorResponse(403, `invitation_${result}`, messages[result]);
    }

    return jsonResponse({ device: publicPairedDevice(device, deviceToken) }, 201);
  }

  private async claimAdministrator(
    request: Request,
    device: DeviceRecord
  ): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const pairingCode = body.pairing_code;

    if (typeof pairingCode !== "string" || pairingCode.length === 0) {
      return errorResponse(400, "invalid_pairing_code", "Pairing code is required.");
    }

    if (!this.env.PAIRING_CODE) {
      return errorResponse(
        503,
        "administrator_claim_unavailable",
        "Administrator migration is unavailable for this provider."
      );
    }

    const suppliedHash = await sha256(pairingCode);
    const configuredHash = await sha256(this.env.PAIRING_CODE);

    if (!constantTimeEqual(suppliedHash, configuredHash)) {
      return errorResponse(403, "invalid_pairing_code", "Pairing code is invalid.");
    }

    const claimed = await this.ctx.storage.transaction(async (transaction) => {
      const complete = await transaction.get<boolean>("bootstrap:completed");

      if (complete) {
        return false;
      }

      await transaction.put("bootstrap:completed", true);
      await transaction.put(`device:${device.token_hash}`, {
        ...device,
        administrator: true
      });
      await transaction.put(`device-id:${device.device_id}`, device.token_hash);
      return true;
    });

    if (!claimed) {
      return errorResponse(
        409,
        "administrator_exists",
        "This group already has an administrator."
      );
    }

    return jsonResponse({ administrator: true });
  }

  private async createInvitation(
    request: Request,
    device: DeviceRecord
  ): Promise<Response> {
    const denied = requireAdministrator(device);

    if (denied) {
      return denied;
    }

    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const requestedSeconds = body.expires_in_seconds;
    const expiresInSeconds = requestedSeconds === undefined
      ? DEFAULT_INVITATION_SECONDS
      : requestedSeconds;

    if (
      typeof expiresInSeconds !== "number" ||
      !Number.isInteger(expiresInSeconds) ||
      expiresInSeconds < MIN_INVITATION_SECONDS ||
      expiresInSeconds > MAX_INVITATION_SECONDS
    ) {
      return errorResponse(
        400,
        "invalid_expiration",
        "Invitation expiration must be between 5 minutes and 7 days."
      );
    }

    const now = new Date();
    const invitationToken = randomToken();
    const invitation: InvitationRecord = {
      invitation_id: crypto.randomUUID(),
      token_hash: await sha256(invitationToken),
      created_at_utc: now.toISOString(),
      expires_at_utc: expiresAt(now, expiresInSeconds).toISOString(),
      created_by_device_id: device.device_id,
      used_at_utc: null
    };
    await this.ctx.storage.put(`invitation:${invitation.token_hash}`, invitation);

    return jsonResponse({
      invitation: {
        invitation_id: invitation.invitation_id,
        invitation_token: invitationToken,
        expires_at_utc: invitation.expires_at_utc
      }
    }, 201);
  }

  private async listDevices(device: DeviceRecord): Promise<Response> {
    const denied = requireAdministrator(device);

    if (denied) {
      return denied;
    }

    const records = await this.ctx.storage.list<DeviceRecord>({ prefix: "device:" });
    const devices = Array.from(records.values())
      .map(publicDevice)
      .sort((left, right) => left.created_at_utc.localeCompare(right.created_at_utc));
    return jsonResponse({ devices });
  }

  private async revokeDevice(
    encodedDeviceId: string,
    administrator: DeviceRecord
  ): Promise<Response> {
    const denied = requireAdministrator(administrator);

    if (denied) {
      return denied;
    }

    let deviceId: string;

    try {
      deviceId = decodeURIComponent(encodedDeviceId);
    } catch {
      return errorResponse(400, "invalid_device", "Device ID is invalid.");
    }

    if (deviceId === administrator.device_id) {
      return errorResponse(409, "cannot_revoke_self", "You cannot revoke this computer.");
    }

    let tokenHash = await this.ctx.storage.get<string>(`device-id:${deviceId}`);

    if (!tokenHash) {
      const records = await this.ctx.storage.list<DeviceRecord>({ prefix: "device:" });
      const existing = Array.from(records.values()).find(
        (candidate) => candidate.device_id === deviceId
      );
      tokenHash = existing?.token_hash;
    }

    if (!tokenHash) {
      return errorResponse(404, "device_not_found", "Device was not found.");
    }

    const key = `device:${tokenHash}`;
    const existing = await this.ctx.storage.get<DeviceRecord>(key);

    if (!existing) {
      return errorResponse(404, "device_not_found", "Device was not found.");
    }

    await this.ctx.storage.put(key, { ...existing, revoked: true });
    await this.ctx.storage.delete(CURRENT_PACKAGE_KEY);
    return jsonResponse({ revoked: true });
  }

  private async leaveGroup(device: DeviceRecord): Promise<Response> {
    const result = await this.ctx.storage.transaction(async (transaction) => {
      const deviceRecords = await transaction.list<DeviceRecord>({
        prefix: "device:"
      });
      const otherActiveDevices = Array.from(deviceRecords.values()).filter(
        (candidate) =>
          !candidate.revoked && candidate.device_id !== device.device_id
      );

      if (device.administrator && otherActiveDevices.length > 0) {
        return "administrator_required" as const;
      }

      const locks = await transaction.list<LockRecord>({ prefix: "lock:" });
      const ownedLockKeys = Array.from(locks.entries())
        .filter(([, lock]) => lock.owner_device_id === device.device_id)
        .map(([key]) => key);

      if (ownedLockKeys.length > 0) {
        await transaction.delete(ownedLockKeys);
      }

      await transaction.put(`device:${device.token_hash}`, {
        ...device,
        revoked: true
      });

      if (otherActiveDevices.length > 0) {
        await transaction.delete(CURRENT_PACKAGE_KEY);
      }

      return otherActiveDevices.length === 0 ? "empty" as const : "left" as const;
    });

    if (result === "administrator_required") {
      return errorResponse(
        409,
        "administrator_transfer_required",
        "Revoke the other computers before the administrator leaves the group."
      );
    }

    if (result === "empty") {
      await this.ctx.storage.deleteAll();
      return jsonResponse({ left: true, group_empty: true });
    }

    return jsonResponse({ left: true, group_empty: false });
  }

  private async storeDevice(device: DeviceRecord): Promise<void> {
    await this.ctx.storage.put({
      [`device:${device.token_hash}`]: device,
      [`device-id:${device.device_id}`]: device.token_hash
    });
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

    return { ...device, administrator: device.administrator === true };
  }

  private async registerPackage(
    request: Request,
    projectUuid: string,
    device: DeviceRecord
  ): Promise<Response> {
    const body = await readJsonBody(request);

    if (body instanceof Response) {
      return body;
    }

    const leaseId = body.lease_id;
    const transportName = normalizeName(
      body.transport_name,
      MAX_TRANSPORT_NAME_LENGTH
    );
    const remoteId = normalizeName(body.remote_id, MAX_REMOTE_ID_LENGTH);
    const projectVersion = body.project_version;
    const packageChecksum = body.package_checksum;
    const packageSizeBytes = body.package_size_bytes;
    const encryptionKeyId = normalizeName(
      body.encryption_key_id,
      MAX_KEY_ID_LENGTH
    );
    const projectName = normalizeName(
      body.project_name,
      MAX_PROJECT_NAME_LENGTH
    );
    const gameId = normalizeName(body.game_id, MAX_GAME_ID_LENGTH);
    const createdBy = normalizeName(body.created_by, MAX_OWNER_NAME_LENGTH);

    if (typeof leaseId !== "string" || !leaseId) {
      return errorResponse(400, "invalid_lease", "Lease ID is required.");
    }

    if (!transportName) {
      return errorResponse(
        400,
        "invalid_transport",
        "Package transport name is required."
      );
    }

    if (!remoteId) {
      return errorResponse(
        400,
        "invalid_remote_id",
        "Package remote identifier is required."
      );
    }

    if (
      typeof projectVersion !== "number" ||
      !Number.isSafeInteger(projectVersion) ||
      projectVersion < 1
    ) {
      return errorResponse(
        400,
        "invalid_project_version",
        "Package project version must be a positive integer."
      );
    }

    if (
      typeof packageChecksum !== "string" ||
      !/^[0-9a-f]{64}$/i.test(packageChecksum)
    ) {
      return errorResponse(
        400,
        "invalid_package_checksum",
        "Package checksum must be a SHA-256 value."
      );
    }

    if (
      typeof packageSizeBytes !== "number" ||
      !Number.isSafeInteger(packageSizeBytes) ||
      packageSizeBytes < 1
    ) {
      return errorResponse(
        400,
        "invalid_package_size",
        "Package size must be a positive integer."
      );
    }

    if (!encryptionKeyId) {
      return errorResponse(
        400,
        "invalid_encryption_key",
        "Package encryption key identifier is required."
      );
    }

    const metadataValues = [projectName, gameId, createdBy];
    if (
      metadataValues.some((value) => value !== null) &&
      metadataValues.some((value) => value === null)
    ) {
      return errorResponse(
        400,
        "invalid_package_metadata",
        "Package display metadata must include project name, game ID, and creator."
      );
    }

    const result = await this.ctx.storage.transaction(async (transaction) => {
      const lockStorageKey = lockKey(projectUuid);
      const lock = await transaction.get<LockRecord>(lockStorageKey);
      const now = new Date();

      if (!lock || isExpired(lock, now)) {
        if (lock) {
          await transaction.delete(lockStorageKey);
        }
        return { error: "expired" as const };
      }

      if (
        lock.owner_device_id !== device.device_id ||
        lock.lease_id !== leaseId
      ) {
        return { error: "ownership" as const, lock };
      }

      const currentKeyId = await transaction.get<string>(CURRENT_PACKAGE_KEY);

      if (currentKeyId !== encryptionKeyId) {
        return { error: "encryption_key" as const };
      }

      const storageKey = packageKey(projectUuid, projectVersion);
      const existing = await transaction.get<PackageArtifactRecord>(storageKey);

      if (existing) {
        const identical =
          existing.transport_name === transportName &&
          existing.remote_id === remoteId &&
          existing.package_checksum === packageChecksum.toLowerCase() &&
          existing.package_size_bytes === packageSizeBytes &&
          existing.encryption_key_id === encryptionKeyId;
        if (!identical) {
          return { error: "collision" as const };
        }

        if (projectName && gameId && createdBy && !existing.project_name) {
          const enriched = {
            ...existing,
            project_name: projectName,
            game_id: gameId,
            created_by: createdBy
          };
          await transaction.put(storageKey, enriched);
          return { package: enriched, created: false };
        }

        return { package: existing, created: false };
      }

      const packageRecord: PackageArtifactRecord = {
        catalog_id: crypto.randomUUID(),
        transport_name: transportName,
        remote_id: remoteId,
        project_uuid: projectUuid,
        project_version: projectVersion,
        package_checksum: packageChecksum.toLowerCase(),
        package_size_bytes: packageSizeBytes,
        encryption_key_id: encryptionKeyId,
        published_by_device_id: device.device_id,
        published_at_utc: now.toISOString()
      };
      if (projectName && gameId && createdBy) {
        packageRecord.project_name = projectName;
        packageRecord.game_id = gameId;
        packageRecord.created_by = createdBy;
      }
      await transaction.put(storageKey, packageRecord);
      return { package: packageRecord, created: true };
    });

    if ("error" in result && result.error === "expired") {
      return errorResponse(
        409,
        "lease_expired",
        "An active project lease is required to publish a package."
      );
    }

    if ("error" in result && result.error === "ownership") {
      return errorResponse(
        403,
        "lock_not_owned",
        "This device does not own the project lease.",
        result.lock
      );
    }

    if ("error" in result && result.error === "encryption_key") {
      return errorResponse(
        409,
        "package_key_rotated",
        "The package encryption key changed. Encrypt and publish the package again."
      );
    }

    if ("error" in result) {
      return errorResponse(
        409,
        "package_version_conflict",
        "A different package is already registered for this project version."
      );
    }

    return jsonResponse(
      { package: result.package },
      result.created ? 201 : 200
    );
  }

  private async getCurrentPackageEncryptionKey(): Promise<Response> {
    const key = await this.ctx.storage.transaction(
      async (transaction) => {
        const currentId = await transaction.get<string>(CURRENT_PACKAGE_KEY);

        if (currentId) {
          const existing = await transaction.get<PackageEncryptionKeyRecord>(
            packageEncryptionKey(currentId)
          );

          if (existing) {
            return existing;
          }
        }

        const created: PackageEncryptionKeyRecord = {
          key_id: crypto.randomUUID(),
          algorithm: "AES-256-GCM",
          key_material: randomToken(),
          created_at_utc: new Date().toISOString()
        };
        await transaction.put(CURRENT_PACKAGE_KEY, created.key_id);
        await transaction.put(packageEncryptionKey(created.key_id), created);
        return created;
      }
    );
    return jsonResponse({ key });
  }

  private async getPackageEncryptionKey(encodedKeyId: string): Promise<Response> {
    let keyId: string;

    try {
      keyId = decodeURIComponent(encodedKeyId);
    } catch {
      return errorResponse(400, "invalid_encryption_key", "Key ID is invalid.");
    }

    if (!normalizeName(keyId, MAX_KEY_ID_LENGTH)) {
      return errorResponse(400, "invalid_encryption_key", "Key ID is invalid.");
    }

    const key = await this.ctx.storage.get<PackageEncryptionKeyRecord>(
      packageEncryptionKey(keyId)
    );

    return key
      ? jsonResponse({ key })
      : errorResponse(404, "encryption_key_not_found", "Package key was not found.");
  }

  private async listPackages(projectUuid: string): Promise<Response> {
    const records = await this.ctx.storage.list<PackageArtifactRecord>({
      prefix: packagePrefix(projectUuid)
    });
    const packages = Array.from(records.values()).sort(
      (left, right) => right.project_version - left.project_version
    );
    return jsonResponse({ packages });
  }

  private async listLatestPackages(): Promise<Response> {
    const records = await this.ctx.storage.list<PackageArtifactRecord>({
      prefix: "package:"
    });
    const latestByProject = new Map<string, PackageArtifactRecord>();

    for (const record of records.values()) {
      const current = latestByProject.get(record.project_uuid);
      if (!current || record.project_version > current.project_version) {
        latestByProject.set(record.project_uuid, record);
      }
    }

    const packages = Array.from(latestByProject.values()).sort(
      (left, right) => right.published_at_utc.localeCompare(left.published_at_utc)
    );
    return jsonResponse({ packages });
  }

  private async removeProject(
    projectUuid: string,
    device: DeviceRecord
  ): Promise<Response> {
    if (!device.administrator) {
      return errorResponse(
        403,
        "administrator_required",
        "Only the group administrator can unshare a world."
      );
    }

    const activeLock = await this.ctx.storage.get<LockRecord>(lockKey(projectUuid));
    if (activeLock && !isExpired(activeLock, new Date())) {
      return errorResponse(
        409,
        "project_locked",
        "Finish the hosted session before unsharing this world.",
        activeLock
      );
    }

    const records = await this.ctx.storage.list<PackageArtifactRecord>({
      prefix: packagePrefix(projectUuid)
    });
    const packageKeys = Array.from(records.keys());
    for (let index = 0; index < packageKeys.length; index += 128) {
      await this.ctx.storage.delete(packageKeys.slice(index, index + 128));
    }
    await this.ctx.storage.delete([
      lockKey(projectUuid),
      fencingKey(projectUuid)
    ]);
    return jsonResponse({ removed: true, package_count: records.size });
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

function publicPairedDevice(device: DeviceRecord, deviceToken: string): object {
  return {
    device_id: device.device_id,
    device_token: deviceToken,
    administrator: device.administrator
  };
}

function publicDevice(device: DeviceRecord): PublicDevice {
  return {
    device_id: device.device_id,
    device_name: device.device_name,
    created_at_utc: device.created_at_utc,
    revoked: device.revoked,
    administrator: device.administrator === true
  };
}

function requireAdministrator(device: DeviceRecord): Response | null {
  return device.administrator
    ? null
    : errorResponse(403, "administrator_required", "Group administrator access is required.");
}

function lockKey(projectUuid: string): string {
  return `lock:${projectUuid}`;
}

function fencingKey(projectUuid: string): string {
  return `fencing:${projectUuid}`;
}

function packagePrefix(projectUuid: string): string {
  return `package:${projectUuid}:`;
}

function packageKey(projectUuid: string, projectVersion: number): string {
  return `${packagePrefix(projectUuid)}${projectVersion}`;
}

function packageEncryptionKey(keyId: string): string {
  return `package-encryption-key:${keyId}`;
}

function parseProjectUuid(encodedValue: string): string | null {
  try {
    const value = decodeURIComponent(encodedValue);
    return PROJECT_UUID_PATTERN.test(value) ? value : null;
  } catch {
    return null;
  }
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
