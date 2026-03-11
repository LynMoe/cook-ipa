const API_BASE = "";

// ------------------------------------------------------------------ //
// Types
// ------------------------------------------------------------------ //

export type Build = {
  uuid: string;
  status: string;
  created_at: string;
  app_name?: string;
  bundle_id?: string;
  short_version?: string;
  bundle_version?: string;
  install_url?: string;
  icon_url?: string;
  error_message?: string;
};

export type BuildListResponse = {
  builds: Build[];
  total: number;
  page: number;
};

export type Device = {
  apple_device_id: string;
  udid: string;
  name: string;
  platform: string;
  status: string;
};

export type DevicesResponse = {
  devices: Device[];
  total: number;
};

export type ProfileStatus = {
  active_path: string | null;
  latest: {
    id: string;
    name: string;
    uuid: string;
    expiration_date: string | null;
    device_count?: number;
  } | null;
  coverage: boolean;
  missing_devices: { udid: string; name: string; platform: string }[];
  enabled_count: number;
  error: string | null;
};

export type AppleProfile = {
  apple_profile_id: string;
  name: string;
  profile_type: string;
  platform: string;
  expiry_date: string | null;
  state: string;
  uuid: string | null;
  is_active: boolean;
  local_metadata: {
    uuid: string;
    devices: string[];
    device_count: number;
    bundle_id: string;
    expiration_date: string | null;
    file_size: number;
    modified: string;
  } | null;
};

export type ProfilesResponse = {
  profiles: AppleProfile[];
  total: number;
};

export type RegenerateProfileResponse = {
  success: boolean;
  profile: {
    apple_profile_id: string;
    name: string;
    bundle_id: string;
    expiry_date: string;
    device_count_actual: number;
  };
  device_count_total: number;
  device_count_enabled: number;
  device_count_in_profile: number;
  logs: string[];
  message: string;
};

export type CheckUpdateResponse = {
  needs_update: boolean;
  active_profile: {
    path: string;
    name: string;
    bundle_id: string;
    device_count: number;
    expiration_date: string | null;
  };
  missing_enabled_devices: { id: string; name: string; udid: string }[];
  total_devices: number;
  enabled_devices: number;
  regenerated: boolean;
  new_profile?: object;
  logs?: string[];
};

// ------------------------------------------------------------------ //
// Internal helpers
// ------------------------------------------------------------------ //

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error || res.statusText);
  }
  return res.json() as Promise<T>;
}

// ------------------------------------------------------------------ //
// Builds
// ------------------------------------------------------------------ //

export async function listBuilds(page = 1, perPage = 50): Promise<BuildListResponse> {
  return request(`/api/builds?page=${page}&per_page=${perPage}`);
}

export async function getBuild(uuid: string): Promise<{ build: Build }> {
  return request(`/api/builds/${uuid}`);
}

export async function deleteBuild(uuid: string): Promise<{ success: boolean }> {
  return request(`/api/builds/${uuid}`, { method: "DELETE" });
}

export async function getBuildLogs(
  uuid: string,
  sinceId = 0
): Promise<{ status: string; logs: { id: number; message: string; level: string }[] }> {
  return request(`/api/builds/${uuid}/logs?since_id=${sinceId}`);
}

export function buildLogsStreamUrl(uuid: string): string {
  return `${API_BASE}/api/builds/${uuid}/logs/stream`;
}

export async function uploadIpa(
  file: File
): Promise<{ success: boolean; build: Build; message: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error || res.statusText);
  }
  return res.json();
}

export async function submitIpaUrl(
  url: string
): Promise<{ success: boolean; build: Build; message: string }> {
  return request("/api/upload-url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function cleanupBuilds(
  days: number
): Promise<{ success: boolean; builds_removed: number }> {
  return request("/api/builds/cleanup", {
    method: "POST",
    body: JSON.stringify({ days }),
  });
}

export function iconUrl(uuid: string): string {
  return `${API_BASE}/api/build-icon/${uuid}`;
}

// ------------------------------------------------------------------ //
// Devices
// ------------------------------------------------------------------ //

export async function listDevices(): Promise<DevicesResponse> {
  return request("/api/devices");
}

export async function registerDevice(
  name: string,
  udid: string,
  platform = "IOS"
): Promise<{ success: boolean; device: Device }> {
  return request("/api/devices", {
    method: "POST",
    body: JSON.stringify({ name, udid, platform }),
  });
}

// ------------------------------------------------------------------ //
// Profiles
// ------------------------------------------------------------------ //

export async function getProfileStatus(): Promise<ProfileStatus> {
  return request("/api/profiles/status");
}

export async function listProfiles(): Promise<ProfilesResponse> {
  return request("/api/profiles");
}

export async function downloadProfile(
  appleProfileId: string
): Promise<{ success: boolean; profile_path: string; metadata: object | null }> {
  return request(`/api/profiles/${appleProfileId}/download`, { method: "POST" });
}

export async function regenerateProfile(
  bundleId: string,
  name?: string
): Promise<RegenerateProfileResponse> {
  return request("/api/profiles/regenerate", {
    method: "POST",
    body: JSON.stringify({ bundle_id: bundleId, name }),
  });
}

export async function checkUpdateProfile(
  autoRegenerate = false
): Promise<CheckUpdateResponse> {
  return request("/api/profiles/check-update", {
    method: "POST",
    body: JSON.stringify({ auto_regenerate: autoRegenerate }),
  });
}
