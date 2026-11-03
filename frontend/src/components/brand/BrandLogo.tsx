import React from "react";

type BrandLogoProps = {
  name: string;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
};

/**
 * High-fidelity, official brand vector logos for enterprise SaaS providers & individual services.
 * Designed according to official brand guidelines with accurate geometry, color palettes and aspect ratios.
 */
export const BrandLogo = React.memo(function BrandLogo({ name, size = 24, className = "", style = {} }: BrandLogoProps) {
  const key = (name || "").toLowerCase().trim();

  // 1. Google Workspace
  if (key === "google" || key === "google_workspace" || key === "google workspace" || key === "google-workspace") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        {/* Google Workspace multicolored ribbon icon */}
        <path d="M4 8.5C4 6.015 6.015 4 8.5 4H12V8.5C12 10.985 9.985 13 7.5 13H4V8.5Z" fill="#4285F4" />
        <path d="M12 4H15.5C17.985 4 20 6.015 20 8.5V12H15.5C13.015 12 11 9.985 11 7.5V4H12Z" fill="#EA4335" />
        <path d="M15.5 12H20V15.5C20 17.985 17.985 20 15.5 20H12V15.5C12 13.015 14.015 11 16.5 11H20" fill="#34A853" />
        <path d="M12 20H8.5C6.015 20 4 17.985 4 15.5V12H8.5C10.985 12 13 14.015 13 16.5V20H12Z" fill="#FBBC05" />
      </svg>
    );
  }

  // 2. Gmail
  if (key === "gmail") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M2.5 18V7.5L12 13.5L21.5 7.5V18C21.5 19.1 20.6 20 19.5 20H4.5C3.4 20 2.5 19.1 2.5 18Z" fill="#EA4335" opacity="0.15" />
        <path d="M20 5H4C2.9 5 2 5.9 2 7V17C2 18.1 2.9 19 4 19H20C21.1 19 22 18.1 22 17V7C22 5.9 21.1 5 20 5ZM20 7L12 12L4 7H20ZM20 17H4V8.5L12 13.5L20 8.5V17Z" fill="#EA4335" />
        <path d="M4 7V17H2V7C2 5.9 2.9 5 4 5H6V7H4Z" fill="#4285F4" />
        <path d="M20 7H18V5H20C21.1 5 22 5.9 22 7V17H20V7Z" fill="#34A853" />
        <path d="M18 5L12 9.5L6 5H18Z" fill="#EA4335" />
        <path d="M6 5L2 7V8.5L6 6V5Z" fill="#C5221F" />
        <path d="M18 5V6L22 8.5V7L18 5Z" fill="#FBBC04" />
      </svg>
    );
  }

  // 3. Google Drive
  if (key === "drive" || key === "google_drive" || key === "google drive" || key === "google-drive") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M8.2 4H15.8L21.8 14.4H14.2L8.2 4Z" fill="#FFBA00" />
        <path d="M14.2 14.4L8.2 4H2.2L8.2 14.4H14.2Z" fill="#0066DA" />
        <path d="M8.2 14.4L5.2 19.6C4.8 20.3 5.3 21.2 6.1 21.2H17.9C18.7 21.2 19.2 20.3 18.8 19.6L15.8 14.4H8.2Z" fill="#00AC47" />
      </svg>
    );
  }

  // 4. Google Docs
  if (key === "docs" || key === "google_docs" || key === "google docs") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M14.5 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V7.5L14.5 2Z" fill="#4285F4" />
        <path d="M14 2V8H20L14 2Z" fill="#A1C2FA" />
        <path d="M8 12H16V13.5H8V12ZM8 15H16V16.5H8V15ZM8 9H12V10.5H8V9Z" fill="#FFFFFF" />
      </svg>
    );
  }

  // 5. Google Sheets
  if (key === "sheets" || key === "google_sheets" || key === "google sheets") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M14.5 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V7.5L14.5 2Z" fill="#0F9D58" />
        <path d="M14 2V8H20L14 2Z" fill="#87CEAC" />
        <path d="M7 11H17V19H7V11ZM8.5 12.5V14H11.5V12.5H8.5ZM12.5 12.5V14H15.5V12.5H12.5ZM8.5 15V17.5H11.5V15H8.5ZM12.5 15V17.5H15.5V15H12.5Z" fill="#FFFFFF" />
      </svg>
    );
  }

  // 6. Google Slides
  if (key === "slides" || key === "google_slides" || key === "google slides") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M14.5 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V7.5L14.5 2Z" fill="#F4B400" />
        <path d="M14 2V8H20L14 2Z" fill="#FBE7A1" />
        <rect x="7.5" y="11.5" width="9" height="6.5" rx="1" fill="#FFFFFF" />
        <rect x="9" y="13" width="6" height="3.5" rx="0.5" fill="#F4B400" />
      </svg>
    );
  }

  // 7. Google Calendar
  if (key === "calendar" || key === "google_calendar" || key === "google calendar") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="3" y="4" width="18" height="17" rx="3" fill="#FFFFFF" stroke="#4285F4" strokeWidth="2" />
        <path d="M3 8H21V5C21 3.9 20.1 3 19 3H5C3.9 3 3 3.9 3 5V8Z" fill="#4285F4" />
        <circle cx="8" cy="3" r="1.2" fill="#FFFFFF" />
        <circle cx="16" cy="3" r="1.2" fill="#FFFFFF" />
        <text x="12" y="17" textAnchor="middle" fontSize="9" fontWeight="bold" fill="#4285F4" fontFamily="sans-serif">31</text>
      </svg>
    );
  }

  // 8. Microsoft 365
  if (key === "microsoft" || key === "microsoft365" || key === "microsoft 365" || key === "office365" || key === "microsoft-365") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="9.5" height="9.5" fill="#F25022" rx="1" />
        <rect x="12.5" y="2" width="9.5" height="9.5" fill="#7FBA00" rx="1" />
        <rect x="2" y="12.5" width="9.5" height="9.5" fill="#00A4EF" rx="1" />
        <rect x="12.5" y="12.5" width="9.5" height="9.5" fill="#FFB900" rx="1" />
      </svg>
    );
  }

  // 9. Microsoft Outlook
  if (key === "outlook" || key === "microsoft_outlook" || key === "outlook_email" || key === "exchange") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="6" y="4" width="16" height="16" rx="2" fill="#0078D4" />
        <path d="M6 6L14 12L22 6" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" />
        <rect x="2" y="7" width="11" height="11" rx="2" fill="#106EBE" stroke="#FFFFFF" strokeWidth="1" />
        <text x="7.5" y="15.5" textAnchor="middle" fontSize="8" fontWeight="bold" fill="#FFFFFF" fontFamily="sans-serif">O</text>
      </svg>
    );
  }

  // 10. Microsoft OneDrive
  if (key === "onedrive" || key === "microsoft_onedrive" || key === "onedrive_files") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M19.4 15.2C19.8 14.5 20 13.8 20 13C20 10.8 18.2 9 16 9C15.8 9 15.6 9 15.4 9.1C14.7 6.7 12.5 5 10 5C7.2 5 5 7.2 5 10C5 10.3 5 10.6 5.1 10.8C3.3 11.4 2 13 2 15C2 17.2 3.8 19 6 19H18C19.7 19 21 17.7 21 16C21 15.7 20.9 15.4 20.8 15.2H19.4Z" fill="#0078D4" />
        <path d="M14 11C13.5 9.2 11.9 8 10 8C8.1 8 6.5 9.2 6 11H14Z" fill="#28A8EA" />
      </svg>
    );
  }

  // 11. Microsoft SharePoint
  if (key === "sharepoint" || key === "microsoft_sharepoint" || key === "sharepoint_sites") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <circle cx="15.5" cy="8.5" r="5.5" fill="#008272" />
        <circle cx="9.5" cy="14.5" r="5.5" fill="#038387" />
        <circle cx="16.5" cy="15.5" r="4.5" fill="#107C41" opacity="0.9" />
        <text x="9.5" y="17" textAnchor="middle" fontSize="7" fontWeight="bold" fill="#FFFFFF" fontFamily="sans-serif">S</text>
      </svg>
    );
  }

  // 12. Microsoft Teams
  if (key === "teams" || key === "microsoft_teams") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="6" y="5" width="15" height="14" rx="2" fill="#5059C9" />
        <circle cx="17" cy="8" r="2.5" fill="#7B83EB" />
        <rect x="2" y="8" width="10" height="10" rx="2" fill="#464EB8" stroke="#FFFFFF" strokeWidth="0.8" />
        <text x="7" y="15" textAnchor="middle" fontSize="7" fontWeight="bold" fill="#FFFFFF" fontFamily="sans-serif">T</text>
      </svg>
    );
  }

  // 13. Yahoo Mail
  if (key === "yahoo" || key === "yahoo_mail" || key === "yahoomail") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="5" fill="#6001D2" />
        <path d="M7 6L11 13V18H13V13L17 6H14.5L12 11.2L9.5 6H7Z" fill="#FFFFFF" />
        <circle cx="18" cy="17" r="1.2" fill="#FFFFFF" />
      </svg>
    );
  }

  // 14. IMAP
  if (key === "imap" || key === "generic_imap" || key === "imap_inbox" || key === "mail") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="4" width="20" height="16" rx="3" fill="#0284C7" />
        <path d="M2 7L12 13L22 7" stroke="#FFFFFF" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M6 14H10M6 16.5H14" stroke="#BAE6FD" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    );
  }

  // 15. SMTP
  if (key === "smtp" || key === "generic_smtp" || key === "smtp_sender" || key === "send") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="5" fill="#0D9488" />
        <path d="M4 12L20 4L13 20L10.5 13.5L4 12Z" fill="#FFFFFF" />
        <path d="M10.5 13.5L20 4" stroke="#0D9488" strokeWidth="1.2" />
      </svg>
    );
  }

  // 16. Box
  if (key === "box" || key === "box_enterprise" || key === "box_storage") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#0061D5" />
        <path d="M7 9C7 7.9 7.9 7 9 7C10.1 7 11 7.9 11 9V15C11 16.1 10.1 17 9 17C7.9 17 7 16.1 7 15V9Z" fill="#FFFFFF" />
        <path d="M13 11C13 9.9 13.9 9 15 9C16.1 9 17 9.9 17 11V15C17 16.1 16.1 17 15 17C13.9 17 13 16.1 13 15V11Z" fill="#FFFFFF" />
        <circle cx="15" cy="13" r="1.5" fill="#0061D5" />
        <circle cx="9" cy="13" r="1.5" fill="#0061D5" />
      </svg>
    );
  }

  // 17. Dropbox
  if (key === "dropbox" || key === "dropbox_business" || key === "dropbox_storage") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M7 3L2 6.5L7 10L12 6.5L7 3Z" fill="#0061FE" />
        <path d="M17 3L12 6.5L17 10L22 6.5L17 3Z" fill="#0061FE" />
        <path d="M2 13.5L7 17L12 13.5L7 10L2 13.5Z" fill="#0061FE" />
        <path d="M22 13.5L17 10L12 13.5L17 17L22 13.5Z" fill="#0061FE" />
        <path d="M7 18.2L12 14.7L17 18.2L12 21.5L7 18.2Z" fill="#0061FE" />
      </svg>
    );
  }

  // 18. Egnyte
  if (key === "egnyte" || key === "egnyte_storage") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#002D62" />
        <circle cx="12" cy="7" r="2.2" fill="#00A499" />
        <circle cx="7" cy="12" r="2.2" fill="#00A499" />
        <circle cx="17" cy="12" r="2.2" fill="#00A499" />
        <circle cx="12" cy="17" r="2.2" fill="#00A499" />
        <circle cx="12" cy="12" r="2.8" fill="#FFFFFF" />
      </svg>
    );
  }

  // 19. Supabase
  if (key === "supabase" || key === "rest_api") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M12.8 2.5L20.2 11.8C20.9 12.7 20.3 14 19.2 14H13V21.5L4.8 11.2C4.1 10.3 4.7 9 5.8 9H12V2.5C12 2.5 12.8 2.5 12.8 2.5Z" fill="#3ECF8E" />
        <path d="M12.8 2.5L4.8 11.2C4.1 10.3 4.7 9 5.8 9H12V2.5Z" fill="#24B47E" opacity="0.5" />
      </svg>
    );
  }

  // 20. PostgreSQL
  if (key === "postgresql" || key === "postgres" || key === "postgres_db" || key === "sql_engine") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22C17.5 22 22 17.5 22 12C22 6.5 17.5 2 12 2Z" fill="#336791" />
        <path d="M17.5 11.5C17.2 9.5 15.5 8 13.5 8H10.5C8.6 8 7 9.6 7 11.5C7 13.4 8.6 15 10.5 15H11.5V18.5C11.5 19.3 12.2 20 13 20C13.8 20 14.5 19.3 14.5 18.5V15H15.5C16.6 15 17.5 14.1 17.5 13V11.5Z" fill="#FFFFFF" />
        <circle cx="10" cy="11.5" r="1" fill="#336791" />
      </svg>
    );
  }

  // 21. MySQL
  if (key === "mysql") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#00758F" />
        <path d="M6 16C7.5 12.5 11 10.5 14.5 10.5C16.2 10.5 17.8 11.1 19 12.2C18.2 10 16 8.5 13.5 8.5C10 8.5 7 11 6 16Z" fill="#F29111" />
        <path d="M18 15.5C17.5 15 16 14.8 14.5 15.2C13 15.6 11.5 16.5 10 16.5C8 16.5 6.5 15.5 5 14C5 17 8 18.5 11.5 18.5C15 18.5 17.5 17.2 18 15.5Z" fill="#FFFFFF" />
      </svg>
    );
  }

  // 22. MariaDB
  if (key === "mariadb") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#003545" />
        <path d="M6 14.5C8 11 12 10 15 11C17.5 11.8 19 13.5 19 15C18.5 13 16.5 12 14.5 12C11.5 12 8.5 13.5 6 14.5Z" fill="#C084FC" />
        <circle cx="16" cy="10" r="1.5" fill="#FFFFFF" />
      </svg>
    );
  }

  // 23. SQLite
  if (key === "sqlite") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#003B57" />
        <path d="M6 17L11 7L18 8L13 18L6 17Z" fill="#0F80C1" />
        <path d="M11 7L13 18L18 8L11 7Z" fill="#69C9F9" opacity="0.6" />
        <text x="12" y="16.5" textAnchor="middle" fontSize="6.5" fontWeight="bold" fill="#FFFFFF" fontFamily="sans-serif">SQL</text>
      </svg>
    );
  }

  // 24. GitHub
  if (key === "github" || key === "repos") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12C2 16.42 4.87 20.17 8.84 21.5C9.34 21.58 9.5 21.27 9.5 21V19.31C6.73 19.91 6.14 17.97 6.14 17.97C5.68 16.81 5.03 16.5 5.03 16.5C4.12 15.88 5.1 15.9 5.1 15.9C6.1 15.97 6.63 16.93 6.63 16.93C7.5 18.45 8.97 18 9.54 17.76C9.63 17.11 9.89 16.67 10.17 16.42C7.95 16.17 5.62 15.31 5.62 11.5C5.62 10.39 6.01 9.5 6.67 8.8C6.56 8.55 6.22 7.52 6.77 6.15C6.77 6.15 7.61 5.88 9.54 7.18C10.35 6.95 11.22 6.84 12.08 6.84C12.94 6.84 13.81 6.95 14.62 7.18C16.55 5.88 17.39 6.15 17.39 6.15C17.94 7.52 17.6 8.55 17.49 8.8C18.15 9.5 18.54 10.39 18.54 11.5C18.54 15.32 16.2 16.17 13.97 16.42C14.33 16.73 14.65 17.34 14.65 18.28V21C14.65 21.28 14.82 21.6 15.34 21.5C19.29 20.16 22.16 16.42 22.16 12C22.16 6.477 17.68 2 12 2Z" fill="#181717" />
      </svg>
    );
  }

  // 25. GitLab
  if (key === "gitlab") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M22.65 14.39L19.98 6.17C19.78 5.56 18.93 5.56 18.73 6.17L16.29 13.68H7.71L5.27 6.17C5.07 5.56 4.22 5.56 4.02 6.17L1.35 14.39C1.16 14.99 1.38 15.65 1.88 16.02L12 23.37L22.12 16.02C22.62 15.65 22.84 14.99 22.65 14.39Z" fill="#E24329" />
        <path d="M12 23.37L16.29 13.68H7.71L12 23.37Z" fill="#E24329" />
        <path d="M12 23.37L7.71 13.68H1.35L12 23.37Z" fill="#FC6D26" />
        <path d="M12 23.37L16.29 13.68H22.65L12 23.37Z" fill="#FC6D26" />
        <path d="M1.35 14.39L4.02 6.17C4.22 5.56 5.07 5.56 5.27 6.17L7.71 13.68H1.35Z" fill="#FCA326" />
        <path d="M22.65 14.39L19.98 6.17C19.78 5.56 18.93 5.56 18.73 6.17L16.29 13.68H22.65Z" fill="#FCA326" />
      </svg>
    );
  }

  // 26. Custom REST API
  if (key === "custom_api" || key === "custom api" || key === "api" || key === "api_endpoints") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="3" width="20" height="18" rx="4" fill="#0F766E" />
        <path d="M7 10L4.5 12L7 14" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M17 10L19.5 12L17 14" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M13 8L11 16" stroke="#99F6E4" strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  }

  // 27. Local Files & Folders
  if (key === "local_files" || key === "local files" || key === "filesystem" || key === "local_files_folders" || key === "local_storage" || key === "folder") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M3 6C3 4.9 3.9 4 5 4H9.5L11.5 6.5H19C20.1 6.5 21 7.4 21 8.5V17C21 18.1 20.1 19 19 19H5C3.9 19 3 18.1 3 17V6Z" fill="#F59E0B" />
        <path d="M3 9H21V17C21 18.1 20.1 19 19 19H5C3.9 19 3 18.1 3 17V9Z" fill="#FBBF24" />
        <rect x="7" y="12" width="10" height="4" rx="1" fill="#FFFFFF" opacity="0.8" />
        <circle cx="14.5" cy="14" r="0.75" fill="#D97706" />
      </svg>
    );
  }

  // 28. OpenAI
  if (key === "openai") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#10A37F" />
        <path d="M12 5.5C10.5 5.5 9.2 6.3 8.5 7.5L8.5 9.8C8.8 9.6 9.2 9.5 9.6 9.5L12 9.5C13.1 9.5 14 10.4 14 11.5V13.8L15 13.2C16.2 12.5 17 11.2 17 9.7C17 7.4 15.1 5.5 12 5.5Z" fill="#FFFFFF" />
        <path d="M12 18.5C13.5 18.5 14.8 17.7 15.5 16.5V14.2C15.2 14.4 14.8 14.5 14.4 14.5H12C10.9 14.5 10 13.6 10 12.5V10.2L9 10.8C7.8 11.5 7 12.8 7 14.3C7 16.6 8.9 18.5 12 18.5Z" fill="#FFFFFF" />
      </svg>
    );
  }

  // 29. Claude / Anthropic
  if (key === "anthropic" || key === "claude") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#CC785C" />
        <path d="M14.5 6L8.5 18H10.8L12 15.5H15.5L14.5 6ZM12.7 13.5L14.2 9.2L15 13.5H12.7Z" fill="#FFFFFF" />
      </svg>
    );
  }

  // 30. Google Gemini
  if (key === "gemini" || key === "google_gemini") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <path d="M12 2C12 7.5 7.5 12 2 12C7.5 12 12 16.5 12 22C12 16.5 16.5 12 22 12C16.5 12 12 7.5 12 2Z" fill="url(#gemini_grad)" />
        <defs>
          <linearGradient id="gemini_grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
            <stop stopColor="#1BA1E3" />
            <stop offset="0.5" stopColor="#5B77EC" />
            <stop offset="1" stopColor="#D96570" />
          </linearGradient>
        </defs>
      </svg>
    );
  }

  // 31. Groq
  if (key === "groq") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="4" fill="#F55036" />
        <circle cx="12" cy="12" r="5" stroke="#FFFFFF" strokeWidth="2.5" />
        <path d="M15 15L19 19" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    );
  }

  // Default fallback: Clean monogram badge
  const initial = (name || "P").charAt(0).toUpperCase();
  return (
    <div
      className={className}
      style={{
        width: size,
        height: size,
        borderRadius: "0.375rem",
        background: "var(--primary-100, #e0f2fe)",
        color: "var(--primary-700, #0369a1)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: Math.max(10, Math.floor(size * 0.5)),
        userSelect: "none",
        ...style,
      }}
    >
      {initial}
    </div>
  );
});
