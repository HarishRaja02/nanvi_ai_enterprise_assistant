import { BookOpen, Database, FileText, Landmark, Mail, MessagesSquare, ScrollText, Settings, Users, type LucideIcon } from "lucide-react";
import type { View } from "../../lib/access";

/** One icon per module, from a single library, so navigation reads consistently everywhere. */
export const NAV_ICONS: Record<View, LucideIcon> = {
  Chat: MessagesSquare,
  Knowledge: BookOpen,
  Email: Mail,
  Data: Database,
  Reports: FileText,
  Finance: Landmark,
  HR: Users,
  Audit: ScrollText,
  Settings: Settings,
};

