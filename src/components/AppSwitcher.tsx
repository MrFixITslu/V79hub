import React, { useState, useRef, useEffect } from "react";
import {
  Grid,
  Headphones,
  Wallet,
  Megaphone,
  GraduationCap,
  CreditCard,
  TrendingUp,
  Sparkles,
  Target,
  ArrowRight,
} from "lucide-react";
import { EcosystemApp } from "../types";

interface AppSwitcherProps {
  apps: EcosystemApp[];
  onNavigateToEcosystem: () => void;
  authToken: string | null;
}

export function AppSwitcher({
  apps,
  onNavigateToEcosystem,
  authToken,
}: AppSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const renderIcon = (iconName: string) => {
    switch (iconName) {
      case "Wallet":
        return <Wallet className="w-4 h-4 text-white" />;
      case "Headphones":
        return <Headphones className="w-4 h-4 text-white" />;
      case "Megaphone":
        return <Megaphone className="w-4 h-4 text-white" />;
      case "GraduationCap":
        return <GraduationCap className="w-4 h-4 text-white" />;
      case "CreditCard":
        return <CreditCard className="w-4 h-4 text-white" />;
      case "TrendingUp":
        return <TrendingUp className="w-4 h-4 text-white" />;
      case "Target":
        return <Target className="w-4 h-4 text-white" />;
      default:
        return <Sparkles className="w-4 h-4 text-white" />;
    }
  };

  const getLaunchUrl = (app: EcosystemApp): string | null => {
    if (app.launchReady === false) return null;
    const managed: Record<string, string> = {
      "app-ffpro": "/api/apps/ffpro/launch",
      "app-tiquet": "/api/apps/tiquet/launch",
      "app-marketing": "/api/apps/marketing/launch",
      "app-v79pos": "/api/apps/pos/launch",
    };
    if (managed[app.id]) return managed[app.id];
    if (app.id === "app-academy") return "https://academy.v79sl.com/";
    return /^https:\/\//i.test(app.appUrl || "") ? app.appUrl : null;
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 9-Dot Launcher Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        title="V79 Ecosystem App Launcher"
        className={`p-2 rounded-xl transition-all duration-200 cursor-pointer flex items-center justify-center ${
          isOpen
            ? "bg-slate-800 text-cyan-400 shadow-md ring-2 ring-cyan-500/30"
            : "text-slate-400 hover:text-white hover:bg-slate-800/80"
        }`}
      >
        <Grid className="w-5 h-5" />
      </button>

      {/* App Launcher Dropdown Popover */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-[#0B1528] border border-slate-700/80 rounded-2xl shadow-2xl p-4 z-50 animate-in fade-in zoom-in-95">
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-xs font-extrabold text-white uppercase tracking-wider">
                V79 Apps
              </span>
            </div>
            <button
              onClick={() => {
                setIsOpen(false);
                onNavigateToEcosystem();
              }}
              className="text-[11px] font-bold text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span>View All</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {/* Quick App Grid using native <a> links */}
          <div className="grid grid-cols-3 gap-2 py-3">
            {apps.map((app) => {
              const url = getLaunchUrl(app);
              const managedLaunch = app.id in { "app-ffpro": true, "app-tiquet": true, "app-marketing": true, "app-v79pos": true };
              if (!url) return null;
              return (
                <a
                  key={app.id}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setIsOpen(false)}
                  className="group p-2.5 rounded-2xl hover:bg-slate-800/80 border border-transparent hover:border-slate-700 transition-all flex flex-col items-center text-center cursor-pointer no-underline"
                >
                  <div
                    className={`w-10 h-10 rounded-xl bg-gradient-to-tr ${app.colorScheme.primary} flex items-center justify-center text-white shadow-md group-hover:scale-110 transition-transform mb-1.5`}
                  >
                    {renderIcon(app.iconName)}
                  </div>
                  <span className="text-xs font-bold text-slate-200 group-hover:text-cyan-300 truncate w-full">
                    {app.shortName}
                  </span>
                  <span className="text-[9px] text-slate-400 capitalize truncate w-full mt-0.5">
                    {app.category}
                  </span>
                </a>
              );
            })}
          </div>

          {/* Footer Quick Launch Action */}
          <div className="pt-2.5 border-t border-slate-800 flex items-center justify-between text-[11px] px-1">
            <span className="text-slate-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Open apps in a new tab</span>
            </span>

            <button
              onClick={() => {
                setIsOpen(false);
                onNavigateToEcosystem();
              }}
              className="font-semibold text-slate-300 hover:text-white transition-colors cursor-pointer"
            >
              Manage Apps →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}