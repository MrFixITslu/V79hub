import { EcosystemApp } from "../types";

const managedById: Record<string, string> = {
  "app-ffpro": "/api/apps/ffpro/launch",
  "app-tiquet": "/api/apps/tiquet/launch",
  "app-marketing": "/api/apps/marketing/launch",
  "app-v79pos": "/api/apps/pos/launch",
};

const managedByHost: Record<string, string> = {
  "ffpro.v79sl.com": "/api/apps/ffpro/launch",
  "tiquet.v79sl.com": "/api/apps/tiquet/launch",
  "marketing.v79sl.com": "/api/apps/marketing/launch",
  "pos.v79sl.com": "/api/apps/pos/launch",
};

export function managedLaunchPath(
  app?: Pick<EcosystemApp, "id" | "appUrl"> | null,
  fallback = "",
): string | null {
  if (app?.id && managedById[app.id]) return managedById[app.id];

  const candidate = app?.appUrl || fallback;
  if (!candidate) return null;
  try {
    return managedByHost[new URL(candidate).hostname.toLowerCase()] || null;
  } catch {
    return null;
  }
}

export function appLaunchUrl(
  app?: Pick<EcosystemApp, "id" | "appUrl" | "launchReady"> | null,
  fallback = "",
): string | null {
  if (app?.launchReady === false) return null;
  const external = [app?.appUrl, fallback].find(candidate => {
    if (!candidate) return false;
    try {
      const url = new URL(candidate);
      return url.protocol === "https:" && !url.username && !url.password;
    } catch {
      return false;
    }
  });
  return managedLaunchPath(app, fallback) || external || null;
}

export function isManagedHubApp(
  app?: Pick<EcosystemApp, "id" | "appUrl"> | null,
  fallback = "",
): boolean {
  return Boolean(managedLaunchPath(app, fallback));
}
