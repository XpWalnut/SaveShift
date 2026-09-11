import { SELF, env, runInDurableObject } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";

import { CoordinationGroup } from "../src/index";
import type { Env as CoordinationEnv } from "../src/index";

const API = "https://coordination.test/api/v1";

beforeEach(async () => {
  const group = (env as CoordinationEnv).COORDINATION.getByName("test-group");
  await runInDurableObject(
    group,
    async (_instance: CoordinationGroup, state) => {
      await state.storage.deleteAll();
    }
  );
});

interface Device {
  device_id: string;
  device_token: string;
  administrator?: boolean;
}

interface Invitation {
  invitation_id: string;
  invitation_token: string;
  expires_at_utc: string;
}

interface PackageRecord {
  catalog_id: string;
  transport_name: string;
  remote_id: string;
  project_uuid: string;
  project_version: number;
  package_checksum: string;
  package_size_bytes: number;
  published_by_device_id: string;
  published_at_utc: string;
  project_name?: string;
  game_id?: string;
  created_by?: string;
}

async function pair(deviceName: string): Promise<Device> {
  const response = await SELF.fetch(`${API}/devices/pair`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pairing_code: "test-pairing-code",
      device_name: deviceName
    })
  });
  expect(response.status).toBe(201);
  return (await response.json<{ device: Device }>()).device;
}

async function bootstrap(deviceName: string): Promise<Device> {
  const response = await SELF.fetch(`${API}/devices/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bootstrap_token: "test-bootstrap-token",
      device_name: deviceName
    })
  });
  expect(response.status).toBe(201);
  return (await response.json<{ device: Device }>()).device;
}

async function createInvitation(deviceToken: string): Promise<Invitation> {
  const response = await SELF.fetch(`${API}/invitations`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${deviceToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ expires_in_seconds: 3600 })
  });
  expect(response.status).toBe(201);
  return (await response.json<{ invitation: Invitation }>()).invitation;
}

async function join(invitationToken: string, deviceName: string): Promise<Response> {
  return SELF.fetch(`${API}/devices/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      invitation_token: invitationToken,
      device_name: deviceName
    })
  });
}

function lockRequest(
  projectUuid: string,
  action: string | null,
  deviceToken: string,
  body?: object
): Promise<Response> {
  const suffix = action ? `/${action}` : "";
  return SELF.fetch(`${API}/locks/${projectUuid}${suffix}`, {
    method: action ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${deviceToken}`,
      "Content-Type": "application/json"
    },
    body: body ? JSON.stringify(body) : undefined
  });
}

function packageRequest(
  projectUuid: string,
  deviceToken: string,
  body?: object
): Promise<Response> {
  return SELF.fetch(`${API}/projects/${projectUuid}/packages`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${deviceToken}`,
      "Content-Type": "application/json"
    },
    body: body ? JSON.stringify(body) : undefined
  });
}

describe("provider-neutral lock contract", () => {
  it("checks health through the durable coordination backend", async () => {
    const response = await SELF.fetch("https://coordination.test/health");

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      api_version: "v1",
      provider_version: "1.5.0"
    });
  });

  it("isolates package catalogs and encryption keys by group identity", async () => {
    const namespace = (env as CoordinationEnv).COORDINATION;
    const firstGroup = namespace.getByName("isolated-group-one");
    const secondGroup = namespace.getByName("isolated-group-two");
    const bootstrapRequest = (deviceName: string) => new Request(
      `${API}/devices/bootstrap`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bootstrap_token: "test-bootstrap-token",
          device_name: deviceName
        })
      }
    );

    const firstBootstrap = await firstGroup.fetch(
      bootstrapRequest("First Group Owner")
    );
    const secondBootstrap = await secondGroup.fetch(
      bootstrapRequest("Second Group Owner")
    );
    expect(firstBootstrap.status).toBe(201);
    expect(secondBootstrap.status).toBe(201);
    const firstDevice = (
      await firstBootstrap.json<{ device: Device }>()
    ).device;
    const secondDevice = (
      await secondBootstrap.json<{ device: Device }>()
    ).device;

    const firstKeyResponse = await firstGroup.fetch(new Request(
      `${API}/package-encryption-key`,
      { headers: { Authorization: `Bearer ${firstDevice.device_token}` } }
    ));
    const secondKeyResponse = await secondGroup.fetch(new Request(
      `${API}/package-encryption-key`,
      { headers: { Authorization: `Bearer ${secondDevice.device_token}` } }
    ));
    const firstKey = await firstKeyResponse.json<{ key: { key_id: string } }>();
    const secondKey = await secondKeyResponse.json<{ key: { key_id: string } }>();
    expect(firstKey.key.key_id).not.toBe(secondKey.key.key_id);

    const isolatedProjectUuid = "12345678-1234-4234-9234-567812345698";
    const leaseResponse = await firstGroup.fetch(new Request(
      `${API}/locks/${isolatedProjectUuid}/acquire`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${firstDevice.device_token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ owner_display_name: "First Owner" })
      }
    ));
    const lease = await leaseResponse.json<{ lock: { lease_id: string } }>();
    const publishResponse = await firstGroup.fetch(new Request(
      `${API}/projects/${isolatedProjectUuid}/packages`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${firstDevice.device_token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          lease_id: lease.lock.lease_id,
          transport_name: "steam-ugc",
          remote_id: "first-group-item",
          project_version: 1,
          package_checksum: "a".repeat(64),
          package_size_bytes: 1024,
          encryption_key_id: firstKey.key.key_id,
          project_name: "First Group World",
          game_id: "v_rising",
          created_by: "First Owner"
        })
      }
    ));
    expect(publishResponse.status).toBe(201);

    const firstCatalogUsingSecondCredential = await firstGroup.fetch(new Request(
      `${API}/packages/latest`,
      { headers: { Authorization: `Bearer ${secondDevice.device_token}` } }
    ));
    expect(firstCatalogUsingSecondCredential.status).toBe(401);

    const firstCatalog = await firstGroup.fetch(new Request(
      `${API}/packages/latest`,
      { headers: { Authorization: `Bearer ${firstDevice.device_token}` } }
    ));
    expect((await firstCatalog.json<{ packages: PackageRecord[] }>()).packages)
      .toHaveLength(1);

    const secondCatalog = await secondGroup.fetch(new Request(
      `${API}/packages/latest`,
      { headers: { Authorization: `Bearer ${secondDevice.device_token}` } }
    ));
    expect(secondCatalog.status).toBe(200);
    expect(await secondCatalog.json()).toEqual({ packages: [] });
  });

  it("rejects an invalid pairing code", async () => {
    const response = await SELF.fetch(`${API}/devices/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pairing_code: "wrong-code",
        device_name: "Unknown PC"
      })
    });

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      error: { code: "invalid_pairing_code" }
    });
  });

  it("acquires, renews, reads, and releases a lease", async () => {
    const projectUuid = "12345678-1234-4234-9234-567812345601";
    const device = await pair("Jake's PC");

    const acquiredResponse = await lockRequest(
      projectUuid,
      "acquire",
      device.device_token,
      { owner_display_name: "Jake" }
    );
    expect(acquiredResponse.status).toBe(200);
    const acquired = (await acquiredResponse.json<any>()).lock;
    expect(acquired).toMatchObject({
      project_uuid: projectUuid,
      fencing_token: 1,
      owner_device_id: device.device_id,
      owner_display_name: "Jake"
    });

    const renewedResponse = await lockRequest(
      projectUuid,
      "renew",
      device.device_token,
      { lease_id: acquired.lease_id }
    );
    expect(renewedResponse.status).toBe(200);
    const renewed = (await renewedResponse.json<any>()).lock;
    expect(renewed.lease_id).toBe(acquired.lease_id);
    expect(renewed.fencing_token).toBe(acquired.fencing_token);

    const statusResponse = await lockRequest(
      projectUuid,
      null,
      device.device_token
    );
    expect(statusResponse.status).toBe(200);
    expect((await statusResponse.json<any>()).lock.lease_id).toBe(
      acquired.lease_id
    );

    const releaseResponse = await lockRequest(
      projectUuid,
      "release",
      device.device_token,
      { lease_id: acquired.lease_id }
    );
    expect(releaseResponse.status).toBe(200);
    expect(await releaseResponse.json()).toEqual({ released: true });

    const unlockedResponse = await lockRequest(
      projectUuid,
      null,
      device.device_token
    );
    expect(await unlockedResponse.json()).toEqual({ lock: null });
  });

  it("rejects a competing device and returns the current owner", async () => {
    const projectUuid = "12345678-1234-4234-9234-567812345602";
    const first = await pair("First PC");
    const second = await pair("Second PC");

    await lockRequest(projectUuid, "acquire", first.device_token, {
      owner_display_name: "Alex"
    });
    const conflictResponse = await lockRequest(
      projectUuid,
      "acquire",
      second.device_token,
      { owner_display_name: "Jake" }
    );

    expect(conflictResponse.status).toBe(409);
    expect(await conflictResponse.json()).toMatchObject({
      error: {
        code: "lock_conflict",
        lock: {
          project_uuid: projectUuid,
          owner_display_name: "Alex"
        }
      }
    });
  });

  it("rejects a second process using the same device identity", async () => {
    const projectUuid = "12345678-1234-4234-9234-567812345605";
    const device = await pair("Shared PC");

    await lockRequest(projectUuid, "acquire", device.device_token, {
      owner_display_name: "First Process"
    });
    const conflictResponse = await lockRequest(
      projectUuid,
      "acquire",
      device.device_token,
      { owner_display_name: "Second Process" }
    );

    expect(conflictResponse.status).toBe(409);
    expect(await conflictResponse.json()).toMatchObject({
      error: {
        code: "lock_conflict",
        lock: { owner_display_name: "First Process" }
      }
    });
  });

  it("increments the fencing token after a released lease", async () => {
    const projectUuid = "12345678-1234-4234-9234-567812345603";
    const device = await pair("Fencing PC");

    const firstResponse = await lockRequest(
      projectUuid,
      "acquire",
      device.device_token,
      { owner_display_name: "Jake" }
    );
    const first = (await firstResponse.json<any>()).lock;
    await lockRequest(projectUuid, "release", device.device_token, {
      lease_id: first.lease_id
    });

    const secondResponse = await lockRequest(
      projectUuid,
      "acquire",
      device.device_token,
      { owner_display_name: "Jake" }
    );
    const second = (await secondResponse.json<any>()).lock;

    expect(second.fencing_token).toBe(first.fencing_token + 1);
    expect(second.lease_id).not.toBe(first.lease_id);
  });

  it("requires a paired device for lock status", async () => {
    const response = await SELF.fetch(
      `${API}/locks/12345678-1234-4234-9234-567812345604`
    );

    expect(response.status).toBe(401);
    expect(await response.json()).toMatchObject({
      error: { code: "authentication_required" }
    });
  });
});

describe("group package catalog", () => {
  const projectUuid = "12345678-1234-4234-9234-567812345611";
  const checksum = "a".repeat(64);

  async function acquire(device: Device): Promise<string> {
    const response = await lockRequest(
      projectUuid,
      "acquire",
      device.device_token,
      { owner_display_name: "Alice" }
    );
    expect(response.status).toBe(200);
    return (await response.json<{ lock: { lease_id: string } }>()).lock.lease_id;
  }

  async function currentKey(deviceToken: string): Promise<{
    key_id: string;
    algorithm: string;
    key_material: string;
  }> {
    const response = await SELF.fetch(`${API}/package-encryption-key`, {
      headers: { Authorization: `Bearer ${deviceToken}` }
    });
    expect(response.status).toBe(200);
    return (await response.json<{
      key: {
        key_id: string;
        algorithm: string;
        key_material: string;
      };
    }>()).key;
  }

  function packageBody(leaseId: string, keyId: string): object {
    return {
      lease_id: leaseId,
      transport_name: "steam-ugc",
      remote_id: "1234567890123456789",
      project_version: 4,
      package_checksum: checksum,
      package_size_bytes: 4096,
      encryption_key_id: keyId,
      project_name: "Shared World",
      game_id: "abiotic_factor",
      created_by: "Alice"
    };
  }

  it("shares one stable package encryption key with authenticated members", async () => {
    const first = await pair("First PC");
    const second = await pair("Second PC");

    const firstResponse = await SELF.fetch(
      `${API}/package-encryption-key`,
      { headers: { Authorization: `Bearer ${first.device_token}` } }
    );
    const secondResponse = await SELF.fetch(
      `${API}/package-encryption-key`,
      { headers: { Authorization: `Bearer ${second.device_token}` } }
    );
    expect(firstResponse.status).toBe(200);
    expect(secondResponse.status).toBe(200);
    const firstKey = await firstResponse.json<{
      key: { key_id: string; algorithm: string; key_material: string };
    }>();
    expect(firstKey.key.key_id).toBeTruthy();
    expect(firstKey.key.algorithm).toBe("AES-256-GCM");
    expect(firstKey.key.key_material).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(await secondResponse.json()).toEqual(firstKey);
  });

  it("does not expose package encryption keys to unpaired callers", async () => {
    const response = await SELF.fetch(`${API}/package-encryption-key`);

    expect(response.status).toBe(401);
    expect(await response.json()).toMatchObject({
      error: { code: "authentication_required" }
    });
  });

  it("rotates future package encryption after a device is revoked", async () => {
    const administrator = await bootstrap("Owner PC");
    const invitation = await createInvitation(administrator.device_token);
    const joinedResponse = await join(invitation.invitation_token, "Former PC");
    const former = (await joinedResponse.json<{ device: Device }>()).device;
    const previous = await currentKey(former.device_token);

    const revokeResponse = await SELF.fetch(
      `${API}/devices/${former.device_id}/revoke`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${administrator.device_token}` }
      }
    );
    expect(revokeResponse.status).toBe(200);
    const current = await currentKey(administrator.device_token);
    expect(current.key_id).not.toBe(previous.key_id);
    expect(current.key_material).not.toBe(previous.key_material);

    const historicalResponse = await SELF.fetch(
      `${API}/package-encryption-keys/${previous.key_id}`,
      { headers: { Authorization: `Bearer ${administrator.device_token}` } }
    );
    expect(historicalResponse.status).toBe(200);
    expect(
      (await historicalResponse.json<{ key: { key_id: string } }>()).key.key_id
    ).toBe(previous.key_id);

    const revokedResponse = await SELF.fetch(
      `${API}/package-encryption-keys/${previous.key_id}`,
      { headers: { Authorization: `Bearer ${former.device_token}` } }
    );
    expect(revokedResponse.status).toBe(401);
  });

  it("requires an active owned lease to register a package", async () => {
    const first = await pair("First PC");
    const second = await pair("Second PC");
    const leaseId = await acquire(first);
    const key = await currentKey(first.device_token);

    const wrongOwner = await packageRequest(
      projectUuid,
      second.device_token,
      packageBody(leaseId, key.key_id)
    );
    expect(wrongOwner.status).toBe(403);
    expect(await wrongOwner.json()).toMatchObject({
      error: { code: "lock_not_owned" }
    });

    await lockRequest(projectUuid, "release", first.device_token, {
      lease_id: leaseId
    });
    const unlocked = await packageRequest(
      projectUuid,
      first.device_token,
      packageBody(leaseId, key.key_id)
    );
    expect(unlocked.status).toBe(409);
    expect(await unlocked.json()).toMatchObject({
      error: { code: "lease_expired" }
    });
  });

  it("registers idempotently and lists packages for group members", async () => {
    const owner = await pair("Owner PC");
    const member = await pair("Member PC");
    const leaseId = await acquire(owner);
    const key = await currentKey(owner.device_token);
    const body = packageBody(leaseId, key.key_id);

    const createdResponse = await packageRequest(
      projectUuid,
      owner.device_token,
      body
    );
    expect(createdResponse.status).toBe(201);
    const created = (
      await createdResponse.json<{ package: PackageRecord }>()
    ).package;
    expect(created).toMatchObject({
      transport_name: "steam-ugc",
      remote_id: "1234567890123456789",
      project_uuid: projectUuid,
      project_version: 4,
      package_checksum: checksum,
      package_size_bytes: 4096,
      published_by_device_id: owner.device_id,
      project_name: "Shared World",
      game_id: "abiotic_factor",
      created_by: "Alice"
    });

    const replayResponse = await packageRequest(
      projectUuid,
      owner.device_token,
      body
    );
    expect(replayResponse.status).toBe(200);
    expect(
      (await replayResponse.json<{ package: PackageRecord }>()).package
        .catalog_id
    ).toBe(created.catalog_id);

    const listResponse = await packageRequest(
      projectUuid,
      member.device_token
    );
    expect(listResponse.status).toBe(200);
    expect(
      (await listResponse.json<{ packages: PackageRecord[] }>()).packages
    ).toEqual([created]);
  });

  it("lists the newest shared package for the group inbox", async () => {
    const owner = await pair("Owner PC");
    const member = await pair("Member PC");
    const leaseId = await acquire(owner);
    const key = await currentKey(owner.device_token);
    await packageRequest(
      projectUuid,
      owner.device_token,
      packageBody(leaseId, key.key_id)
    );
    await packageRequest(
      projectUuid,
      owner.device_token,
      {
        ...packageBody(leaseId, key.key_id),
        project_version: 5,
        remote_id: "newer-item",
        package_checksum: "b".repeat(64)
      }
    );

    const response = await SELF.fetch(`${API}/packages/latest`, {
      headers: { Authorization: `Bearer ${member.device_token}` }
    });

    expect(response.status).toBe(200);
    const packages = (
      await response.json<{ packages: PackageRecord[] }>()
    ).packages;
    expect(packages).toHaveLength(1);
    expect(packages[0]).toMatchObject({
      project_uuid: projectUuid,
      project_version: 5,
      project_name: "Shared World",
      game_id: "abiotic_factor"
    });
  });

  it("rejects different content for an existing project version", async () => {
    const owner = await pair("Owner PC");
    const leaseId = await acquire(owner);
    const key = await currentKey(owner.device_token);
    await packageRequest(
      projectUuid,
      owner.device_token,
      packageBody(leaseId, key.key_id)
    );

    const collisionResponse = await packageRequest(
      projectUuid,
      owner.device_token,
      {
        ...packageBody(leaseId, key.key_id),
        remote_id: "different-item",
        package_checksum: "b".repeat(64)
      }
    );

    expect(collisionResponse.status).toBe(409);
    expect(await collisionResponse.json()).toMatchObject({
      error: { code: "package_version_conflict" }
    });
  });
});

describe("group onboarding and administration", () => {
  it("allows exactly one legacy device to claim administrator access", async () => {
    const first = await pair("Existing Owner PC");
    const second = await pair("Existing Friend PC");

    const claimResponse = await SELF.fetch(
      `${API}/devices/claim-administrator`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${first.device_token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ pairing_code: "test-pairing-code" })
      }
    );
    expect(claimResponse.status).toBe(200);
    expect(await claimResponse.json()).toEqual({ administrator: true });

    const invitation = await createInvitation(first.device_token);
    expect(invitation.invitation_token).toBeTruthy();

    const secondClaim = await SELF.fetch(
      `${API}/devices/claim-administrator`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${second.device_token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ pairing_code: "test-pairing-code" })
      }
    );
    expect(secondClaim.status).toBe(409);
    expect(await secondClaim.json()).toMatchObject({
      error: { code: "administrator_exists" }
    });
  });

  it("rejects a legacy administrator claim with the wrong pairing code", async () => {
    const device = await pair("Existing PC");
    const response = await SELF.fetch(
      `${API}/devices/claim-administrator`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${device.device_token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ pairing_code: "wrong-code" })
      }
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      error: { code: "invalid_pairing_code" }
    });
  });

  it("replays bootstrap idempotently with the original administrator credential", async () => {
    const administrator = await bootstrap("Owner PC");
    expect(administrator.administrator).toBe(true);

    const secondResponse = await SELF.fetch(`${API}/devices/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bootstrap_token: "test-bootstrap-token",
        device_name: "Owner PC retry"
      })
    });
    expect(secondResponse.status).toBe(200);
    const replayed = (await secondResponse.json<{ device: Device }>()).device;
    expect(replayed).toEqual(administrator);

    const listResponse = await SELF.fetch(`${API}/devices`, {
      headers: { Authorization: `Bearer ${administrator.device_token}` }
    });
    expect(listResponse.status).toBe(200);
    expect((await listResponse.json<{ devices: Device[] }>()).devices).toHaveLength(1);
  });

  it("joins through a single-use invitation", async () => {
    const administrator = await bootstrap("Owner PC");
    const invitation = await createInvitation(administrator.device_token);

    const joinedResponse = await join(invitation.invitation_token, "Friend PC");
    expect(joinedResponse.status).toBe(201);
    const joined = (await joinedResponse.json<{ device: Device }>()).device;
    expect(joined.administrator).toBe(false);

    const reusedResponse = await join(invitation.invitation_token, "Other PC");
    expect(reusedResponse.status).toBe(403);
    expect(await reusedResponse.json()).toMatchObject({
      error: { code: "invitation_used" }
    });
  });

  it("prevents non-administrators from creating invitations", async () => {
    const administrator = await bootstrap("Owner PC");
    const invitation = await createInvitation(administrator.device_token);
    const joinedResponse = await join(invitation.invitation_token, "Friend PC");
    const friend = (await joinedResponse.json<{ device: Device }>()).device;

    const response = await SELF.fetch(`${API}/invitations`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${friend.device_token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({})
    });
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      error: { code: "administrator_required" }
    });
  });

  it("lists and revokes a joined device", async () => {
    const administrator = await bootstrap("Owner PC");
    const invitation = await createInvitation(administrator.device_token);
    const joinedResponse = await join(invitation.invitation_token, "Friend PC");
    const friend = (await joinedResponse.json<{ device: Device }>()).device;

    const listResponse = await SELF.fetch(`${API}/devices`, {
      headers: { Authorization: `Bearer ${administrator.device_token}` }
    });
    expect(listResponse.status).toBe(200);
    expect(await listResponse.json()).toMatchObject({
      devices: [
        { device_name: "Owner PC", administrator: true, revoked: false },
        { device_name: "Friend PC", administrator: false, revoked: false }
      ]
    });

    const revokeResponse = await SELF.fetch(
      `${API}/devices/${friend.device_id}/revoke`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${administrator.device_token}` }
      }
    );
    expect(revokeResponse.status).toBe(200);

    const lockResponse = await lockRequest(
      "12345678-1234-4234-9234-567812345699",
      null,
      friend.device_token
    );
    expect(lockResponse.status).toBe(401);
  });

  it("lets a member leave and invalidates that device", async () => {
    const administrator = await bootstrap("Owner PC");
    const invitation = await createInvitation(administrator.device_token);
    const joinedResponse = await join(invitation.invitation_token, "Friend PC");
    const friend = (await joinedResponse.json<{ device: Device }>()).device;

    const leaveResponse = await SELF.fetch(`${API}/devices/leave`, {
      method: "POST",
      headers: { Authorization: `Bearer ${friend.device_token}` }
    });
    expect(leaveResponse.status).toBe(200);
    expect(await leaveResponse.json()).toEqual({
      left: true,
      group_empty: false
    });

    const rejectedResponse = await SELF.fetch(`${API}/devices/leave`, {
      method: "POST",
      headers: { Authorization: `Bearer ${friend.device_token}` }
    });
    expect(rejectedResponse.status).toBe(401);
  });

  it("requires an administrator to revoke others, then clears an empty group", async () => {
    const administrator = await bootstrap("Owner PC");
    const invitation = await createInvitation(administrator.device_token);
    const joinedResponse = await join(invitation.invitation_token, "Friend PC");
    const friend = (await joinedResponse.json<{ device: Device }>()).device;

    const blockedResponse = await SELF.fetch(`${API}/devices/leave`, {
      method: "POST",
      headers: { Authorization: `Bearer ${administrator.device_token}` }
    });
    expect(blockedResponse.status).toBe(409);
    expect(await blockedResponse.json()).toMatchObject({
      error: { code: "administrator_transfer_required" }
    });

    await SELF.fetch(`${API}/devices/${friend.device_id}/revoke`, {
      method: "POST",
      headers: { Authorization: `Bearer ${administrator.device_token}` }
    });
    const leaveResponse = await SELF.fetch(`${API}/devices/leave`, {
      method: "POST",
      headers: { Authorization: `Bearer ${administrator.device_token}` }
    });
    expect(leaveResponse.status).toBe(200);
    expect(await leaveResponse.json()).toEqual({
      left: true,
      group_empty: true
    });

    const group = (env as CoordinationEnv).COORDINATION.getByName("test-group");
    await runInDurableObject(
      group,
      async (_instance: CoordinationGroup, state) => {
        expect((await state.storage.list()).size).toBe(0);
      }
    );
  });
});
