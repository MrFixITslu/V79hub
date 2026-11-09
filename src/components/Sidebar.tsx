import { useState } from "react";
import {
  Bot,
  CreditCard,
  Grid3X3,
  Home,
  LogOut,
  MoreHorizontal,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
  X,
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
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const permissions = new Set<ViewState>(user.permissions || ["overview"]);
  const can = (view: ViewState) =>
    view === "overview" ||
    (user.platformOperator === true && ["connections", "team", "security", "billing"].includes(view)) ||
    permissions.has(view);

  const primary: NavItem[] = [
    { view: "overview", label: "Overview", icon: Home, visible: true },
    { view: "connections", label: "My Apps", icon: Grid3X3, visible: can("connections") },
    { view: "team", label: "Team & Access", icon: Users, visible: can("team") },
    { view: "security", label: "Security", icon: ShieldCheck, visible: can("security") },
    { view: "billing", label: "Billing", icon: CreditCard, visible: can("billing") },
  ];

  const active = (view: ViewState) =>
    view === "overview"
      ? currentView === "overview" || currentView === "dashboard"
      : currentView === view;

  const buttonClass = (view: ViewState) => `v79-nav-link ${active(view) ? "is-active" : ""}`;

  return (
    <>
      <aside aria-label="Primary workspace navigation" className="v79-sidebar hidden lg:flex">
        <div className="v79-brand"><span className="v79-brand-mark">V<span>79</span></span><div><strong>Vision<span>79</span></strong><small>From Idea to Advantage.</small></div></div>
        <nav className="v79-side-nav"><div className="v79-nav-label">WORKSPACE</div>
          {primary.filter((item) => item.visible).map((item) => {
            const Icon = item.icon;
            return <button key={item.view} onClick={() => onViewChange(item.view)} className={buttonClass(item.view)} aria-current={active(item.view) ? "page" : undefined}><Icon size={19} /><span>{item.label}</span>{active(item.view) && <span className="v79-nav-dot" />}</button>;
          })}
          {user.ownerAgent && <div className="v79-nav-group"><div className="v79-nav-label">INTELLIGENCE</div><button onClick={() => onViewChange("assistant")} className={buttonClass("assistant")} aria-current={active("assistant") ? "page" : undefined}><Bot size={19} /><span>Owner Assistant</span><Sparkles size={15} /></button></div>}
          {user.platformOperator && <div className="v79-nav-group"><div className="v79-nav-label">ADMINISTRATION</div><button onClick={() => onViewChange("admin")} className={buttonClass("admin")} aria-current={active("admin") ? "page" : undefined}><Settings2 size={19} /><span>Platform Admin</span></button></div>}
        </nav>
        <div className="v79-side-note"><Sparkles size={20} /><strong>Your next advantage<br />starts here.</strong><p>One workspace.<br />More possibilities.</p></div>
        <div className="v79-workspace-switch"><span className="v79-workspace-avatar">V</span><div><strong title={organizationName}>{organizationName}</strong><span>Current workspace</span></div><button onClick={onLogout} title="Log out" aria-label="Log out"><LogOut size={18} /></button></div>
      </aside>

      <nav
        className="v79-mobile-nav lg:hidden fixed bottom-0 inset-x-0 z-[70] bg-[#06101d]/95 backdrop-blur-xl border-t border-[#17324d] px-2 pt-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))] flex items-center gap-1"
        aria-label="Mobile workspace navigation"
      >
        {primary.filter((item) => item.visible).slice(0, 4).map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.view}
              onClick={() => {
                onViewChange(item.view);
                setMobileMoreOpen(false);
              }}
              aria-current={active(item.view) ? "page" : undefined}
              className={`min-w-0 flex-1 min-h-12 flex flex-col items-center justify-center gap-1 rounded-xl py-1.5 px-1 text-[11px] font-semibold ${
                active(item.view) ? "text-[#55c7ff] bg-[#0A86FF]/10" : "text-slate-400"
              }`}
            >
              <Icon className="w-5 h-5" />
              <span className="max-w-full truncate">{item.view === "team" ? "Team" : item.label}</span>
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => setMobileMoreOpen((open) => !open)}
          aria-expanded={mobileMoreOpen}
          aria-controls="hub-mobile-more"
          className={`min-w-0 flex-1 min-h-12 flex flex-col items-center justify-center gap-1 rounded-xl py-1.5 px-1 text-[11px] font-semibold ${
            mobileMoreOpen ? "text-[#55c7ff] bg-[#0A86FF]/10" : "text-slate-400"
          }`}
        >
          <MoreHorizontal className="w-5 h-5" />
          <span>More</span>
        </button>
      </nav>

      {mobileMoreOpen && (
        <div className="lg:hidden fixed inset-0 z-[80]">
          <button
            type="button"
            aria-label="Close mobile menu"
            className="absolute inset-0 bg-[#020711]/75 backdrop-blur-sm"
            onClick={() => setMobileMoreOpen(false)}
          />
          <section
            id="hub-mobile-more"
            role="dialog"
            aria-modal="true"
            aria-label="More workspace options"
            className="v79-mobile-menu absolute inset-x-0 bottom-0 rounded-t-3xl border-t border-[#1a3854] bg-[#07111f] px-4 pt-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-2xl"
          >
            <div className="mx-auto mb-3 h-1 w-12 rounded-full bg-slate-700" />
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-black text-white">Workspace menu</div>
                <div className="mt-0.5 truncate text-xs text-slate-500">{organizationName}</div>
              </div>
              <button
                type="button"
                onClick={() => setMobileMoreOpen(false)}
                className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#1a3854] bg-[#091728] text-slate-300"
                aria-label="Close menu"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-2">
              {primary.filter((item) => item.visible).slice(4).map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.view}
                    type="button"
                    onClick={() => {
                      onViewChange(item.view);
                      setMobileMoreOpen(false);
                    }}
                    className="flex min-h-12 items-center gap-3 rounded-xl border border-[#1a3854] bg-[#091728] px-4 text-left text-sm font-semibold text-slate-200"
                  >
                    <Icon className="h-5 w-5 text-[#55c7ff]" />
                    <span>{item.label}</span>
                  </button>
                );
              })}

              {user.ownerAgent && (
                <button
                  type="button"
                  onClick={() => {
                    onViewChange("assistant");
                    setMobileMoreOpen(false);
                  }}
                  className="flex min-h-12 items-center gap-3 rounded-xl border border-[#1a3854] bg-[#091728] px-4 text-left text-sm font-semibold text-slate-200"
                >
                  <Bot className="h-5 w-5 text-[#a78bfa]" />
                  <span>Owner Assistant</span>
                  <Sparkles className="ml-auto h-4 w-4 text-amber-400" />
                </button>
              )}

              {user.platformOperator && (
                <button
                  type="button"
                  onClick={() => {
                    onViewChange("admin");
                    setMobileMoreOpen(false);
                  }}
                  className="flex min-h-12 items-center gap-3 rounded-xl border border-[#1a3854] bg-[#091728] px-4 text-left text-sm font-semibold text-slate-200"
                >
                  <Settings2 className="h-5 w-5 text-[#55c7ff]" />
                  <span>Platform Admin</span>
                </button>
              )}

              <button
                type="button"
                onClick={() => {
                  setMobileMoreOpen(false);
                  onLogout();
                }}
                className="flex min-h-12 items-center gap-3 rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 text-left text-sm font-semibold text-rose-200"
              >
                <LogOut className="h-5 w-5" />
                <span>Sign out</span>
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
