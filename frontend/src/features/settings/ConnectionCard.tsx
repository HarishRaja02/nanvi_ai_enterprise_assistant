import React from "react";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { BrandLogo } from "../../components/brand/BrandLogo";
import { CheckCircleIcon, AlertCircleIcon, RefreshCwIcon, TrashIcon } from "../../icons";
import type { ConnectionPublic, ProviderPublic } from "../../api";

type ActiveConnectionCardProps = {
  connection: ConnectionPublic;
  onManage: (conn: ConnectionPublic) => void;
  onTest: (conn: ConnectionPublic) => void;
  onDisconnect?: (conn: ConnectionPublic) => void;
  testing?: boolean;
};

export function ActiveConnectionCard({
  connection,
  onManage,
  onTest,
  onDisconnect,
  testing,
}: ActiveConnectionCardProps) {
  const isHealthy = connection.status === "CONNECTED";
  const isError = connection.status === "ERROR";
  const isReauth = connection.status === "REAUTH_REQUIRED";

  const services = connection.services || [];
  const enabledServices = services.filter((s) => s.enabled);
  const enabledCount = connection.enabled_services_count ?? enabledServices.length;
  const totalCount = connection.total_services_count ?? services.length;

  return (
    <div
      style={{
        background: "var(--bg-surface, #ffffff)",
        border: "1px solid var(--border, #e2e8f0)",
        borderRadius: "0.625rem",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        gap: "1rem",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
    >
      <div>
        {/* Header with Provider Logo, Name, Account Email & Status Badges */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
            <div
              style={{
                width: "2.75rem",
                height: "2.75rem",
                borderRadius: "0.5rem",
                background: "var(--bg-sunken, #f8fafc)",
                border: "1px solid var(--border, #e2e8f0)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <BrandLogo name={connection.provider} size={28} />
            </div>
            <div>
              <h4
                style={{
                  margin: 0,
                  fontSize: "0.9375rem",
                  fontWeight: 600,
                  color: "var(--text, #0f172a)",
                  letterSpacing: "-0.01em",
                }}
              >
                {connection.display_name || connection.provider}
              </h4>
              <p style={{ margin: "0.125rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                {connection.account_identifier || connection.provider}
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.375rem", alignItems: "center" }}>
            <Badge tone={connection.scope_level === "organization" ? "primary" : "neutral"}>
              {connection.account_type || (connection.scope_level === "organization" ? "Organization" : "Personal")}
            </Badge>
            <Badge tone={isHealthy ? "success" : isError ? "danger" : isReauth ? "warning" : "neutral"}>
              {connection.status}
            </Badge>
          </div>
        </div>

        {/* Enabled Services Counter & Service Pills */}
        <div
          style={{
            marginTop: "1rem",
            padding: "0.625rem 0.75rem",
            background: "var(--bg-sunken, #f8fafc)",
            borderRadius: "0.375rem",
            border: "1px solid var(--border-subtle, #f1f5f9)",
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary, #475569)" }}>
              {totalCount > 0 ? `${enabledCount} of ${totalCount} services enabled` : "Service active"}
            </span>
            <span style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)" }}>
              {connection.last_synced_at
                ? `Synced ${new Date(connection.last_synced_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : "Not synced"}
            </span>
          </div>

          {enabledServices.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
              {enabledServices.slice(0, 4).map((srv) => (
                <span
                  key={srv.id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.3125rem",
                    padding: "0.1875rem 0.5rem",
                    background: "var(--bg-surface, #ffffff)",
                    borderRadius: "0.25rem",
                    border: "1px solid var(--border, #e2e8f0)",
                    fontSize: "0.6875rem",
                    color: "var(--text, #0f172a)",
                    fontWeight: 500,
                  }}
                >
                  <BrandLogo name={srv.id} size={14} />
                  {srv.name}
                </span>
              ))}
              {enabledServices.length > 4 && (
                <span
                  style={{
                    fontSize: "0.6875rem",
                    color: "var(--text-muted, #64748b)",
                    alignSelf: "center",
                    padding: "0 0.25rem",
                  }}
                >
                  +{enabledServices.length - 4} more
                </span>
              )}
            </div>
          )}
        </div>

        {/* Status reason alert if any */}
        {connection.status_reason && (
          <div
            style={{
              marginTop: "0.75rem",
              padding: "0.5rem 0.625rem",
              background: isHealthy ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)",
              borderRadius: "0.375rem",
              fontSize: "0.75rem",
              color: isHealthy ? "var(--success-700, #047857)" : "var(--error-600, #dc2626)",
              display: "flex",
              alignItems: "center",
              gap: "0.375rem",
            }}
          >
            {isHealthy ? <CheckCircleIcon size={14} /> : <AlertCircleIcon size={14} />}
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {connection.status_reason}
            </span>
          </div>
        )}
      </div>

      {/* Footer Actions: Test, Manage Services, Disconnect */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid var(--border-subtle, #f1f5f9)",
          paddingTop: "0.75rem",
        }}
      >
        <span style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)" }}>
          {connection.last_tested_at
            ? `Tested ${new Date(connection.last_tested_at).toLocaleDateString()}`
            : "Untested"}
        </span>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onTest(connection)}
            disabled={testing}
          >
            {testing ? "Testing..." : "Test"}
          </Button>

          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => onManage(connection)}
            style={{
              background: "var(--primary-700, #0f766e)",
              borderColor: "var(--primary-700, #0f766e)",
              fontWeight: 500,
            }}
          >
            Manage Services
          </Button>
        </div>
      </div>
    </div>
  );
}

type ProviderCatalogCardProps = {
  provider: ProviderPublic;
  isConnected: boolean;
  onConnect: (provider: ProviderPublic) => void;
};

export function ProviderCatalogCard({ provider, isConnected, onConnect }: ProviderCatalogCardProps) {
  const isAvailable = Boolean(provider?.available);
  const isComingSoon =
    provider?.available_reason === "coming_soon" ||
    (!provider?.available && provider?.available_reason !== "not_configured");
  const isSetupRequired = provider?.available_reason === "not_configured";
  const supportedServices = provider?.supported_services || [];
  const authLabel =
    provider?.auth_type === "oauth2"
      ? "OAuth 2.0"
      : provider?.auth_type === "db_password"
      ? "Direct Database"
      : provider?.auth_type === "filesystem"
      ? "Desktop Agent"
      : (provider?.auth_type || "api_key").replace("_", " ");

  return (
    <div
      style={{
        background: "var(--bg-surface, #ffffff)",
        border: "1px solid var(--border, #e2e8f0)",
        borderRadius: "0.625rem",
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        gap: "0.875rem",
        boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
        opacity: isComingSoon ? 0.75 : 1,
        transition: "border-color 0.2s, box-shadow 0.2s",
      }}
    >
      <div>
        {/* Header with Provider Logo, Name, Categories and Status Badge */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
            <div
              style={{
                width: "2.75rem",
                height: "2.75rem",
                borderRadius: "0.5rem",
                background: "var(--bg-sunken, #f8fafc)",
                border: "1px solid var(--border, #e2e8f0)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <BrandLogo name={provider.id || provider.name} size={28} />
            </div>
            <div>
              <h4
                style={{
                  margin: 0,
                  fontSize: "0.9375rem",
                  fontWeight: 600,
                  color: "var(--text, #0f172a)",
                  letterSpacing: "-0.01em",
                }}
              >
                {provider?.name || "Provider"}
              </h4>
              <span style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)" }}>
                {Array.isArray(provider?.categories) ? provider.categories.join(", ") : ""}
              </span>
            </div>
          </div>

          <div>
            {isConnected ? (
              <Badge tone="success">Connected</Badge>
            ) : isSetupRequired ? (
              <Badge tone="neutral">Setup required</Badge>
            ) : isComingSoon ? (
              <Badge tone="neutral">Coming soon</Badge>
            ) : (
              <Badge tone="primary">Ready</Badge>
            )}
          </div>
        </div>

        {/* Clear Description */}
        <p
          style={{
            margin: "0.75rem 0 0",
            fontSize: "0.75rem",
            color: "var(--text-secondary, #475569)",
            lineHeight: 1.45,
            minHeight: "2.2rem",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {provider?.description || ""}
        </p>

        {/* Supported Services Chips */}
        {supportedServices.length > 0 && (
          <div style={{ marginTop: "0.625rem", display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
            {supportedServices.slice(0, 4).map((s) => (
              <span
                key={s.id}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.25rem",
                  padding: "0.125rem 0.375rem",
                  background: "var(--bg-sunken, #f8fafc)",
                  borderRadius: "0.25rem",
                  fontSize: "0.6875rem",
                  color: "var(--text-secondary, #475569)",
                  border: "1px solid var(--border-subtle, #f1f5f9)",
                }}
              >
                <BrandLogo name={s.id} size={12} />
                {s.name}
              </span>
            ))}
            {supportedServices.length > 4 && (
              <span style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)", alignSelf: "center" }}>
                +{supportedServices.length - 4} more
              </span>
            )}
          </div>
        )}
      </div>

      {/* Footer with Auth Type & Connect Button */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid var(--border-subtle, #f1f5f9)",
          paddingTop: "0.75rem",
        }}
      >
        <span
          style={{
            fontSize: "0.6875rem",
            color: "var(--text-muted, #64748b)",
            textTransform: "capitalize",
            fontFamily: "var(--font-sans, inherit)",
          }}
        >
          {authLabel}
        </span>

        {isAvailable ? (
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => onConnect(provider)}
            style={{
              background: isConnected ? "var(--bg-surface, #ffffff)" : "var(--primary-700, #0f766e)",
              color: isConnected ? "var(--primary-700, #0f766e)" : "#ffffff",
              border: isConnected ? "1px solid var(--primary-600, #0f766e)" : "none",
            }}
          >
            {isConnected ? "Add Another" : "Connect"}
          </Button>
        ) : isSetupRequired ? (
          <span style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)" }}>Missing server config</span>
        ) : (
          <span style={{ fontSize: "0.6875rem", color: "var(--text-muted, #64748b)" }}>Coming soon</span>
        )}
      </div>
    </div>
  );
}
