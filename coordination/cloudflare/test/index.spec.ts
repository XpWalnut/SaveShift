import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

const API = "https://coordination.test/api/v1";

interface Device {
  device_id: string;
  device_token: string;
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

describe("provider-neutral lock contract", () => {
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
