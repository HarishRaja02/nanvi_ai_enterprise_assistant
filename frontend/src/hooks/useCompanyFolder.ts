import { useCallback, useEffect, useState } from "react";
import type { NanviApiClient, CompanyFolderResponse } from "../api";

export function useCompanyFolder(api?: NanviApiClient) {
  const [folderPath, setFolderPath] = useState<string>("");
  const [folderName, setFolderName] = useState<string>("");
  const [folderExists, setFolderExists] = useState<boolean>(true);
  const [folderCount, setFolderCount] = useState<number>(0);
  const [fileCount, setFileCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const extractName = (fullPath: string): string => {
    if (!fullPath) return "";
    const clean = fullPath.replace(/[/\\]+$/, "");
    const parts = clean.split(/[/\\]/);
    return parts[parts.length - 1] || fullPath;
  };

  const refresh = useCallback(async () => {
    if (!api) return;
    try {
      const res: CompanyFolderResponse = await api.getCompanyFolder();
      setFolderPath(res.path);
      setFolderName(extractName(res.path));
      setFolderExists(res.exists);
      setFolderCount(res.folder_count);
      setFileCount(res.file_count);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load company folder");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refresh();

    const onUpdated = (e: Event) => {
      const customEvent = e as CustomEvent<{
        path: string;
        exists: boolean;
        folder_count: number;
        file_count: number;
      }>;
      if (customEvent.detail) {
        setFolderPath(customEvent.detail.path);
        setFolderName(extractName(customEvent.detail.path));
        setFolderExists(customEvent.detail.exists);
        setFolderCount(customEvent.detail.folder_count);
        setFileCount(customEvent.detail.file_count);
        setError(null);
      } else {
        void refresh();
      }
    };

    window.addEventListener("nanvi:company-folder-updated", onUpdated);
    return () => {
      window.removeEventListener("nanvi:company-folder-updated", onUpdated);
    };
  }, [api, refresh]);

  return {
    folderPath,
    folderName,
    folderExists,
    folderCount,
    fileCount,
    loading,
    error,
    refresh,
  };
}
