/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback } from "react";
import { ViewState, User, EcosystemApp } from "./types";
import { Sidebar } from "./components/Sidebar";
import { Login } from "./components/Login";
import { InviteAcceptance } from "./components/InviteAcceptance";
import { TeamInviteAcceptance } from "./components/TeamInviteAcceptance";
import { UserManagement } from "./components/UserManagement";
import { AppSwitcher } from "./components/AppSwitcher";
import { HubOverview } from "./components/HubOverview";
import { WorkspaceConnections } from "./components/WorkspaceConnections";
import { WorkspaceTeam } from "./components/WorkspaceTeam";
import { WorkspaceSecurity } from "./components/WorkspaceSecurity";
import { WorkspaceBilling } from "./components/WorkspaceBilling";
import { AdminConsole } from "./components/AdminConsole";
import { OwnerAssistant } from "./components/OwnerAssistant";
import { CheckCircle2, AlertCircle, RotateCw, Bell, Sun, Moon, ShieldCheck, LogOut, ChevronDown } from "lucide-react";

export default function App() {
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const searchParams = new URLSearchParams(window.location.search);
  const inviteToken = hashParams.get("invite") || searchParams.get("invite") || "";
  const teamInviteToken = hashParams.get("teamInvite") || searchParams.get("teamInvite") || "";
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [organizationName, setOrganizationName] = useState("V79 Digital");
  const [isVerifyingSession, setIsVerifyingSession] = useState(true);
  const [users, setUsers] = useState<User[]>([]);
  const [ecosystemApps, setEcosystemApps] = useState<EcosystemApp[]>([]);
  const [currentView, setCurrentView] = useState<ViewState>(() => searchParams.get("payment") ? "billing" : "overview");
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try { return (localStorage.getItem("v79-hub-theme") as "light" | "dark") || "dark"; }
    catch { return "dark"; }
  });
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("error") !== "launch_denied") return;
    const names: Record<string, string> = { ffpro: "FFPRO", tiquet: "Tiquet", marketing: "Marketing" };
    const name = names[params.get("return") || ""] || "The app";
    setToast({ message: `${name} could not complete sign-in. Check its launch configuration and account link.`, type: "error" });
    setTimeout(() => setToast(null), 8000);
    params.delete("error");
    params.delete("return");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }, []);

  useEffect(() => {
    try { localStorage.setItem("v79-hub-theme", theme); } catch {}
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (inviteToken || teamInviteToken) {
      setIsVerifyingSession(false);
      return;
    }
    const verifySession = async () => {
      try {
        const res = await fetch("/api/auth/me", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          setUser(data.user);
          setOrganizationName(data.organization?.name || "V79 Digital");
        } else {
          setAuthToken(null);
          setUser(null);
          setOrganizationName("V79 Digital");
        }
      } catch (err) {
        console.error("Session verification failed:", err);
      } finally {
        setIsVerifyingSession(false);
      }
    };
    verifySession();
  }, [authToken, inviteToken, teamInviteToken]);

  const fetchHubData = useCallback(async () => {
    try {
      const ecoRes = await fetch("/api/ecosystem/apps", { cache: "no-store" });
      if (ecoRes.ok) setEcosystemApps(await ecoRes.json());
      if (user?.permissions?.includes("team")) {
        const usersRes = await fetch("/api/users", { cache: "no-store" });
        if (usersRes.ok) setUsers(await usersRes.json());
        else setUsers([]);
      } else {
        setUsers([]);
      }
    } catch (err) {
      console.error("Error fetching Hub state:", err);
    }
  }, [user?.permissions]);

  useEffect(() => {
    if (user) fetchHubData();
  }, [user, fetchHubData]);

  useEffect(() => {
    if (!user) return;
    let socket: WebSocket | undefined;
    let reconnectTimeout: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}`);
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "USERS_UPDATED" && user.permissions?.includes("team")) setUsers(msg.payload);
          if (msg.type === "ECOSYSTEM_APPS_UPDATED") setEcosystemApps(msg.apps);
        } catch (err) {
          console.error("WS parse error", err);
        }
      };
      socket.onclose = () => {
        if (!closed) reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      socket?.close();
    };
  }, [user]);

  const handleLoginSuccess = (authenticatedUser: User, _token: string) => {
    setAuthToken("cookie");
    setUser(authenticatedUser);
    setCurrentView("overview");
    showToast(`Welcome back, ${authenticatedUser.fullName || authenticatedUser.username}!`);
  };

  const handleLogout = async () => {
    try {
      if (user) await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // Clear local state even if the network request fails.
    }
    setAuthToken(null);
    setUser(null);
    setOrganizationName("V79 Digital");
    setUsers([]);
    setCurrentView("overview");
  };

  const handleAddUser = async (userData: any) => {
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(userData),
    });
    if (!res.ok) throw new Error((await res.json()).error || "Failed to create user");
    showToast(`User @${userData.username} created`);
    await fetchHubData();
  };

  const handleUpdateUser = async (id: string, updateData: any) => {
    const res = await fetch(`/api/users/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updateData),
    });
    if (!res.ok) throw new Error((await res.json()).error || "Failed to update user");
    showToast("User permissions updated");
    await fetchHubData();
  };

  const handleDeleteUser = async (id: string) => {
    const res = await fetch(`/api/users/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json()).error || "Failed to delete user");
    showToast("User account removed");
    await fetchHubData();
  };

  if (teamInviteToken) {
    return (
      <TeamInviteAcceptance
        token={teamInviteToken}
        onAccepted={(acceptedUser) => {
          const params = new URLSearchParams(window.location.search);
          params.delete("teamInvite");
          const query = params.toString();
          window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
          handleLoginSuccess(acceptedUser, "cookie");
        }}
        onCancel={() => window.location.assign("/")}
      />
    );
  }

  if (inviteToken) {
    return (
      <InviteAcceptance
        token={inviteToken}
        onAccepted={(acceptedUser) => {
          const params = new URLSearchParams(window.location.search);
          params.delete("invite");
          const query = params.toString();
          window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
          handleLoginSuccess(acceptedUser, "cookie");
        }}
        onCancel={() => window.location.assign("/")}
      />
    );
  }

  if (isVerifyingSession) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-white">
        <div className="w-10 h-10 border-3 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin mb-4" />
        <p className="text-xs text-slate-400 font-mono tracking-wider uppercase">
          Initializing V79 Secure Hub...
        </p>
      </div>
    );
  }

  if (!user) return <Login onLoginSuccess={handleLoginSuccess} />;

  const isAdmin = user.platformOperator === true;
  const canView = (view: ViewState) =>
    view === "overview" ||
    view === "dashboard" ||
    (view === "admin"
      ? isAdmin
      : view === "assistant"
        ? user.ownerAgent === true
        : isAdmin && ["connections", "team", "security", "billing"].includes(view)
          ? true
          : Boolean(user.permissions?.includes(view)));

  const viewLabel: Record<string, string> = {
    overview: "Dashboard",
    dashboard: "Dashboard",
    connections: "Apps",
    team: "Team",
    security: "Security",
    billing: "Plans & Billing",
    admin: "Platform Admin",
    users: "User Management",
    assistant: "Owner Assistant",
  };

  return (
    <div className={"hub-theme-" + theme + " flex h-screen bg-slate-100 font-sans text-slate-800 antialiased overflow-hidden"}>
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        onLogout={handleLogout}
        user={user}
        organizationName={organizationName}
      />
      <main className="flex-1 min-w-0 overflow-y-auto relative flex flex-col bg-[#07111f]">
        <header className="h-[60px] px-4 sm:px-5 xl:px-7 border-b border-[#17324d]/80 bg-[#07111f]/95 backdrop-blur-xl flex items-center justify-between shrink-0 sticky top-0 z-30 text-slate-200">
          <div className="flex items-center gap-3 min-w-0">
            <div className="hidden sm:flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-[#1a3854] bg-[#091728] min-w-0 max-w-[260px]">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#0A86FF] to-[#0057b7] flex items-center justify-center text-[11px] font-black text-white shrink-0">V</div>
              <div className="min-w-0">
                <div className="text-[8px] uppercase tracking-[0.15em] font-bold text-slate-600">Workspace</div>
                <div className="text-[11px] font-bold text-white truncate">{organizationName}</div>
              </div>
            </div>
            <div className="hidden xl:flex items-center gap-2 text-[10px]">
              <span className="text-slate-600">/</span>
              <span className="font-semibold text-slate-400">{viewLabel[currentView] || "Workspace"}</span>
            </div>
          </div>

          <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 items-center gap-2">
            <span className="text-[13px] font-black tracking-[-0.03em] text-white"><span className="text-[#55c7ff]">V</span>79</span>
            <span className="text-[9px] font-black tracking-[0.2em] text-slate-500">HUB BY V79 DIGITAL</span>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              className="w-9 h-9 rounded-xl border border-[#1a3854] bg-[#091728] text-slate-500 hover:text-[#55c7ff] hover:border-[#2b5275] flex items-center justify-center transition-colors"
            >
              {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button
              onClick={() => {
                fetchHubData();
                showToast("Hub data refreshed");
              }}
              title="Refresh Hub data"
              className="w-9 h-9 rounded-xl border border-[#1a3854] bg-[#091728] text-slate-500 hover:text-[#55c7ff] hover:border-[#2b5275] flex items-center justify-center transition-colors"
            >
              <RotateCw className="w-4 h-4" />
            </button>
            <button
              type="button"
              disabled
              title="No new notifications"
              aria-label="No new notifications"
              className="hidden sm:flex w-9 h-9 rounded-xl border border-[#1a3854] bg-[#091728] text-slate-600 items-center justify-center cursor-default"
            >
              <Bell className="w-4 h-4" />
            </button>
            <AppSwitcher
              apps={ecosystemApps}
              onNavigateToEcosystem={() => setCurrentView("overview")}
              authToken={authToken}
            />
            <div className="relative hidden sm:block pl-2 border-l border-[#17324d]">
              <button
                type="button"
                onClick={() => setAccountMenuOpen(open => !open)}
                aria-expanded={accountMenuOpen}
                aria-haspopup="menu"
                className="flex items-center gap-2 rounded-xl px-1.5 py-1 hover:bg-white/[0.04] transition-colors"
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#0A86FF] to-[#6d5dfc] flex items-center justify-center text-[10px] font-black text-white">
                  {(user.fullName || user.username || "U").trim().split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase()}
                </div>
                <div className="hidden xl:block min-w-0 max-w-[130px] text-left">
                  <div className="text-[10px] font-bold text-white truncate">{user.fullName || user.username}</div>
                  <div className="text-[8px] text-slate-600 capitalize">{user.workspaceOwner ? "Owner" : user.role}</div>
                </div>
                <ChevronDown className={"w-3.5 h-3.5 text-slate-600 transition-transform " + (accountMenuOpen ? "rotate-180" : "")} />
              </button>

              {accountMenuOpen && (
                <div role="menu" className="absolute right-0 top-12 w-56 rounded-2xl border border-[#1a3854] bg-[#091728] shadow-2xl p-2 z-50">
                  <div className="px-3 py-2 border-b border-[#17324d] mb-1">
                    <div className="text-[10px] font-bold text-white truncate">{user.fullName || user.username}</div>
                    <div className="text-[9px] text-slate-500 truncate">{organizationName}</div>
                  </div>
                  <button
                    role="menuitem"
                    onClick={() => { setCurrentView("security"); setAccountMenuOpen(false); }}
                    className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-white/[0.05]"
                  >
                    <ShieldCheck className="w-4 h-4 text-[#55c7ff]" />
                    Security
                  </button>
                  <button
                    role="menuitem"
                    onClick={() => { setAccountMenuOpen(false); void handleLogout(); }}
                    className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-xs font-semibold text-rose-300 hover:text-white hover:bg-rose-500/10"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {toast && (
          <div className="fixed top-20 right-5 z-[80] animate-in fade-in slide-in-from-top-3">
            <div
              className={`px-4 py-3 rounded-2xl shadow-xl border text-xs font-semibold flex items-center gap-2.5 backdrop-blur-md ${
                toast.type === "success"
                  ? "bg-slate-900/95 text-white border-slate-700"
                  : "bg-rose-900/95 text-rose-100 border-rose-700"
              }`}
            >
              {toast.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              )}
              <span>{toast.message}</span>
            </div>
          </div>
        )}

        {(currentView === "overview" || currentView === "dashboard") && (
          <HubOverview ecosystemApps={ecosystemApps} onNavigate={setCurrentView} user={user} organizationName={organizationName} />
        )}

        {currentView === "connections" && canView("connections") && (
          <WorkspaceConnections
            apps={ecosystemApps}
            onNavigate={setCurrentView}
            authToken={authToken}
          />
        )}

        {currentView === "team" && canView("team") && (
          <WorkspaceTeam
            users={users}
            apps={ecosystemApps}
            currentUser={user}
            onNavigate={setCurrentView}
            onAddUser={handleAddUser}
            onUpdateUser={handleUpdateUser}
            onDeleteUser={handleDeleteUser}
          />
        )}

        {currentView === "security" && canView("security") && <WorkspaceSecurity onNavigate={setCurrentView} />}
        {currentView === "billing" && canView("billing") && <WorkspaceBilling onNavigate={setCurrentView} />}
        {currentView === "admin" && canView("admin") && <AdminConsole ecosystemApps={ecosystemApps} />}
        {currentView === "assistant" && canView("assistant") && <OwnerAssistant />}

        {currentView === "users" && isAdmin && (
          <UserManagement
            users={users}
            onAddUser={handleAddUser}
            onUpdateUser={handleUpdateUser}
            onDeleteUser={handleDeleteUser}
            currentUserId={user.id}
          />
        )}
      </main>
    </div>
  );
}
