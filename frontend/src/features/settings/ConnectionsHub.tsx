import React, { useState, useEffect, useMemo } from "react";
import { SearchIcon, RefreshCwIcon, PlugIcon, AlertCircleIcon, ShieldCheckIcon } from "../../icons";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { ActiveConnectionCard, ProviderCatalogCard } from "./ConnectionCard";
import { ConnectModal } from "./ConnectModal";
import { AccountManagementDrawer } from "./AccountManagementDrawer";
import { DisconnectConfirmModal } from "./DisconnectConfirmModal";
import type { NanviApiClient, ProviderPublic, ConnectionPublic } from "../../api";
import { useToast } from "../../components/ui/Toast";

type Props = {
  api: NanviApiClient;
  canManageOrg: boolean;
};

export function ConnectionsHub({ api, canManageOrg }: Props) {
  const notify = useToast();
  const [providers, setProviders] = useState<ProviderPublic[]>([]);
  const [connections, setConnections] = useState<ConnectionPublic[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [selectedScope, setSelectedScope] = useState<string>("all");
  const [testingId, setTestingId] = useState<string | null>(null);

  // Modals & Drawer State
  const [connectProvider, setConnectProvider] = useState<ProviderPublic | null>(null);
  const [drawerConnection, setDrawerConnection] = useState<ConnectionPublic | null>(null);
  const [disconnectConnection, setDisconnectConnection] = useState<ConnectionPublic | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [provRes, catsRes, connRes] = await Promise.all([
        api.listProviders(),
        api.listConnectionCategories(),
        api.listConnections(),
      ]);
      setProviders(provRes.providers || []);
      setCategories(catsRes || []);
      setConnections(connRes.connections || []);

      // If drawer is currently open for a connection, refresh its object reference
      if (drawerConnection) {
        const updated = (connRes.connections || []).find((c) => c.id === drawerConnection.id);
        if (updated) setDrawerConnection(updated);
      }
    } catch (err: any) {
      notify(err.message || "Failed to load connections data.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleTestConnection = async (conn: ConnectionPublic) => {
    try {
      setTestingId(conn.id);
      const res = await api.testConnection(conn.id);
      if (res.ok) {
        notify(`${conn.display_name} connectivity verified successfully!`, "success");
      } else {
        notify(res.message || "Connection test failed.", "error");
      }
      await loadData();
    } catch (err: any) {
      notify(err.message || "Test failed.", "error");
    } finally {
      setTestingId(null);
    }
  };

  // Set of connected provider IDs
  const connectedProviderIds = useMemo(() => {
    return new Set((connections || []).map((c) => c?.provider || ""));
  }, [connections]);

  // Filtered active connections
  const filteredConnections = useMemo(() => {
    return (connections || []).filter((c) => {
      if (!c) return false;
      if (selectedScope !== "all" && c.scope_level !== selectedScope) return false;
      if (search) {
        const q = search.toLowerCase();
        const name = (c.display_name || "").toLowerCase();
        const prov = (c.provider || "").toLowerCase();
        const acc = (c.account_identifier || "").toLowerCase();
        if (!name.includes(q) && !prov.includes(q) && !acc.includes(q)) return false;
      }
      return true;
    });
  }, [connections, selectedScope, search]);

  // Filtered providers catalog
  const filteredProviders = useMemo(() => {
    return (providers || []).filter((p) => {
      if (!p) return false;
      const isComingSoon =
        p.available_reason === "coming_soon" ||
        (!p.available && p.available_reason !== "not_configured");
      if (isComingSoon) return false;
      const cats = Array.isArray(p.categories) ? p.categories : [];
      if (selectedCategory !== "All" && !cats.includes(selectedCategory)) {
        return false;
      }
      if (search) {
        const q = search.toLowerCase();
        const name = (p.name || "").toLowerCase();
        const desc = (p.description || "").toLowerCase();
        const cat = cats.join(" ").toLowerCase();
        if (!name.includes(q) && !desc.includes(q) && !cat.includes(q)) return false;
      }
      return true;
    });
  }, [providers, selectedCategory, search]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "2rem",
        width: "100%",
        minWidth: 0,
        fontFamily: "var(--font-sans, 'IBM Plex Sans', -apple-system, sans-serif)",
      }}
    >
      {/* Search, Scope Filter, and Refresh Bar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
          background: "var(--bg-surface, #ffffff)",
          padding: "1rem",
          borderRadius: "0.5rem",
          border: "1px solid var(--border, #e2e8f0)",
          boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
        }}
      >
        {/* Search Input */}
        <div style={{ position: "relative", minWidth: "280px", flex: "1 1 auto" }}>
          <div
            style={{
              position: "absolute",
              left: "0.75rem",
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--text-muted, #64748b)",
              display: "flex",
              alignItems: "center",
            }}
          >
            <SearchIcon size={16} />
          </div>
          <input
            type="text"
            placeholder="Search connections, services, or providers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem 0.5rem 2.25rem",
              borderRadius: "0.375rem",
              border: "1px solid var(--border, #e2e8f0)",
              background: "var(--bg-sunken, #f8fafc)",
              color: "var(--text, #0f172a)",
              fontSize: "0.875rem",
            }}
          />
        </div>

        {/* Scope and Refresh Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <select
            value={selectedScope}
            onChange={(e) => setSelectedScope(e.target.value)}
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "0.375rem",
              border: "1px solid var(--border, #e2e8f0)",
              background: "var(--bg-sunken, #f8fafc)",
              color: "var(--text, #0f172a)",
              fontSize: "0.875rem",
              fontWeight: 500,
            }}
          >
            <option value="all">All Scopes</option>
            <option value="user">Personal Accounts</option>
            <option value="organization">Organization Accounts</option>
          </select>

          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={loadData}
            disabled={loading}
            style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
          >
            <RefreshCwIcon size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Category Pills Navigation */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          overflowX: "auto",
          paddingBottom: "0.375rem",
          scrollbarWidth: "thin",
        }}
      >
        <button
          type="button"
          onClick={() => setSelectedCategory("All")}
          style={{
            padding: "0.375rem 0.875rem",
            borderRadius: "2rem",
            fontSize: "0.75rem",
            fontWeight: selectedCategory === "All" ? 600 : 500,
            border: `1px solid ${selectedCategory === "All" ? "var(--primary-600, #0f766e)" : "var(--border, #e2e8f0)"}`,
            background: selectedCategory === "All" ? "var(--primary-600, #0f766e)" : "var(--bg-surface, #ffffff)",
            color: selectedCategory === "All" ? "#ffffff" : "var(--text-secondary, #475569)",
            cursor: "pointer",
            whiteSpace: "nowrap",
            transition: "all 0.15s ease",
          }}
        >
          All Categories
        </button>
        {(categories || []).map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setSelectedCategory(cat)}
            style={{
              padding: "0.375rem 0.875rem",
              borderRadius: "2rem",
              fontSize: "0.75rem",
              fontWeight: selectedCategory === cat ? 600 : 500,
              border: `1px solid ${selectedCategory === cat ? "var(--primary-600, #0f766e)" : "var(--border, #e2e8f0)"}`,
              background: selectedCategory === cat ? "var(--primary-600, #0f766e)" : "var(--bg-surface, #ffffff)",
              color: selectedCategory === cat ? "#ffffff" : "var(--text-secondary, #475569)",
              cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "all 0.15s ease",
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* SECTION 1: Connected Accounts */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
              Active Connections ({filteredConnections.length})
            </h2>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
              Authenticated provider accounts with service-level access controls and synchronization.
            </p>
          </div>
        </div>

        {filteredConnections.length === 0 ? (
          <div
            style={{
              padding: "2.5rem 1.5rem",
              textAlign: "center",
              background: "var(--bg-surface, #ffffff)",
              borderRadius: "0.5rem",
              border: "1px dashed var(--border, #e2e8f0)",
              color: "var(--text-muted, #64748b)",
            }}
          >
            <PlugIcon size={32} style={{ margin: "0 auto 0.75rem", opacity: 0.4 }} />
            <p style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
              No active connections found
            </p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem" }}>
              Choose a provider from the catalog below to connect your first enterprise integration.
            </p>
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))",
              gap: "1.25rem",
              minWidth: 0,
            }}
          >
            {filteredConnections.map((conn) => (
              <ActiveConnectionCard
                key={conn.id}
                connection={conn}
                onManage={(c) => setDrawerConnection(c)}
                onTest={handleTestConnection}
                onDisconnect={(c) => setDisconnectConnection(c)}
                testing={testingId === conn.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* SECTION 2: Integrations Catalog */}
      <div>
        <div style={{ marginBottom: "1rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 600, color: "var(--text, #0f172a)" }}>
            Integrations Catalog ({filteredProviders.length})
          </h2>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
            Connect cloud services, enterprise storage, mailboxes, and databases for assistant retrieval.
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))",
            gap: "1.25rem",
            minWidth: 0,
          }}
        >
          {filteredProviders.map((provider, idx) => (
            <ProviderCatalogCard
              key={provider.id || provider.name || idx}
              provider={provider}
              isConnected={connectedProviderIds.has(provider.id)}
              onConnect={(p) => setConnectProvider(p)}
            />
          ))}
        </div>
      </div>

      {/* Provider Connection Wizard Modal */}
      <ConnectModal
        open={Boolean(connectProvider)}
        provider={connectProvider}
        onClose={() => setConnectProvider(null)}
        onSuccess={() => loadData()}
        api={api}
        canManageOrg={canManageOrg}
      />

      {/* Enterprise Account Management Drawer */}
      <AccountManagementDrawer
        open={Boolean(drawerConnection)}
        connection={drawerConnection}
        onClose={() => setDrawerConnection(null)}
        onUpdated={() => loadData()}
        onRequestDisconnect={(conn) => {
          setDrawerConnection(null);
          setDisconnectConnection(conn);
        }}
        api={api}
      />

      {/* Safe Disconnect & Revocation Modal */}
      <DisconnectConfirmModal
        open={Boolean(disconnectConnection)}
        connection={disconnectConnection}
        onClose={() => setDisconnectConnection(null)}
        onSuccess={() => loadData()}
        api={api}
      />
    </div>
  );
}
