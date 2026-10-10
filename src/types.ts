export type UserRole = 'admin' | 'manager' | 'staff' | 'viewer';

export type ViewState =
  | 'overview'
  | 'connections'
  | 'team'
  | 'security'
  | 'billing'
  | 'admin'
  | 'dashboard'
  | 'users'
  | 'assistant';

export interface User {
  id: string;
  username: string;
  fullName?: string;
  role: UserRole;
  platformOperator?: boolean;
  ownerAgent?: boolean;
  workspaceOwner?: boolean;
  email?: string;
  permissions?: ViewState[];
  appIds?: string[];
  lastLogin?: string;
  createdAt?: string;
}

export type EcosystemCategory =
  | 'finance'
  | 'support'
  | 'marketing'
  | 'operations'
  | 'analytics'
  | 'team';

export interface EcosystemApp {
  id: string;
  name: string;
  shortName: string;
  tagline: string;
  description: string;
  category: EcosystemCategory;
  status: 'active' | 'syncing' | 'maintenance' | 'beta';
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
  launchReady?: boolean;
  accessMessage?: string;
}
