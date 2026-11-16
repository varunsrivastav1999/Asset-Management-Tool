import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const status = vi.fn();
const create = vi.fn();
const remove = vi.fn();
const upload = vi.fn();
const restore = vi.fn();
const downloadFile = vi.fn(async () => {});
vi.mock("@/api", () => ({
  backupsApi: {
    status: (...a) => status(...a),
    create: (...a) => create(...a),
    remove: (...a) => remove(...a),
    upload: (...a) => upload(...a),
    restore: (...a) => restore(...a),
  },
}));
vi.mock("@/api/http", () => ({
  downloadFile: (...a) => downloadFile(...a),
  parseError: (e) => ({ message: e?.message || "failed" }),
}));

import BackupsView from "@/views/settings/BackupsView.vue";
import ConfirmHost from "@/components/ui/ConfirmHost.vue";

const base = { service_online: true, pending: 0, schedule: "02:00", keep: 7 };
const files = [
  {
    name: "manual-20261116-101500.dump",
    kind: "manual",
    size: 2_621_440,
    created_at: "2026-11-16T10:15:00Z",
  },
];

let wrappers = [];
const mountView = (comp) => {
  const w = mount(comp, {
    attachTo: document.body,
    global: { stubs: { RouterLink: true } },
  });
  wrappers.push(w);
  return w;
};
beforeEach(() => {
  setActivePinia(createPinia());
  [status, create, remove, upload, restore, downloadFile].forEach((f) =>
    f.mockReset(),
  );
});
afterEach(() => {
  wrappers.forEach((w) => w.unmount());
  wrappers = [];
  document.body.innerHTML = "";
});

describe("BackupsView", () => {
  it("lists backups with size and service state, and downloads one", async () => {
    status.mockResolvedValue({ ...base, backups: files });
    const w = mountView(BackupsView);
    await flushPromises();
    expect(w.text()).toContain("Running");
    expect(w.text()).toContain("Daily at 02:00");
    expect(w.text()).toContain("2.5 MB");
    await w
      .find('[aria-label="Download manual-20261116-101500.dump"]')
      .trigger("click");
    expect(downloadFile).toHaveBeenCalledWith(
      "/backups/manual-20261116-101500.dump/",
      { filename: "manual-20261116-101500.dump" },
    );
  });

  it('"Back up now" queues a backup', async () => {
    status.mockResolvedValue({ ...base, backups: [] });
    create.mockResolvedValue({ ...base, pending: 1, backups: [] });
    const w = mountView(BackupsView);
    await flushPromises();
    await w
      .findAll("button")
      .find((b) => b.text() === "Back up now")
      .trigger("click");
    await flushPromises();
    expect(create).toHaveBeenCalledOnce();
    expect(w.text()).toContain("Backing up…");
  });

  it("deletes only after confirming, then refreshes", async () => {
    mountView(ConfirmHost);
    status.mockResolvedValue({ ...base, backups: files });
    remove.mockResolvedValue("");
    const w = mountView(BackupsView);
    await flushPromises();
    await w
      .find('[aria-label="Delete manual-20261116-101500.dump"]')
      .trigger("click");
    await flushPromises();
    expect(remove).not.toHaveBeenCalled();
    document.body
      .querySelector('[data-testid="confirm-dialog"] [data-confirm]')
      .click();
    await flushPromises();
    expect(remove).toHaveBeenCalledWith("manual-20261116-101500.dump");
    expect(status).toHaveBeenCalledTimes(2);
  });

  it("uploads a .dump with progress, then lists it", async () => {
    status.mockResolvedValue({ ...base, backups: [] });
    upload.mockImplementation(async (file, onProgress) => {
      onProgress(55);
      return {
        name: "uploaded-20261116-120000.dump",
        kind: "uploaded",
        size: 10,
        created_at: "2026-11-16T12:00:00Z",
      };
    });
    const w = mountView(BackupsView);
    await flushPromises();
    const input = w.find('[data-testid="backup-file"]');
    Object.defineProperty(input.element, "files", {
      value: [new File(["PGDMP"], "prod.dump")],
      configurable: true,
    });
    await input.trigger("change");
    await flushPromises();
    expect(upload).toHaveBeenCalledWith(expect.any(File), expect.any(Function));
    expect(status).toHaveBeenCalledTimes(2); // refreshed after upload
  });

  it("refuses non-.dump files before uploading", async () => {
    status.mockResolvedValue({ ...base, backups: [] });
    const w = mountView(BackupsView);
    await flushPromises();
    const input = w.find('[data-testid="backup-file"]');
    Object.defineProperty(input.element, "files", {
      value: [new File(["x"], "data.sql")],
      configurable: true,
    });
    await input.trigger("change");
    await flushPromises();
    expect(upload).not.toHaveBeenCalled();
  });

  it("restores a backup only after its name is typed, then shows progress", async () => {
    const name = "uploaded-20261116-120000.dump";
    status.mockResolvedValue({
      ...base,
      backups: [{ ...files[0], name, kind: "uploaded" }],
    });
    restore.mockResolvedValue({
      ...base,
      backups: [{ ...files[0], name, kind: "uploaded" }],
      restore: {
        state: "queued",
        name,
        message: "Waiting for the backup service",
        at: null,
        id: null,
      },
    });
    const w = mountView(BackupsView);
    await flushPromises();
    expect(w.text()).toContain("Uploaded");
    await w.find(`[aria-label="Restore ${name}"]`).trigger("click");
    await flushPromises();
    const modal = document.body.querySelector('[data-testid="restore-steps"]');
    expect(modal.textContent).toContain(
      `docker compose run --rm backup restore ${name}`,
    );
    const start = document.body.querySelector('[data-testid="restore-start"]');
    expect(start.disabled).toBe(true);
    const input = modal.querySelector('[data-testid="restore-confirm"]');
    input.value = name;
    input.dispatchEvent(new Event("input"));
    await flushPromises();
    expect(start.disabled).toBe(false);
    start.click();
    await flushPromises();
    expect(restore).toHaveBeenCalledWith(name);
    expect(w.find('[data-testid="restore-progress"]').text()).toContain(
      `Restoring ${name}`,
    );
    expect(
      w.find(`[aria-label="Restore ${name}"]`).attributes("disabled"),
    ).toBeDefined();
  });

  it("reloads the app when a running restore finishes", async () => {
    vi.useFakeTimers();
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      value: { ...original, reload },
      configurable: true,
    });
    try {
      const running = {
        state: "running",
        name: files[0].name,
        message: "Loading the backup",
        at: 1,
        id: "r1",
      };
      status.mockResolvedValueOnce({
        ...base,
        backups: files,
        restore: running,
      });
      status.mockResolvedValue({
        ...base,
        backups: files,
        restore: { ...running, state: "done", message: "Restored" },
      });
      const w = mountView(BackupsView);
      await flushPromises();
      expect(w.text()).toContain("Loading the backup");
      await vi.advanceTimersByTimeAsync(3000); // poll
      await flushPromises();
      expect(w.text()).toContain("Restore finished");
      await vi.advanceTimersByTimeAsync(2500);
      expect(reload).toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, "location", {
        value: original,
        configurable: true,
      });
      vi.useRealTimers();
    }
  });

  it("shows why a recent restore failed", async () => {
    const failed = {
      state: "failed",
      name: files[0].name,
      message: "Restore failed, so your data was not changed.",
      at: Date.now() / 1000,
      id: "r2",
    };
    status.mockResolvedValue({ ...base, backups: files, restore: failed });
    const w = mountView(BackupsView);
    await flushPromises();
    expect(w.find('[data-testid="restore-result"]').text()).toContain(
      "your data was not changed",
    );
  });
});
