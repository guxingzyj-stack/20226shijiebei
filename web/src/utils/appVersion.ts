const FALLBACK_VERSION = "v2026.06.15";

export function appVersion(): string {
  const explicitVersion = import.meta.env.VITE_APP_VERSION?.trim();
  const gitSha = import.meta.env.VITE_GIT_SHA?.trim();
  if (explicitVersion && gitSha) {
    return `${explicitVersion}-${gitSha.slice(0, 7)}`;
  }
  if (explicitVersion) {
    return explicitVersion;
  }
  if (gitSha) {
    return `${FALLBACK_VERSION}-${gitSha.slice(0, 7)}`;
  }
  return FALLBACK_VERSION;
}
