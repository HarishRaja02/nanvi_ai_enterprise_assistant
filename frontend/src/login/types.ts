export type AuthView = 'signin' | 'signup' | 'forgot' | 'dashboard';

export interface RoleProfile {
  id: 'ceo' | 'finance' | 'hr' | 'manager' | 'employee' | 'itadmin';
  title: string;
  department: string;
  username: string;
  iconName: string;
  description: string;
  permissions: string[];
}

export interface UserSession {
  id: string;
  name: string;
  username: string;
  email: string;
  avatarUrl?: string;
  roleId: string;
  roleTitle: string;
  department: string;
  accessLevel: string;
  sessionToken: string;
  lastLogin: string;
  permissions: string[];
}

export interface QuoteItem {
  id: string;
  category: string;
  headline: string[];
  quote: string;
  author: string;
}
