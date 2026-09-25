import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { PlugIcon, CheckCircleIcon, AlertCircleIcon, SettingsIcon } from "../../icons";
import type { ConnectionPublic, ProviderPublic } from "../../api";

type ConnectionCardProps = {
  connection: ConnectionPublic;
  onManage: (conn: ConnectionPublic) => void;
  onTest: (conn: ConnectionPublic) => void;
  testing?: boolean;
};

export function ActiveConnectionCard({ connection, onManage, onTest, testing }: ConnectionCardProps) {
  const isHealthy = connection.status === "CONNECTED";
  const isError = connection.status === "ERROR";

  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: "0.5rem",
      padding: "1.125rem",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      gap: "1rem",
      transition: "border-color 0.2s, box-shadow 0.2s",
      boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }}>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{
              width: "2.5rem",
              height: "2.5rem",
              borderRadius: "0.5rem",
              background: "var(--bg-sunken)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "1px solid var(--border)",
              color: "var(--primary-600)",
            }}>
              <PlugIcon size={20} />
            </div>
            <div>
              <h4 style={{ margin: 0, fontSize: "var(--text-base)", fontWeight: "var(--weight-semibold)", color: "var(--text)" }}>
                {connection?.display_name || connection?.provider || "Connection"}
              </h4>
              <p style={{ margin: "0.125rem 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                {connection?.account_identifier || connection?.provider || ""}
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.375rem", alignItems: "center" }}>
            <Badge tone={connection?.scope_level === "organization" ? "primary" : "neutral"}>
              {connection?.scope_level === "organization" ? "Org" : "Personal"}
            </Badge>
            <Badge tone={isHealthy ? "success" : isError ? "danger" : "neutral"}>
              {connection?.status || "UNKNOWN"}
            </Badge>
          </div>
        </div>

        {connection.status_reason && (
          <div style={{
            marginTop: "0.75rem",
            padding: "0.5rem 0.625rem",
            background: "rgba(239, 68, 68, 0.08)",
            borderRadius: "0.375rem",
            fontSize: "0.75rem",
            color: "var(--error-600)",
            display: "flex",
            alignItems: "center",
            gap: "0.375rem",
          }}>
            <AlertCircleIcon size={14} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {connection.status_reason}
            </span>
          </div>
        )}
      </div>

      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderTop: "1px solid var(--border-subtle)",
        paddingTop: "0.75rem",
      }}>
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          {connection.last_tested_at ? `Tested ${new Date(connection.last_tested_at).toLocaleDateString()}` : "Not tested yet"}
        </span>

        <div style={{ display: "flex", gap: "0.5rem" }}>
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
            variant="secondary"
            size="sm"
            onClick={() => onManage(connection)}
          >
            Manage
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
  const isComingSoon = provider?.available_reason === "coming_soon" || (!provider?.available && provider?.available_reason !== "not_configured");
  const isSetupRequired = provider?.available_reason === "not_configured";
  const categoriesList = Array.isArray(provider?.categories) ? provider.categories.join(", ") : "";
  const authLabel = provider?.auth_type === "oauth2" ? "OAuth 2.0" : (provider?.auth_type || "api_key").replace("_", " ");

  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: "0.5rem",
      padding: "1.125rem",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      gap: "0.875rem",
      boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
      opacity: isComingSoon ? 0.75 : 1,
    }}>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{
              width: "2.5rem",
              height: "2.5rem",
              borderRadius: "0.5rem",
              background: "var(--bg-sunken)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "1px solid var(--border)",
              color: isAvailable ? "var(--primary-600)" : "var(--text-muted)",
            }}>
              <PlugIcon size={20} />
            </div>
            <div>
              <h4 style={{ margin: 0, fontSize: "var(--text-base)", fontWeight: "var(--weight-semibold)" }}>{provider?.name || "Provider"}</h4>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                {categoriesList}
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

        <p style={{
          margin: "0.75rem 0 0",
          fontSize: "var(--text-xs)",
          color: "var(--text-secondary)",
          lineHeight: 1.45,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}>
          {provider?.description || ""}
        </p>
      </div>

      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderTop: "1px solid var(--border-subtle)",
        paddingTop: "0.75rem",
      }}>
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "capitalize" }}>
          {authLabel}
        </span>

        {isAvailable ? (
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => onConnect(provider)}
          >
            {isConnected ? "Add Another" : "Connect"}
          </Button>
        ) : isSetupRequired ? (
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Missing server config</span>
        ) : (
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Coming soon</span>
        )}
      </div>
    </div>
  );
}
