import type { User, ViewState } from "../types";

const hubViews = new Set<ViewState>([
  "overview", "dashboard", "connections", "team", "security", "billing",
  "admin", "users", "assistant",
]);

/** Only known page IDs may be read from the URL. Payment returns retain precedence. */
export function readHubView(search: string): ViewState {
  const query = new URLSearchParams(search);
  if (query.has("payment")) return "billing";
  const requested = query.get("view");
  return requested && hubViews.has(requested as ViewState)
    ? requested as ViewState : "overview";
}

/** Browser navigation is never an authorization decision. Match existing Hub access. */
export function canAccessHubView(view: ViewState, user: User | null): boolean {
  if (!user || !hubViews.has(view)) return false;
  if (view === "overview" || view === "dashboard") return true;
  if (view === "admin" || view === "users") return user.platformOperator === true;
  if (view === "assistant") return user.ownerAgent === true;
  if (user.platformOperator === true &&
      ["connections", "team", "security", "billing"].includes(view)) return true;
  return Boolean(user.permissions?.includes(view));
}

/** Keep unrelated callback parameters/hash intact; leaving Billing clears payment return. */
export function hubViewUrl(href: string, view: ViewState): string {
  if (!hubViews.has(view)) throw new Error("Invalid Hub view");
  const url = new URL(href);
  if (view === "overview") url.searchParams.delete("view");
  else url.searchParams.set("view", view);
  if (view !== "billing") url.searchParams.delete("payment");
  return url.pathname + url.search + url.hash;
}
