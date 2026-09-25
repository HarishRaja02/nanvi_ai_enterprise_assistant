import { useState, useEffect, useMemo } from "react";
import { SearchIcon, RefreshCwIcon, PlugIcon, AlertCircleIcon } from "../../icons";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { ActiveConnectionCard, ProviderCatalogCard } from "./ConnectionCard";
import { ConnectModal } from "./ConnectModal";
import { ManageConnectionModal } from "./ManageConnectionModal";
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

  // Modals
  const [connectProvider, setConnectProvider] = useState<ProviderPublic | null>(null);
  const [manageConnection, setManageConnection] = useState<ConnectionPublic | null>(null);

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
        notify(`${conn.display_name} test succeeded!`, "success");
      } else {
        notify(res.message || "Test failed.", "error");
      }
      await loadData();
    } catch (err: any) {
      notify(err.message || "Test failed.", "error");
    } finally {
      setTestingId(null);
    }
  };

  // Connected provider IDs set
  const connectedProviderIds = useMemo(() => {
    return new Set(connections.map((c) => c.provider));
  }, [connections]);

  // Filtered active connections
  const filteredConnections = useMemo(() => {
    return connections.filter((c) => {
      if (selectedScope !== "all" && c.scope_level !== selectedScope) return false;
      if (search) {
        const q = search.toLowerCase();
        const name = c.display_name.toLowerCase();
        const prov = c.provider.toLowerCase();
        const acc = (c.account_identifier || "").toLowerCase();
        if (!name.includes(q) && !prov.includes(q) && !acc.includes(q)) return false;
      }
      return true;
    });
  }, [connections, selectedScope, search]);

  // Filtered providers catalog
  const filteredProviders = useMemo(() => {
    return providers.filter((p) => {
      if (selectedCategory !== "All" && !p.categories.includes(selectedCategory)) {
        return false;
      }
      if (search) {
        const q = search.toLowerCase();
        const name = p.name.toLowerCase();
        const desc = p.description.toLowerCase();
        const cat = p.categories.join(" ").toLowerCase();
        if (!name.includes(q) && !desc.includes(q) && !cat.includes(q)) return false;
      }
      return true;
    });
  }, [providers, selectedCategory, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Search and Filters Bar */}
      <div style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1rem",
        background: "var(--bg-surface)",
        padding: "1rem",
        borderRadius: "0.5rem",
        border: "1px solid var(--border)",
      }}>
        {/* Search Input */}
        <div style={{ position: "relative", minWidth: "260px", flex: "1 1 auto" }}>
          <div style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}>
            <SearchIcon size={16} />
          </div>
          <input
            type="text"
            placeholder="Search connections and providers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem 0.5rem 2.25rem",
              borderRadius: "0.375rem",
              border: "1px solid var(--border)",
              background: "var(--bg-sunken)",
              color: "var(--text)",
              fontSize: "var(--text-sm)",
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
              border: "1px solid var(--border)",
              background: "var(--bg-sunken)",
              color: "var(--text)",
              fontSize: "var(--text-sm)",
            }}
          >
            <option value="all">All Scopes</option>
            <option value="user">Personal Connections</option>
            <option value="organization">Organization Connections</option>
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

      {/* Category Pills */}
      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.25rem" }}>
        <button
          type="button"
          onClick={() => setSelectedCategory("All")}
          style={{
            padding: "0.375rem 0.875rem",
            borderRadius: "2rem",
            fontSize: "var(--text-xs)",
            fontWeight: "var(--weight-medium)",
            border: "1px solid var(--border)",
            background: selectedCategory === "All" ? "var(--primary-600)" : "var(--bg-surface)",
            color: selectedCategory === "All" ? "#ffffff" : "var(--text)",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          All Categories
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setSelectedCategory(cat)}
            style={{
              padding: "0.375rem 0.875rem",
              borderRadius: "2rem",
              fontSize: "var(--text-xs)",
              fontWeight: "var(--weight-medium)",
              border: "1px solid var(--border)",
              background: selectedCategory === cat ? "var(--primary-600)" : "var(--bg-surface)",
              color: selectedCategory === cat ? "#ffffff" : "var(--text)",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* SECTION 1: Active Connections */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)" }}>
              Active Connections ({filteredConnections.length})
            </h2>
            <p style={{ margin: "0.25rem 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
              Configured tools and services authenticated for assistant agents.
            </p>
          </div>
        </div>

        {filteredConnections.length === 0 ? (
          <div style={{
            padding: "2rem",
            textAlign: "center",
            background: "var(--bg-surface)",
            borderRadius: "0.5rem",
            border: "1px dashed var(--border)",
            color: "var(--text-muted)",
          }}>
            <PlugIcon size={32} style={{ margin: "0 auto 0.75rem", opacity: 0.5 }} />
            <p style={{ margin: 0, fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
              No active connections found
            </p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "var(--text-xs)" }}>
              Choose a provider from the catalog below to connect your first integration.
            </p>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "1rem",
          }}>
            {filteredConnections.map((conn) => (
              <ActiveConnectionCard
                key={conn.id}
                connection={conn}
                onManage={(c) => setManageConnection(c)}
                onTest={handleTestConnection}
                testing={testingId === conn.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* SECTION 2: Integrations Catalog */}
      <div>
        <div style={{ marginBottom: "1rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)" }}>
            Integrations Catalog ({filteredProviders.length})
          </h2>
          <p style={{ margin: "0.25rem 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            Connect cloud services, relational databases, repositories, and local storage.
          </p>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: "1rem",
        }}>
          {filteredProviders.map((provider) => (
            <ProviderCatalogCard
              key={provider.id}
              provider={provider}
              isConnected={connectedProviderIds.has(provider.id)}
              onConnect={(p) => setConnectProvider(p)}
            />
          ))}
        </div>
      </div>

      {/* Connect Modal */}
      <ConnectModal
        open={Boolean(connectProvider)}
        provider={connectProvider}
        onClose={() => setConnectProvider(null)}
        onSuccess={() => loadData()}
        api={api}
        canManageOrg={canManageOrg}
      />

      {/* Manage Connection Modal */}
      <ManageConnectionModal
        open={Boolean(manageConnection)}
        connection={manageConnection}
        onClose={() => setManageConnection(null)}
        onUpdated={() => loadData()}
        api={api}
      />
    </div>
  );
}
