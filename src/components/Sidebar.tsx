import {
  Bot,
  CreditCard,
  Grid3X3,
  Home,
  LogOut,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { ViewState, User } from "../types";

interface SidebarProps {
  currentView: ViewState;
  onViewChange: (view: ViewState) => void;
  onLogout: () => void;
  user: User;
  organizationName?: string;
}

type NavItem = {
  view: ViewState;
  label: string;
  icon: typeof Home;
  visible: boolean;
};

export function Sidebar({
  currentView,
  onViewChange,
  onLogout,
  user,
  organizationName = "V79 Digital",
}: SidebarProps) {
  const permissions = new Set<ViewState>(user.permissions || ["overview"]);
  const can = (view: ViewState) => view === "overview" || permissions.has(view);

  const primary: NavItem[] = [
    { view: "overview", label: "Dashboard", icon: Home, visible: true },
    { view: "connections", label: "Apps", icon: Grid3X3, visible: can("connections") },
    { view: "team", label: "Team", icon: Users, visible: can("team") },
    { view: "security", label: "Security", icon: ShieldCheck, visible: can("security") },
    { view: "billing", label: "Plans & Billing", icon: CreditCard, visible: can("billing") },
  ];

  const active = (view: ViewState) =>
    view === "overview"
      ? currentView === "overview" || currentView === "dashboard"
      : currentView === view;

  const buttonClass = (view: ViewState) =>
    `group w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all border ${
      active(view)
        ? "text-white bg-gradient-to-r from-[#0A86FF]/30 to-[#075fbc]/20 border-[#0A86FF]/60 shadow-[0_0_24px_rgba(10,134,255,0.16)]"
        : "text-slate-400 border-transparent hover:text-white hover:bg-white/[0.045]"
    }`;

  return (
    <>
      <aside className="hidden lg:flex w-[250px] h-screen shrink-0 flex-col bg-[#06101d] border-r border-[#17324d]/70 text-slate-300 select-none relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-56 bg-[radial-gradient(circle_at_30%_0%,rgba(10,134,255,0.16),transparent_62%)] pointer-events-none" />
        <div className="relative px-5 pt-5 pb-6">
          <div className="flex items-center gap-3">
            <div className="relative w-12 h-11 flex items-center justify-center">
              <div className="absolute inset-0 rounded-2xl bg-[#0A86FF]/12 blur-xl" />
              <div className="relative text-[24px] font-black tracking-[-0.08em] text-white">
                <span className="text-[#4dc3ff]">V</span>79
              </div>
            </div>
            <div>
              <div className="text-[13px] font-black tracking-[0.18em] text-white">V79 HUB</div>
              <div className="text-[10px] text-slate-500 mt-0.5">by V79 Digital</div>
            </div>
          </div>
        </div>

        <nav className="relative flex-1 px-3.5 pb-5 overflow-y-auto">
          <div className="px-3 mb-2 text-[9px] font-black uppercase tracking-[0.2em] text-slate-600">
            Workspace
          </div>
          <div className="space-y-1">
            {primary.filter((item) => item.visible).map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.view} onClick={() => onViewChange(item.view)} className={buttonClass(item.view)}>
                  <Icon className={`w-[17px] h-[17px] ${active(item.view) ? "text-[#55c7ff]" : "text-slate-500 group-hover:text-slate-300"}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          {user.ownerAgent && (
            <div className="mt-7">
              <div className="px-3 mb-2 text-[9px] font-black uppercase tracking-[0.2em] text-slate-600">
                Intelligence
              </div>
              <button onClick={() => onViewChange("assistant")} className={buttonClass("assistant")}>
                <Bot className="w-[17px] h-[17px] text-[#8b5cf6]" />
                <span>Owner Assistant</span>
                <Sparkles className="w-3.5 h-3.5 ml-auto text-[#f59e0b]" />
              </button>
            </div>
          )}

          {user.platformOperator && (
            <div className="mt-7">
              <div className="px-3 mb-2 text-[9px] font-black uppercase tracking-[0.2em] text-slate-600">
                Administration
              </div>
              <button onClick={() => onViewChange("admin")} className={buttonClass("admin")}>
                <Settings2 className="w-[17px] h-[17px]" />
                <span>Platform Admin</span>
              </button>
            </div>
          )}
        </nav>

        <div className="relative p-3.5 border-t border-[#17324d]/70 bg-[#050d17]">
          <div className="mb-2 px-1 text-[9px] font-black uppercase tracking-[0.18em] text-slate-600">
            Active workspace
          </div>
          <div className="rounded-2xl border border-[#1b3956] bg-[#091727] p-3 flex items-center gap-2.5">
            <div className="w-9 h-9 shrink-0 rounded-xl bg-gradient-to-br from-[#0A86FF] to-[#0057b7] flex items-center justify-center text-white font-black text-sm shadow-[0_0_18px_rgba(10,134,255,.2)]">
              V
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-bold text-white truncate" title={organizationName}>
                {organizationName}
              </div>
              <div className="flex items-center gap-1.5 text-[9px] text-emerald-400 mt-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Connected
              </div>
            </div>
            <button
              onClick={onLogout}
              title="Log out"
              className="p-2 rounded-lg text-slate-500 hover:text-rose-300 hover:bg-rose-500/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-[70] bg-[#06101d]/95 backdrop-blur-xl border-t border-[#17324d] px-2 py-2 flex items-center gap-1 overflow-x-auto">
        {primary.filter((item) => item.visible).map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.view}
              onClick={() => onViewChange(item.view)}
              className={`min-w-[68px] flex-1 flex flex-col items-center gap-1 rounded-xl py-2 px-2 text-[10px] font-semibold ${
                active(item.view) ? "text-[#55c7ff] bg-[#0A86FF]/10" : "text-slate-500"
              }`}
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </button>
          );
        })}
      </nav>
    </>
  );
}

[executed on device: firelion-Aspire-A315-51 (729abacc-4888-407d-b7ef-15ffed4122f0)]