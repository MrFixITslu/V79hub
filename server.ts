import express, { Request, Response } from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { createServer as createViteServer } from "vite";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";
import crypto from "crypto";
import { signPlatformRequest, verifyPlatformRequest } from "./server/platform-contract.mjs";
import { migrateLegacyOrganization } from "./server/organization-store.mjs";
import { activeMembership, activeMembershipsForUser, enabledAppIds, organizationCanAccessApp, organizationCanMutateApp, sessionRole, validLegacyLaunch, visibleEcosystemApps } from "./server/organization-access.mjs";
import { acceptInvitationState, invitationStatus } from "./server/onboarding-store.mjs";
import { acceptTeamInvitationState, teamInvitationStatus } from "./server/team-invitation-store.mjs";
import { hasOwnerAssistantAccess, normalizeEmail } from "./server/agent-access.mjs";
import { createAgentProposal, decideAgentProposal, listAgentProposals, appendAgentProposalAudit } from "./server/agent-approval-ledger.mjs";
import { activatePosTenantMapping, posProvisioningTarget, posTenantLaunchReady, posTenantMapping } from "./server/pos-provisioning.mjs";
import { activateFfproTenantMapping, ffproProvisioningTarget, ffproTenantLaunchReady, ffproTenantMapping } from "./server/ffpro-provisioning.mjs";
import { activateTiquetTenantMapping, tiquetProvisioningTarget, tiquetTenantLaunchReady, tiquetTenantMapping } from "./server/tiquet-provisioning.mjs";
import { activateMarketingTenantMapping, marketingProvisioningTarget, marketingTenantLaunchReady, marketingTenantMapping } from "./server/marketing-provisioning.mjs";
import { createHubStorePersistence } from "./server/runtime-store.mjs";
import { retryTransient } from "./server/transient-retry.mjs";
import { createOpaqueToken, decryptSecret as decryptTotpSecret, encryptSecret as encryptTotpSecret, generateTotpSecret, opaqueTokenHash, totpProvisioningUri, verifyTotp } from "./server/security-contract.mjs";
import { addBillingPeriod, normalizeMoney } from "./server/billing-contract.mjs";
import { beginTrial, accessDecision } from "./server/subscription-access.mjs";
import { dispatchDueTrialReminders } from "./server/trial-reminder-dispatch.mjs";
import { createResendTransactionalSender } from "./server/resend-transactional.mjs";
import { validateProductEntitlement, PRODUCTS as ENTITLEMENT_PRODUCTS } from "./server/entitlement-validation.mjs";
import { createWipayCheckout, getWipayConfig, publicWipayConfig, verifyWipayReturn } from "./server/wipay-provider.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ noServer: true });

app.use(express.json({ limit: "2mb", verify: (req: any, _res, body) => { req.rawBody = Buffer.from(body); } }));
app.disable("x-powered-by");
app.use((req, res, next) => {
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("X-Frame-Options", "DENY");
  res.setHeader("Referrer-Policy", "no-referrer");
  // Seven-day HSTS probation on this host only; never include unrelated subdomains.
  res.setHeader("Strict-Transport-Security", "max-age=604800");
  // Conservative first CSP: avoids breaking authenticated app launchers.
  res.setHeader("Content-Security-Policy", "object-src 'none'; base-uri 'self'; frame-ancestors 'none'");
  res.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  if (req.path.startsWith("/api/")) res.setHeader("Cache-Control", "no-store");
  next();
});

// --- Persistent File Store ---
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(__dirname, "data"));
const STORE_FILE = path.join(DATA_DIR, "v79_store.json");
const SESSION_FILE = path.join(DATA_DIR, "hub-sessions.json");

process.umask(0o077);
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true, mode: 0o700 });

interface StoredUser {
  id: string;
  username: string;
  password: string;
  fullName: string;
  email?: string;
  role: "admin" | "manager" | "staff" | "viewer";
  permissions: string[];
  lastLogin?: string;
  createdAt: string;
  mfaEnabled?: boolean;
  mfaSecretEnc?: string;
  mfaPendingSecretEnc?: string;
  mfaPendingCreatedAt?: string;
}

interface WorkspaceProfile {
  companyName: string;
}

interface Organization {
  id: string;
  name: string;
  slug: string;
  status: "active" | "suspended";
  createdAt: string;
}

interface Membership {
  organizationId: string;
  userId: string;
  role: StoredUser["role"] | "owner";
  permissions?: string[];
  appIds?: string[];
  status: "active" | "revoked";
  createdAt: string;
}

interface AppEntitlement {
  organizationId: string;
  appId: string;
  enabled: boolean;
  createdAt: string;
}

interface OrganizationPlan {
  organizationId: string;
  planName: string;
  status: "active" | "trial" | "paused" | "cancelled";
  billingCycle: "monthly" | "annual" | "custom";
  appIds: string[];
  priceXcd?: number;
  renewalDate?: string;
  accessPolicyType?: "internal" | "trial" | "paid" | "legacy_review";
  trialStartedAt?: string;
  trialEndsAt?: string;
  paidThroughAt?: string;
  createdAt: string;
  updatedAt: string;
}

interface TrialReminderEvent { key:string; organizationId:string; kind:string; status:"sending"|"sent"|"failed"; attempts:number; claimedAt:string; sentAt?:string; nextAttemptAt?:string; }

interface BillingOrder {
  id: string;
  organizationId?: string;
  subjectReference?: string;
  sourceApp: "hub" | "academy" | "tiquet";
  kind: "subscription" | "course" | "invoice";
  externalReference?: string;
  returnPath?: string;
  description: string;
  amount: number;
  currency: string;
  provider: "wipay";
  providerEnvironment: "sandbox" | "live";
  status: "pending" | "paid" | "failed" | "cancelled";
  createdByUserId?: string;
  providerTransactionId?: string;
  providerMessage?: string;
  createdAt: string;
  updatedAt: string;
  paidAt?: string;
}

interface BillingPaymentEvent {
  id: string;
  provider: "wipay";
  orderId?: string;
  transactionId?: string;
  status: string;
  verified: boolean;
  reason: string;
  amount?: number;
  currency?: string;
  message?: string;
  createdAt: string;
}

interface OwnerInvitation {
  id: string;
  organizationId: string;
  organizationName: string;
  organizationSlug: string;
  email: string;
  appIds: string[];
  tokenHash: string;
  status: "pending" | "accepted" | "revoked";
  expiresAt: string;
  createdAt: string;
  createdByUserId: string;
  acceptedAt?: string;
  acceptedUserId?: string;
  revokedAt?: string;
  revokedByUserId?: string;
}

interface TeamInvitation {
  id: string;
  organizationId: string;
  email: string;
  role: "manager" | "staff" | "viewer";
  permissions: string[];
  appIds: string[];
  tokenHash: string;
  status: "pending" | "accepted" | "revoked";
  expiresAt: string;
  createdAt: string;
  createdByUserId: string;
  acceptedAt?: string;
  acceptedUserId?: string;
  revokedAt?: string;
  revokedByUserId?: string;
}

interface AppTenantMapping {
  organizationId: string;
  appId: string;
  status: "pending" | "active" | "disabled";
  externalTenantId?: string;
  externalOwnerId?: string;
  createdAt: string;
  updatedAt: string;
}

interface PasswordResetRequest {
  id: string;
  userId: string;
  tokenHash: string;
  expiresAt: string;
  createdAt: string;
  usedAt?: string;
}

interface AuditEvent {
  id: string;
  organizationId?: string;
  actorUserId?: string;
  type: string;
  createdAt: string;
  details: Record<string, unknown>;
}

interface EcosystemApp {
  id: string;
  name: string;
  shortName: string;
  tagline: string;
  description: string;
  category: "finance" | "support" | "marketing" | "operations" | "analytics" | "team";
  status: "active" | "syncing" | "maintenance" | "beta";
  appUrl: string;
  githubRepo?: string;
  iconName: string;
  colorScheme: {
    primary: string;
    bgGradient: string;
    badgeBg: string;
    badgeText: string;
    border: string;
  };
  metrics?: {
    label: string;
    value: string;
    sublabel?: string;
  }[];
  features: string[];
  ssoSupported: boolean;
  isFlagship?: boolean;
  version?: string;
  lastSync?: string;
  ownerOrganizationId?: string;
}

interface AgentActionProposal {
  id: string; organizationId: string; createdByUserId: string;
  operation: string; targetSystem: string; summary: string; rationale: string;
  evidenceRef: string | null; idempotencyKey: string; fingerprint: string;
  status: "pending" | "approved" | "rejected"; revision: number;
  createdAt: string; expiresAt: string;
  decidedAt: string | null; decidedByUserId: string | null;
  decisionNote: string | null; executionStatus: "disabled";
}

interface AppStore {
  users: StoredUser[];
  workspace: WorkspaceProfile;
  ecosystemApps: EcosystemApp[];
  organizations: Organization[];
  memberships: Membership[];
  appEntitlements: AppEntitlement[];
  organizationPlans: OrganizationPlan[];
  trialReminderEvents: TrialReminderEvent[];
  billingOrders: BillingOrder[];
  billingPaymentEvents: BillingPaymentEvent[];
  ownerInvitations: OwnerInvitation[];
  teamInvitations: TeamInvitation[];
  appTenantMappings: AppTenantMapping[];
  passwordResetRequests: PasswordResetRequest[];
  auditEvents: AuditEvent[];
  agentActionProposals: AgentActionProposal[];
}

// Initial Seed Data
const defaultUsers: StoredUser[] = [];

const defaultWorkspace: WorkspaceProfile = {
  companyName: process.env.V79_HUB_ORG_NAME || "V79 Digital",
};

const academyPublicUrl = String(process.env.ACADEMY_PUBLIC_URL || "https://academy.v79sl.com").replace(/\/$/, "");

const defaultEcosystemApps: EcosystemApp[] = [
  {
    id: "app-ffpro",
    name: "Fire Finance Pro (FFPRO)",
    shortName: "FFPRO",
    tagline: "Strategic Personal & Enterprise Wealth Hub",
    description: "Cloud-synchronized personal & business finance engine. Manages cash flow forecasting, net worth, automated budgeting, and seamless register sync with V79 POS.",
    category: "finance",
    status: "active",
    appUrl: "https://ffpro.v79sl.com",
    githubRepo: "https://github.com/MrFixITslu/FFPRO",
    iconName: "Wallet",
    colorScheme: {
      primary: "from-amber-500 to-orange-600",
      bgGradient: "bg-gradient-to-br from-amber-500/10 via-orange-500/5 to-transparent",
      badgeBg: "bg-amber-500/15 border-amber-500/30",
      badgeText: "text-amber-400",
      border: "border-amber-500/30 hover:border-amber-500/60"
    },
    metrics: [
      { label: "Cash Inflow (MTD)", value: "$28,450 XCD", sublabel: "+12.4% vs last mo" },
      { label: "Budget Health", value: "94.2%", sublabel: "Optimal allocation" },
      { label: "Wealth Forecast", value: "+18.4% YoY", sublabel: "Next 12 months" }
    ],
    features: [
      "Real-time POS Cash Register Sync",
      "Cash Flow & Burn Forecasting",
      "Capital Expenditure & Depreciation",
      "Interactive Goal Planner",
      "V79 Unified SSO Authentication"
    ],
    ssoSupported: true,
    isFlagship: true,
    version: "v2.4.0",
    lastSync: new Date(Date.now() - 15 * 60 * 1000).toISOString()
  },
  {
    id: "app-tiquet",
    name: "V79 Tiquet (Service Desk & RMA)",
    shortName: "Tiquet",
    tagline: "Omnichannel Support, Service Desk & RMA Dispatch",
    description: "Enterprise ticketing system and field technician dispatch. Directly links work orders to inventory replacement parts, warranty SLAs, and POS client invoices.",
    category: "support",
    status: "active",
    appUrl: "https://tiquet.v79sl.com",
    githubRepo: "https://github.com/MrFixITslu/V79Tiquet",
    iconName: "Headphones",
    colorScheme: {
      primary: "from-blue-600 to-cyan-600",
      bgGradient: "bg-gradient-to-br from-blue-500/10 via-cyan-500/5 to-transparent",
      badgeBg: "bg-blue-500/15 border-blue-500/30",
      badgeText: "text-blue-400",
      border: "border-blue-500/30 hover:border-blue-500/60"
    },
    metrics: [
      { label: "Open Service Tickets", value: "4 Active", sublabel: "1 urgent RMA" },
      { label: "Avg SLA Resolution", value: "1.4 hrs", sublabel: "Target < 4 hrs" },
      { label: "SLA Adherence Rate", value: "98.5%", sublabel: "Last 30 days" }
    ],
    features: [
      "Direct Inventory Hardware/SKU Linking",
      "Field Dispatch & Technician Tracker",
      "Automated WhatsApp & Email SLA Alerts",
      "Hardware RMA & Warranty Tracking",
      "One-Click Ticket from POS Receipts"
    ],
    ssoSupported: true,
    isFlagship: true,
    version: "v3.1.2",
    lastSync: new Date(Date.now() - 5 * 60 * 1000).toISOString()
  },
  {
    id: "app-marketing",
    name: "V79 Marketing Suite",
    shortName: "Marketing",
    tagline: "Campaign Orchestration & Brand Asset Management",
    description: "Unified digital marketing and promotional campaign platform. Automates promo codes, social media broadcasting, customer WhatsApp campaigns, and ad attribution.",
    category: "marketing",
    status: "active",
    appUrl: "https://marketing.v79sl.com",
    githubRepo: "https://github.com/MrFixITslu/V79Marketing",
    iconName: "Megaphone",
    colorScheme: {
      primary: "from-pink-500 to-rose-600",
      bgGradient: "bg-gradient-to-br from-pink-500/10 via-rose-500/5 to-transparent",
      badgeBg: "bg-pink-500/15 border-pink-500/30",
      badgeText: "text-pink-400",
      border: "border-pink-500/30 hover:border-pink-500/60"
    },
    metrics: [
      { label: "Active Campaigns", value: "3 Live", sublabel: "Instagram + WhatsApp" },
      { label: "Audience Reach", value: "14.2k", sublabel: "St. Lucia & Caribbean" },
      { label: "Campaign ROI", value: "4.8x", sublabel: "$12.8k converted sales" }
    ],
    features: [
      "POS Coupon & Discount Generator",
      "Social Media Campaign Scheduler",
      "Product Launch Asset Library",
      "Conversion Attribution & Lead CRM",
      "Direct Inventory Item Promotion"
    ],
    ssoSupported: true,
    isFlagship: true,
    version: "v1.9.0",
    lastSync: new Date(Date.now() - 30 * 60 * 1000).toISOString()
  },
  {
    id: "app-academy",
    name: "V79 Academy (Learning & Capability)",
    shortName: "Academy",
    tagline: "Public Training & Capability Development",
    description: "Public training stays independent; businesses can link learner progress to their Hub.",
    category: "team",
    status: "active",
    appUrl: academyPublicUrl,
    githubRepo: "https://github.com/MrFixITslu/V79acaedmy",
    iconName: "GraduationCap",
    colorScheme: {
      primary: "from-blue-600 to-indigo-700",
      bgGradient: "bg-gradient-to-br from-blue-500/10 via-indigo-500/5 to-transparent",
      badgeBg: "bg-teal-500/15 border-teal-500/30",
      badgeText: "text-teal-400",
      border: "border-teal-500/30 hover:border-teal-500/60"
    },
    metrics: [
      { label: "Enrolled", value: "1", sublabel: "Active learner" },
      { label: "Progress", value: "0%", sublabel: "Initial onboarding" },
      { label: "Certificates", value: "0", sublabel: "In progress" }
    ],
    features: [
      "Public & Independent Training Modules",
      "Employee Hub Learner Sync",
      "Hardware Repair & POS Safety Certifications",
      "Customer Care Masterclasses",
      "Verifiable Digital Completion Badges"
    ],
    ssoSupported: true,
    isFlagship: true,
    version: "v1.0.8",
    lastSync: new Date().toISOString()
  },
  {
    id: "app-v79pos",
    name: "V79 POS (Point of Sale & Register)",
    shortName: "V79 POS",
    tagline: "High-Performance Omnichannel Point of Sale & Register Terminal",
    description: "Cloud-synchronized retail register checkout, hardware peripherals (receipt printers, barcode scanners, cash drawers), offline resiliency, and real-time inventory deduction.",
    category: "operations",
    status: "active",
    appUrl: "https://pos.v79sl.com",
    githubRepo: "https://github.com/MrFixITslu/v79pos",
    iconName: "CreditCard",
    colorScheme: {
      primary: "from-emerald-500 to-teal-600",
      bgGradient: "bg-gradient-to-br from-emerald-500/10 via-teal-500/5 to-transparent",
      badgeBg: "bg-emerald-500/15 border-emerald-500/30",
      badgeText: "text-emerald-400",
      border: "border-emerald-500/30 hover:border-emerald-500/60"
    },
    metrics: [
      { label: "Terminal URL", value: "pos.v79sl.com", sublabel: "Live production sync" },
      { label: "Hardware Link", value: "Ready", sublabel: "Thermal & Drawer kick" },
      { label: "Checkout Velocity", value: "< 1.2s", sublabel: "Sub-second scanning" }
    ],
    features: [
      "Barcode Scanner & Thermal Printer Ready",
      "Offline-Resilient Cart Queue",
      "Split Payments & Multi-Currency (XCD/USD)",
      "Customer Loyalty & Promo Vouchers",
      "Live Multi-Terminal Inventory Sync"
    ],
    ssoSupported: true,
    isFlagship: true,
    version: "v2.5.0",
    lastSync: new Date(Date.now() - 5 * 60 * 1000).toISOString()
  },
  {
    id: "app-lasertag",
    name: "CombatZone SLU",
    shortName: "CombatZone",
    tagline: "Mobile Combat Laser Tag Operations",
    description: "Bookings, event operations, payments, customer engagement and store activity for CombatZone SLU.",
    category: "operations",
    status: "active",
    appUrl: "https://combatzone.v79sl.com",
    githubRepo: "https://github.com/MrFixITslu/Lasertag",
    iconName: "Target",
    colorScheme: {
      primary: "from-orange-500 to-red-600",
      bgGradient: "bg-gradient-to-br from-orange-500/10 via-red-500/5 to-transparent",
      badgeBg: "bg-orange-500/15 border-orange-500/30",
      badgeText: "text-orange-400",
      border: "border-orange-500/30 hover:border-orange-500/60"
    },
    metrics: [],
    features: [
      "Booking & Event Operations",
      "Team Registration & Check-in",
      "Payments & Revenue Tracking",
      "Equipment & Incident Management",
      "CombatZone Store"
    ],
    ssoSupported: false,
    isFlagship: true,
    version: "v0.1.0",
    lastSync: new Date().toISOString()
  },
  {
    id: "app-analytics",
    name: "V79 Analytics & BI",
    shortName: "Analytics",
    tagline: "Cross-Ecosystem Telemetry & Executive Insights",
    description: "Deep business intelligence combining POS cash receipts, FFPRO finance books, support ticket costs from Tiquet, and advertising metrics into one executive cockpit.",
    category: "analytics",
    status: "active",
    appUrl: "https://analytics.vision79.lc",
    githubRepo: "https://github.com/MrFixITslu/V79Analytics",
    iconName: "LineChart",
    colorScheme: {
      primary: "from-violet-600 to-indigo-600",
      bgGradient: "bg-gradient-to-br from-violet-500/10 via-indigo-500/5 to-transparent",
      badgeBg: "bg-violet-500/15 border-violet-500/30",
      badgeText: "text-violet-400",
      border: "border-violet-500/30 hover:border-violet-500/60"
    },
    metrics: [
      { label: "Catalog Sales Velocity", value: "34.5 items/d", sublabel: "+8.2% week-on-week" },
      { label: "Blended Gross Margin", value: "33.8%", sublabel: "Target 30%" },
      { label: "Client Retention Rate", value: "88.4%", sublabel: "30-day recurring" }
    ],
    features: [
      "Cross-App Executive Telemetry",
      "Customer Lifetime Value (LTV) Cohorts",
      "Stockout Revenue Impact Calculator",
      "Daily Sales vs Expense Waterfall",
      "Executive PDF Reporting Export"
    ],
    ssoSupported: true,
    isFlagship: false,
    version: "v1.5.0",
    lastSync: new Date(Date.now() - 45 * 60 * 1000).toISOString()
  },
  {
    id: "app-lifehealth",
    name: "LifeHealth SLU (Team & Safety)",
    shortName: "LifeHealth",
    tagline: "Staff Rostering, Field Certifications & OSHA Safety",
    description: "Workforce health, scheduling, technician OSHA compliance, tool safety checks, and employee wellness portal for Vision 79 field staff.",
    category: "team",
    status: "active",
    appUrl: "https://lifehealth.vision79.lc",
    githubRepo: "https://github.com/MrFixITslu/LifeHealthSLU",
    iconName: "HeartPulse",
    colorScheme: {
      primary: "from-teal-500 to-emerald-600",
      bgGradient: "bg-gradient-to-br from-teal-500/10 via-emerald-500/5 to-transparent",
      badgeBg: "bg-teal-500/15 border-teal-500/30",
      badgeText: "text-teal-400",
      border: "border-teal-500/30 hover:border-teal-500/60"
    },
    metrics: [
      { label: "Active Field Roster", value: "8 Staff", sublabel: "All shifts staffed" },
      { label: "Safety Compliance", value: "100%", sublabel: "OSHA certifications current" },
      { label: "Wellness Index", value: "9.2/10", sublabel: "Team survey score" }
    ],
    features: [
      "Field Technician Shift Scheduler",
      "OSHA & Equipment Safety Log",
      "Driver & High-Voltage Certifications",
      "Team Wellness Check-ins",
      "Incident Reporting & Emergency Contacts"
    ],
    ssoSupported: true,
    isFlagship: false,
    version: "v1.2.0",
    lastSync: new Date(Date.now() - 60 * 60 * 1000).toISOString()
  }
];

// Custom catalog entries are outbound links, never Hub SSO clients.
function catalogHttpsUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" && url.hostname && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

function catalogText(value: unknown, maxLength: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed && trimmed.length <= maxLength ? trimmed : null;
}

// Store loader and writer
function normalizeEcosystemApps(value: unknown): EcosystemApp[] {
  let loadedApps: EcosystemApp[] = Array.isArray(value) && value.length > 0
    ? value as EcosystemApp[]
    : defaultEcosystemApps.map(app => ({ ...app }));

  const v79posApp = defaultEcosystemApps.find(app => app.id === "app-v79pos")!;
  const academyApp = defaultEcosystemApps.find(app => app.id === "app-academy")!;
  const laserTagApp = defaultEcosystemApps.find(app => app.id === "app-lasertag")!;

  loadedApps = loadedApps.map((app) => {
    if (app.id === "app-ffpro" || app.shortName === "FFPRO") return { ...app, appUrl: "https://ffpro.v79sl.com" };
    if (app.id === "app-tiquet" || app.shortName === "Tiquet") return { ...app, appUrl: "https://tiquet.v79sl.com" };
    if (app.id === "app-marketing" || app.shortName === "Marketing") return { ...app, appUrl: "https://marketing.v79sl.com" };
    if (app.id === "app-v79pos" || app.shortName === "V79 POS") return { ...app, appUrl: "https://pos.v79sl.com" };
    if (app.id === "app-academy" || app.shortName === "Academy") return { ...app, appUrl: academyPublicUrl };
    if (app.id === "app-lasertag" || app.shortName === "CombatZone") return { ...app, appUrl: "https://combatzone.v79sl.com" };
    if (app.id === "app-ordely" || app.shortName === "Ordely" || app.name?.toLowerCase().includes("ordely")) return { ...v79posApp };
    return app;
  });

  if (!loadedApps.some(app => app.id === "app-v79pos")) loadedApps.splice(3, 0, { ...v79posApp });
  if (!loadedApps.some(app => app.id === "app-academy")) {
    const posIndex = loadedApps.findIndex(app => app.id === "app-v79pos");
    loadedApps.splice(posIndex >= 0 ? posIndex : loadedApps.length, 0, { ...academyApp });
  }
  if (!loadedApps.some(app => app.id === "app-lasertag")) loadedApps.push({ ...laserTagApp });
  return loadedApps;
}

function normalizeLoadedStore(parsed: any): AppStore {
  const legacyCompanyName = typeof parsed?.settings?.companyName === "string"
    ? parsed.settings.companyName.trim()
    : "";
  const workspaceCompanyName = typeof parsed?.workspace?.companyName === "string"
    ? parsed.workspace.companyName.trim()
    : "";
  if ((parsed.organizations !== undefined && !Array.isArray(parsed.organizations)) ||
      (parsed.memberships !== undefined && !Array.isArray(parsed.memberships)) ||
      (parsed.appEntitlements !== undefined && !Array.isArray(parsed.appEntitlements)) ||
      (parsed.organizationPlans !== undefined && !Array.isArray(parsed.organizationPlans)) ||
      (parsed.trialReminderEvents !== undefined && !Array.isArray(parsed.trialReminderEvents)) ||
      (parsed.billingOrders !== undefined && !Array.isArray(parsed.billingOrders)) ||
      (parsed.billingPaymentEvents !== undefined && !Array.isArray(parsed.billingPaymentEvents)) ||
      (parsed.ownerInvitations !== undefined && !Array.isArray(parsed.ownerInvitations)) ||
      (parsed.teamInvitations !== undefined && !Array.isArray(parsed.teamInvitations)) ||
      (parsed.appTenantMappings !== undefined && !Array.isArray(parsed.appTenantMappings)) ||
      (parsed.passwordResetRequests !== undefined && !Array.isArray(parsed.passwordResetRequests)) ||
      (parsed.auditEvents !== undefined && !Array.isArray(parsed.auditEvents)) ||
      (parsed.agentActionProposals !== undefined && !Array.isArray(parsed.agentActionProposals))) {
    throw new Error("Organization records are malformed.");
  }
  return {
    users: Array.isArray(parsed.users) ? parsed.users : defaultUsers,
    workspace: { companyName: workspaceCompanyName || legacyCompanyName || defaultWorkspace.companyName },
    ecosystemApps: normalizeEcosystemApps(parsed.ecosystemApps),
    organizations: Array.isArray(parsed.organizations) ? parsed.organizations : [],
    memberships: Array.isArray(parsed.memberships) ? parsed.memberships : [],
    appEntitlements: Array.isArray(parsed.appEntitlements) ? parsed.appEntitlements : [],
    organizationPlans: Array.isArray(parsed.organizationPlans) ? parsed.organizationPlans : [],
    trialReminderEvents: Array.isArray(parsed.trialReminderEvents) ? parsed.trialReminderEvents : [],
    billingOrders: Array.isArray(parsed.billingOrders) ? parsed.billingOrders : [],
    billingPaymentEvents: Array.isArray(parsed.billingPaymentEvents) ? parsed.billingPaymentEvents : [],
    ownerInvitations: Array.isArray(parsed.ownerInvitations) ? parsed.ownerInvitations : [],
    teamInvitations: Array.isArray(parsed.teamInvitations) ? parsed.teamInvitations : [],
    appTenantMappings: Array.isArray(parsed.appTenantMappings) ? parsed.appTenantMappings : [],
    passwordResetRequests: Array.isArray(parsed.passwordResetRequests) ? parsed.passwordResetRequests : [],
    auditEvents: Array.isArray(parsed.auditEvents) ? parsed.auditEvents : [],
    agentActionProposals: Array.isArray(parsed.agentActionProposals) ? parsed.agentActionProposals : [],
  };
}

function initialStore(): AppStore {
  return {
    users: defaultUsers,
    workspace: { ...defaultWorkspace },
    ecosystemApps: defaultEcosystemApps.map(app => ({ ...app })),
    organizations: [], memberships: [], appEntitlements: [], organizationPlans: [], trialReminderEvents: [], billingOrders: [], billingPaymentEvents: [], ownerInvitations: [],
    teamInvitations: [], appTenantMappings: [], passwordResetRequests: [], auditEvents: [], agentActionProposals: [],
  };
}

const storePersistence = createHubStorePersistence({
  backend: process.env.V79_HUB_STORE_BACKEND || "json",
  storeFile: STORE_FILE,
  databaseUrl: process.env.DATABASE_URL || "",
} as any);

let store = await storePersistence.load(normalizeLoadedStore, initialStore) as AppStore;

async function saveStore(nextStore: AppStore): Promise<void> {
  await storePersistence.save(nextStore);
}

async function commitStore(nextStore: AppStore) {
  await saveStore(nextStore);
  store = nextStore;
}

function cloneStore() {
  return structuredClone(store) as AppStore;
}

const knownDemoPasswords = new Set(["password123", "manager123", "viewer123"]);
function hashPassword(password: string) {
  const salt = crypto.randomBytes(16).toString("hex");
  return `scrypt:${salt}:${crypto.scryptSync(password, salt, 64).toString("hex")}`;
}
function checkPassword(password: string, stored: string) {
  if (!stored.startsWith("scrypt:")) return false;
  const [, salt, digest] = stored.split(":");
  if (!salt || !/^[a-f0-9]{128}$/.test(digest || "")) return false;
  const actual = crypto.scryptSync(password, salt, 64);
  return crypto.timingSafeEqual(actual, Buffer.from(digest, "hex"));
}
const adminPassword = process.env.V79_HUB_ADMIN_PASSWORD || "";
const vision79OwnerEmail = "vision79slu@gmail.com";
if (process.env.NODE_ENV === "production" && (adminPassword.length < 16 || knownDemoPasswords.has(adminPassword))) {
  throw new Error("Set V79_HUB_ADMIN_PASSWORD to a unique password of at least 16 characters before production startup.");
}
if (process.env.NODE_ENV === "production" && normalizeEmail(process.env.V79_HUB_ADMIN_EMAIL) !== vision79OwnerEmail) {
  throw new Error("V79_HUB_ADMIN_EMAIL must remain vision79slu@gmail.com for platform administration.");
}
let usersChanged = false;
for (const user of store.users) {
  if (user.password.startsWith("scrypt:")) continue;
  user.password = hashPassword(knownDemoPasswords.has(user.password) ? crypto.randomBytes(32).toString("hex") : user.password);
  usersChanged = true;
}
if (adminPassword) {
  const username = process.env.V79_HUB_ADMIN_USERNAME || "admin";
  let admin = store.users.find(u => u.username.toLowerCase() === username.toLowerCase());
  if (!admin) {
    admin = { id: crypto.randomUUID(), username, password: "", fullName: "Hub Administrator", email: normalizeEmail(process.env.V79_HUB_ADMIN_EMAIL), role: "admin", permissions: ["overview","connections","team","security","billing","users"], createdAt: new Date().toISOString() };
    store.users.push(admin);
  }
  // Only replace a password when initially bootstrapping; subsequent edits in
  // the team UI must survive container recreation.
  if (!admin.password || (usersChanged && admin.username === "admin" && admin.id === "u-1")) {
    admin.password = hashPassword(adminPassword);
    usersChanged = true;
  }
  admin.role = "admin";
  const configuredOwnerEmail = normalizeEmail(process.env.V79_HUB_ADMIN_EMAIL);
  if (configuredOwnerEmail && admin.email !== configuredOwnerEmail) {
    admin.email = configuredOwnerEmail;
    usersChanged = true;
  }
}
if (usersChanged) await saveStore(store);

// Restart-safe auth sessions. Only SHA-256 token hashes are persisted; usable
// browser session tokens never touch disk.
type HubSession = {
  userId: string;
  organizationId: string;
  username: string;
  role: string;
  expiresAt: number;
};

function sessionKey(token: string) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

function loadPersistedSessions() {
  const loaded = new Map<string, HubSession>();
  if (!fs.existsSync(SESSION_FILE)) return loaded;
  try {
    const parsed = JSON.parse(fs.readFileSync(SESSION_FILE, "utf8"));
    const rows = Array.isArray(parsed?.sessions) ? parsed.sessions : [];
    for (const row of rows) {
      if (
        !row ||
        !/^[a-f0-9]{64}$/.test(String(row.tokenHash || "")) ||
        typeof row.userId !== "string" ||
        typeof row.organizationId !== "string" ||
        typeof row.username !== "string" ||
        typeof row.role !== "string" ||
        !Number.isFinite(row.expiresAt) ||
        row.expiresAt <= Date.now()
      ) continue;
      loaded.set(row.tokenHash, {
        userId: row.userId,
        organizationId: row.organizationId,
        username: row.username,
        role: row.role,
        expiresAt: row.expiresAt,
      });
    }
  } catch (error) {
    console.warn("Hub session store could not be read; starting with no active sessions.");
  }
  return loaded;
}

const sessions = loadPersistedSessions();
const loginAttempts = new Map<string, { count: number; until: number }>();
const inviteAttempts = new Map<string, { count: number; until: number }>();
const recoveryAttempts = new Map<string, { count: number; until: number }>();

type PendingMfaChallenge = {
  id: string;
  userId: string;
  organizationId: string;
  mode: "setup" | "verify";
  secret?: string;
  expiresAt: number;
  attempts: number;
};
const mfaChallenges = new Map<string, PendingMfaChallenge>();
const hubSecurityKey = String(process.env.V79_HUB_SECURITY_KEY || process.env.V79_PLATFORM_SHARED_SECRET || "").trim();

function pruneMfaChallenges() {
  const now = Date.now();
  for (const [id, challenge] of mfaChallenges) if (challenge.expiresAt <= now) mfaChallenges.delete(id);
  while (mfaChallenges.size > 2_000) {
    const oldest = mfaChallenges.keys().next().value;
    if (oldest === undefined) break;
    mfaChallenges.delete(oldest);
  }
}

function createMfaChallenge(userId: string, organizationId: string, mode: "setup" | "verify", secret?: string) {
  pruneMfaChallenges();
  const id = createOpaqueToken(24);
  const challenge: PendingMfaChallenge = { id, userId, organizationId, mode, secret, expiresAt: Date.now() + 5 * 60_000, attempts: 0 };
  mfaChallenges.set(id, challenge);
  return challenge;
}

function persistSessions() {
  const temp = `${SESSION_FILE}.${process.pid}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  const payload = {
    version: 1,
    sessions: [...sessions.entries()].map(([tokenHash, session]) => ({ tokenHash, ...session })),
  };
  fs.writeFileSync(temp, JSON.stringify(payload), { mode: 0o600 });
  fs.renameSync(temp, SESSION_FILE);
  fs.chmodSync(SESSION_FILE, 0o600);
}

function deleteSessionKey(key: string) {
  if (!sessions.delete(key)) return false;
  persistSessions();
  return true;
}

function deleteSessionToken(token: string) {
  return token ? deleteSessionKey(sessionKey(token)) : false;
}

function deleteSessionsWhere(predicate: (session: HubSession) => boolean) {
  let changed = false;
  for (const [key, session] of sessions) {
    if (!predicate(session)) continue;
    sessions.delete(key);
    changed = true;
  }
  if (changed) persistSessions();
  return changed;
}

function storeSessionToken(token: string, session: HubSession) {
  if (sessions.size >= 5_000) {
    const oldest = sessions.keys().next().value;
    if (oldest !== undefined) sessions.delete(oldest);
  }
  sessions.set(sessionKey(token), session);
  persistSessions();
}

function sessionFromToken(token: string) {
  if (!token) return null;
  const key = sessionKey(token);
  const session = sessions.get(key);
  if (!session || session.expiresAt < Date.now()) {
    if (session) deleteSessionKey(key);
    return null;
  }
  const user = store.users.find(u => u.id === session.userId);
  if (!user) {
    deleteSessionKey(key);
    return null;
  }
  const membership = activeMembership(store, user.id, session.organizationId);
  if (!membership) {
    deleteSessionKey(key);
    return null;
  }
  session.role = sessionRole(membership)!;
  return session;
}
function cookieToken(header = "") {
  return header.split(";").map(part => part.trim()).find(part => part.startsWith("v79_hub_session="))?.slice(16) || "";
}
function sessionCookie(value: string, maxAge: number) {
  return `v79_hub_session=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${process.env.NODE_ENV === "production" ? "; Secure" : ""}`;
}

const posSecret = process.env.V79_PLATFORM_SHARED_SECRET || "";
const posServiceSecret = process.env.V79_POS_PLATFORM_SHARED_SECRET || posSecret;
const posServiceUrl = process.env.POS_BASE_URL || "http://v79-commerce-api:8080";
const posPublicUrl = process.env.POS_PUBLIC_URL || "https://pos.v79sl.com";
const posIdentityPath = path.join(DATA_DIR, "pos-identity.json");
const posIdentity = (() => {
  if (fs.existsSync(posIdentityPath)) return JSON.parse(fs.readFileSync(posIdentityPath, "utf8")) as { organizationId: string; ownerUserId: string };
  const owner = store.users.find(u => u.username === (process.env.V79_HUB_ADMIN_USERNAME || "admin") && u.role === "admin");
  const identity = { organizationId: process.env.V79_POS_ORG_ID || crypto.randomUUID(), ownerUserId: owner?.id || "" };
  fs.writeFileSync(posIdentityPath, JSON.stringify(identity), { mode: 0o600, flag: "wx" });
  return identity;
})();
const organizationMigration = posIdentity.ownerUserId
  ? migrateLegacyOrganization(store, posIdentity.organizationId, posIdentity.ownerUserId)
  : null;
if (process.env.NODE_ENV === "production" && !organizationMigration) throw new Error("The Hub owner identity is missing.");
if (process.env.V79_REQUIRE_ADMIN_MFA === "1") {
  const platformOwner = store.users.find(user => user.id === posIdentity.ownerUserId);
  if (platformOwner && !platformOwner.mfaEnabled) {
    deleteSessionsWhere(session => session.userId === platformOwner.id);
  }
}

if (organizationMigration?.changed) {
  const backupPath = path.join(DATA_DIR, "v79_store_pre_organizations.json");
  if (!fs.existsSync(backupPath)) {
    fs.copyFileSync(STORE_FILE, backupPath, fs.constants.COPYFILE_EXCL);
    fs.chmodSync(backupPath, 0o600);
  }
  store.organizations = organizationMigration.organizations;
  store.memberships = organizationMigration.memberships;
  await saveStore(store);
}

if (!Array.isArray(store.appEntitlements)) store.appEntitlements = [];
const ownerEntitlements = store.appEntitlements.filter(entry => entry.organizationId === posIdentity.organizationId);
if (ownerEntitlements.length === 0) {
  const now = new Date().toISOString();
  store.appEntitlements.push(...store.ecosystemApps.map(app => ({
    organizationId: posIdentity.organizationId,
    appId: app.id,
    enabled: true,
    createdAt: now,
  })));
  await saveStore(store);
}
for (const appId of ["app-lasertag"]) {
  if (!store.appEntitlements.some(entry => entry.organizationId === posIdentity.organizationId && entry.appId === appId)) {
    store.appEntitlements.push({ organizationId: posIdentity.organizationId, appId, enabled: true, createdAt: new Date().toISOString() });
    await saveStore(store);
  }
}

let legacyCustomOwnershipChanged = false;
for (const app of store.ecosystemApps) {
  if (!app.id.startsWith("app-custom-") || app.ownerOrganizationId) continue;
  const entitledOrganizations = [...new Set(store.appEntitlements
    .filter(entry => entry.appId === app.id && entry.enabled)
    .map(entry => entry.organizationId))];
  if (entitledOrganizations.length === 1 && entitledOrganizations[0] === posIdentity.organizationId) {
    app.ownerOrganizationId = posIdentity.organizationId;
    legacyCustomOwnershipChanged = true;
  }
}
if (legacyCustomOwnershipChanged) await saveStore(store);

const posKeyPath = path.join(DATA_DIR, "pos-signing-ed25519.pem");
if (!fs.existsSync(posKeyPath)) {
  const pair = crypto.generateKeyPairSync("ed25519");
  fs.writeFileSync(posKeyPath, pair.privateKey.export({ format: "pem", type: "pkcs8" }), { mode: 0o600, flag: "wx" });
}
const posPrivateKey = crypto.createPrivateKey(fs.readFileSync(posKeyPath));
const posPublicKey = crypto.createPublicKey(posPrivateKey);
const posKeyId = crypto.createHash("sha256").update(posPublicKey.export({ format: "der", type: "spki" })).digest("hex").slice(0, 20);
type LaunchProduct = "pos" | "ffpro" | "tiquet" | "marketing";
const launchTickets = new Map<string, { userId: string; tenantId: string; product: LaunchProduct; expiresAt: number }>();
function pruneAuthState(now = Date.now()) {
  let sessionsChanged = false;
  for (const [key, session] of sessions) {
    if (session.expiresAt > now) continue;
    sessions.delete(key);
    sessionsChanged = true;
  }
  if (sessionsChanged) persistSessions();
  for (const [key, attempt] of loginAttempts) if (attempt.until <= now) loginAttempts.delete(key);
  for (const [key, attempt] of inviteAttempts) if (attempt.until <= now) inviteAttempts.delete(key);
  for (const [ticket, entry] of launchTickets) if (entry.expiresAt <= now) launchTickets.delete(ticket);
}
const authCleanup = setInterval(pruneAuthState, 60_000);
authCleanup.unref();
const managedLaunch = {
  ffpro: { serviceId: "v79-ffpro", secretEnv: "V79_FFPRO_LAUNCH_SECRET", publicEnv: "FFPRO_PUBLIC_URL", defaultUrl: "https://ffpro.v79sl.com" },
  tiquet: { serviceId: "v79-tiquet", secretEnv: "V79_TIQUET_LAUNCH_SECRET", publicEnv: "TIQUET_PUBLIC_URL", defaultUrl: "https://tiquet.v79sl.com" },
  marketing: { serviceId: "v79-marketing", secretEnv: "V79_MARKETING_LAUNCH_SECRET", publicEnv: "MARKETING_PUBLIC_URL", defaultUrl: "https://marketing.v79sl.com" },
} as const;
function managedProduct(source: string): keyof typeof managedLaunch | null {
  return (Object.keys(managedLaunch) as (keyof typeof managedLaunch)[]).find(product => managedLaunch[product].serviceId === source) || null;
}
function launchTicket(userId: string, tenantId: string, product: LaunchProduct) {
  for (const [key, entry] of launchTickets) if (entry.expiresAt < Date.now() || (entry.userId === userId && entry.product === product)) launchTickets.delete(key);
  const ticket = crypto.randomBytes(32).toString("base64url");
  launchTickets.set(crypto.createHash("sha256").update(ticket).digest("hex"), { userId, tenantId, product, expiresAt: Date.now() + 120000 });
  return ticket;
}
function posUserId(userId: string, organizationId: string) {
  if (process.env.V79_POS_OWNER_USER_ID && userId === posIdentity.ownerUserId && organizationId === posIdentity.organizationId) {
    return process.env.V79_POS_OWNER_USER_ID;
  }
  const hex = crypto.createHash("sha256").update(`${organizationId}:${userId}`).digest("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}
const posTeamRoleMap = {
  manager: "MANAGER",
  staff: "CASHIER",
  viewer: "AUDITOR",
} as const;

const ffproTeamRoles = new Set(["manager", "staff", "viewer"]);

function ffproTeamRole(role: string | undefined) {
  return role && ffproTeamRoles.has(role) ? role as "manager" | "staff" | "viewer" : null;
}

const tiquetTeamPermissions = {
  manager: ["dashboard", "jobs", "clients", "invoices", "files", "new-request"],
  staff: ["dashboard", "jobs", "clients", "files", "new-request"],
  viewer: ["dashboard"],
} as const;

const marketingTeamRoleMap = {
  manager: "MARKETING_MANAGER",
  staff: "MARKETING_STAFF",
  viewer: "MARKETING_VIEWER",
} as const;

function posTeamRole(role: string | undefined) {
  return role && role in posTeamRoleMap ? role as keyof typeof posTeamRoleMap : null;
}

function tiquetTeamRole(role: string | undefined) {
  return role && role in tiquetTeamPermissions ? role as keyof typeof tiquetTeamPermissions : null;
}

function marketingTeamRole(role: string | undefined) {
  return role && role in marketingTeamRoleMap ? role as keyof typeof marketingTeamRoleMap : null;
}

function posJwt(userId: string, tenantId: string) {
  const now = Math.floor(Date.now() / 1000);
  const header = Buffer.from(JSON.stringify({ alg: "EdDSA", typ: "JWT", kid: posKeyId })).toString("base64url");
  const claims = Buffer.from(JSON.stringify({ iss: new URL(process.env.APP_URL || "https://hub.v79sl.com").origin, aud: "v79-commerce", sub: userId, tenant_id: tenantId, iat: now, nbf: now, exp: now + 300 })).toString("base64url");
  const input = `${header}.${claims}`;
  return `${input}.${crypto.sign(null, Buffer.from(input), posPrivateKey).toString("base64url")}`;
}

async function provisionPosWorkspace(organization: Organization, hubUserId: string, requireReturnedIdentity = true) {
  if (posServiceSecret.length < 32) {
    return { ok: false as const, status: 503, error: "POS shared secret is not configured" };
  }
  const ownerUserId = posUserId(hubUserId, organization.id);
  const pathname = "/api/platform/provision";
  const body = JSON.stringify({
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    user: { id: ownerUserId },
    role: "owner",
  });
  const timestamp = String(Date.now());
  try {
    const response = await fetch(new URL(pathname, posServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posServiceSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "POS workspace provisioning failed", upstreamStatus: response.status };
    }
    const returnedIdentityMismatch =
      (payload.organizationId !== undefined && payload.organizationId !== organization.id) ||
      (payload.ownerUserId !== undefined && payload.ownerUserId !== ownerUserId);
    const returnedIdentityMissing = payload.organizationId === undefined || payload.ownerUserId === undefined;
    if (payload.provisioned !== true || returnedIdentityMismatch || (requireReturnedIdentity && returnedIdentityMissing)) {
      return { ok: false as const, status: 502, error: "POS returned a mismatched tenant identity" };
    }
    return { ok: true as const, organizationId: organization.id, ownerUserId };
  } catch {
    return { ok: false as const, status: 503, error: "POS service is unavailable" };
  }
}

async function provisionPosTeamMember(organization: Organization, hubUserId: string, role: keyof typeof posTeamRoleMap) {
  if (posServiceSecret.length < 32) {
    return { ok: false as const, status: 503, error: "POS shared secret is not configured" };
  }
  const userId = posUserId(hubUserId, organization.id);
  const pathname = "/api/platform/members/provision";
  const body = JSON.stringify({
    organizationId: organization.id,
    user: { id: userId },
    role,
  });
  const timestamp = String(Date.now());
  try {
    const response = await fetch(new URL(pathname, posServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posServiceSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "POS team member provisioning failed", upstreamStatus: response.status };
    }
    const expectedRoleKey = posTeamRoleMap[role];
    if (
      payload.provisioned !== true ||
      payload.organizationId !== organization.id ||
      payload.userId !== userId ||
      payload.roleKey !== expectedRoleKey ||
      !Array.isArray(payload.locationIds) ||
      payload.locationIds.length !== 1 ||
      typeof payload.locationIds[0] !== "string"
    ) {
      return { ok: false as const, status: 502, error: "POS returned a mismatched team member identity" };
    }
    return { ok: true as const, organizationId: organization.id, userId, roleKey: expectedRoleKey, locationId: payload.locationIds[0] as string };
  } catch {
    return { ok: false as const, status: 503, error: "POS service is unavailable" };
  }
}

async function deprovisionPosTeamMember(organizationId: string, hubUserId: string) {
  if (posServiceSecret.length < 32) {
    return { ok: false as const, status: 503, error: "POS shared secret is not configured" };
  }
  const userId = posUserId(hubUserId, organizationId);
  const pathname = "/api/platform/members/deprovision";
  const body = JSON.stringify({ organizationId, user: { id: userId } });
  const timestamp = String(Date.now());
  try {
    const response = await fetch(new URL(pathname, posServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posServiceSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "POS team member deprovisioning failed", upstreamStatus: response.status };
    }
    if (
      payload.deprovisioned !== true ||
      payload.organizationId !== organizationId ||
      payload.userId !== userId
    ) {
      return { ok: false as const, status: 502, error: "POS returned a mismatched team deprovisioning identity" };
    }
    return { ok: true as const, organizationId, userId };
  } catch {
    return { ok: false as const, status: 503, error: "POS service is unavailable" };
  }
}

async function provisionFfproWorkspace(organization: Organization, owner: StoredUser) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const email = String(owner.email || owner.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false as const, status: 409, error: "FFPRO owner email is not valid" };
  }
  const ownerHubUserId = posUserId(owner.id, organization.id);
  const pathname = "/api/platform/provision";
  const body = JSON.stringify({
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    user: { id: ownerHubUserId, email, name: owner.fullName || email },
    role: "owner",
  });
  const timestamp = String(Date.now());
  const ffproServiceUrl = process.env.FFPRO_INTERNAL_URL || "http://fire-finance-app:3010";
  try {
    const response = await fetch(new URL(pathname, ffproServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "FFPRO workspace provisioning failed", upstreamStatus: response.status };
    }
    if (
      payload.provisioned !== true ||
      payload.organizationId !== organization.id ||
      payload.ownerHubUserId !== ownerHubUserId ||
      typeof payload.financeUserId !== "string" ||
      !payload.financeUserId
    ) {
      return { ok: false as const, status: 502, error: "FFPRO returned a mismatched tenant identity" };
    }
    return { ok: true as const, organizationId: organization.id, ownerHubUserId, financeUserId: payload.financeUserId as string };
  } catch {
    return { ok: false as const, status: 503, error: "FFPRO service is unavailable" };
  }
}

async function provisionTiquetWorkspace(organization: Organization, owner: StoredUser) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const email = String(owner.email || owner.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false as const, status: 409, error: "Tiquet owner email is not valid" };
  }
  const ownerHubUserId = posUserId(owner.id, organization.id);
  const pathname = "/api/platform/provision";
  const body = JSON.stringify({
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    user: { id: ownerHubUserId, email, name: owner.fullName || email },
    role: "owner",
    plan: "hub",
  });
  const timestamp = String(Date.now());
  const tiquetServiceUrl = process.env.TIQUET_INTERNAL_URL || "http://v79-tiquet-manager:3000";
  try {
    const response = await fetch(new URL(pathname, tiquetServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "Tiquet workspace provisioning failed", upstreamStatus: response.status };
    }
    if (
      payload.provisioned !== true ||
      payload.organizationId !== organization.id ||
      payload.ownerHubUserId !== ownerHubUserId ||
      typeof payload.accountId !== "string" ||
      !payload.accountId ||
      typeof payload.userId !== "string" ||
      !payload.userId
    ) {
      return { ok: false as const, status: 502, error: "Tiquet returned a mismatched tenant identity" };
    }
    return {
      ok: true as const,
      organizationId: organization.id,
      ownerHubUserId,
      accountId: payload.accountId as string,
      userId: payload.userId as string,
    };
  } catch {
    return { ok: false as const, status: 503, error: "Tiquet service is unavailable" };
  }
}

async function provisionTiquetTeamMember(
  organization: Organization,
  member: StoredUser,
  role: keyof typeof tiquetTeamPermissions,
) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const email = String(member.email || member.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false as const, status: 409, error: "Tiquet team member email is not valid" };
  }
  const hubUserId = posUserId(member.id, organization.id);
  const pathname = "/api/platform/members/provision";
  const body = JSON.stringify({
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    user: { id: hubUserId, email, name: member.fullName || email },
    role,
    plan: "hub",
  });
  const timestamp = String(Date.now());
  const tiquetServiceUrl = process.env.TIQUET_INTERNAL_URL || "http://v79-tiquet-manager:3000";
  try {
    const response = await fetch(new URL(pathname, tiquetServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "Tiquet team member provisioning failed", upstreamStatus: response.status };
    }
    const expectedPermissions = [...tiquetTeamPermissions[role]];
    const returnedPermissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    if (
      payload.provisioned !== true ||
      payload.organizationId !== organization.id ||
      payload.hubUserId !== hubUserId ||
      typeof payload.accountId !== "string" ||
      !payload.accountId ||
      typeof payload.userId !== "string" ||
      !payload.userId ||
      payload.localRole !== "Member" ||
      returnedPermissions.length !== expectedPermissions.length ||
      !expectedPermissions.every(permission => returnedPermissions.includes(permission))
    ) {
      return { ok: false as const, status: 502, error: "Tiquet returned a mismatched team identity" };
    }
    return {
      ok: true as const,
      organizationId: organization.id,
      hubUserId,
      accountId: payload.accountId as string,
      userId: payload.userId as string,
      permissions: expectedPermissions,
    };
  } catch {
    return { ok: false as const, status: 503, error: "Tiquet service is unavailable" };
  }
}

async function deprovisionTiquetTeamMember(organizationId: string, hubUserId: string) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const scopedHubUserId = posUserId(hubUserId, organizationId);
  const pathname = "/api/platform/members/deprovision";
  const body = JSON.stringify({ organizationId, user: { id: scopedHubUserId } });
  const timestamp = String(Date.now());
  const tiquetServiceUrl = process.env.TIQUET_INTERNAL_URL || "http://v79-tiquet-manager:3000";
  try {
    const response = await fetch(new URL(pathname, tiquetServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posSecret }),
      },
      body,
      signal: AbortSignal.timeout(5000),
    });
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "Tiquet team member deprovisioning failed", upstreamStatus: response.status };
    }
    if (
      payload.deprovisioned !== true ||
      payload.organizationId !== organizationId ||
      payload.hubUserId !== scopedHubUserId
    ) {
      return { ok: false as const, status: 502, error: "Tiquet returned a mismatched team deprovisioning identity" };
    }
    return { ok: true as const, organizationId, hubUserId: scopedHubUserId };
  } catch {
    return { ok: false as const, status: 503, error: "Tiquet service is unavailable" };
  }
}

async function fetchMarketingPlatform(pathname: string, body: string) {
  const marketingServiceUrl = process.env.MARKETING_INTERNAL_URL || "http://v79marketing-app:3070";
  return retryTransient(async () => {
    const timestamp = String(Date.now());
    return fetch(new URL(pathname, marketingServiceUrl), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signPlatformRequest({ method: "POST", pathname, timestamp, body, secret: posSecret }),
      },
      body,
      signal: AbortSignal.timeout(3000),
    });
  }, { attempts: 2, delayMs: 150 });
}

async function provisionMarketingWorkspace(organization: Organization, owner: StoredUser) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const email = String(owner.email || owner.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false as const, status: 409, error: "Marketing owner email is not valid" };
  }
  const ownerHubUserId = posUserId(owner.id, organization.id);
  const pathname = "/api/platform/provision";
  const body = JSON.stringify({
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    user: { id: ownerHubUserId, email, name: owner.fullName || email },
    role: "owner",
    plan: "hub",
  });
  try {
    const response = await fetchMarketingPlatform(pathname, body);
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "Marketing workspace provisioning failed", upstreamStatus: response.status };
    }
    if (
      payload.provisioned !== true ||
      payload.organizationId !== organization.id ||
      payload.ownerHubUserId !== ownerHubUserId ||
      typeof payload.businessId !== "string" ||
      !payload.businessId ||
      typeof payload.userId !== "string" ||
      !payload.userId
    ) {
      return { ok: false as const, status: 502, error: "Marketing returned a mismatched tenant identity" };
    }
    return {
      ok: true as const,
      organizationId: organization.id,
      ownerHubUserId,
      businessId: payload.businessId as string,
      userId: payload.userId as string,
    };
  } catch {
    return { ok: false as const, status: 503, error: "Marketing service is unavailable" };
  }
}

async function provisionMarketingTeamMember(
  organization: Organization,
  member: StoredUser,
  role: keyof typeof marketingTeamRoleMap,
) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const email = String(member.email || member.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false as const, status: 409, error: "Marketing team member email is not valid" };
  }
  const hubUserId = posUserId(member.id, organization.id);
  const pathname = "/api/platform/members/provision";
  const body = JSON.stringify({
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    user: { id: hubUserId, email, name: member.fullName || email },
    role,
    plan: "hub",
  });
  try {
    const response = await fetchMarketingPlatform(pathname, body);
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "Marketing team member provisioning failed", upstreamStatus: response.status };
    }
    const expectedLocalRole = marketingTeamRoleMap[role];
    if (
      payload.provisioned !== true ||
      payload.organizationId !== organization.id ||
      payload.hubUserId !== hubUserId ||
      typeof payload.businessId !== "string" ||
      !payload.businessId ||
      typeof payload.userId !== "string" ||
      !payload.userId ||
      payload.localRole !== expectedLocalRole
    ) {
      return { ok: false as const, status: 502, error: "Marketing returned a mismatched team identity" };
    }
    return {
      ok: true as const,
      organizationId: organization.id,
      hubUserId,
      businessId: payload.businessId as string,
      userId: payload.userId as string,
      localRole: expectedLocalRole,
    };
  } catch {
    return { ok: false as const, status: 503, error: "Marketing service is unavailable" };
  }
}

async function deprovisionMarketingTeamMember(organizationId: string, hubUserId: string) {
  if (posSecret.length < 32) {
    return { ok: false as const, status: 503, error: "Platform shared secret is not configured" };
  }
  const scopedHubUserId = posUserId(hubUserId, organizationId);
  const mapping = marketingTenantMapping(store, organizationId);
  if (mapping?.status !== "active" || !mapping.externalTenantId) {
    return { ok: false as const, status: 409, error: "Marketing workspace mapping is not active" };
  }
  const pathname = "/api/platform/members/deprovision";
  const body = JSON.stringify({ organizationId, user: { id: scopedHubUserId } });
  try {
    const response = await fetchMarketingPlatform(pathname, body);
    const payload = await response.json().catch(() => ({})) as any;
    if (!response.ok) {
      return { ok: false as const, status: 502, error: "Marketing team member deprovisioning failed", upstreamStatus: response.status };
    }
    if (
      payload.deprovisioned !== true ||
      payload.organizationId !== organizationId ||
      payload.hubUserId !== scopedHubUserId ||
      payload.businessId !== mapping.externalTenantId
    ) {
      return { ok: false as const, status: 502, error: "Marketing returned a mismatched team deprovisioning identity" };
    }
    return { ok: true as const, organizationId, hubUserId: scopedHubUserId, businessId: payload.businessId as string };
  } catch {
    return { ok: false as const, status: 503, error: "Marketing service is unavailable" };
  }
}

app.get("/.well-known/jwks.json", (_req, res) => {
  res.setHeader("Cache-Control", "public, max-age=300");
  res.json({ keys: [{ ...posPublicKey.export({ format: "jwk" }), kid: posKeyId, alg: "EdDSA", use: "sig" }] });
});
app.get("/api/health", (_req, res) => res.json({ status: "ok" }));
// Read-only, authenticated entitlement revalidation for existing product sessions.
// The downstream app MUST fail closed if this check fails or becomes unreachable.
// HMAC service IDs are bound to the product so one app cannot query another.
app.post("/api/platform/entitlement/check", (req, res) => {
  const pathname = "/api/platform/entitlement/check";
  const source = req.get("x-v79-service-id") || "";
  const product = source === "v79-pos" ? "pos" : managedProduct(source);
  const secret = product === "pos"
    ? posServiceSecret
    : product ? process.env[managedLaunch[product].secretEnv] || "" : "";
  const body = (req as any).rawBody?.toString("utf8") || "";
  if (!product || !verifyPlatformRequest({
    method: "POST", pathname, body,
    timestamp: req.get("x-v79-timestamp") || "",
    signature: req.get("x-v79-signature") || "", secret,
  })) return res.status(401).json({ error: "Invalid service signature" });

  const requestedProduct = String(req.body?.product || "");
  const organizationId = String(req.body?.organizationId || "");
  const scopedUserId = String(req.body?.scopedUserId || "");
  if (requestedProduct !== product || !ENTITLEMENT_PRODUCTS[requestedProduct as keyof typeof ENTITLEMENT_PRODUCTS] ||
      organizationId.length < 5 || organizationId.length > 180 ||
      scopedUserId.length < 5 || scopedUserId.length > 180) {
    return res.status(400).json({ error: "Invalid entitlement identity" });
  }

  const readyByProduct = {
    pos: posTenantLaunchReady, ffpro: ffproTenantLaunchReady,
    tiquet: tiquetTenantLaunchReady, marketing: marketingTenantLaunchReady,
  };
  const roleEligible = (selected: string, role: string) => role === "owner" || Boolean(
    selected === "pos" ? posTeamRole(role) :
    selected === "ffpro" ? ffproTeamRole(role) :
    selected === "tiquet" ? tiquetTeamRole(role) : marketingTeamRole(role)
  );
  const result = validateProductEntitlement(store, {
    product, organizationId, scopedUserId, ownerOrganizationId: posIdentity.organizationId,
    resolveScopedUserId: posUserId,
    memberCanAccessApp: membershipCanAccessApp,
    roleEligible,
    tenantReady: (selected: string, org: string, owner: string) =>
      readyByProduct[selected as keyof typeof readyByProduct](store, org, owner),
  });
  res.setHeader("Cache-Control", "no-store");
  res.json(result);
});

app.post("/api/platform/session/consume", (req, res) => {
  const body = (req as any).rawBody?.toString("utf8") || "";
  const source = req.get("x-v79-service-id") || "";
  const managed = managedProduct(source);
  const expectedProduct: LaunchProduct | null = source === "v79-pos" ? "pos" : managed;
  const secret = expectedProduct === "pos" ? posServiceSecret : managed ? process.env[managedLaunch[managed].secretEnv] || "" : "";
  if (!expectedProduct || !verifyPlatformRequest({ method: "POST", pathname: "/api/platform/session/consume", timestamp: req.get("x-v79-timestamp") || "", signature: req.get("x-v79-signature") || "", body, secret })) return res.status(401).json({ error: "Invalid service signature" });
  const { product, ticket } = req.body || {};
  if (product !== expectedProduct || typeof ticket !== "string" || !/^[A-Za-z0-9_-]{32,180}$/.test(ticket)) return res.status(400).json({ error: "Invalid ticket" });
  const ticketHash = crypto.createHash("sha256").update(ticket).digest("hex");
  const entry = launchTickets.get(ticketHash);
  const posTicketMembership = entry
    ? activeMembership(store, entry.userId, entry.tenantId)
    : null;
  const validPosTicket = product === "pos" && Boolean(
    entry &&
    entry.product === "pos" &&
    entry.expiresAt >= Date.now() &&
    (posTicketMembership?.role === "owner" || posTeamRole(posTicketMembership?.role)) &&
    membershipCanAccessApp(posTicketMembership, "app-v79pos") &&
    organizationCanAccessApp(store, entry.tenantId, "app-v79pos", posIdentity.organizationId) &&
    posTenantLaunchReady(store, entry.tenantId, posIdentity.organizationId)
  );
  const ffproTicketMembership = entry
    ? activeMembership(store, entry.userId, entry.tenantId)
    : null;
  const validFfproTicket = product === "ffpro" && Boolean(
    entry &&
    entry.product === "ffpro" &&
    entry.expiresAt >= Date.now() &&
    (ffproTicketMembership?.role === "owner" || ffproTeamRole(ffproTicketMembership?.role)) &&
    membershipCanAccessApp(ffproTicketMembership, "app-ffpro") &&
    organizationCanAccessApp(store, entry.tenantId, "app-ffpro", posIdentity.organizationId) &&
    ffproTenantLaunchReady(store, entry.tenantId, posIdentity.organizationId)
  );
  const tiquetTicketMembership = entry
    ? activeMembership(store, entry.userId, entry.tenantId)
    : null;
  const validTiquetTicket = product === "tiquet" && Boolean(
    entry &&
    entry.product === "tiquet" &&
    entry.expiresAt >= Date.now() &&
    (tiquetTicketMembership?.role === "owner" || tiquetTeamRole(tiquetTicketMembership?.role)) &&
    membershipCanAccessApp(tiquetTicketMembership, "app-tiquet") &&
    organizationCanAccessApp(store, entry.tenantId, "app-tiquet", posIdentity.organizationId) &&
    tiquetTenantLaunchReady(store, entry.tenantId, posIdentity.organizationId)
  );
  const marketingTicketMembership = entry
    ? activeMembership(store, entry.userId, entry.tenantId)
    : null;
  const validMarketingTicket = product === "marketing" && Boolean(
    entry &&
    entry.product === "marketing" &&
    entry.expiresAt >= Date.now() &&
    (marketingTicketMembership?.role === "owner" || marketingTeamRole(marketingTicketMembership?.role)) &&
    membershipCanAccessApp(marketingTicketMembership, "app-marketing") &&
    organizationCanAccessApp(store, entry.tenantId, "app-marketing", posIdentity.organizationId) &&
    marketingTenantLaunchReady(store, entry.tenantId, posIdentity.organizationId)
  );
  const validTicket = product === "pos"
    ? validPosTicket
    : product === "ffpro"
      ? validFfproTicket
      : product === "tiquet"
        ? validTiquetTicket
        : product === "marketing"
          ? validMarketingTicket
          : Boolean(entry && validLegacyLaunch(store, entry, product, posIdentity.organizationId, posIdentity.ownerUserId));
  if (!entry || !validTicket) return res.status(401).json({ error: "Ticket expired or revoked" });
  launchTickets.delete(ticketHash);
  res.setHeader("Cache-Control", "no-store");
  if (product === "pos") return res.json({ token: posJwt(posUserId(entry.userId, entry.tenantId), entry.tenantId), tenantId: entry.tenantId });

  const user = store.users.find(u => u.id === entry.userId);
  const organization = store.organizations.find(org => org.id === entry.tenantId);
  const email = entry.tenantId === posIdentity.organizationId
    ? (process.env.V79_HUB_ADMIN_EMAIL || "").trim().toLowerCase()
    : String(user?.email || user?.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return res.status(503).json({ error: "Hub owner email is not configured." });
  if (!organization) return res.status(409).json({ error: "Hub organization is unavailable." });

  const consumedMembership = activeMembership(store, entry.userId, entry.tenantId);
  const consumedFfproTeamRole = product === "ffpro" ? ffproTeamRole(consumedMembership?.role) : null;
  const consumedTiquetTeamRole = product === "tiquet" ? tiquetTeamRole(consumedMembership?.role) : null;
  const consumedMarketingTeamRole = product === "marketing" ? marketingTeamRole(consumedMembership?.role) : null;
  const consumedRole = consumedMembership?.role === "owner"
    ? "owner"
    : consumedFfproTeamRole || consumedTiquetTeamRole || consumedMarketingTeamRole;
  if (!consumedRole) return res.status(401).json({ error: "Ticket role is no longer eligible" });

  res.json({
    user: { id: posUserId(entry.userId, entry.tenantId), email, name: user?.fullName || email },
    organization: { id: organization.id, name: organization.name, slug: organization.slug },
    role: consumedRole, plan: "beta", accessMode: "beta",
    entitlement: { product, enabled: true, access: consumedRole === "owner" ? "owner" : "team" },
    assignedProducts: enabledAppIds(store, entry.tenantId, posIdentity.organizationId)
      .map((appId: string) => ({ "app-ffpro": "ffpro", "app-tiquet": "tiquet", "app-marketing": "marketing" } as Record<string,string>)[appId])
      .filter(Boolean),
  });
});
server.on("upgrade", (request, socket, head) => {
  const origin = process.env.APP_URL ? new URL(process.env.APP_URL).origin : `http://${request.headers.host}`;
  const session = sessionFromToken(cookieToken(request.headers.cookie));
  if (request.headers.origin !== origin || !session) { socket.destroy(); return; }
  wss.handleUpgrade(request, socket, head, ws => {
    (ws as any).sessionToken = cookieToken(request.headers.cookie);
    wss.emit("connection", ws, request);
  });
});

// Broadcast helper for real-time WebSocket clients
function broadcast(organizationId: string, data: any, sender?: WebSocket) {
  wss.clients.forEach((client) => {
    const session = sessionFromToken((client as any).sessionToken || "");
    if (!session) { client.close(1008, "Session expired"); return; }
    if (client.readyState !== WebSocket.OPEN || client === sender ||
        session.organizationId !== organizationId ||
        (data.type === "USERS_UPDATED" && !hasHubPermission(session.userId, organizationId, "team"))) return;
    const payload = data.type === "USERS_UPDATED"
      ? { ...data, payload: store.users.map(user => sanitizeUserForOrganization(user, organizationId)).filter(Boolean) }
      : data.type === "ECOSYSTEM_APPS_UPDATED"
        ? { ...data, apps: visibleEcosystemApps(store, organizationId, posIdentity.organizationId) }
        : data;
    client.send(JSON.stringify(payload));
  });
}

// Auth Middleware
function requireAuth(req: Request, res: Response, next: () => void) {
  const authHeader = req.headers.authorization;
  const bearer = authHeader?.startsWith("Bearer ") ? authHeader.slice(7) : "";
  const token = bearer || cookieToken(req.headers.cookie);
  const session = sessionFromToken(token);
  if (!session) {
    return res.status(401).json({ error: "Session expired or invalid" });
  }
  if (!bearer && !["GET", "HEAD", "OPTIONS"].includes(req.method)) {
    const origin = process.env.APP_URL ? new URL(process.env.APP_URL).origin : `${req.protocol}://${req.get("host")}`;
    if (req.get("origin") !== origin) return res.status(403).json({ error: "Invalid request origin" });
  }
  // Extend session expiration on activity
  session.expiresAt = Date.now() + 12 * 60 * 60 * 1000;
  (req as any).user = session;
  next();
}
function isPlatformOperatorIdentity(userId: string, organizationId: string) {
  const user = store.users.find(item => item.id === userId);
  const membership = activeMembership(store, userId, organizationId);
  return Boolean(
    user &&
    user.id === posIdentity.ownerUserId &&
    organizationId === posIdentity.organizationId &&
    membership?.role === "owner" &&
    normalizeEmail(user.email) === vision79OwnerEmail &&
    normalizeEmail(process.env.V79_HUB_ADMIN_EMAIL) === vision79OwnerEmail
  );
}

function requirePlatformOperator(req: Request, res: Response, next: () => void) {
  const session = (req as any).user;
  if (!isPlatformOperatorIdentity(session.userId, session.organizationId)) {
    return res.status(403).json({ error: "Platform operator access required" });
  }
  next();
}
function requireRole(...roles: StoredUser["role"][]) {
  return (req: Request, res: Response, next: () => void) => {
    if (!roles.includes((req as any).user.role)) return res.status(403).json({ error: "Permission denied" });
    next();
  };
}

function requireWorkspaceOwner(req: Request, res: Response, next: () => void) {
  const session = (req as any).user;
  if (activeMembership(store, session.userId, session.organizationId)?.role !== "owner") {
    return res.status(403).json({ error: "Workspace owner access required" });
  }
  next();
}

const rolePermissionDefaults: Record<StoredUser["role"], string[]> = {
  admin: ["overview", "connections", "team", "security", "billing", "admin", "users"],
  manager: ["overview", "connections", "team", "security", "billing"],
  staff: ["overview", "connections"],
  viewer: ["overview"],
};
function normalizePermissions(value: unknown, role: StoredUser["role"]) {
  const allowedForRole = new Set(rolePermissionDefaults[role]);
  const requested = Array.isArray(value)
    ? value.filter(permission => typeof permission === "string" && allowedForRole.has(permission))
    : [];
  if (requested.length > 0) return [...new Set(requested)];
  return [...rolePermissionDefaults[role]];
}
function hasHubPermission(userId: string, organizationId: string, permission: string) {
  const user = store.users.find(item => item.id === userId);
  const membership = activeMembership(store, userId, organizationId);
  if (!user || !membership) return false;
  const role = sessionRole(membership) as StoredUser["role"];
  return normalizePermissions(membership.permissions ?? user.permissions, role).includes(permission);
}
function requirePermission(permission: string) {
  return (req: Request, res: Response, next: () => void) => {
    const session = (req as any).user;
    if (!hasHubPermission(session.userId, session.organizationId, permission)) {
      return res.status(403).json({ error: "Permission denied" });
    }
    next();
  };
}
function sanitizeUser(u: StoredUser) {
  const { password, mfaSecretEnc, mfaPendingSecretEnc, mfaPendingCreatedAt, ...safeUser } = u;
  return { ...safeUser, mfaEnabled: Boolean(u.mfaEnabled), permissions: normalizePermissions(safeUser.permissions, safeUser.role) };
}
function sanitizeUserForOrganization(u: StoredUser, organizationId: string) {
  const membership = activeMembership(store, u.id, organizationId);
  if (!membership) return null;
  const role = sessionRole(membership) as StoredUser["role"];
  return {
    ...sanitizeUser(u),
    role,
    workspaceOwner: membership.role === "owner",
    permissions: normalizePermissions(membership.permissions ?? u.permissions, role),
    appIds: membership.role === "owner"
      ? enabledAppIds(store, organizationId, posIdentity.organizationId)
      : normalizeTeamAppIds(membership.appIds, organizationId),
  };
}

const customerAssignableAppIds = ["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing", "app-academy"];
const tenantMappedAppIds = new Set(["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"]);
const teamAssignableAppIds = new Set(["app-v79pos", "app-ffpro", "app-tiquet", "app-marketing"]);

function normalizeTeamAppIds(value: unknown, organizationId: string) {
  if (!Array.isArray(value)) return [];
  const enabled = new Set(enabledAppIds(store, organizationId, posIdentity.organizationId));
  return [...new Set(value.filter((appId): appId is string =>
    typeof appId === "string" &&
    teamAssignableAppIds.has(appId) &&
    enabled.has(appId)
  ))];
}

function membershipCanAccessApp(membership: Membership | null | undefined, appId: string) {
  if (!membership) return false;
  if (membership.role === "owner") return true;
  return normalizeTeamAppIds(membership.appIds, membership.organizationId).includes(appId);
}

function validEmail(value: unknown) {
  const email = normalizeEmail(value);
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) ? email : "";
}

function validBusinessName(value: unknown) {
  if (typeof value !== "string") return "";
  const name = value.trim().replace(/\s+/g, " ");
  return name.length >= 2 && name.length <= 120 ? name : "";
}

function organizationSlug(name: string, currentStore: AppStore) {
  const base = name.normalize("NFKD").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "business";
  let slug = base;
  let attempt = 2;
  while (currentStore.organizations.some(org => org.slug === slug) ||
         currentStore.ownerInvitations.some(invite => invite.status === "pending" && invite.organizationSlug === slug)) {
    slug = `${base.slice(0, 42)}-${attempt++}`;
  }
  return slug;
}

function inviteHash(token: string) {
  return crypto.createHash("sha256").update(token).digest("hex");
}

function inviteTokenFromRequest(req: Request) {
  const token = String(req.get("x-v79-invite-token") || "");
  return /^[A-Za-z0-9_-]{40,180}$/.test(token) ? token : "";
}

function teamInviteTokenFromRequest(req: Request) {
  const token = String(req.get("x-v79-team-invite-token") || "");
  return /^[A-Za-z0-9_-]{40,180}$/.test(token) ? token : "";
}

function maskEmail(email: string) {
  const at = email.indexOf("@");
  if (at < 1) return "";
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  const visible = local.slice(0, Math.min(2, local.length));
  return `${visible}***@${domain}`;
}

function onboardingAudit(nextStore: AppStore, type: string, details: Record<string, unknown>, actorUserId?: string, organizationId?: string) {
  nextStore.auditEvents.push({
    id: crypto.randomUUID(),
    type,
    details,
    actorUserId,
    organizationId,
    createdAt: new Date().toISOString(),
  });
  if (nextStore.auditEvents.length > 5000) nextStore.auditEvents = nextStore.auditEvents.slice(-5000);
}

function organizationPlanFor(currentStore: AppStore, organizationId: string): OrganizationPlan {
  const stored = (currentStore.organizationPlans || []).find(plan => plan.organizationId === organizationId);
  if (stored) {
    return {
      ...stored,
      appIds: Array.isArray(stored.appIds) ? stored.appIds : rawEntitledAppIds(currentStore, organizationId),
    };
  }

  const isOwnerWorkspace = organizationId === posIdentity.organizationId;
  const monthly = Number(process.env.V79_HUB_MONTHLY_PRICE_XCD || "");
  const annual = Number(process.env.V79_HUB_ANNUAL_PRICE_XCD || "");
  const renewalDate = String(process.env.V79_HUB_RENEWAL_DATE || "").trim();
  const fallbackPrice = Number.isFinite(monthly) && monthly >= 0
    ? monthly
    : Number.isFinite(annual) && annual >= 0
      ? annual
      : undefined;

  return {
    organizationId,
    planName: isOwnerWorkspace ? String(process.env.V79_HUB_PLAN_NAME || "V79 Hub Beta").trim() : "Custom",
    status: "active",
    billingCycle: isOwnerWorkspace && Number.isFinite(annual) && annual >= 0 && !(Number.isFinite(monthly) && monthly >= 0)
      ? "annual"
      : isOwnerWorkspace && Number.isFinite(monthly) && monthly >= 0
        ? "monthly"
        : "custom",
    appIds: rawEntitledAppIds(currentStore, organizationId),
    ...(fallbackPrice !== undefined ? { priceXcd: fallbackPrice } : {}),
    ...(/^\d{4}-\d{2}-\d{2}$/.test(renewalDate) ? { renewalDate } : {}),
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
  };
}

function rawEntitledAppIds(currentStore: AppStore, organizationId: string) {
  return (currentStore.appEntitlements || [])
    .filter(entry => entry.organizationId === organizationId && entry.enabled === true)
    .map(entry => entry.appId);
}

function customerLifecycle(currentStore: AppStore, organization: Organization) {
  if (organization.status === "suspended") return "suspended";
  const enabled = new Set(rawEntitledAppIds(currentStore, organization.id));
  const mappedApps = [...tenantMappedAppIds].filter(appId => enabled.has(appId));
  const mappings = currentStore.appTenantMappings.filter(mapping => mapping.organizationId === organization.id);
  if (mappedApps.some(appId => mappings.find(mapping => mapping.appId === appId)?.status !== "active")) return "provisioning";
  return "active";
}

function sameOriginMutation(req: Request) {
  try {
    const expectedOrigin = process.env.APP_URL
      ? new URL(process.env.APP_URL).origin
      : `${req.protocol}://${req.get("host")}`;
    return req.get("origin") === expectedOrigin;
  } catch {
    return false;
  }
}

function createHubSession(userId: string, organizationId: string) {
  const user = store.users.find(item => item.id === userId);
  const membership = activeMembership(store, userId, organizationId);
  if (!user || !membership) throw new Error("Unable to create Hub session.");
  pruneAuthState();
  const token = "v79_tok_" + crypto.randomBytes(24).toString("hex");
  storeSessionToken(token, {
    userId,
    organizationId,
    username: user.username,
    role: sessionRole(membership)!,
    expiresAt: Date.now() + 12 * 60 * 60 * 1000,
  });
  return token;
}

async function completeInvitationAcceptance(
  invitation: OwnerInvitation,
  existingUser: StoredUser | undefined,
  fullName: string,
  password: string,
  attemptKey: string,
  res: Response,
) {
  if (store.organizations.some(org => org.id === invitation.organizationId)) {
    return res.status(409).json({ error: "This invitation needs manual review before it can be completed" });
  }

  const now = new Date().toISOString();
  const newUser = existingUser ? undefined : {
    id: crypto.randomUUID(),
    username: invitation.email,
    email: invitation.email,
    password: hashPassword(password),
    fullName,
    role: "admin" as const,
    permissions: normalizePermissions([], "admin"),
  };

  let transition;
  try {
    transition = acceptInvitationState(store, invitation.id, {
      existingUserId: existingUser?.id,
      newUser,
      ownerPermissions: normalizePermissions([], "admin"),
      tenantMappedAppIds: [...tenantMappedAppIds],
      auditId: crypto.randomUUID(),
      now,
    });
  } catch (error) {
    console.error("Invitation acceptance state transition failed", error);
    return res.status(409).json({ error: "This invitation needs manual review before it can be completed" });
  }

  if (!Array.isArray(transition.nextStore.organizationPlans)) transition.nextStore.organizationPlans = [];
  if (!transition.nextStore.organizationPlans.some((plan: OrganizationPlan) => plan.organizationId === transition.organizationId)) {
    transition.nextStore.organizationPlans.push({
      organizationId: transition.organizationId,
      planName: "V79 Hub Beta Trial",
      ...beginTrial(new Date(now)),
      billingCycle: "custom",
      appIds: [...transition.appIds],
      createdAt: now,
      updatedAt: now,
    });
  }
  await commitStore(transition.nextStore);
  inviteAttempts.delete(attemptKey);
  const user = store.users.find(item => item.id === transition.userId)!;
  const sessionToken = createHubSession(user.id, transition.organizationId);
  const organization = store.organizations.find(org => org.id === transition.organizationId)!;
  res.setHeader("Set-Cookie", sessionCookie(sessionToken, 12 * 60 * 60));
  res.setHeader("Cache-Control", "no-store");
  return res.status(201).json({
    user: { ...sanitizeUserForOrganization(user, transition.organizationId), platformOperator: false, ownerAgent: false },
    organization,
    onboarding: {
      appIds: transition.appIds,
      productSetupPending: transition.appIds.filter((appId: string) => tenantMappedAppIds.has(appId)),
    },
  });
}

async function completeTeamInvitationAcceptance(
  invitation: TeamInvitation,
  existingUser: StoredUser | undefined,
  fullName: string,
  password: string,
  attemptKey: string,
  res: Response,
) {
  const now = new Date().toISOString();
  const newUser = existingUser ? undefined : {
    id: crypto.randomUUID(),
    username: invitation.email,
    email: invitation.email,
    password: hashPassword(password),
    fullName,
    role: invitation.role,
    permissions: [...invitation.permissions],
  };

  let transition;
  try {
    transition = acceptTeamInvitationState(store, invitation.id, {
      existingUserId: existingUser?.id,
      newUser,
      auditId: crypto.randomUUID(),
      now,
    });
  } catch (error) {
    console.error("Team invitation acceptance state transition failed", error);
    return res.status(409).json({ error: "This team invitation needs manual review before it can be completed" });
  }

  await commitStore(transition.nextStore as AppStore);
  inviteAttempts.delete(attemptKey);
  const user = store.users.find(item => item.id === transition.userId)!;
  const sessionToken = createHubSession(user.id, transition.organizationId);
  const organization = store.organizations.find(org => org.id === transition.organizationId)!;
  res.setHeader("Set-Cookie", sessionCookie(sessionToken, 12 * 60 * 60));
  res.setHeader("Cache-Control", "no-store");
  return res.status(201).json({
    user: { ...sanitizeUserForOrganization(user, transition.organizationId), platformOperator: false, ownerAgent: false },
    organization,
    teamOnboarding: {
      role: transition.role,
      permissions: transition.permissions,
      appIds: transition.appIds,
      managedProductAccess: {
        pos: "role_mapped",
        ffpro: "role_mapped",
        tiquet: "role_mapped",
        marketing: "role_mapped",
      },
    },
  });
}

// ==========================================
// AUTHENTICATION ROUTES
// ==========================================

async function completeHubLogin(foundUser: StoredUser, organizationId: string, res: Response) {
  const token = createHubSession(foundUser.id, organizationId);
  foundUser.lastLogin = new Date().toISOString();
  await saveStore(store);
  res.setHeader("Set-Cookie", sessionCookie(token, 12 * 60 * 60));
  res.setHeader("Cache-Control", "no-store");
  const membership = activeMembership(store, foundUser.id, organizationId);
  const ownerAgent = hasOwnerAssistantAccess({ user: foundUser, membership, organizationId, ownerOrganizationId: posIdentity.organizationId, ownerUserId: posIdentity.ownerUserId, ownerEmail: process.env.V79_HUB_ADMIN_EMAIL });
  return res.json({
    user: { ...sanitizeUserForOrganization(foundUser, organizationId), platformOperator: isPlatformOperatorIdentity(foundUser.id, organizationId), ownerAgent },
    organization: store.organizations.find(org => org.id === organizationId)
  });
}

async function startLoginMfa(foundUser: StoredUser, organizationId: string, res: Response) {
  const platformOperator = isPlatformOperatorIdentity(foundUser.id, organizationId);
  const adminMfaRequired = platformOperator && process.env.V79_REQUIRE_ADMIN_MFA === "1";
  if (!adminMfaRequired && !foundUser.mfaEnabled) return null;
  if (hubSecurityKey.length < 32) {
    return res.status(503).json({ error: "Hub MFA encryption is not configured. Contact V79 Digital." });
  }
  const mode: "setup" | "verify" = foundUser.mfaEnabled ? "verify" : "setup";
  let secret: string | undefined;
  if (mode === "setup") {
    const pendingAge = foundUser.mfaPendingCreatedAt ? Date.now() - new Date(foundUser.mfaPendingCreatedAt).getTime() : Number.POSITIVE_INFINITY;
    if (foundUser.mfaPendingSecretEnc && Number.isFinite(pendingAge) && pendingAge >= 0 && pendingAge < 30 * 60_000) {
      try { secret = decryptTotpSecret(foundUser.mfaPendingSecretEnc, hubSecurityKey); }
      catch { secret = undefined; }
    }
    if (!secret) {
      secret = generateTotpSecret();
      foundUser.mfaPendingSecretEnc = encryptTotpSecret(secret, hubSecurityKey);
      foundUser.mfaPendingCreatedAt = new Date().toISOString();
      await saveStore(store);
    }
  }
  const challenge = createMfaChallenge(foundUser.id, organizationId, mode, secret);
  return res.status(202).json({
    mfaRequired: true,
    setupRequired: mode === "setup",
    challengeId: challenge.id,
    serverTime: Date.now(),
    ...(secret ? {
      secret,
      provisioningUri: totpProvisioningUri({
        secret,
        account: normalizeEmail(foundUser.email) || foundUser.username,
        issuer: "V79 Hub",
      }),
    } : {}),
  });
}

app.post("/api/auth/login", async (req, res) => {
  const { username, password, organizationId } = req.body || {};
  if (typeof username !== "string" || typeof password !== "string" || !username.trim() || username.length > 120 || !password || password.length > 1024 ||
      (organizationId !== undefined && (typeof organizationId !== "string" || organizationId.length > 160))) {
    return res.status(400).json({ error: "Valid username and password required" });
  }
  const attemptKey = `${req.ip}:${username.trim().toLowerCase()}`;
  const attempts = loginAttempts.get(attemptKey);
  if (attempts && attempts.count >= 10 && attempts.until > Date.now()) return res.status(429).json({ error: "Too many login attempts. Try again later." });

  const lookup = String(username).trim().toLowerCase();
  const foundUser = store.users.find(
    (u) => (u.username.toLowerCase() === lookup || normalizeEmail(u.email) === lookup) && checkPassword(password, u.password)
  );

  if (!foundUser) {
    if (!loginAttempts.has(attemptKey) && loginAttempts.size >= 10_000) {
      const oldest = loginAttempts.keys().next().value;
      if (oldest !== undefined) loginAttempts.delete(oldest);
    }
    loginAttempts.set(attemptKey, { count: (attempts?.until && attempts.until > Date.now() ? attempts.count : 0) + 1, until: Date.now() + 15 * 60_000 });
    return res.status(401).json({ error: "Invalid username or password" });
  }
  loginAttempts.delete(attemptKey);
  const memberships = activeMembershipsForUser(store, foundUser.id) as Membership[];
  const selectedMembership = typeof organizationId === "string" && organizationId
    ? memberships.find((member: Membership) => member.organizationId === organizationId)
    : foundUser.id === posIdentity.ownerUserId
      ? memberships.find((member: Membership) => member.organizationId === posIdentity.organizationId)
      : memberships.length === 1 ? memberships[0] : null;
  if (!selectedMembership) {
    if (memberships.length > 1 && !organizationId) {
      return res.status(409).json({
        error: "Workspace selection required",
        organizations: memberships.map((member: Membership) => store.organizations.find((org: Organization) => org.id === member.organizationId))
          .filter((org): org is Organization => Boolean(org))
          .map((org: Organization) => ({ id: org.id, name: org.name, slug: org.slug })),
      });
    }
    return res.status(401).json({ error: "Invalid username, password, or workspace" });
  }

  const mfaResponse = await startLoginMfa(foundUser, selectedMembership.organizationId, res);
  if (mfaResponse) return mfaResponse;
  return completeHubLogin(foundUser, selectedMembership.organizationId, res);
});

app.post("/api/auth/mfa/complete-login", async (req, res) => {
  const challengeId = String(req.body?.challengeId || "");
  const code = String(req.body?.code || "");
  pruneMfaChallenges();
  const challenge = mfaChallenges.get(challengeId);
  if (!challenge || challenge.expiresAt <= Date.now()) return res.status(401).json({ error: "MFA challenge expired. Sign in again." });
  if (challenge.attempts >= 6) {
    mfaChallenges.delete(challengeId);
    return res.status(429).json({ error: "Too many MFA attempts. Sign in again." });
  }
  challenge.attempts += 1;
  const user = store.users.find(item => item.id === challenge.userId);
  const membership = activeMembership(store, challenge.userId, challenge.organizationId);
  if (!user || !membership) {
    mfaChallenges.delete(challengeId);
    return res.status(401).json({ error: "MFA challenge is no longer valid." });
  }

  let secret = challenge.secret;
  if (challenge.mode === "verify") {
    if (!user.mfaEnabled || !user.mfaSecretEnc) return res.status(401).json({ error: "MFA enrollment is missing." });
    try { secret = decryptTotpSecret(user.mfaSecretEnc, hubSecurityKey); }
    catch { return res.status(503).json({ error: "MFA verification is unavailable. Contact V79 Digital." }); }
  }
  if (!secret || !verifyTotp(secret, code, Date.now(), 2)) return res.status(401).json({ error: "Invalid authentication code. Confirm your authenticator uses the current V79 Hub setup key and that automatic date/time is enabled on the device." });

  if (challenge.mode === "setup") {
    user.mfaSecretEnc = encryptTotpSecret(secret, hubSecurityKey);
    user.mfaEnabled = true;
    delete user.mfaPendingSecretEnc;
    delete user.mfaPendingCreatedAt;
    onboardingAudit(store, "mfa_enabled", { method: "totp", mandatory: isPlatformOperatorIdentity(user.id, challenge.organizationId) && process.env.V79_REQUIRE_ADMIN_MFA === "1" }, user.id, challenge.organizationId);
    await saveStore(store);
  }
  mfaChallenges.delete(challengeId);
  return completeHubLogin(user, challenge.organizationId, res);
});

app.post("/api/auth/register", (_req, res) => {
  res.status(403).json({ error: "Registration is invite-only. Ask V79 Digital for an owner invitation." });
});

app.get("/api/onboarding/invitation", (req, res) => {
  const token = inviteTokenFromRequest(req);
  if (!token) return res.status(404).json({ error: "Invitation unavailable" });
  const invitation = store.ownerInvitations.find(item => item.tokenHash === inviteHash(token));
  if (!invitation) return res.status(404).json({ error: "Invitation unavailable" });
  const status = invitationStatus(invitation);
  res.setHeader("Cache-Control", "no-store");
  if (status !== "pending") return res.status(410).json({ error: "Invitation is no longer available", status });
  res.json({
    organizationName: invitation.organizationName,
    organizationSlug: invitation.organizationSlug,
    email: maskEmail(invitation.email),
    expiresAt: invitation.expiresAt,
    appIds: invitation.appIds,
  });
});

app.post("/api/onboarding/invitation/accept", async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const token = inviteTokenFromRequest(req);
  if (!token) return res.status(404).json({ error: "Invitation unavailable" });
  const tokenHash = inviteHash(token);
  const attemptKey = `${req.ip}:${tokenHash.slice(0, 20)}`;
  const attempts = inviteAttempts.get(attemptKey);
  if (attempts && attempts.count >= 10 && attempts.until > Date.now()) {
    return res.status(429).json({ error: "Too many invitation attempts. Try again later." });
  }

  const invitation = store.ownerInvitations.find(item => item.tokenHash === tokenHash);
  if (!invitation) return res.status(404).json({ error: "Invitation unavailable" });
  const status = invitationStatus(invitation);
  if (status !== "pending") {
    if (status === "expired" && invitation.status === "pending") {
      const nextStore = cloneStore();
      const expired = nextStore.ownerInvitations.find(item => item.id === invitation.id)!;
      expired.status = "revoked";
      expired.revokedAt = new Date().toISOString();
      onboardingAudit(nextStore, "owner_invitation_expired", { invitationId: expired.id, email: expired.email }, undefined, expired.organizationId);
      await commitStore(nextStore);
    }
    return res.status(410).json({ error: "Invitation is no longer available", status });
  }

  const fullName = typeof req.body?.fullName === "string" ? req.body.fullName.trim() : "";
  const password = typeof req.body?.password === "string" ? req.body.password : "";
  if (!fullName || fullName.length > 120 || password.length < 12 || password.length > 1024) {
    return res.status(400).json({ error: "Full name and a password of at least 12 characters are required" });
  }

  const existingUser = store.users.find(user =>
    normalizeEmail(user.email) === invitation.email || user.username.toLowerCase() === invitation.email
  );
  if (existingUser) {
    if (normalizeEmail(existingUser.email) && normalizeEmail(existingUser.email) !== invitation.email) {
      return res.status(409).json({ error: "This email conflicts with an existing Hub identity" });
    }
    if (!checkPassword(password, existingUser.password)) {
      inviteAttempts.set(attemptKey, {
        count: (attempts?.until && attempts.until > Date.now() ? attempts.count : 0) + 1,
        until: Date.now() + 15 * 60_000,
      });
      return res.status(401).json({ error: "Use the password for the existing Hub account linked to this email" });
    }
  }

  return completeInvitationAcceptance(invitation, existingUser, fullName, password, attemptKey, res);
});

app.get("/api/team-invitation", (req, res) => {
  const token = teamInviteTokenFromRequest(req);
  if (!token) return res.status(404).json({ error: "Team invitation unavailable" });
  const invitation = store.teamInvitations.find(item => item.tokenHash === inviteHash(token));
  if (!invitation) return res.status(404).json({ error: "Team invitation unavailable" });
  const status = teamInvitationStatus(invitation);
  res.setHeader("Cache-Control", "no-store");
  if (status !== "pending") return res.status(410).json({ error: "Team invitation is no longer available", status });
  const organization = store.organizations.find(org => org.id === invitation.organizationId && org.status === "active");
  if (!organization) return res.status(410).json({ error: "Team invitation is no longer available", status: "organization_unavailable" });
  res.json({
    organizationName: organization.name,
    email: maskEmail(invitation.email),
    role: invitation.role,
    permissions: invitation.permissions,
    appIds: normalizeTeamAppIds(invitation.appIds, invitation.organizationId),
    expiresAt: invitation.expiresAt,
  });
});

app.post("/api/team-invitation/accept", async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const token = teamInviteTokenFromRequest(req);
  if (!token) return res.status(404).json({ error: "Team invitation unavailable" });
  const tokenHash = inviteHash(token);
  const attemptKey = `team:${req.ip}:${tokenHash.slice(0, 20)}`;
  const attempts = inviteAttempts.get(attemptKey);
  if (attempts && attempts.count >= 10 && attempts.until > Date.now()) {
    return res.status(429).json({ error: "Too many invitation attempts. Try again later." });
  }

  const invitation = store.teamInvitations.find(item => item.tokenHash === tokenHash);
  if (!invitation) return res.status(404).json({ error: "Team invitation unavailable" });
  const status = teamInvitationStatus(invitation);
  if (status !== "pending") {
    if (status === "expired" && invitation.status === "pending") {
      const nextStore = cloneStore();
      const expired = nextStore.teamInvitations.find(item => item.id === invitation.id)!;
      expired.status = "revoked";
      expired.revokedAt = new Date().toISOString();
      onboardingAudit(nextStore, "team_invitation_expired", { invitationId: expired.id, email: expired.email }, undefined, expired.organizationId);
      await commitStore(nextStore);
    }
    return res.status(410).json({ error: "Team invitation is no longer available", status });
  }

  const fullName = typeof req.body?.fullName === "string" ? req.body.fullName.trim() : "";
  const password = typeof req.body?.password === "string" ? req.body.password : "";
  if (!fullName || fullName.length > 120 || password.length < 12 || password.length > 1024) {
    return res.status(400).json({ error: "Full name and a password of at least 12 characters are required" });
  }

  const existingUser = store.users.find(user =>
    normalizeEmail(user.email) === invitation.email || user.username.toLowerCase() === invitation.email
  );
  if (existingUser) {
    if (normalizeEmail(existingUser.email) && normalizeEmail(existingUser.email) !== invitation.email) {
      return res.status(409).json({ error: "This email conflicts with an existing Hub identity" });
    }
    if (activeMembership(store, existingUser.id, invitation.organizationId)) {
      return res.status(409).json({ error: "This account is already a member of the workspace" });
    }
    if (!checkPassword(password, existingUser.password)) {
      inviteAttempts.set(attemptKey, {
        count: (attempts?.until && attempts.until > Date.now() ? attempts.count : 0) + 1,
        until: Date.now() + 15 * 60_000,
      });
      return res.status(401).json({ error: "Use the password for the existing Hub account linked to this email" });
    }
  }

  return completeTeamInvitationAcceptance(invitation, existingUser, fullName, password, attemptKey, res);
});

const resendApiKey = String(process.env.RESEND_API_KEY || "").trim();
const hubEmailFrom = String(process.env.V79_HUB_EMAIL_FROM || "").trim();
const hubRecoveryContact = normalizeEmail(process.env.V79_HUB_RECOVERY_EMAIL) || vision79OwnerEmail;
const appPublicUrl = String(process.env.APP_URL || "").replace(/\/$/, "");
let transactionalEmail: ReturnType<typeof createResendTransactionalSender> | null = null;
if (resendApiKey && hubEmailFrom) {
  try {
    transactionalEmail = createResendTransactionalSender({
      apiKey: resendApiKey, from: hubEmailFrom,
      replyTo: hubRecoveryContact, hubUrl: appPublicUrl,
    });
  } catch {
    // Sender/config errors fail closed, without printing credentials or addresses.
    console.warn("[Hub Email] Transactional email configuration is invalid; delivery disabled.");
  }
}
const recoveryEmailEnabled = transactionalEmail !== null;

// Off by default. Single nominated leader only; stale sending claims require manual review.
const trialReminderLeader = process.env.V79_TRIAL_REMINDERS_ENABLED === "1" &&
  process.env.V79_TRIAL_REMINDERS_WORKER_LEADER === "1";
let reminderBusy=false;
async function dispatchTrialReminderEmail(reminder: {
  email:string; kind:string; trialEndsAt:string; key:string;
}) {
  return transactionalEmail ? transactionalEmail.sendTrialReminder(reminder) : false;
}
async function dispatchTrialReminders() {
  if (!trialReminderLeader || !recoveryEmailEnabled || reminderBusy) return;
  reminderBusy=true;
  try {
    await dispatchDueTrialReminders({
      ownerOrganizationId:posIdentity.organizationId,
      getStore:()=>store,
      commit:async (next: AppStore)=>commitStore(next),
      send:dispatchTrialReminderEmail,
    });
  } catch {console.warn("[Hub Trial] Review stuck notification claims before next attempt");}
  finally {reminderBusy=false;}
}

async function deliverPasswordReset(email: string, resetUrl: string) {
  return transactionalEmail ? transactionalEmail.sendPasswordReset(email,resetUrl) : false;
}

app.get("/api/auth/recovery-status", (_req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.json({ emailRecoveryEnabled: recoveryEmailEnabled, supportEmail: hubRecoveryContact });
});

app.post("/api/auth/password-reset/request", async (req, res) => {
  const generic = { accepted: true, message: "If that email is eligible for recovery, reset instructions will be sent." };
  const email = validEmail(req.body?.email);
  const key = `${req.ip}:${email || "invalid"}`;
  const attempts = recoveryAttempts.get(key);
  if (attempts && attempts.count >= 5 && attempts.until > Date.now()) return res.status(202).json(generic);
  recoveryAttempts.set(key, { count: (attempts?.until && attempts.until > Date.now() ? attempts.count : 0) + 1, until: Date.now() + 30 * 60_000 });
  if (!email || !recoveryEmailEnabled) return res.status(202).json(generic);

  const user = store.users.find(item => normalizeEmail(item.email) === email || item.username.toLowerCase() === email);
  if (!user) return res.status(202).json(generic);

  const token = createOpaqueToken(32);
  const now = new Date();
  store.passwordResetRequests = (store.passwordResetRequests || [])
    .filter(item => new Date(item.expiresAt).getTime() > Date.now() - 24 * 60 * 60_000)
    .map(item => item.userId === user.id && !item.usedAt ? { ...item, usedAt: now.toISOString() } : item);
  store.passwordResetRequests.push({
    id: crypto.randomUUID(),
    userId: user.id,
    tokenHash: opaqueTokenHash(token),
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + 30 * 60_000).toISOString(),
  });
  await saveStore(store);

  try {
    const delivered = await deliverPasswordReset(email, `${appPublicUrl}/?reset=${encodeURIComponent(token)}`);
    if (!delivered) console.warn("[Hub Recovery] Reset email provider rejected the request.");
  } catch (error) {
    console.error("[Hub Recovery] Reset email delivery failed.");
  }
  return res.status(202).json(generic);
});

app.post("/api/auth/password-reset/complete", async (req, res) => {
  const token = String(req.body?.token || "");
  const password = typeof req.body?.password === "string" ? req.body.password : "";
  if (!/^[A-Za-z0-9_-]{30,180}$/.test(token) || password.length < 12 || password.length > 1024) {
    return res.status(400).json({ error: "A valid reset token and password of at least 12 characters are required." });
  }
  const hash = opaqueTokenHash(token);
  const reset = (store.passwordResetRequests || []).find(item => item.tokenHash === hash && !item.usedAt);
  if (!reset || new Date(reset.expiresAt).getTime() <= Date.now()) {
    return res.status(400).json({ error: "This reset link is invalid or has expired." });
  }
  const user = store.users.find(item => item.id === reset.userId);
  if (!user) return res.status(400).json({ error: "This reset link is invalid or has expired." });

  user.password = hashPassword(password);
  reset.usedAt = new Date().toISOString();
  deleteSessionsWhere(session => session.userId === user.id);
  onboardingAudit(store, "password_reset_completed", {}, user.id);
  await saveStore(store);
  res.setHeader("Set-Cookie", sessionCookie("", 0));
  return res.json({ success: true });
});

app.get("/api/auth/me", requireAuth, (req, res) => {
  const session = (req as any).user;
  const user = store.users.find((u) => u.id === session.userId);
  if (!user) {
    return res.status(404).json({ error: "User record not found" });
  }
  const membership = activeMembership(store, user.id, session.organizationId);
  const ownerAgent = hasOwnerAssistantAccess({ user, membership, organizationId: session.organizationId, ownerOrganizationId: posIdentity.organizationId, ownerUserId: posIdentity.ownerUserId, ownerEmail: process.env.V79_HUB_ADMIN_EMAIL });
  res.json({ user: { ...sanitizeUserForOrganization(user, session.organizationId), platformOperator: isPlatformOperatorIdentity(user.id, session.organizationId), ownerAgent }, organization: store.organizations.find(org => org.id === session.organizationId) });
});

app.post("/api/auth/logout", requireAuth, (req, res) => {
  const authHeader = req.headers.authorization;
  deleteSessionToken(authHeader?.startsWith("Bearer ") ? authHeader.slice(7) : cookieToken(req.headers.cookie));
  res.setHeader("Set-Cookie", sessionCookie("", 0));
  res.json({ success: true });
});


app.get("/api/billing/summary", requireAuth, requirePermission("billing"), (req, res) => {
  const session = (req as any).user;
  const organization = store.organizations.find(org => org.id === session.organizationId);
  const enabledIds = new Set(enabledAppIds(store, session.organizationId, posIdentity.organizationId));
  const enabledApps = (store.ecosystemApps || [])
    .filter(app => enabledIds.has(app.id))
    .filter(app => !["app-analytics", "app-lifehealth", "app-lasertag"].includes(app.id) || session.organizationId === posIdentity.organizationId)
    .map(app => ({ id: app.id, name: app.shortName || app.name }));

  const plan = organizationPlanFor(store, session.organizationId);
  const provider = publicWipayConfig(getWipayConfig(process.env));
  res.setHeader("Cache-Control", "no-store");
  res.json({
    organization: organization?.name || "Business workspace",
    planName: plan.planName,
    status: plan.status,
    accessStatus: accessDecision(plan, Date.now(), session.organizationId === posIdentity.organizationId).reason,
    trialStartedAt: plan.trialStartedAt || null,
    trialEndsAt: plan.trialEndsAt || null,
    paidThroughAt: plan.paidThroughAt || null,
    billingCycle: plan.billingCycle,
    enabledApps,
    pricing: {
      currency: "XCD",
      monthly: plan.billingCycle === "monthly" && Number.isFinite(plan.priceXcd) ? plan.priceXcd : null,
      annual: plan.billingCycle === "annual" && Number.isFinite(plan.priceXcd) ? plan.priceXcd : null,
      custom: plan.billingCycle === "custom" && Number.isFinite(plan.priceXcd) ? plan.priceXcd : null,
    },
    renewalDate: plan.renewalDate || null,
    billingManagedBy: "V79 Digital",
    supportEmail: normalizeEmail(process.env.V79_HUB_RECOVERY_EMAIL) || vision79OwnerEmail,
    selfServicePaymentsEnabled: provider.ready && provider.environment === "live" && provider.currency === "XCD" && ["monthly", "annual"].includes(plan.billingCycle) && Number(plan.priceXcd) > 0,
    sandboxTestPaymentsEnabled: provider.ready && provider.environment === "sandbox",
    paymentProvider: provider,
  });
});

function billingServiceFromRequest(req: Request) {
  const source = String(req.get("x-v79-service-id") || "");
  const entries: Record<string, { sourceApp: "academy" | "tiquet"; secret: string }> = {
    "v79-academy-billing": { sourceApp: "academy", secret: String(process.env.V79_ACADEMY_BILLING_SECRET || "") },
    "v79-tiquet-billing": { sourceApp: "tiquet", secret: String(process.env.V79_TIQUET_BILLING_SECRET || "") },
  };
  const entry = entries[source];
  if (!entry) return null;
  const body = (req as any).rawBody?.toString("utf8") || "";
  const pathname = req.path;
  const verified = verifyPlatformRequest({
    method: req.method,
    pathname,
    timestamp: req.get("x-v79-timestamp") || "",
    signature: req.get("x-v79-signature") || "",
    body,
    secret: entry.secret,
  });
  return verified ? entry : null;
}

function validBillingReturnPath(value: unknown) {
  const returnPath = typeof value === "string" ? value.trim() : "";
  if (!returnPath || returnPath.length > 500 || !returnPath.startsWith("/") || returnPath.startsWith("//") || /[\r\n]/.test(returnPath)) return "";
  return returnPath;
}

function billingOrderReturnUrl(order: BillingOrder) {
  const appUrl = String(process.env.APP_URL || "https://hub.v79sl.com").replace(/\/$/, "");
  const base = order.sourceApp === "academy"
    ? String(process.env.ACADEMY_PUBLIC_URL || "https://academy.v79sl.com").replace(/\/$/, "")
    : order.sourceApp === "tiquet"
      ? String(process.env.TIQUET_PUBLIC_URL || "https://tiquet.v79sl.com").replace(/\/$/, "")
      : appUrl;
  const safePath = validBillingReturnPath(order.returnPath) || "/";
  const target = new URL(safePath, base + "/");
  if (target.origin !== new URL(base).origin) return new URL("/", base).toString();
  return target.toString();
}

app.post("/api/billing/internal/order", async (req, res) => {
  const service = billingServiceFromRequest(req);
  if (!service) return res.status(401).json({ error: "Invalid billing service signature." });

  const config = getWipayConfig(process.env);
  if (!config.ready) return res.status(503).json({ error: "WiPay checkout is not configured.", problems: config.problems });

  const kind = String(req.body?.kind || "");
  const externalReference = String(req.body?.externalReference || "").trim();
  const subjectReference = String(req.body?.subjectReference || "").trim();
  const description = String(req.body?.description || "").trim();
  const returnPath = validBillingReturnPath(req.body?.returnPath);
  const amount = normalizeMoney(req.body?.amount);
  const sourceCurrency = String(req.body?.currency || "").trim().toUpperCase();

  if ((service.sourceApp === "academy" && kind !== "course") ||
      (service.sourceApp === "tiquet" && kind !== "invoice") ||
      !externalReference || externalReference.length > 160 ||
      !subjectReference || subjectReference.length > 160 ||
      !description || description.length > 220 ||
      !returnPath ||
      amount === null || amount <= 0 || amount > 1_000_000 ||
      !/^[A-Z]{3}$/.test(sourceCurrency)) {
    return res.status(400).json({ error: "Valid billing order details are required." });
  }
  if (config.environment === "live" && sourceCurrency !== config.currency) {
    return res.status(409).json({ error: "The source application's currency does not match the live WiPay merchant currency.", code: "BILLING_CURRENCY_MISMATCH" });
  }

  // Tiquet invoice collection is intentionally owner-only until WiPay confirms
  // a marketplace/sub-merchant settlement model for third-party V79 tenants.
  const requestedOrganizationId = String(req.body?.organizationId || "").trim();
  if (service.sourceApp === "tiquet" &&
      (req.body?.merchantScope !== "v79-owner" || requestedOrganizationId !== posIdentity.organizationId)) {
    return res.status(403).json({ error: "Tiquet WiPay invoice collection is restricted to the V79 Digital merchant workspace." });
  }

  const now = new Date().toISOString();
  const order: BillingOrder = {
    id: `v79_${Date.now().toString(36)}_${crypto.randomBytes(8).toString("hex")}`,
    ...(service.sourceApp === "tiquet" ? { organizationId: requestedOrganizationId } : {}),
    subjectReference,
    sourceApp: service.sourceApp,
    kind: kind as BillingOrder["kind"],
    externalReference,
    returnPath,
    description,
    amount,
    currency: config.currency,
    provider: "wipay",
    providerEnvironment: config.environment as BillingOrder["providerEnvironment"],
    status: "pending",
    createdAt: now,
    updatedAt: now,
  };

  const checkout = createWipayCheckout({ order, config });
  const nextStore = cloneStore();
  nextStore.billingOrders.push(order);
  onboardingAudit(nextStore, "billing_service_checkout_created", {
    orderId: order.id,
    sourceApp: order.sourceApp,
    kind: order.kind,
    externalReference: order.externalReference,
    amount: order.amount,
    currency: order.currency,
    providerEnvironment: order.providerEnvironment,
  }, undefined, order.organizationId);
  await commitStore(nextStore);

  res.status(201).json({
    order: {
      id: order.id,
      sourceApp: order.sourceApp,
      kind: order.kind,
      externalReference: order.externalReference,
      amount: order.amount,
      currency: order.currency,
      status: order.status,
    },
    checkout,
  });
});

app.post("/api/billing/internal/capabilities", (req, res) => {
  const service = billingServiceFromRequest(req);
  if (!service) return res.status(401).json({ error: "Invalid billing service signature." });

  const provider = publicWipayConfig(getWipayConfig(process.env));
  const requestedOrganizationId = String(req.body?.organizationId || "").trim();
  const sourceCurrency = String(req.body?.currency || "").trim().toUpperCase();
  const currencyCompatible = /^[A-Z]{3}$/.test(sourceCurrency) &&
    (provider.environment !== "live" || sourceCurrency === provider.currency);
  const checkoutAvailable = service.sourceApp === "tiquet"
    ? Boolean(provider.ready && currencyCompatible && requestedOrganizationId && requestedOrganizationId === posIdentity.organizationId)
    : Boolean(provider.ready && currencyCompatible);

  res.setHeader("Cache-Control", "no-store");
  res.json({
    sourceApp: service.sourceApp,
    checkoutAvailable,
    currencyCompatible,
    provider: {
      provider: provider.provider,
      environment: provider.environment,
      currency: provider.currency,
      countryCode: provider.countryCode,
      ready: provider.ready,
    },
  });
});

app.post("/api/billing/internal/status", (req, res) => {
  const service = billingServiceFromRequest(req);
  if (!service) return res.status(401).json({ error: "Invalid billing service signature." });
  const orderId = String(req.body?.orderId || "").trim();
  if (!/^v79_[A-Za-z0-9_]+$/.test(orderId) || orderId.length > 64) return res.status(400).json({ error: "Invalid billing order." });
  const order = (store.billingOrders || []).find(item => item.id === orderId && item.sourceApp === service.sourceApp);
  if (!order) return res.status(404).json({ error: "Billing order not found." });
  res.setHeader("Cache-Control", "no-store");
  res.json({
    order: {
      id: order.id,
      sourceApp: order.sourceApp,
      kind: order.kind,
      externalReference: order.externalReference || null,
      subjectReference: order.subjectReference || null,
      amount: order.amount,
      currency: order.currency,
      status: order.status,
      providerEnvironment: order.providerEnvironment,
      providerTransactionId: order.status === "paid" ? order.providerTransactionId || null : null,
      paidAt: order.paidAt || null,
    },
  });
});

app.get("/api/billing/orders", requireAuth, requirePermission("billing"), (req, res) => {
  const session = (req as any).user;
  const orders = (store.billingOrders || [])
    .filter(order => order.organizationId === session.organizationId)
    .slice(-25)
    .reverse()
    .map(order => ({
      id: order.id,
      sourceApp: order.sourceApp,
      kind: order.kind,
      description: order.description,
      amount: order.amount,
      currency: order.currency,
      provider: order.provider,
      providerEnvironment: order.providerEnvironment,
      status: order.status,
      providerTransactionId: order.providerTransactionId || null,
      createdAt: order.createdAt,
      paidAt: order.paidAt || null,
    }));
  res.setHeader("Cache-Control", "no-store");
  res.json({ orders });
});

app.post("/api/billing/checkout", requireAuth, requirePermission("billing"), async (req, res) => {
  const session = (req as any).user;
  const config = getWipayConfig(process.env);
  if (!config.ready) return res.status(503).json({ error: "WiPay checkout is not configured.", problems: config.problems });

  if (config.environment !== "live") {
    return res.status(409).json({ error: "Use the dedicated sandbox test checkout while WiPay is in sandbox mode." });
  }
  if (config.currency !== "XCD") {
    return res.status(409).json({
      error: "Hub plan prices are stored in XCD and cannot be charged through a different live merchant currency.",
      code: "BILLING_CURRENCY_MISMATCH",
    });
  }

  const plan = organizationPlanFor(store, session.organizationId);
  if (!["monthly", "annual"].includes(plan.billingCycle)) {
    return res.status(409).json({ error: "This workspace plan is not configured for self-service monthly or annual renewal." });
  }
  const amount = normalizeMoney(plan.priceXcd);
  if (amount === null || amount <= 0) return res.status(409).json({ error: "A positive workspace plan price must be configured before checkout." });

  const now = new Date().toISOString();
  const order: BillingOrder = {
    id: `v79_${Date.now().toString(36)}_${crypto.randomBytes(8).toString("hex")}`,
    organizationId: session.organizationId,
    sourceApp: "hub",
    kind: "subscription",
    description: `${plan.planName} ${plan.billingCycle} renewal`,
    amount,
    currency: config.currency,
    provider: "wipay",
    providerEnvironment: config.environment as BillingOrder["providerEnvironment"],
    status: "pending",
    createdByUserId: session.userId,
    createdAt: now,
    updatedAt: now,
  };

  const checkout = createWipayCheckout({ order, config });
  const nextStore = cloneStore();
  nextStore.billingOrders.push(order);
  onboardingAudit(nextStore, "billing_checkout_created", {
    orderId: order.id,
    provider: order.provider,
    providerEnvironment: order.providerEnvironment,
    amount: order.amount,
    currency: order.currency,
    billingCycle: plan.billingCycle,
  }, session.userId, session.organizationId);
  await commitStore(nextStore);

  res.status(201).json({
    order: {
      id: order.id,
      description: order.description,
      amount: order.amount,
      currency: order.currency,
      status: order.status,
    },
    checkout,
  });
});

app.post("/api/billing/sandbox-test", requireAuth, requirePermission("billing"), async (req, res) => {
  const session = (req as any).user;
  const config = getWipayConfig(process.env);
  if (!config.ready || config.environment !== "sandbox") {
    return res.status(409).json({ error: "WiPay sandbox testing is not enabled." });
  }

  const amount = 10;
  const now = new Date().toISOString();
  const order: BillingOrder = {
    id: `v79_${Date.now().toString(36)}_${crypto.randomBytes(8).toString("hex")}`,
    organizationId: session.organizationId,
    sourceApp: "hub",
    kind: "subscription",
    description: "WiPay sandbox integration test",
    amount,
    currency: config.currency,
    provider: "wipay",
    providerEnvironment: "sandbox",
    status: "pending",
    createdByUserId: session.userId,
    createdAt: now,
    updatedAt: now,
  };

  const checkout = createWipayCheckout({ order, config });
  const nextStore = cloneStore();
  nextStore.billingOrders.push(order);
  onboardingAudit(nextStore, "billing_sandbox_checkout_created", {
    orderId: order.id,
    amount: order.amount,
    currency: order.currency,
  }, session.userId, session.organizationId);
  await commitStore(nextStore);

  res.status(201).json({
    order: {
      id: order.id,
      description: order.description,
      amount: order.amount,
      currency: order.currency,
      status: order.status,
    },
    checkout,
  });
});

app.get("/api/billing/wipay/return", async (req, res) => {
  const config = getWipayConfig(process.env);
  const orderId = String(req.query.order_id || "").trim();
  const appUrl = String(process.env.APP_URL || "https://hub.v79sl.com").replace(/\/$/, "");
  const redirect = (status: string, reason = "", order?: BillingOrder) => {
    const url = new URL(order ? billingOrderReturnUrl(order) : (appUrl || "https://hub.v79sl.com"));
    url.searchParams.set("payment", status);
    if (orderId) url.searchParams.set("order", orderId);
    if (reason) url.searchParams.set("payment_reason", reason);
    return res.redirect(302, url.toString());
  };

  if (!orderId || orderId.length > 64) return redirect("error", "invalid_order");
  const nextStore = cloneStore();
  const order = nextStore.billingOrders.find(item => item.id === orderId);
  if (!order) return redirect("error", "order_not_found");

  const query = req.query as Record<string, unknown>;
  const verification = verifyWipayReturn({ query, expectedOrder: order, config });
  const now = new Date().toISOString();

  if (order.status === "paid") {
    const sameTransaction = Boolean(order.providerTransactionId && order.providerTransactionId === verification.transactionId);
    return redirect(sameTransaction ? "success" : "error", sameTransaction ? "already_processed" : "order_already_paid", order);
  }

  const replay = verification.ok && nextStore.billingOrders.some(
    item => item.id !== order.id && item.providerTransactionId && item.providerTransactionId === verification.transactionId,
  );
  const verified = Boolean(verification.ok && !replay);
  const reason = replay ? "transaction_replay" : verification.reason;

  nextStore.billingPaymentEvents.push({
    id: crypto.randomUUID(),
    provider: "wipay",
    orderId: order.id,
    ...(verification.transactionId ? { transactionId: verification.transactionId } : {}),
    status: String(req.query.status || "unknown").slice(0, 30),
    verified,
    reason,
    ...(verification.amount !== undefined ? { amount: verification.amount } : {}),
    ...(verification.currency ? { currency: verification.currency } : {}),
    ...(verification.message ? { message: verification.message } : {}),
    createdAt: now,
  });
  if (nextStore.billingPaymentEvents.length > 5000) nextStore.billingPaymentEvents = nextStore.billingPaymentEvents.slice(-5000);

  if (!verified) {
    if (["failed", "error"].includes(String(req.query.status || "").toLowerCase())) {
      order.status = "failed";
      order.updatedAt = now;
    }
    onboardingAudit(nextStore, "billing_payment_rejected", { orderId: order.id, reason }, order.createdByUserId, order.organizationId);
    await commitStore(nextStore);
    return redirect("failed", reason, order);
  }

  order.status = "paid";
  order.providerTransactionId = verification.transactionId;
  order.providerMessage = verification.message || "WiPay payment verified";
  order.paidAt = now;
  order.updatedAt = now;

  if (order.providerEnvironment === "sandbox") {
    onboardingAudit(nextStore, "billing_sandbox_payment_verified", {
      orderId: order.id,
      transactionId: verification.transactionId,
      amount: order.amount,
      currency: order.currency,
      sourceApp: order.sourceApp,
    }, order.createdByUserId, order.organizationId);
    await commitStore(nextStore);
    return redirect("success", "sandbox_verified_no_entitlement_change", order);
  }

  if (order.sourceApp === "hub" && order.kind === "subscription") {
    const billedOrganizationId = order.organizationId;
    if (!billedOrganizationId) {
      onboardingAudit(nextStore, "billing_payment_rejected", { orderId: order.id, reason: "subscription_organization_missing" }, order.createdByUserId);
      await commitStore(nextStore);
      return redirect("error", "subscription_organization_missing", order);
    }
    let plan = nextStore.organizationPlans.find(item => item.organizationId === billedOrganizationId);
    if (!plan) {
      const fallback = organizationPlanFor(nextStore, billedOrganizationId);
      plan = { ...fallback, createdAt: now, updatedAt: now };
      nextStore.organizationPlans.push(plan);
    }
    if (plan.billingCycle === "monthly" || plan.billingCycle === "annual") {
      // Never extend a paid period from an administrator-editable renewal label.
      // Only a previously verified paid-through value may carry forward.
      const currentPaidThrough = plan.accessPolicyType === "paid" && plan.paidThroughAt
        ? new Date(plan.paidThroughAt) : null;
      const base = currentPaidThrough && Number.isFinite(currentPaidThrough.getTime()) &&
        currentPaidThrough.getTime() > Date.now() ? currentPaidThrough : new Date();
      const paidThroughAt = addBillingPeriod(base, plan.billingCycle).toISOString();
      plan.renewalDate = paidThroughAt.slice(0, 10);
      plan.paidThroughAt = paidThroughAt;
      plan.accessPolicyType = "paid";
      plan.status = "active";
      plan.updatedAt = now;
    }
  }

  onboardingAudit(nextStore, "billing_payment_verified", {
    orderId: order.id,
    transactionId: verification.transactionId,
    amount: order.amount,
    currency: order.currency,
    providerEnvironment: order.providerEnvironment,
  }, order.createdByUserId, order.organizationId);
  await commitStore(nextStore);
  return redirect("success", "", order);
});

app.get("/api/security/mfa/status", requireAuth, (req, res) => {
  const session = (req as any).user;
  const user = store.users.find(item => item.id === session.userId);
  if (!user) return res.status(404).json({ error: "User record not found" });
  res.setHeader("Cache-Control", "no-store");
  res.json({
    enabled: Boolean(user.mfaEnabled),
    mandatory: isPlatformOperatorIdentity(user.id, session.organizationId) && process.env.V79_REQUIRE_ADMIN_MFA === "1",
    method: user.mfaEnabled ? "totp" : null,
  });
});

app.post("/api/security/mfa/setup", requireAuth, async (req, res) => {
  const session = (req as any).user;
  const user = store.users.find(item => item.id === session.userId);
  if (!user) return res.status(404).json({ error: "User record not found" });
  if (hubSecurityKey.length < 32) return res.status(503).json({ error: "MFA encryption is not configured." });
  if (user.mfaEnabled) return res.status(409).json({ error: "MFA is already enabled." });
  let secret: string | undefined;
  const pendingAge = user.mfaPendingCreatedAt ? Date.now() - new Date(user.mfaPendingCreatedAt).getTime() : Number.POSITIVE_INFINITY;
  if (user.mfaPendingSecretEnc && Number.isFinite(pendingAge) && pendingAge >= 0 && pendingAge < 30 * 60_000) {
    try { secret = decryptTotpSecret(user.mfaPendingSecretEnc, hubSecurityKey); } catch {}
  }
  if (!secret) {
    secret = generateTotpSecret();
    user.mfaPendingSecretEnc = encryptTotpSecret(secret, hubSecurityKey);
    user.mfaPendingCreatedAt = new Date().toISOString();
    await saveStore(store);
  }
  const challenge = createMfaChallenge(user.id, session.organizationId, "setup", secret);
  res.json({
    challengeId: challenge.id,
    secret,
    provisioningUri: totpProvisioningUri({
      secret,
      account: normalizeEmail(user.email) || user.username,
      issuer: "V79 Hub",
    }),
  });
});

app.post("/api/security/mfa/confirm", requireAuth, async (req, res) => {
  const session = (req as any).user;
  const challenge = mfaChallenges.get(String(req.body?.challengeId || ""));
  const code = String(req.body?.code || "");
  if (!challenge || challenge.userId !== session.userId || challenge.organizationId !== session.organizationId || challenge.mode !== "setup" || challenge.expiresAt <= Date.now()) {
    return res.status(400).json({ error: "MFA setup expired. Start again." });
  }
  if (!challenge.secret || !verifyTotp(challenge.secret, code, Date.now(), 2)) return res.status(400).json({ error: "Invalid authentication code. Confirm the setup key and automatic date/time on your authenticator device." });
  const user = store.users.find(item => item.id === session.userId);
  if (!user) return res.status(404).json({ error: "User record not found" });
  user.mfaSecretEnc = encryptTotpSecret(challenge.secret, hubSecurityKey);
  user.mfaEnabled = true;
  delete user.mfaPendingSecretEnc;
  delete user.mfaPendingCreatedAt;
  mfaChallenges.delete(challenge.id);
  onboardingAudit(store, "mfa_enabled", { method: "totp" }, user.id, session.organizationId);
  await saveStore(store);
  res.json({ success: true, enabled: true });
});

app.post("/api/security/mfa/disable", requireAuth, async (req, res) => {
  const session = (req as any).user;
  const user = store.users.find(item => item.id === session.userId);
  if (!user) return res.status(404).json({ error: "User record not found" });
  if (isPlatformOperatorIdentity(user.id, session.organizationId) && process.env.V79_REQUIRE_ADMIN_MFA === "1") {
    return res.status(403).json({ error: "MFA is mandatory for the V79 platform administrator." });
  }
  if (!user.mfaEnabled || !user.mfaSecretEnc) return res.status(409).json({ error: "MFA is not enabled." });
  const password = String(req.body?.password || "");
  const code = String(req.body?.code || "");
  if (!checkPassword(password, user.password)) return res.status(401).json({ error: "Current password is incorrect." });
  let secret = "";
  try { secret = decryptTotpSecret(user.mfaSecretEnc, hubSecurityKey); }
  catch { return res.status(503).json({ error: "MFA verification is unavailable." }); }
  if (!verifyTotp(secret, code, Date.now(), 2)) return res.status(401).json({ error: "Invalid authentication code." });
  user.mfaEnabled = false;
  delete user.mfaSecretEnc;
  onboardingAudit(store, "mfa_disabled", {}, user.id, session.organizationId);
  await saveStore(store);
  res.json({ success: true, enabled: false });
});

app.use("/api", requireAuth);

app.get("/api/team/invitations", requireWorkspaceOwner, (req, res) => {
  const organizationId = (req as any).user.organizationId;
  res.setHeader("Cache-Control", "no-store");
  res.json({
    invitations: [...store.teamInvitations]
      .filter(invitation => invitation.organizationId === organizationId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map(invitation => ({
        id: invitation.id,
        email: invitation.email,
        role: invitation.role,
        permissions: invitation.permissions,
        appIds: normalizeTeamAppIds(invitation.appIds, invitation.organizationId),
        status: teamInvitationStatus(invitation),
        expiresAt: invitation.expiresAt,
        createdAt: invitation.createdAt,
        acceptedAt: invitation.acceptedAt || null,
        revokedAt: invitation.revokedAt || null,
      })),
  });
});

app.post("/api/team/invitations", requireWorkspaceOwner, async (req, res) => {
  const session = (req as any).user;
  const organizationId = session.organizationId;
  const organization = store.organizations.find(org => org.id === organizationId && org.status === "active");
  if (!organization) return res.status(409).json({ error: "Workspace is not active" });

  const email = validEmail(req.body?.email);
  const role = req.body?.role;
  const requestedAppIds = req.body?.appIds === undefined ? [] : req.body.appIds;
  const expiresInHours = req.body?.expiresInHours === undefined ? 72 : Number(req.body.expiresInHours);
  if (!email || !["manager", "staff", "viewer"].includes(role)) {
    return res.status(400).json({ error: "A valid email and team role are required" });
  }
  if (!Array.isArray(requestedAppIds) || requestedAppIds.some(appId =>
    typeof appId !== "string" ||
    !teamAssignableAppIds.has(appId) ||
    !organizationCanAccessApp(store, organizationId, appId, posIdentity.organizationId)
  )) {
    return res.status(400).json({ error: "Team app access must use enabled POS, Tiquet or Marketing apps only" });
  }
  if (!Number.isInteger(expiresInHours) || expiresInHours < 1 || expiresInHours > 168) {
    return res.status(400).json({ error: "Invitation expiry must be between 1 and 168 hours" });
  }

  const existingUser = store.users.find(user =>
    normalizeEmail(user.email) === email || user.username.toLowerCase() === email
  );
  if (existingUser && activeMembership(store, existingUser.id, organizationId)) {
    return res.status(409).json({ error: "This person is already a member of the workspace" });
  }
  const duplicate = store.teamInvitations.find(invitation =>
    invitation.organizationId === organizationId &&
    invitation.email === email &&
    teamInvitationStatus(invitation) === "pending"
  );
  if (duplicate) return res.status(409).json({ error: "A pending invitation already exists for this email" });

  const permissions = normalizePermissions(req.body?.permissions, role);
  const appIds = normalizeTeamAppIds(requestedAppIds, organizationId);
  const token = crypto.randomBytes(32).toString("base64url");
  const now = new Date();
  const invitation: TeamInvitation = {
    id: crypto.randomUUID(),
    organizationId,
    email,
    role,
    permissions,
    appIds,
    tokenHash: inviteHash(token),
    status: "pending",
    expiresAt: new Date(now.getTime() + expiresInHours * 60 * 60 * 1000).toISOString(),
    createdAt: now.toISOString(),
    createdByUserId: session.userId,
  };

  const nextStore = cloneStore();
  nextStore.teamInvitations.push(invitation);
  onboardingAudit(nextStore, "team_invitation_created", {
    invitationId: invitation.id,
    email,
    role,
    permissions,
    appIds,
    expiresAt: invitation.expiresAt,
  }, session.userId, organizationId);
  await commitStore(nextStore);

  const baseUrl = process.env.APP_URL
    ? new URL(process.env.APP_URL).origin
    : `${req.protocol}://${req.get("host")}`;
  const inviteUrl = new URL("/", baseUrl);
  inviteUrl.hash = "teamInvite=" + encodeURIComponent(token);
  let emailDeliveryStatus = "not_configured";
  if (transactionalEmail) {
    try {
      emailDeliveryStatus = await transactionalEmail.sendInvitation({
        to:email,inviteUrl:inviteUrl.toString(),invitationId:invitation.id,
        kind:"team",expiresAt:invitation.expiresAt,
      }) ? "accepted_by_provider" : "provider_rejected";
    } catch {
      emailDeliveryStatus = "delivery_unavailable";
    }
  }
  res.setHeader("Cache-Control", "no-store");
  res.status(201).json({
    invitation: {
      id: invitation.id,
      email: invitation.email,
      role: invitation.role,
      permissions: invitation.permissions,
      appIds: invitation.appIds,
      status: invitation.status,
      expiresAt: invitation.expiresAt,
      createdAt: invitation.createdAt,
    },
    inviteUrl: inviteUrl.toString(),
    emailDeliveryStatus,
  });
});

app.post("/api/team/invitations/:id/revoke", requireWorkspaceOwner, async (req, res) => {
  const session = (req as any).user;
  const invitation = store.teamInvitations.find(item =>
    item.id === req.params.id && item.organizationId === session.organizationId
  );
  if (!invitation) return res.status(404).json({ error: "Team invitation not found" });
  if (teamInvitationStatus(invitation) !== "pending") {
    return res.status(409).json({ error: "Only pending team invitations can be revoked" });
  }

  const nextStore = cloneStore();
  const target = nextStore.teamInvitations.find(item => item.id === invitation.id)!;
  target.status = "revoked";
  target.revokedAt = new Date().toISOString();
  target.revokedByUserId = session.userId;
  onboardingAudit(nextStore, "team_invitation_revoked", {
    invitationId: target.id,
    email: target.email,
  }, session.userId, session.organizationId);
  await commitStore(nextStore);
  res.json({ success: true, status: "revoked" });
});

const customerProvisionProducts = {
  pos: "app-v79pos",
  ffpro: "app-ffpro",
  tiquet: "app-tiquet",
  marketing: "app-marketing",
} as const;
type CustomerProvisionProduct = keyof typeof customerProvisionProducts;

function customerOwner(currentStore: AppStore, organizationId: string) {
  const membership = currentStore.memberships.find(member =>
    member.organizationId === organizationId && member.status === "active" && member.role === "owner"
  );
  return membership ? currentStore.users.find(user => user.id === membership.userId) || null : null;
}

function customerAdminRecord(currentStore: AppStore, organization: Organization) {
  const owner = customerOwner(currentStore, organization.id);
  const memberIds = new Set(currentStore.memberships
    .filter(member => member.organizationId === organization.id && member.status === "active")
    .map(member => member.userId));
  const members = currentStore.users.filter(user => memberIds.has(user.id));
  const plan = organizationPlanFor(currentStore, organization.id);
  const plannedAppIds = plan.appIds?.length ? plan.appIds : rawEntitledAppIds(currentStore, organization.id);
  const mappings = currentStore.appTenantMappings.filter(mapping => mapping.organizationId === organization.id);
  const apps = plannedAppIds.map(appId => {
    const app = currentStore.ecosystemApps.find(item => item.id === appId);
    const mapping = mappings.find(item => item.appId === appId);
    return {
      id: appId,
      name: app?.name || appId,
      shortName: app?.shortName || appId,
      provisioningStatus: ["paused", "cancelled"].includes(plan.status)
        ? "disabled_by_plan"
        : tenantMappedAppIds.has(appId)
          ? (mapping?.status || "pending")
          : "not_required",
    };
  });
  const invite = [...currentStore.ownerInvitations]
    .filter(item => item.organizationId === organization.id)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  const activityTimes = [
    organization.createdAt,
    ...members.map(member => member.lastLogin).filter((value): value is string => Boolean(value)),
    ...currentStore.auditEvents.filter(event => event.organizationId === organization.id).map(event => event.createdAt),
  ].filter(Boolean);
  const lastActivityAt = activityTimes.sort().at(-1) || organization.createdAt;
  return {
    id: organization.id,
    name: organization.name,
    slug: organization.slug,
    lifecycle: customerLifecycle(currentStore, organization),
    organizationStatus: organization.status,
    owner: owner ? {
      id: owner.id,
      name: owner.fullName || owner.username,
      email: normalizeEmail(owner.email) || owner.username,
      lastLogin: owner.lastLogin || null,
      mfaEnabled: Boolean(owner.mfaEnabled),
    } : null,
    memberCount: members.length,
    apps,
    plan,
    invitation: invite ? {
      id: invite.id,
      status: invitationStatus(invite),
      email: invite.email,
      createdAt: invite.createdAt,
      acceptedAt: invite.acceptedAt || null,
      expiresAt: invite.expiresAt,
    } : null,
    createdAt: organization.createdAt,
    lastActivityAt,
  };
}

async function provisionCustomerProduct(product: CustomerProvisionProduct, organizationId: string, actorUserId: string) {
  const appId = customerProvisionProducts[product];
  const existing = store.appTenantMappings.find(mapping => mapping.organizationId === organizationId && mapping.appId === appId);
  if (existing?.status === "active") return { product, appId, status: "active" as const, skipped: true };

  if (product === "pos") {
    const target = posProvisioningTarget(store, organizationId);
    const provisioned = await provisionPosWorkspace(target.organization, target.owner.id);
    if (!provisioned.ok) throw new Error(provisioned.error);
    await commitStore(activatePosTenantMapping(store, organizationId, provisioned.organizationId, actorUserId, new Date().toISOString()) as AppStore);
  } else if (product === "ffpro") {
    const target = ffproProvisioningTarget(store, organizationId);
    const provisioned = await provisionFfproWorkspace(target.organization, target.owner);
    if (!provisioned.ok) throw new Error(provisioned.error);
    await commitStore(activateFfproTenantMapping(store, organizationId, provisioned.organizationId, provisioned.financeUserId, actorUserId, new Date().toISOString()) as AppStore);
  } else if (product === "tiquet") {
    const target = tiquetProvisioningTarget(store, organizationId);
    const provisioned = await provisionTiquetWorkspace(target.organization, target.owner);
    if (!provisioned.ok) throw new Error(provisioned.error);
    await commitStore(activateTiquetTenantMapping(store, organizationId, provisioned.organizationId, provisioned.accountId, provisioned.userId, actorUserId, new Date().toISOString()) as AppStore);
  } else {
    const target = marketingProvisioningTarget(store, organizationId);
    const provisioned = await provisionMarketingWorkspace(target.organization, target.owner);
    if (!provisioned.ok) throw new Error(provisioned.error);
    await commitStore(activateMarketingTenantMapping(store, organizationId, provisioned.organizationId, provisioned.businessId, provisioned.userId, actorUserId, new Date().toISOString()) as AppStore);
  }

  return { product, appId, status: "active" as const, skipped: false };
}

app.get("/api/admin/customers", requirePlatformOperator, (_req, res) => {
  const customers = store.organizations
    .filter(organization => organization.id !== posIdentity.organizationId)
    .map(organization => customerAdminRecord(store, organization))
    .sort((a, b) => b.lastActivityAt.localeCompare(a.lastActivityAt));

  const invited = store.ownerInvitations
    .filter(invitation => !store.organizations.some(org => org.id === invitation.organizationId))
    .filter(invitation => invitationStatus(invitation) === "pending")
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map(invitation => ({
      id: invitation.organizationId,
      name: invitation.organizationName,
      slug: invitation.organizationSlug,
      lifecycle: "invited",
      organizationStatus: null,
      owner: { id: null, name: invitation.email, email: invitation.email, lastLogin: null, mfaEnabled: false },
      memberCount: 0,
      apps: invitation.appIds.map(appId => {
        const app = store.ecosystemApps.find(item => item.id === appId);
        return { id: appId, name: app?.name || appId, shortName: app?.shortName || appId, provisioningStatus: "waiting_for_acceptance" };
      }),
      plan: null,
      invitation: {
        id: invitation.id,
        status: "pending",
        email: invitation.email,
        createdAt: invitation.createdAt,
        acceptedAt: null,
        expiresAt: invitation.expiresAt,
      },
      createdAt: invitation.createdAt,
      lastActivityAt: invitation.createdAt,
    }));

  const assignableApps = customerAssignableAppIds
    .map(appId => store.ecosystemApps.find(app => app.id === appId))
    .filter((app): app is EcosystemApp => Boolean(app))
    .map(app => ({ id: app.id, name: app.name, shortName: app.shortName }));
  res.setHeader("Cache-Control", "no-store");
  res.json({ customers, invited, assignableApps });
});

app.post("/api/admin/customers/:organizationId/provision", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  const organization = store.organizations.find(org => org.id === organizationId && org.id !== posIdentity.organizationId);
  if (!organization) return res.status(404).json({ error: "Customer organization not found" });
  if (organization.status !== "active") return res.status(409).json({ error: "Customer organization must be active before provisioning." });

  const enabled = new Set(rawEntitledAppIds(store, organizationId));
  const requested = Array.isArray(req.body?.appIds) ? req.body.appIds : [...tenantMappedAppIds].filter(appId => enabled.has(appId));
  if (requested.some((appId: unknown) => typeof appId !== "string" || !tenantMappedAppIds.has(appId as string) || !enabled.has(appId as string))) {
    return res.status(400).json({ error: "Provision only enabled tenant-mapped apps for this customer." });
  }

  const actorUserId = (req as any).user.userId;
  const products = [...new Set(requested as string[])]
    .map(appId => (Object.entries(customerProvisionProducts).find(([, value]) => value === appId)?.[0] || "") as CustomerProvisionProduct)
    .filter(Boolean);

  const results: Array<{ product: string; appId: string; status: string; skipped?: boolean; error?: string }> = [];
  for (const product of products) {
    try {
      results.push(await provisionCustomerProduct(product, organizationId, actorUserId));
    } catch (error) {
      results.push({
        product,
        appId: customerProvisionProducts[product],
        status: "failed",
        error: error instanceof Error ? error.message : "Provisioning failed",
      });
    }
  }

  const failed = results.filter(result => result.status === "failed");
  res.setHeader("Cache-Control", "no-store");
  res.status(failed.length ? 207 : 200).json({
    success: failed.length === 0,
    organizationId,
    lifecycle: customerLifecycle(store, store.organizations.find(org => org.id === organizationId)!),
    results,
  });
});

app.put("/api/admin/customers/:organizationId/plan", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  const organization = store.organizations.find(org => org.id === organizationId && org.id !== posIdentity.organizationId);
  if (!organization) return res.status(404).json({ error: "Customer organization not found" });

  const planName = typeof req.body?.planName === "string" ? req.body.planName.trim() : "";
  const status = String(req.body?.status || "");
  const billingCycle = String(req.body?.billingCycle || "");
  const priceValue = req.body?.priceXcd;
  const priceXcd = priceValue === null || priceValue === "" || priceValue === undefined ? undefined : Number(priceValue);
  const renewalDate = typeof req.body?.renewalDate === "string" && req.body.renewalDate.trim() ? req.body.renewalDate.trim() : undefined;
  const appIds = req.body?.appIds;
  const reason = typeof req.body?.reason === "string" ? req.body.reason.trim() : "";

  if (planName.length < 2 || planName.length > 80 ||
      !["active", "trial", "paused", "cancelled"].includes(status) ||
      !["monthly", "annual", "custom"].includes(billingCycle) ||
      (priceXcd !== undefined && (!Number.isFinite(priceXcd) || priceXcd < 0 || priceXcd > 1_000_000)) ||
      (renewalDate !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(renewalDate)) ||
      !Array.isArray(appIds) || appIds.some((appId: unknown) => typeof appId !== "string" || !customerAssignableAppIds.includes(appId as string)) ||
      reason.length < 5 || reason.length > 500) {
    return res.status(400).json({ error: "Valid plan, billing, app selection and a change reason are required." });
  }

  const selected = new Set(appIds as string[]);
  const now = new Date().toISOString();
  const nextStore = cloneStore();
  if (!Array.isArray(nextStore.organizationPlans)) nextStore.organizationPlans = [];
  const existingPlan = nextStore.organizationPlans.find(plan => plan.organizationId === organizationId);
  // Trials cannot be restarted by editing a plan. Paid activation needs verified billing.
  if (status === "active" && !(existingPlan?.accessPolicyType === "paid" &&
      Number.isFinite(Date.parse(existingPlan.paidThroughAt || "")) &&
      Date.parse(existingPlan.paidThroughAt || "") > Date.now())) {
    return res.status(409).json({ error: "Verified payment required before activating a paid customer plan." });
  }
  if (status === "trial" && existingPlan?.status !== "trial") {
    return res.status(409).json({ error: "A trial cannot be restarted through plan administration." });
  }
  const nextPlan: OrganizationPlan = {
    organizationId,
    planName,
    status: status as OrganizationPlan["status"],
    ...(existingPlan?.accessPolicyType ? { accessPolicyType: existingPlan.accessPolicyType } : {}),
    ...(existingPlan?.trialStartedAt ? { trialStartedAt: existingPlan.trialStartedAt } : {}),
    ...(existingPlan?.trialEndsAt ? { trialEndsAt: existingPlan.trialEndsAt } : {}),
    ...(existingPlan?.paidThroughAt ? { paidThroughAt: existingPlan.paidThroughAt } : {}),
    billingCycle: billingCycle as OrganizationPlan["billingCycle"],
    appIds: [...selected],
    ...(priceXcd !== undefined ? { priceXcd } : {}),
    ...(renewalDate ? { renewalDate } : {}),
    createdAt: existingPlan?.createdAt || now,
    updatedAt: now,
  };
  if (existingPlan) Object.assign(existingPlan, nextPlan);
  else nextStore.organizationPlans.push(nextPlan);

  for (const appId of customerAssignableAppIds) {
    const entitlement = nextStore.appEntitlements.find(entry => entry.organizationId === organizationId && entry.appId === appId);
    const enabled = selected.has(appId) && ["active", "trial"].includes(status);
    if (entitlement) entitlement.enabled = enabled;
    else if (enabled) nextStore.appEntitlements.push({ organizationId, appId, enabled: true, createdAt: now });

    if (tenantMappedAppIds.has(appId)) {
      const mapping = nextStore.appTenantMappings.find(item => item.organizationId === organizationId && item.appId === appId);
      if (enabled) {
        if (!mapping) nextStore.appTenantMappings.push({ organizationId, appId, status: "pending", createdAt: now, updatedAt: now });
        else if (mapping.status === "disabled") {
          mapping.status = "pending";
          mapping.updatedAt = now;
        }
      } else if (mapping && mapping.status !== "disabled") {
        mapping.status = "disabled";
        mapping.updatedAt = now;
      }
    }
  }

  onboardingAudit(nextStore, "customer_plan_updated", {
    planName,
    status,
    billingCycle,
    priceXcd: priceXcd ?? null,
    renewalDate: renewalDate || null,
    appIds: [...selected],
    reason,
  }, (req as any).user.userId, organizationId);
  await commitStore(nextStore);
  res.json({ success: true, customer: customerAdminRecord(store, store.organizations.find(org => org.id === organizationId)!) });
});

app.post("/api/admin/customers/:organizationId/status", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  const organization = store.organizations.find(org => org.id === organizationId && org.id !== posIdentity.organizationId);
  if (!organization) return res.status(404).json({ error: "Customer organization not found" });
  const status = String(req.body?.status || "");
  const reason = typeof req.body?.reason === "string" ? req.body.reason.trim() : "";
  const confirmName = typeof req.body?.confirmName === "string" ? req.body.confirmName.trim() : "";
  if (!["active", "suspended"].includes(status) || reason.length < 5 || reason.length > 500 || confirmName !== organization.name) {
    return res.status(400).json({ error: "Type the exact business name and provide a reason to change customer status." });
  }

  const nextStore = cloneStore();
  const target = nextStore.organizations.find(org => org.id === organizationId)!;
  target.status = status as Organization["status"];
  onboardingAudit(nextStore, status === "suspended" ? "customer_suspended" : "customer_reactivated", {
    reason,
    previousStatus: organization.status,
  }, (req as any).user.userId, organizationId);
  await commitStore(nextStore);
  if (status === "suspended") deleteSessionsWhere(session => session.organizationId === organizationId);
  res.json({ success: true, customer: customerAdminRecord(store, store.organizations.find(org => org.id === organizationId)!) });
});

app.get("/api/admin/audit", requirePlatformOperator, (req, res) => {
  const requestedLimit = Number(req.query.limit || 200);
  const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(500, Math.floor(requestedLimit))) : 200;
  const organizationId = typeof req.query.organizationId === "string" ? req.query.organizationId : "";
  const type = typeof req.query.type === "string" ? req.query.type.trim().toLowerCase() : "";
  const events = [...store.auditEvents]
    .filter(event => !organizationId || event.organizationId === organizationId)
    .filter(event => !type || event.type.toLowerCase().includes(type))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .slice(0, limit)
    .map(event => {
      const actor = event.actorUserId ? store.users.find(user => user.id === event.actorUserId) : null;
      const organization = event.organizationId ? store.organizations.find(org => org.id === event.organizationId) : null;
      return {
        ...event,
        actor: actor ? { id: actor.id, name: actor.fullName || actor.username, email: normalizeEmail(actor.email) || actor.username } : null,
        organization: organization ? { id: organization.id, name: organization.name, slug: organization.slug } : null,
      };
    });
  res.setHeader("Cache-Control", "no-store");
  res.json({ events });
});

app.get("/api/admin/onboarding/invitations", requirePlatformOperator, (_req, res) => {
  const invitations = [...store.ownerInvitations]
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map(invitation => ({
      id: invitation.id,
      organizationId: invitation.organizationId,
      organizationName: invitation.organizationName,
      organizationSlug: invitation.organizationSlug,
      email: invitation.email,
      appIds: invitation.appIds,
      status: invitationStatus(invitation),
      expiresAt: invitation.expiresAt,
      createdAt: invitation.createdAt,
      acceptedAt: invitation.acceptedAt || null,
      revokedAt: invitation.revokedAt || null,
      appMappings: store.appTenantMappings
        .filter(mapping => mapping.organizationId === invitation.organizationId)
        .map(mapping => ({
          appId: mapping.appId,
          status: mapping.status,
          externalTenantId: mapping.externalTenantId || null,
          externalOwnerId: mapping.externalOwnerId || null,
          updatedAt: mapping.updatedAt,
        })),
    }));
  const assignableApps = customerAssignableAppIds
    .map(appId => store.ecosystemApps.find(app => app.id === appId))
    .filter((app): app is EcosystemApp => Boolean(app))
    .map(app => ({ id: app.id, name: app.name, shortName: app.shortName }));
  const audit = store.auditEvents
    .filter(event => event.type.startsWith("owner_invitation_"))
    .slice(-50)
    .reverse();
  res.setHeader("Cache-Control", "no-store");
  res.json({ invitations, assignableApps, audit });
});

app.post("/api/admin/onboarding/invitations", requirePlatformOperator, async (req, res) => {
  const email = validEmail(req.body?.email);
  const organizationName = validBusinessName(req.body?.organizationName);
  const expiresInHours = Number(req.body?.expiresInHours ?? 72);
  const requestedApps = req.body?.appIds === undefined ? [] : req.body.appIds;
  if (!email || !organizationName || !Number.isFinite(expiresInHours) || expiresInHours < 1 || expiresInHours > 168 ||
      !Array.isArray(requestedApps) || requestedApps.some(appId => typeof appId !== "string" || !customerAssignableAppIds.includes(appId))) {
    return res.status(400).json({ error: "Valid business, email, app selection and expiry between 1 and 168 hours are required" });
  }

  const appIds = [...new Set(requestedApps as string[])];
  const duplicate = store.ownerInvitations.find(invitation =>
    invitationStatus(invitation) === "pending" &&
    invitation.email === email &&
    invitation.organizationName.toLowerCase() === organizationName.toLowerCase()
  );
  if (duplicate) return res.status(409).json({ error: "An active invitation already exists for this business and email" });

  let appUrl: URL;
  try {
    appUrl = new URL(process.env.APP_URL || "");
    const loopback = ["127.0.0.1", "localhost", "::1"].includes(appUrl.hostname);
    if (!["http:", "https:"].includes(appUrl.protocol) ||
        (process.env.NODE_ENV === "production" && appUrl.protocol !== "https:" && !loopback)) throw new Error("invalid app URL");
  } catch {
    return res.status(503).json({ error: "Hub public URL is not configured for invitations" });
  }

  const session = (req as any).user;
  const token = crypto.randomBytes(32).toString("base64url");
  const now = new Date();
  const invitation: OwnerInvitation = {
    id: crypto.randomUUID(),
    organizationId: crypto.randomUUID(),
    organizationName,
    organizationSlug: organizationSlug(organizationName, store),
    email,
    appIds,
    tokenHash: inviteHash(token),
    status: "pending",
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + expiresInHours * 60 * 60 * 1000).toISOString(),
    createdByUserId: session.userId,
  };

  const nextStore = cloneStore();
  nextStore.ownerInvitations.push(invitation);
  onboardingAudit(nextStore, "owner_invitation_created", {
    invitationId: invitation.id,
    email,
    organizationName,
    appIds,
    expiresAt: invitation.expiresAt,
  }, session.userId, invitation.organizationId);
  await commitStore(nextStore);

  const inviteUrl = new URL("/", appUrl);
  inviteUrl.hash = `invite=${encodeURIComponent(token)}`;
  let emailDeliveryStatus = "not_configured";
  if (transactionalEmail) {
    try {
      emailDeliveryStatus = await transactionalEmail.sendInvitation({
        to:email,inviteUrl:inviteUrl.toString(),invitationId:invitation.id,
        kind:"owner",expiresAt:invitation.expiresAt,
      }) ? "accepted_by_provider" : "provider_rejected";
    } catch {
      emailDeliveryStatus = "delivery_unavailable";
    }
  }
  res.setHeader("Cache-Control", "no-store");
  res.status(201).json({
    invitation: {
      id: invitation.id,
      organizationId: invitation.organizationId,
      organizationName: invitation.organizationName,
      organizationSlug: invitation.organizationSlug,
      email: invitation.email,
      appIds: invitation.appIds,
      status: invitation.status,
      expiresAt: invitation.expiresAt,
      createdAt: invitation.createdAt,
    },
    inviteUrl: inviteUrl.toString(),
    emailDeliveryStatus,
  });
});

app.post("/api/admin/onboarding/invitations/:id/revoke", requirePlatformOperator, async (req, res) => {
  const id = String(req.params.id || "");
  const invitation = store.ownerInvitations.find(item => item.id === id);
  if (!invitation) return res.status(404).json({ error: "Invitation not found" });
  if (invitation.status !== "pending") return res.status(409).json({ error: "Only pending invitations can be revoked" });

  const session = (req as any).user;
  const nextStore = cloneStore();
  const target = nextStore.ownerInvitations.find(item => item.id === id)!;
  target.status = "revoked";
  target.revokedAt = new Date().toISOString();
  target.revokedByUserId = session.userId;
  onboardingAudit(nextStore, "owner_invitation_revoked", {
    invitationId: target.id,
    email: target.email,
    organizationName: target.organizationName,
  }, session.userId, target.organizationId);
  await commitStore(nextStore);
  res.json({ success: true, status: "revoked" });
});

app.post("/api/admin/onboarding/organizations/:organizationId/apps/pos/provision", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  let target;
  try {
    target = posProvisioningTarget(store, organizationId);
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "POS workspace is not ready for provisioning" });
  }

  const provisioned = await provisionPosWorkspace(target.organization, target.owner.id);
  if (!provisioned.ok) {
    return res.status(provisioned.status).json({
      error: provisioned.error,
      ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
    });
  }

  let nextStore: AppStore;
  try {
    nextStore = activatePosTenantMapping(
      store,
      organizationId,
      provisioned.organizationId,
      (req as any).user.userId,
      new Date().toISOString(),
    ) as AppStore;
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "POS tenant mapping could not be activated" });
  }
  await commitStore(nextStore);
  res.setHeader("Cache-Control", "no-store");
  res.json({
    success: true,
    organizationId,
    ownerUserId: provisioned.ownerUserId,
    mapping: posTenantMapping(store, organizationId),
  });
});

app.post("/api/admin/onboarding/organizations/:organizationId/apps/ffpro/provision", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  let target;
  try {
    target = ffproProvisioningTarget(store, organizationId);
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "FFPRO workspace is not ready for provisioning" });
  }

  const provisioned = await provisionFfproWorkspace(target.organization, target.owner);
  if (!provisioned.ok) {
    return res.status(provisioned.status).json({
      error: provisioned.error,
      ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
    });
  }

  let nextStore: AppStore;
  try {
    nextStore = activateFfproTenantMapping(
      store,
      organizationId,
      provisioned.organizationId,
      provisioned.financeUserId,
      (req as any).user.userId,
      new Date().toISOString(),
    ) as AppStore;
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "FFPRO tenant mapping could not be activated" });
  }
  await commitStore(nextStore);
  res.setHeader("Cache-Control", "no-store");
  res.json({
    success: true,
    organizationId,
    ownerHubUserId: provisioned.ownerHubUserId,
    financeUserId: provisioned.financeUserId,
    mapping: ffproTenantMapping(store, organizationId),
  });
});

app.post("/api/admin/onboarding/organizations/:organizationId/apps/tiquet/provision", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  let target;
  try {
    target = tiquetProvisioningTarget(store, organizationId);
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "Tiquet workspace is not ready for provisioning" });
  }

  const provisioned = await provisionTiquetWorkspace(target.organization, target.owner);
  if (!provisioned.ok) {
    return res.status(provisioned.status).json({
      error: provisioned.error,
      ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
    });
  }

  let nextStore: AppStore;
  try {
    nextStore = activateTiquetTenantMapping(
      store,
      organizationId,
      provisioned.organizationId,
      provisioned.accountId,
      provisioned.userId,
      (req as any).user.userId,
      new Date().toISOString(),
    ) as AppStore;
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "Tiquet tenant mapping could not be activated" });
  }
  await commitStore(nextStore);
  res.setHeader("Cache-Control", "no-store");
  res.json({
    success: true,
    organizationId,
    ownerHubUserId: provisioned.ownerHubUserId,
    accountId: provisioned.accountId,
    userId: provisioned.userId,
    mapping: tiquetTenantMapping(store, organizationId),
  });
});

app.post("/api/admin/onboarding/organizations/:organizationId/apps/marketing/provision", requirePlatformOperator, async (req, res) => {
  if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
  const organizationId = String(req.params.organizationId || "");
  let target;
  try {
    target = marketingProvisioningTarget(store, organizationId);
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "Marketing workspace is not ready for provisioning" });
  }

  const provisioned = await provisionMarketingWorkspace(target.organization, target.owner);
  if (!provisioned.ok) {
    return res.status(provisioned.status).json({
      error: provisioned.error,
      ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
    });
  }

  let nextStore: AppStore;
  try {
    nextStore = activateMarketingTenantMapping(
      store,
      organizationId,
      provisioned.organizationId,
      provisioned.businessId,
      provisioned.userId,
      (req as any).user.userId,
      new Date().toISOString(),
    ) as AppStore;
  } catch (error) {
    return res.status(409).json({ error: error instanceof Error ? error.message : "Marketing tenant mapping could not be activated" });
  }
  await commitStore(nextStore);
  res.setHeader("Cache-Control", "no-store");
  res.json({
    success: true,
    organizationId,
    ownerHubUserId: provisioned.ownerHubUserId,
    businessId: provisioned.businessId,
    userId: provisioned.userId,
    mapping: marketingTenantMapping(store, organizationId),
  });
});

type DashboardProduct = "pos" | "ffpro" | "tiquet" | "marketing" | "academy" | "lasertag" | "website" | "games";
const dashboardSources: Record<DashboardProduct, string> = {
  pos: posServiceUrl,
  ffpro: process.env.FFPRO_INTERNAL_URL || "http://fire-finance-app:3010",
  tiquet: process.env.TIQUET_INTERNAL_URL || "http://v79-tiquet-manager:3050",
  marketing: process.env.MARKETING_INTERNAL_URL || "http://v79marketing-app:3070",
  academy: process.env.ACADEMY_INTERNAL_URL || "http://v79_course_builder:3030",
  lasertag: process.env.LASERTAG_INTERNAL_URL || "http://lasertag:5173",
  website: process.env.WEBSITE_INTERNAL_URL || "http://V79website:3000",
  games: process.env.GAMES_INTERNAL_URL || "http://gaming-studio-j:80",
};

const readonlyPlatformSecretFile = process.env.V79_READONLY_PLATFORM_SECRET_FILE || "/run/secrets/v79-readonly-platform-token";
const readonlyPlatformProducts = new Set(["lasertag", "website", "games"]);
function readReadonlyPlatformSecret() {
  const direct = String(process.env.V79_READONLY_PLATFORM_SHARED_SECRET || "").trim();
  if (direct) return direct;
  try { return fs.readFileSync(readonlyPlatformSecretFile, "utf8").trim(); } catch { return ""; }
}
function platformSigningSecret(product: string) {
  if (product === "pos") return posServiceSecret;
  return readonlyPlatformProducts.has(product) ? (readReadonlyPlatformSecret() || posSecret) : posSecret;
}

async function readDashboardSummary(product: DashboardProduct, organizationId: string) {
  if (organizationId !== posIdentity.organizationId && product === "academy") {
    return {
      status: "not_configured",
      metrics: {},
      generatedAt: null,
      accessMessage: "Academy uses a separate learner account. Hub-to-Academy learner linking is not enabled for customer workspaces.",
    };
  }
  if (organizationId !== posIdentity.organizationId && product === "lasertag") {
    return {
      status: "not_configured",
      metrics: {},
      generatedAt: null,
      accessMessage: "CombatZone / LaserTag is a Vision79-owned operation and is not shared with customer workspaces.",
    };
  }
  if (organizationId !== posIdentity.organizationId && product === "website") {
    return {
      status: "not_configured",
      metrics: {},
      generatedAt: null,
      accessMessage: "Vision79 website metrics are platform-owned and are not shared with customer workspaces.",
    };
  }
  if (organizationId !== posIdentity.organizationId && product === "games") {
    return {
      status: "not_configured",
      metrics: {},
      generatedAt: null,
      accessMessage: "Gaming Studio J metrics are Vision79-owned and are not shared with customer workspaces.",
    };
  }

  const customerPosReady = product === "pos" &&
    posTenantLaunchReady(store, organizationId, posIdentity.organizationId);
  const customerFfproReady = product === "ffpro" &&
    ffproTenantLaunchReady(store, organizationId, posIdentity.organizationId);
  const customerTiquetReady = product === "tiquet" &&
    tiquetTenantLaunchReady(store, organizationId, posIdentity.organizationId);
  const customerMarketingReady = product === "marketing" &&
    marketingTenantLaunchReady(store, organizationId, posIdentity.organizationId);
  if (organizationId !== posIdentity.organizationId && !customerPosReady && !customerFfproReady && !customerTiquetReady && !customerMarketingReady) {
    return { status: "not_configured", metrics: {}, generatedAt: null };
  }
  const signingSecret = platformSigningSecret(product);
  if (signingSecret.length < 32) {
    return { status: "misconfigured", error: "Platform summary signing is not configured." };
  }

  const ownerEmail = String(process.env.V79_HUB_ADMIN_EMAIL || "").trim().toLowerCase();
  const subject = product === "academy" ? ownerEmail : organizationId;
  if (!subject || (product === "academy" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(subject))) {
    return { status: "misconfigured", error: "Dashboard subject is not configured." };
  }

  const pathname = `/api/platform/summary/${encodeURIComponent(subject)}`;
  const fetchSummary = async () => {
    const timestamp = String(Date.now());
    const signature = signPlatformRequest({
      method: "GET",
      pathname,
      timestamp,
      body: "",
      secret: signingSecret,
    });
    return fetch(new URL(pathname, dashboardSources[product]), {
      headers: {
        "x-v79-service-id": "v79-hub",
        "x-v79-timestamp": timestamp,
        "x-v79-signature": signature,
      },
      signal: AbortSignal.timeout(product === "marketing" ? 2500 : 5000),
    });
  };

  try {
    const response = product === "marketing"
      ? await retryTransient(fetchSummary, { attempts: 2, delayMs: 150 })
      : await fetchSummary();
    const payload = await response.json().catch(() => ({})) as any;

    if (response.status === 404) {
      return { status: "needs_setup", httpStatus: 404, metrics: {}, generatedAt: null };
    }
    if (!response.ok) {
      return { status: "unavailable", httpStatus: response.status, metrics: {}, error: "Product summary unavailable." };
    }

    return {
      status: "ok",
      httpStatus: response.status,
      metrics: payload && typeof payload.metrics === "object" && payload.metrics ? payload.metrics : {},
      generatedAt: typeof payload.generatedAt === "string" ? payload.generatedAt : new Date().toISOString(),
      // Unlike generatedAt (which can be a Hub fallback), sourceReportedAt
      // is populated only when the product itself supplies a valid timestamp.
      sourceReportedAt: typeof payload.generatedAt === "string" && Number.isFinite(Date.parse(payload.generatedAt))
        ? new Date(Date.parse(payload.generatedAt)).toISOString() : null,
    };
  } catch {
    return { status: "unavailable", metrics: {}, error: "Product service is unavailable." };
  }
}

app.get("/api/dashboard/summary", async (req, res) => {
  const products: DashboardProduct[] = ["pos", "ffpro", "tiquet", "marketing", "academy", "lasertag", "website", "games"];
  const session = (req as any).user;
  const membership = activeMembership(store, session.userId, session.organizationId);
  const workspaceOwner = membership?.role === "owner";
  const platformOperator = isPlatformOperatorIdentity(session.userId, session.organizationId);
  const ownerOnlyProducts = new Set<DashboardProduct>(["pos", "ffpro", "tiquet", "marketing"]);

  const results = await Promise.all(products.map(async product => {
    const appId = dashboardProductAppIds[product];
    if (appId && !organizationCanAccessApp(store, session.organizationId, appId, posIdentity.organizationId)) {
      return [product, { status: "not_enabled", metrics: {}, generatedAt: null }] as const;
    }
    if (!appId && !platformOperator) {
      return [product, { status: "not_enabled", metrics: {}, generatedAt: null }] as const;
    }
    if (appId && membership?.role !== "owner" && !membershipCanAccessApp(membership, appId)) {
      return [product, { status: "restricted", metrics: {}, generatedAt: null, accessMessage: "This app is not assigned to your Hub account." }] as const;
    }
    if (ownerOnlyProducts.has(product) && !workspaceOwner) {
      return [product, {
        status: "restricted",
        metrics: {},
        generatedAt: null,
        accessMessage: product === "ffpro"
          ? "FFPRO finance metrics and full-account finance access are workspace-owner only. Share specific FFPRO projects with editors or viewers inside FFPRO."
          : "Workspace business KPIs remain owner-only even when a team member has role-mapped product access.",
      }] as const;
    }
    return [product, await readDashboardSummary(product, session.organizationId)] as const;
  }));

  res.setHeader("Cache-Control", "no-store");
  res.json({
    generatedAt: new Date().toISOString(),
    apps: Object.fromEntries(results),
  });
});

const serviceHealthPaths: Record<DashboardProduct, string> = {
  pos: "/health",
  ffpro: "/api/health",
  tiquet: "/health",
  marketing: "/api/health",
  academy: "/healthz",
  lasertag: "/health",
  website: "/api/health",
  games: "/healthz",
};

const dashboardProductAppIds: Partial<Record<DashboardProduct, string>> = {
  pos: "app-v79pos",
  ffpro: "app-ffpro",
  tiquet: "app-tiquet",
  marketing: "app-marketing",
  academy: "app-academy",
};

function connectionProductsForSession(userId: string, organizationId: string) {
  const membership = activeMembership(store, userId, organizationId);
  return (Object.keys(serviceHealthPaths) as DashboardProduct[]).filter(product => {
    const appId = dashboardProductAppIds[product];
    if (organizationId === posIdentity.organizationId) {
      if (!appId) return isPlatformOperatorIdentity(userId, organizationId);
      return organizationCanAccessApp(store, organizationId, appId, posIdentity.organizationId);
    }
    if (!appId || !organizationCanAccessApp(store, organizationId, appId, posIdentity.organizationId)) return false;
    if (membership?.role === "owner") return true;
    return membershipCanAccessApp(membership, appId);
  });
}

app.get("/api/connections/status", requirePermission("connections"), async (req, res) => {
  const session = (req as any).user;
  const products = connectionProductsForSession(session.userId, session.organizationId);
  const results = await Promise.all(products.map(async product => {
    const started = performance.now();
    try {
      const response = await fetch(new URL(serviceHealthPaths[product], dashboardSources[product]), {
        redirect: "manual",
        signal: AbortSignal.timeout(3000),
      });
      return [product, { status: response.ok ? "online" : "unavailable", responseMs: Math.round(performance.now() - started) }] as const;
    } catch {
      return [product, { status: "unavailable", responseMs: null }] as const;
    }
  }));
  res.setHeader("Cache-Control", "no-store");
  res.json({ checkedAt: new Date().toISOString(), apps: Object.fromEntries(results) });
});

const academyAdminBaseUrl = process.env.ACADEMY_INTERNAL_URL || "http://v79_course_builder:3030";
const academyAdminAllowedPaths = [
  "/api/courses",
  "/api/modules",
  "/api/lessons",
  "/api/content-blocks",
  "/api/assets",
  "/api/assignments",
  "/api/downloads",
  "/api/media",
  "/api/import-histories",
  "/api/publishing-logs",
  "/api/gemini/assist",
  "/api/learners",
  "/api/junior-admin",
];

app.use("/api/admin/academy", requirePlatformOperator, async (req, res) => {
  if (posSecret.length < 32) {
    return res.status(503).json({ error: "Academy platform integration is not configured." });
  }

  const suffix = req.originalUrl.slice("/api/admin/academy".length) || "/";
  let target: URL;
  try {
    target = new URL(`/api${suffix}`, academyAdminBaseUrl);
  } catch {
    return res.status(400).json({ error: "Invalid Academy admin request." });
  }

  if (!academyAdminAllowedPaths.some(prefix => target.pathname === prefix || target.pathname.startsWith(prefix + "/"))) {
    return res.status(404).json({ error: "Academy admin route is not exposed through Hub." });
  }

  const method = req.method.toUpperCase();
  const body = ["GET", "HEAD", "OPTIONS"].includes(method)
    ? ""
    : (req.body === undefined ? "" : JSON.stringify(req.body));
  const timestamp = String(Date.now());
  const headers: Record<string, string> = {
    "x-v79-service-id": "v79-hub",
    "x-v79-timestamp": timestamp,
    "x-v79-signature": signPlatformRequest({
      method,
      pathname: target.pathname,
      timestamp,
      body,
      secret: posSecret,
    }),
    "accept": String(req.get("accept") || "application/json"),
    "x-user-role": "Admin",
  };
  if (body) headers["content-type"] = "application/json";

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body: body || undefined,
      redirect: "manual",
      signal: AbortSignal.timeout(60_000),
    });

    res.status(upstream.status);
    for (const name of ["content-type", "content-disposition", "etag", "last-modified"]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.setHeader("Cache-Control", "no-store");

    if (upstream.status === 204 || method === "HEAD") return res.end();
    const payload = Buffer.from(await upstream.arrayBuffer());
    return res.send(payload);
  } catch {
    return res.status(503).json({ error: "Academy management service is unavailable." });
  }
});


type PlatformAdminProduct = "pos" | "tiquet" | "marketing" | "ffpro" | "academy" | "lasertag" | "website" | "games";

// Retire the older broad proxy paths so stale clients cannot fall through to the SPA.
app.use(["/api/admin/tiquet", "/api/admin/marketing"], requirePlatformOperator, (_req, res) => {
  res.status(404).json({ error: "Use the platform administration endpoint." });
});

const platformAdminSources: Record<PlatformAdminProduct, string> = {
  pos: process.env.POS_BASE_URL || "http://v79-pos:8080",
  tiquet: process.env.TIQUET_INTERNAL_URL || "http://v79-tiquet-manager:3050",
  marketing: process.env.MARKETING_INTERNAL_URL || "http://v79marketing-app:3070",
  ffpro: process.env.FFPRO_INTERNAL_URL || "http://fire-finance-app:3010",
  academy: process.env.ACADEMY_INTERNAL_URL || "http://v79_course_builder:3030",
  lasertag: process.env.LASERTAG_INTERNAL_URL || "http://lasertag:5173",
  website: process.env.WEBSITE_INTERNAL_URL || "http://V79website:3000",
  games: process.env.GAMES_INTERNAL_URL || "http://gaming-studio-j:80",
};

const platformAdminAllowed: Record<PlatformAdminProduct, Array<{ method: string; path: RegExp }>> = {
  pos: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
    { method: "GET", path: /^\/api\/platform\/admin\/tenants$/ },
    { method: "PUT", path: /^\/api\/platform\/admin\/tenants\/[^/]+\/offline-sales\/(?:enabled|disabled)$/ },
  ],
  tiquet: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
    { method: "GET", path: /^\/api\/platform\/admin\/accounts$/ },
  ],
  marketing: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
    { method: "GET", path: /^\/api\/platform\/admin\/businesses$/ },
  ],
  ffpro: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
    { method: "GET", path: /^\/api\/platform\/admin\/accounts$/ },
  ],
  academy: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
  ],
  lasertag: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
  ],
  website: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
  ],
  games: [
    { method: "GET", path: /^\/api\/platform\/admin\/stats$/ },
  ],
};

async function callPlatformAdmin(product: PlatformAdminProduct, method: string, pathname: string, requestBody?: unknown) {
  const signingSecret = platformSigningSecret(product);
  if (signingSecret.length < 32) {
    return { status: 503, headers: new Headers({ "content-type": "application/json" }), body: Buffer.from(JSON.stringify({ error: "Platform integration is not configured." })) };
  }

  const allowed = platformAdminAllowed[product].some(rule => rule.method === method && rule.path.test(pathname));
  if (!allowed) {
    return { status: 404, headers: new Headers({ "content-type": "application/json" }), body: Buffer.from(JSON.stringify({ error: "Platform admin route is not exposed through Hub." })) };
  }

  const timestamp = String(Date.now());
  const isRead = method === "GET" || method === "HEAD";
  // Tiquet's platform contract intentionally signs an empty body for all methods.
  // POS signs the serialized JSON body for writes.
  const serializedBody = isRead ? "" : (product === "tiquet" ? "" : JSON.stringify(requestBody ?? {}));
  const signature = signPlatformRequest({
    method,
    pathname,
    timestamp,
    body: serializedBody,
    secret: signingSecret,
  });

  const headers: Record<string, string> = {
    "x-v79-service-id": "v79-hub",
    "x-v79-timestamp": timestamp,
    "x-v79-signature": signature,
    "accept": "application/json",
  };
  let body: string | undefined;
  if (!isRead && product !== "tiquet") {
    body = JSON.stringify(requestBody ?? {});
    headers["content-type"] = "application/json";
  }

  try {
    const upstream = await fetch(new URL(pathname, platformAdminSources[product]), {
      method,
      headers,
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(10_000),
    });
    return {
      status: upstream.status,
      headers: upstream.headers,
      body: Buffer.from(await upstream.arrayBuffer()),
    };
  } catch {
    return {
      status: 503,
      headers: new Headers({ "content-type": "application/json" }),
      body: Buffer.from(JSON.stringify({ error: product + " platform service is unavailable." })),
    };
  }
}

app.get("/api/admin/platform/overview", requirePlatformOperator, async (_req, res) => {
  const products: PlatformAdminProduct[] = ["pos", "tiquet", "marketing", "ffpro", "academy", "lasertag", "website", "games"];
  const entries = await Promise.all(products.map(async product => {
    const response = await callPlatformAdmin(product, "GET", "/api/platform/admin/stats");
    let data: any = null;
    try { data = JSON.parse(response.body.toString("utf8")); } catch { /* no-op */ }
    return [product, {
      status: response.status === 200 ? "ok" : "error",
      httpStatus: response.status,
      metrics: response.status === 200 ? data : null,
      error: response.status === 200 ? null : (data?.error || "Platform stats unavailable."),
    }] as const;
  }));

  const customerOrganizations = store.organizations.filter(org => org.id !== posIdentity.organizationId);
  const pendingInvitations = store.ownerInvitations.filter(invitation =>
    !store.organizations.some(org => org.id === invitation.organizationId) &&
    invitationStatus(invitation) === "pending"
  );
  const provisioningCustomers = customerOrganizations.filter(org => customerLifecycle(store, org) === "provisioning");
  const suspendedCustomers = customerOrganizations.filter(org => org.status === "suspended");

  res.setHeader("Cache-Control", "no-store");
  res.json({
    generatedAt: new Date().toISOString(),
    hub: {
      customers: customerOrganizations.length,
      activeCustomers: customerOrganizations.length - suspendedCustomers.length,
      suspendedCustomers: suspendedCustomers.length,
      pendingInvitations: pendingInvitations.length,
      provisioningCustomers: provisioningCustomers.length,
    },
    apps: Object.fromEntries(entries),
  });
});

app.use("/api/admin/platform/:product", requirePlatformOperator, async (req, res) => {
  const product = String(req.params.product || "") as PlatformAdminProduct;
  if (!(product in platformAdminSources)) return res.status(404).json({ error: "Unknown platform product." });

  const prefix = `/api/admin/platform/${product}`;
  const originalPath = new URL(req.originalUrl, "http://hub.internal").pathname;
  const suffix = originalPath.slice(prefix.length);
  const pathname = `/api/platform/admin${suffix || "/"}`;
  const method = req.method.toUpperCase();

  const response = await callPlatformAdmin(product, method, pathname, req.body);
  res.status(response.status);
  const contentType = response.headers.get("content-type");
  if (contentType) res.setHeader("content-type", contentType);
  res.setHeader("Cache-Control", "no-store");
  res.send(response.body);
});

const retiredEmbeddedAppPaths = [
  "/api/inventory",
  "/api/transactions",
  "/api/pos",
  "/api/settings",
  "/api/ai",
  "/api/ecosystem/tiquet",
  "/api/ecosystem/ffpro",
  "/api/ecosystem/marketing",
];
app.use(retiredEmbeddedAppPaths, (_req, res) => {
  res.status(410).json({ error: "This embedded Hub app-data API has been retired. Use the dedicated V79 application." });
});
const agentInternalUrl = process.env.V79_AGENT_INTERNAL_URL || "http://v79-business-agent:3055";
const agentTokenFile = process.env.V79_AGENT_TOKEN_FILE || "/run/secrets/v79-agent-token";
function readAgentApiToken() {
  const direct = String(process.env.V79_AGENT_API_TOKEN || "").trim();
  if (direct) return direct;
  try { return fs.readFileSync(agentTokenFile, "utf8").trim(); } catch { return ""; }
}
const ownerAgentSystems = ["hub", "website", "lasertag", "marketing", "pos", "tiquet", "ffpro", "academy", "games"];

function ownerAssistantContext(req: Request) {
  const session = (req as any).user;
  const user = store.users.find(item => item.id === session.userId);
  const membership = activeMembership(store, session.userId, session.organizationId);
  if (!user || !hasOwnerAssistantAccess({
    user,
    membership,
    organizationId: session.organizationId,
    ownerOrganizationId: posIdentity.organizationId,
    ownerUserId: posIdentity.ownerUserId,
    ownerEmail: process.env.V79_HUB_ADMIN_EMAIL,
  })) return null;

  const organization = store.organizations.find(org => org.id === session.organizationId);
  return {
    userId: user.id,
    email: normalizeEmail(user.email),
    organizationId: session.organizationId,
    organizationName: organization?.name || store.workspace.companyName || "V79 Digital",
    allowedSystems: ownerAgentSystems,
    ownerAgent: true,
    hubAdmin: true,
  };
}

// Phase 3 is a decision ledger only: approval DOES NOT dispatch any action.
// Serialize inbox modifications, preserving idempotency across concurrent calls.
let agentProposalWriteChain: Promise<unknown> = Promise.resolve();
function serializeAgentProposalWrite<T>(task: () => Promise<T>): Promise<T> {
  const pending = agentProposalWriteChain.then(task, task);
  agentProposalWriteChain = pending.then(() => undefined, () => undefined);
  return pending;
}

app.get("/api/agent/proposals", (req, res) => {
  const context = ownerAssistantContext(req);
  if (!context) return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  res.setHeader("Cache-Control", "no-store");
  return res.json({ mode: "decision-only", executionEnabled: false,
    proposals: listAgentProposals(store.agentActionProposals, context.organizationId) });
});

app.post("/api/agent/proposals", async (req, res) => {
  const context = ownerAssistantContext(req);
  if (!context) return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  res.setHeader("Cache-Control", "no-store");
  try {
    return await serializeAgentProposalWrite(async () => {
      const next = cloneStore();
      const result = createAgentProposal(next.agentActionProposals, req.body, {
        organizationId: context.organizationId, actorUserId: context.userId,
      });
      if (result.kind === "invalid") return res.status(400).json({ error: "Invalid draft proposal." });
      if (result.kind === "conflict") return res.status(409).json({ error: "Idempotency key is already bound to another proposal." });
      if (result.kind === "limit") return res.status(429).json({ error: "Proposal inbox limit reached." });
      if (result.kind === "created") {
        appendAgentProposalAudit(next.auditEvents, result.proposal, "agent.proposal.created", context.userId);
        await commitStore(next);
      }
      const proposal = listAgentProposals(
        result.kind === "created" ? next.agentActionProposals : store.agentActionProposals,
        context.organizationId,
      ).find(item => item.id === result.proposal.id);
      return res.status(result.kind === "created" ? 201 : 200).json({
        proposal, executionEnabled: false, duplicate: result.kind === "duplicate",
      });
    });
  } catch (error) {
    console.error("Agent proposal save failed", error instanceof Error ? error.name : "error");
    return res.status(503).json({ error: "Approval inbox storage is unavailable." });
  }
});

app.post("/api/agent/proposals/:proposalId/decision", async (req, res) => {
  const context = ownerAssistantContext(req);
  if (!context) return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  res.setHeader("Cache-Control", "no-store");
  try {
    return await serializeAgentProposalWrite(async () => {
      const next = cloneStore();
      const result = decideAgentProposal(next.agentActionProposals, {
        id: String(req.params.proposalId || ""),
        organizationId: context.organizationId, actorUserId: context.userId,
        expectedRevision: req.body?.expectedRevision,
        decision: req.body?.decision, note: req.body?.note,
      });
      if (result.kind === "invalid") return res.status(400).json({ error: "Invalid proposal decision." });
      if (result.kind === "not_found") return res.status(404).json({ error: "Proposal not found." });
      if (result.kind === "expired") return res.status(410).json({ error: "Proposal expired. Create a new draft." });
      if (result.kind === "conflict") return res.status(409).json({ error: "Proposal has already been reviewed or modified." });
      appendAgentProposalAudit(next.auditEvents, result.proposal, "agent.proposal." + result.proposal.status, context.userId);
      await commitStore(next);
      const proposal = listAgentProposals(next.agentActionProposals, context.organizationId)
        .find(item => item.id === result.proposal.id);
      return res.json({ proposal, executionEnabled: false, message: "Decision recorded. No action executed." });
    });
  } catch (error) {
    console.error("Agent proposal decision failed", error instanceof Error ? error.name : "error");
    return res.status(503).json({ error: "Approval inbox storage is unavailable." });
  }
});

app.get("/api/agent/access", (req, res) => {
  const context = ownerAssistantContext(req);
  res.setHeader("Cache-Control", "no-store");
  res.json({ enabled: Boolean(context), ownerOnly: true, email: context?.email || null });
});

function internalOwnerAgentRequest(req: Request) {
  const token = String(req.get("x-v79-agent-token") || "");
  const email = normalizeEmail(req.get("x-v79-owner-email"));
  const organizationId = String(req.get("x-v79-organization-id") || "");
  const agentApiToken = readAgentApiToken();
  if (!agentApiToken || token.length !== agentApiToken.length) return false;
  if (!crypto.timingSafeEqual(Buffer.from(token), Buffer.from(agentApiToken))) return false;
  return email === "vision79slu@gmail.com" &&
    email === normalizeEmail(process.env.V79_HUB_ADMIN_EMAIL) &&
    organizationId === posIdentity.organizationId;
}

async function connectionSnapshot() {
  const products = Object.keys(serviceHealthPaths) as DashboardProduct[];
  const entries = await Promise.all(products.map(async product => {
    const started = performance.now();
    try {
      const response = await fetch(new URL(serviceHealthPaths[product], dashboardSources[product]), {
        redirect: "manual",
        signal: AbortSignal.timeout(3000),
      });
      return [product, {
        status: response.ok ? "online" : "unavailable",
        responseMs: Math.round(performance.now() - started),
      }] as const;
    } catch {
      return [product, { status: "unavailable", responseMs: null }] as const;
    }
  }));
  return Object.fromEntries(entries);
}

app.get("/internal/agent/snapshot", async (req, res) => {
  if (!internalOwnerAgentRequest(req)) {
    return res.status(403).json({ error: "Vision79 Owner Assistant service access required." });
  }

  const products: DashboardProduct[] = ["pos", "ffpro", "tiquet", "marketing", "academy", "lasertag", "website", "games"];
  const [summaries, connections, platformStats] = await Promise.all([
    Promise.all(products.map(async product => [product, await readDashboardSummary(product, posIdentity.organizationId)] as const)),
    connectionSnapshot(),
    Promise.all(products.map(async product => {
      const response = await callPlatformAdmin(product, "GET", "/api/platform/admin/stats");
      let payload: any = null;
      try { payload = JSON.parse(response.body.toString("utf8")); } catch { /* no-op */ }
      return [product, {
        status: response.status === 200 ? "ok" : "unavailable",
        httpStatus: response.status,
        metrics: response.status === 200 ? payload : null,
      }] as const;
    })),
  ]);

  const organizationId = posIdentity.organizationId;
  const activeMembers = store.memberships.filter(member =>
    member.organizationId === organizationId && member.status === "active"
  );

  res.setHeader("Cache-Control", "no-store");
  res.json({
    generatedAt: new Date().toISOString(),
    owner: {
      email: normalizeEmail(process.env.V79_HUB_ADMIN_EMAIL),
      organizationId,
      organizationName: store.organizations.find(org => org.id === organizationId)?.name || store.workspace.companyName,
    },
    hubAdmin: {
      users: activeMembers.length,
      enabledApps: enabledAppIds(store, organizationId, posIdentity.organizationId),
      activeSessions: [...sessions.values()].filter(session => session.organizationId === organizationId && session.expiresAt > Date.now()).length,
    },
    connections,
    business: Object.fromEntries(summaries),
    platform: Object.fromEntries(platformStats),
  });
});

app.post("/api/agent/chat", async (req, res) => {
  const context = ownerAssistantContext(req);
  if (!context) return res.status(403).json({ error: "Vision79 Owner Assistant access required." });
  const agentApiToken = readAgentApiToken();
  if (!agentApiToken) return res.status(503).json({ error: "Owner Assistant service is not configured." });
  const message = typeof req.body?.message === "string" ? req.body.message.trim() : "";
  if (!message) return res.status(400).json({ error: "message is required" });

  try {
    const response = await fetch(`${agentInternalUrl}/api/agent/chat`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-v79-agent-token": agentApiToken },
      body: JSON.stringify({ message, context }),
      signal: AbortSignal.timeout(90000),
    });
    const body = await response.text();
    res.status(response.status);
    res.setHeader("Cache-Control", "no-store");
    res.type(response.headers.get("content-type") || "application/json").send(body);
  } catch (error) {
    console.error("Owner Assistant proxy failed", error);
    res.status(502).json({ error: "Owner Assistant service is unavailable." });
  }
});

app.use("/api/users", (req, res, next) => {
  if (req.method === "GET") return requirePermission("team")(req, res, next);
  return requireWorkspaceOwner(req, res, next);
});
app.use("/api/ecosystem/apps", (req, res, next) => req.method === "GET" ? next() : requireRole("admin")(req, res, next));

app.get("/api/apps/pos/launch", async (req, res) => {
  const session = (req as any).user;
  if (!organizationCanAccessApp(store, session.organizationId, "app-v79pos", posIdentity.organizationId)) {
    return res.status(403).json({ error: "POS is not enabled for this Hub organization" });
  }
  const membership = activeMembership(store, session.userId, session.organizationId);
  const teamRole = posTeamRole(membership?.role);
  if (membership?.role !== "owner" && !membershipCanAccessApp(membership, "app-v79pos")) {
    return res.status(403).json({ error: "POS is not assigned to your workspace account" });
  }
  if (membership?.role !== "owner" && !teamRole) {
    return res.status(403).json({ error: "Your workspace role is not eligible for POS access" });
  }
  if (session.organizationId === posIdentity.organizationId && session.userId !== posIdentity.ownerUserId) {
    return res.status(403).json({ error: "Only the V79 workspace owner can launch POS" });
  }
  if (!posTenantLaunchReady(store, session.organizationId, posIdentity.organizationId)) {
    return res.status(409).json({ error: "POS workspace setup is pending. Contact V79 Digital." });
  }
  const organization = store.organizations.find(org => org.id === session.organizationId && org.status === "active");
  if (!organization) return res.status(409).json({ error: "Hub organization is not active" });

  const provisioned = membership?.role === "owner"
    ? await provisionPosWorkspace(
        organization,
        session.userId,
        session.organizationId !== posIdentity.organizationId,
      )
    : await provisionPosTeamMember(organization, session.userId, teamRole!);
  if (!provisioned.ok) {
    return res.status(provisioned.status).json({
      error: provisioned.error,
      ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
    });
  }

  const ticket = launchTicket(session.userId, session.organizationId, "pos");
  const url = new URL("/", posPublicUrl);
  url.hash = new URLSearchParams({ ticket }).toString();
  res.setHeader("Cache-Control", "no-store");
  res.redirect(302, url.toString());
});

app.get("/api/apps/:product/launch", async (req, res) => {
  const product = req.params.product as keyof typeof managedLaunch;
  if (!(product in managedLaunch)) return res.status(404).json({ error: "Unknown managed app" });
  const session = (req as any).user;
  const appIdByProduct = { ffpro: "app-ffpro", tiquet: "app-tiquet", marketing: "app-marketing" } as const;
  if (!organizationCanAccessApp(store, session.organizationId, appIdByProduct[product], posIdentity.organizationId)) return res.status(403).json({ error: "This app is not enabled for this Hub organization" });

  const membership = activeMembership(store, session.userId, session.organizationId);
  const assignedAppId = appIdByProduct[product];
  if (membership?.role !== "owner" && !membershipCanAccessApp(membership, assignedAppId)) {
    return res.status(403).json({ error: "This app is not assigned to your workspace account" });
  }
  const teamFfproRole = product === "ffpro" ? ffproTeamRole(membership?.role) : null;
  const teamTiquetRole = product === "tiquet" ? tiquetTeamRole(membership?.role) : null;
  const teamMarketingRole = product === "marketing" ? marketingTeamRole(membership?.role) : null;
  if (product === "ffpro") {
    if (membership?.role !== "owner" && !teamFfproRole) {
      return res.status(403).json({ error: "Your workspace role is not eligible for FFPRO access" });
    }
  } else if (product === "tiquet") {
    if (membership?.role !== "owner" && !teamTiquetRole) {
      return res.status(403).json({ error: "Your workspace role is not eligible for Tiquet access" });
    }
  } else if (product === "marketing") {
    if (membership?.role !== "owner" && !teamMarketingRole) {
      return res.status(403).json({ error: "Your workspace role is not eligible for Marketing access" });
    }
  }
  if (session.organizationId === posIdentity.organizationId && session.userId !== posIdentity.ownerUserId) {
    return res.status(403).json({ error: "Only the V79 workspace owner can launch this app" });
  }
  if (product === "ffpro") {
    if (!ffproTenantLaunchReady(store, session.organizationId, posIdentity.organizationId)) {
      return res.status(409).json({ error: "FFPRO workspace setup is pending. Contact V79 Digital." });
    }
  } else if (product === "tiquet") {
    if (!tiquetTenantLaunchReady(store, session.organizationId, posIdentity.organizationId)) {
      return res.status(409).json({ error: "Tiquet workspace setup is pending. Contact V79 Digital." });
    }
  } else if (product === "marketing") {
    if (!marketingTenantLaunchReady(store, session.organizationId, posIdentity.organizationId)) {
      return res.status(409).json({ error: "Marketing workspace setup is pending. Contact V79 Digital." });
    }
  } else if (session.organizationId !== posIdentity.organizationId) {
    return res.status(409).json({ error: `${product} workspace setup is pending. Contact V79 Digital.` });
  }

  const user = store.users.find(item => item.id === session.userId);
  if (!user) return res.status(409).json({ error: "Hub user is unavailable." });
  const ownerEmail = session.organizationId === posIdentity.organizationId
    ? String(process.env.V79_HUB_ADMIN_EMAIL || "").trim().toLowerCase()
    : String(user.email || user.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(ownerEmail)) {
    return res.status(503).json({ error: "Set the workspace user's verified email before launch." });
  }

  if (product === "tiquet" && teamTiquetRole) {
    const organization = store.organizations.find(org => org.id === session.organizationId && org.status === "active");
    if (!organization) return res.status(409).json({ error: "Hub organization is not active" });
    const provisioned = await provisionTiquetTeamMember(organization, user, teamTiquetRole);
    if (!provisioned.ok) {
      return res.status(provisioned.status).json({
        error: provisioned.error,
        ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
      });
    }
    const mapping = tiquetTenantMapping(store, session.organizationId);
    if (!mapping || mapping.status !== "active" || mapping.externalTenantId !== provisioned.accountId) {
      return res.status(409).json({ error: "Tiquet team identity does not match the active workspace mapping" });
    }
  }

  if (product === "marketing" && teamMarketingRole) {
    const organization = store.organizations.find(org => org.id === session.organizationId && org.status === "active");
    if (!organization) return res.status(409).json({ error: "Hub organization is not active" });
    const provisioned = await provisionMarketingTeamMember(organization, user, teamMarketingRole);
    if (!provisioned.ok) {
      return res.status(provisioned.status).json({
        error: provisioned.error,
        ...("upstreamStatus" in provisioned ? { upstreamStatus: provisioned.upstreamStatus } : {}),
      });
    }
    const mapping = marketingTenantMapping(store, session.organizationId);
    if (!mapping || mapping.status !== "active" || mapping.externalTenantId !== provisioned.businessId) {
      return res.status(409).json({ error: "Marketing team identity does not match the active workspace mapping" });
    }
  }

  const config = managedLaunch[product];
  if ((process.env[config.secretEnv] || "").length < 32) return res.status(503).json({ error: `${product} launch secret is not configured.` });
  const configuredUrl = process.env[config.publicEnv] || config.defaultUrl;
  let target: URL;
  try {
    target = new URL("/api/platform/launch", configuredUrl);
    if (target.protocol !== "https:" || target.username || target.password || !target.hostname.endsWith(".v79sl.com")) throw new Error("Invalid app URL");
  } catch { return res.status(503).json({ error: `${product} public URL is invalid.` }); }

  target.searchParams.set("ticket", launchTicket(session.userId, session.organizationId, product));
  res.setHeader("Cache-Control", "no-store");
  res.redirect(302, target.toString());
});

// ==========================================
// USER MANAGEMENT ROUTES
// ==========================================

app.get("/api/users", (req, res) => {
  const organizationId = (req as any).user.organizationId;
  res.json(store.users.map(user => sanitizeUserForOrganization(user, organizationId)).filter(Boolean));
});

app.post("/api/users", async (req, res) => {
  const organizationId = (req as any).user.organizationId;
  if (organizationId !== posIdentity.organizationId) {
    return res.status(403).json({ error: "Customer workspace members must be added through a team invitation" });
  }
  const { username, password, fullName, role, permissions } = req.body || {};
  if (typeof username !== "string" || !username.trim() || username.trim().length > 120 || typeof password !== "string" || password.length < 12 || password.length > 1024 || !["admin", "manager", "staff", "viewer"].includes(role || "staff")) {
    return res.status(400).json({ error: "Valid username, role and password of at least 12 characters are required" });
  }
  if (fullName !== undefined && (typeof fullName !== "string" || !fullName.trim() || fullName.trim().length > 120)) return res.status(400).json({ error: "Full name must be 1 to 120 characters" });

  const existing = store.users.find((u) => u.username.toLowerCase() === username.trim().toLowerCase());
  if (existing) {
    return res.status(400).json({ error: "Username already exists" });
  }

  const newUser: StoredUser = {
    id: crypto.randomUUID(),
    username: username.trim(),
    password: hashPassword(password),
    fullName: fullName?.trim() || username.trim(),
    role: role || "staff",
    permissions: normalizePermissions(permissions, role || "staff"),
    createdAt: new Date().toISOString(),
    lastLogin: undefined
  };

  store.users.push(newUser);
  store.memberships.push({
    organizationId,
    userId: newUser.id,
    role: newUser.role,
    permissions: normalizePermissions(permissions, newUser.role),
    status: "active",
    createdAt: newUser.createdAt
  });
  await saveStore(store);
  broadcast(organizationId, { type: "USERS_UPDATED" });
  res.status(201).json(sanitizeUserForOrganization(newUser, organizationId));
});

app.put("/api/users/:id", async (req, res) => {
  const { id } = req.params;
  const { username, password, fullName, role, permissions, appIds } = req.body || {};
  const organizationId = (req as any).user.organizationId;
  const userIndex = store.users.findIndex((u) => u.id === id && activeMembership(store, u.id, organizationId));
  if (userIndex === -1) return res.status(404).json({ error: "User not found" });

  const current = store.users[userIndex];
  const member = store.memberships.find(m => m.organizationId === organizationId && m.userId === id && m.status === "active");
  if (!member) return res.status(404).json({ error: "User membership not found" });
  const sharedIdentity = activeMembershipsForUser(store, id).length > 1;

  if (username !== undefined && (typeof username !== "string" || !username.trim() || username.trim().length > 120)) return res.status(400).json({ error: "Username must be 1 to 120 characters" });
  if (username !== undefined && store.users.some(user => user.id !== id && user.username.toLowerCase() === username.trim().toLowerCase())) return res.status(409).json({ error: "Username already exists" });
  if (fullName !== undefined && (typeof fullName !== "string" || !fullName.trim() || fullName.trim().length > 120)) return res.status(400).json({ error: "Full name must be 1 to 120 characters" });
  if (password !== undefined && (typeof password !== "string" || password.length < 12 || password.length > 1024)) return res.status(400).json({ error: "Password must be 12 to 1024 characters" });
  if (role !== undefined && !["admin", "manager", "staff", "viewer"].includes(role)) return res.status(400).json({ error: "Invalid role" });
  if (organizationId !== posIdentity.organizationId && role === "admin") {
    return res.status(400).json({ error: "Delegated workspace admin is not enabled; use manager, staff or viewer" });
  }
  if (appIds !== undefined) {
    if (member.role === "owner") return res.status(400).json({ error: "Workspace owner app access follows workspace entitlements" });
    if (!Array.isArray(appIds) || appIds.some(appId =>
      typeof appId !== "string" ||
      !teamAssignableAppIds.has(appId) ||
      !organizationCanAccessApp(store, organizationId, appId, posIdentity.organizationId)
    )) {
      return res.status(400).json({ error: "Team app access must use enabled POS, Tiquet or Marketing apps only" });
    }
  }
  if (sharedIdentity && (username !== undefined || password !== undefined || fullName !== undefined)) {
    return res.status(409).json({ error: "Shared account identity must be changed by the account owner, not a workspace administrator" });
  }
  if (member.role === "owner" && role && role !== "admin") return res.status(400).json({ error: "Cannot demote the workspace owner" });

  const activeAdmins = store.memberships.filter(m => m.organizationId === organizationId && m.status === "active" && sessionRole(m) === "admin");
  if (sessionRole(member) === "admin" && role && role !== "admin" && activeAdmins.length <= 1) {
    return res.status(400).json({ error: "Cannot demote the sole administrator" });
  }

  const previousAppIds = normalizeTeamAppIds(member.appIds, organizationId);
  const nextAppIds = appIds !== undefined ? normalizeTeamAppIds(appIds, organizationId) : previousAppIds;
  const nextMembershipRole = member.role !== "owner" && role !== undefined ? role : member.role;

  if (organizationId !== posIdentity.organizationId && member.role !== "owner") {
    const organization = store.organizations.find(org => org.id === organizationId && org.status === "active");
    if (!organization) return res.status(409).json({ error: "Workspace is not active" });

    const hadPos = previousAppIds.includes("app-v79pos");
    const willHavePos = nextAppIds.includes("app-v79pos");
    const roleChanged = role !== undefined && nextMembershipRole !== member.role;
    if (hadPos && (!willHavePos || roleChanged)) {
      const deprovisioned = await deprovisionPosTeamMember(organizationId, id);
      if (!deprovisioned.ok) {
        return res.status(deprovisioned.status).json({
          error: deprovisioned.error,
          ...("upstreamStatus" in deprovisioned ? { upstreamStatus: deprovisioned.upstreamStatus } : {}),
        });
      }
    }

    const hadMarketing = previousAppIds.includes("app-marketing");
    const willHaveMarketing = nextAppIds.includes("app-marketing");
    if (hadMarketing && (!willHaveMarketing || roleChanged)) {
      const deprovisioned = await deprovisionMarketingTeamMember(organizationId, id);
      if (!deprovisioned.ok) {
        return res.status(deprovisioned.status).json({
          error: deprovisioned.error,
          ...("upstreamStatus" in deprovisioned ? { upstreamStatus: deprovisioned.upstreamStatus } : {}),
        });
      }
    }

    const hadTiquet = previousAppIds.includes("app-tiquet");
    const willHaveTiquet = nextAppIds.includes("app-tiquet");
    if (hadTiquet && !willHaveTiquet) {
      const deprovisioned = await deprovisionTiquetTeamMember(organizationId, id);
      if (!deprovisioned.ok) {
        return res.status(deprovisioned.status).json({
          error: deprovisioned.error,
          ...("upstreamStatus" in deprovisioned ? { upstreamStatus: deprovisioned.upstreamStatus } : {}),
        });
      }
    } else if (willHaveTiquet && roleChanged) {
      const mappedRole = tiquetTeamRole(nextMembershipRole);
      if (!mappedRole) return res.status(400).json({ error: "Tiquet team access requires manager, staff or viewer role" });
      const synced = await provisionTiquetTeamMember(organization, current, mappedRole);
      if (!synced.ok) {
        return res.status(synced.status).json({
          error: synced.error,
          ...("upstreamStatus" in synced ? { upstreamStatus: synced.upstreamStatus } : {}),
        });
      }
    }
  }

  store.users[userIndex] = {
    ...current,
    username: username !== undefined ? username.trim() : current.username,
    password: password ? hashPassword(password) : current.password,
    fullName: fullName !== undefined ? fullName.trim() : current.fullName,
  };
  if (member.role !== "owner" && role !== undefined) member.role = role;
  const effectiveRole = sessionRole(member) as StoredUser["role"];
  if (permissions !== undefined) member.permissions = normalizePermissions(permissions, effectiveRole);
  if (appIds !== undefined && member.role !== "owner") {
    member.appIds = normalizeTeamAppIds(appIds, organizationId);
  }

  await saveStore(store);
  deleteSessionsWhere(session => session.userId === id && (Boolean(password) || session.organizationId === organizationId));
  broadcast(organizationId, { type: "USERS_UPDATED" });
  res.json(sanitizeUserForOrganization(store.users[userIndex], organizationId));
});

app.delete("/api/users/:id", async (req, res) => {
  const { id } = req.params;
  const organizationId = (req as any).user.organizationId;
  const userToDelete = store.users.find((u) => u.id === id && activeMembership(store, u.id, organizationId));
  const member = store.memberships.find(m => m.organizationId === organizationId && m.userId === id && m.status === "active");
  if (!userToDelete || !member) return res.status(404).json({ error: "User not found" });
  if (member.role === "owner") return res.status(400).json({ error: "Cannot delete the workspace owner" });

  const activeAdmins = store.memberships.filter(m => m.organizationId === organizationId && m.status === "active" && sessionRole(m) === "admin");
  if (sessionRole(member) === "admin" && activeAdmins.length <= 1) {
    return res.status(400).json({ error: "Cannot delete the sole administrator account" });
  }

  if (organizationId !== posIdentity.organizationId) {
    const assignedApps = normalizeTeamAppIds(member.appIds, organizationId);
    if (assignedApps.includes("app-v79pos")) {
      const deprovisioned = await deprovisionPosTeamMember(organizationId, id);
      if (!deprovisioned.ok) {
        return res.status(deprovisioned.status).json({
          error: deprovisioned.error,
          ...("upstreamStatus" in deprovisioned ? { upstreamStatus: deprovisioned.upstreamStatus } : {}),
        });
      }
    }
    if (assignedApps.includes("app-marketing")) {
      const deprovisioned = await deprovisionMarketingTeamMember(organizationId, id);
      if (!deprovisioned.ok) {
        return res.status(deprovisioned.status).json({
          error: deprovisioned.error,
          ...("upstreamStatus" in deprovisioned ? { upstreamStatus: deprovisioned.upstreamStatus } : {}),
        });
      }
    }
    if (assignedApps.includes("app-tiquet")) {
      const deprovisioned = await deprovisionTiquetTeamMember(organizationId, id);
      if (!deprovisioned.ok) {
        return res.status(deprovisioned.status).json({
          error: deprovisioned.error,
          ...("upstreamStatus" in deprovisioned ? { upstreamStatus: deprovisioned.upstreamStatus } : {}),
        });
      }
    }
  }

  store.memberships = store.memberships.filter(m => !(m.organizationId === organizationId && m.userId === id));
  const hasOtherMembership = activeMembershipsForUser(store, id).length > 0;
  if (!hasOtherMembership) store.users = store.users.filter((u) => u.id !== id);
  deleteSessionsWhere(session => session.userId === id && session.organizationId === organizationId);
  await saveStore(store);
  broadcast(organizationId, { type: "USERS_UPDATED" });
  res.json({ success: true });
});

// ==========================================
// ECOSYSTEM APPS & INTEGRATION ROUTES
// ==========================================

// Get all ecosystem applications
app.get("/api/ecosystem/apps", async (req, res) => {
  if (!store.ecosystemApps || store.ecosystemApps.length === 0) {
    store.ecosystemApps = defaultEcosystemApps;
    await saveStore(store);
  }
  const managedDescriptions: Record<string,string> = {
    "app-ffpro": "Finance planning and reporting. Sign in through the Hub after your FFPRO account is linked.",
    "app-tiquet": "Service jobs and tickets. Sign in through the Hub after your Tiquet account is linked.",
    "app-marketing": "Customer and campaign tools. Sign in through the Hub to open your workspace.",
    "app-v79pos": "Sales, stock and purchasing. The POS beta requires its own service and register testing.",
    "app-academy": "Public courses and learning. Academy has its own learner account.",
  };
  const session = (req as any).user;
  const organizationId = session.organizationId;
  const membership = activeMembership(store, session.userId, organizationId);
  const visibleApps = visibleEcosystemApps(store, organizationId, posIdentity.organizationId) as EcosystemApp[];
  const memberVisibleApps = membership?.role === "owner"
    ? visibleApps
    : visibleApps.filter((app: EcosystemApp) => membershipCanAccessApp(membership, app.id));
  res.json(memberVisibleApps
    .filter((a: EcosystemApp) => !["app-analytics","app-lifehealth"].includes(a.id))
    .map((a: EcosystemApp) => {
      const tenantMapping = store.appTenantMappings.find(mapping =>
        mapping.organizationId === organizationId && mapping.appId === a.id
      );
      const isManagedProduct = tenantMappedAppIds.has(a.id);
      const setupPending = organizationId !== posIdentity.organizationId &&
        isManagedProduct && tenantMapping?.status !== "active";
      const teamMappedLaunchReady = organizationId !== posIdentity.organizationId &&
        tenantMapping?.status === "active" &&
        (
          (a.id === "app-v79pos" && Boolean(posTeamRole(membership?.role))) ||
          (a.id === "app-tiquet" && Boolean(tiquetTeamRole(membership?.role))) ||
          (a.id === "app-marketing" && Boolean(marketingTeamRole(membership?.role)))
        );
      const teamLaunchBlocked = isManagedProduct && membership?.role !== "owner" && !teamMappedLaunchReady;
      const launchBlocked = setupPending || teamLaunchBlocked;
      return { ...a, status: setupPending ? "syncing" : "beta", metrics: undefined, lastSync: undefined,
        description: setupPending
          ? "Your Hub access is active. V79 Digital is completing this product workspace before launch is enabled."
          : teamLaunchBlocked
            ? a.id === "app-ffpro"
              ? "FFPRO full-account finance access is restricted to the workspace owner. The owner can share selected FFPRO projects with editors or viewers inside FFPRO."
              : "This product is enabled for the workspace, but this team role is not eligible for launch."
            : managedDescriptions[a.id] || a.description,
        features: managedDescriptions[a.id] ? [] : a.features,
        ssoSupported: ["app-ffpro","app-tiquet","app-marketing","app-v79pos"].includes(a.id) && !launchBlocked,
        appUrl: a.id === "app-academy" ? academyPublicUrl : a.appUrl,
        launchReady: !launchBlocked,
        accessMessage: setupPending
          ? "Product workspace setup pending"
          : teamLaunchBlocked
            ? a.id === "app-ffpro"
              ? "FFPRO full-account finance access is workspace-owner only"
              : "Your workspace role is not eligible to launch this product"
            : undefined,
      };
    }));
});

// Update an ecosystem application configuration (e.g. custom URL, status)
app.put("/api/ecosystem/apps/:id", async (req, res) => {
  const { id } = req.params;
  const organizationId = (req as any).user.organizationId;
  if (!organizationCanMutateApp(store, organizationId, id, posIdentity.organizationId)) return res.status(403).json({ error: "Only custom apps owned by this workspace can be changed" });
  const index = store.ecosystemApps.findIndex((a) => a.id === id && a.ownerOrganizationId === organizationId);
  if (index === -1) {
    return res.status(404).json({ error: "Ecosystem app not found" });
  }

  const fields = req.body;
  if (!fields || typeof fields !== "object" || Array.isArray(fields)) return res.status(400).json({ error: "App changes must be an object" });
  const allowed = new Set(["name", "shortName", "tagline", "description", "category", "status", "appUrl", "githubRepo"]);
  if (!Object.keys(fields).length || Object.keys(fields).some(key => !allowed.has(key))) return res.status(400).json({ error: "Unsupported app field" });
  if ("appUrl" in fields && !id.startsWith("app-custom-")) return res.status(400).json({ error: "Managed app links cannot be changed" });
  const changes: Record<string, string | undefined> = {};
  for (const key of ["name", "shortName", "tagline", "description"] as const) {
    if (key in fields) {
      const value = catalogText(fields[key], key === "description" ? 1000 : 120);
      if (!value) return res.status(400).json({ error: `Invalid ${key}` });
      changes[key] = value;
    }
  }
  if ("category" in fields) {
    if (!["finance", "support", "marketing", "operations", "analytics", "team"].includes(fields.category)) return res.status(400).json({ error: "Invalid category" });
    changes.category = fields.category;
  }
  if ("status" in fields) {
    if (!["active", "syncing", "maintenance", "beta"].includes(fields.status)) return res.status(400).json({ error: "Invalid status" });
    changes.status = fields.status;
  }
  if ("appUrl" in fields) {
    const url = catalogHttpsUrl(fields.appUrl);
    if (!url) return res.status(400).json({ error: "App URL must be HTTPS without credentials" });
    changes.appUrl = url;
  }
  if ("githubRepo" in fields) {
    if (fields.githubRepo !== null && fields.githubRepo !== "" && !catalogHttpsUrl(fields.githubRepo)) return res.status(400).json({ error: "Repository URL must be HTTPS" });
    changes.githubRepo = fields.githubRepo ? catalogHttpsUrl(fields.githubRepo)! : undefined;
  }
  store.ecosystemApps[index] = { ...store.ecosystemApps[index], ...changes, lastSync: new Date().toISOString() };

  await saveStore(store);
  broadcast(organizationId, { type: "ECOSYSTEM_APPS_UPDATED" });
  res.json(store.ecosystemApps[index]);
});

// Register a custom ecosystem app
app.post("/api/ecosystem/apps", async (req, res) => {
  const { name, shortName, tagline, description, category, appUrl, githubRepo } = req.body || {};
  const safeName = catalogText(name, 120);
  const safeUrl = catalogHttpsUrl(appUrl);
  const safeShortName = shortName === undefined ? safeName?.slice(0, 8) : catalogText(shortName, 120);
  const safeTagline = tagline === undefined ? "Custom Ecosystem Module" : catalogText(tagline, 120);
  const safeDescription = description === undefined ? "External application link for this workspace." : catalogText(description, 1000);
  const safeRepo = githubRepo === undefined || githubRepo === "" ? undefined : catalogHttpsUrl(githubRepo);
  if (!safeName || !safeUrl || !safeShortName || !safeTagline || !safeDescription ||
      (safeRepo === null) || (category !== undefined && !["finance", "support", "marketing", "operations", "analytics", "team"].includes(category))) {
    return res.status(400).json({ error: "Valid app details and HTTPS launch URL are required" });
  }

  const newApp: EcosystemApp = {
    id: "app-custom-" + crypto.randomUUID(),
    name: safeName,
    shortName: safeShortName,
    tagline: safeTagline,
    description: safeDescription,
    category: category || "operations",
    status: "active",
    appUrl: safeUrl,
    githubRepo: safeRepo,
    iconName: "Boxes",
    colorScheme: {
      primary: "from-indigo-600 to-cyan-600",
      bgGradient: "bg-gradient-to-br from-indigo-500/10 via-cyan-500/5 to-transparent",
      badgeBg: "bg-indigo-500/15 border-indigo-500/30",
      badgeText: "text-indigo-400",
      border: "border-indigo-500/30 hover:border-indigo-500/60"
    },
    metrics: [{ label: "Status", value: "Connected", sublabel: "Custom integration" }],
    features: ["External application link"],
    ssoSupported: false,
    isFlagship: false,
    version: "v1.0.0",
    lastSync: new Date().toISOString(),
    ownerOrganizationId: (req as any).user.organizationId
  };

  store.ecosystemApps.push(newApp);
  const organizationId = (req as any).user.organizationId;
  if (!organizationCanAccessApp(store, organizationId, newApp.id, posIdentity.organizationId)) {
    store.appEntitlements.push({ organizationId, appId: newApp.id, enabled: true, createdAt: new Date().toISOString() });
  }
  await saveStore(store);
  broadcast(organizationId, { type: "ECOSYSTEM_APPS_UPDATED" });
  res.status(201).json(newApp);
});

// ==========================================
// VITE INTEGRATION & SERVER BOOT
// ==========================================

async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa"
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.join(__dirname, "dist");
    app.use(express.static(distDir, {
      setHeaders(res, filePath) {
        if (filePath.endsWith("index.html")) {
          res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0");
          res.setHeader("Pragma", "no-cache");
          res.setHeader("Expires", "0");
        } else if (filePath.includes(`${path.sep}assets${path.sep}`)) {
          res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
        }
      },
    }));
    app.get("*", (_req, res) => {
      res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0");
      res.setHeader("Pragma", "no-cache");
      res.setHeader("Expires", "0");
      res.sendFile(path.join(distDir, "index.html"));
    });
  }

  const PORT = Number(process.env.PORT || 3040);
  server.listen(PORT, "0.0.0.0", () => {
    if (trialReminderLeader && recoveryEmailEnabled) {
      void dispatchTrialReminders();
      const reminderTimer=setInterval(()=>{void dispatchTrialReminders();},3600000);
      reminderTimer.unref?.();
    }
    console.log(`V79 Client Hub Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();