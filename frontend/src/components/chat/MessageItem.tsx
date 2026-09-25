import { memo, useMemo, useState } from "react";
import { Check, Copy, Download, RefreshCw, Sparkles } from "lucide-react";
import { Alert } from "../ui/Alert";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { useToast } from "../ui/Toast";
import { MarkdownContent } from "./MarkdownContent";
import { SourceList } from "./SourceList";
import { TraceDisclosure } from "./TraceDisclosure";
import { BentoMetrics } from "./BentoMetrics";
import { useCountdown } from "../../hooks/useCountdown";
import { copyText } from "../../lib/clipboard";
import { formatTime, humanize } from "../../lib/format";
import type { ContextMetric } from "../../lib/contextIntelligence";
import type { SourceView } from "../../lib/sources";
import type { Message } from "../../types";

type Props = {
  message: Message;
  onOpenSource: (source: SourceView) => void;
  onDownload: (reportId: string) => void;
  onRetry: (messageId: string) => void;
  onFollowup?: (prompt: string) => void;
};

function AssistantHead({ time, capability }: { time: number; capability?: string }) {
  const isReport = capability && capability.includes("report");
  const isRag = capability && (capability.includes("knowledge") || capability.includes("rag"));
  const isData = capability && (capability.includes("database") || capability.includes("data"));
  const isWeb = capability && capability.includes("web_search");
  const isEmail = capability && capability.includes("email");

  return (
    <div className="msg-head">
      <span className="avatar avatar-bot" aria-hidden="true">N</span>
      <span className="msg-author">Nanvi Assistant</span>
      {capability && (
        <Badge
          tone={isReport ? "primary" : isRag ? "accent" : isData ? "primary" : isWeb ? "accent" : "neutral"}
          className={isRag ? "rag-badge" : undefined}
        >
          {isReport
            ? "📄 Document Generator"
            : isRag
            ? "⚡ RAG Retrieval"
            : isData
            ? "📊 Database Query"
            : isWeb
            ? "🌐 Web Search"
            : isEmail
            ? "✉️ Email Search"
            : humanize(capability)}
        </Badge>
      )}
      <time className="msg-time" dateTime={new Date(time).toISOString()}>
        {formatTime(time)}
      </time>
    </div>
  );
}

function ErrorMessage({ message, onRetry }: { message: Message; onRetry: (id: string) => void }) {
  const wait = useCountdown(message.retryAfter);
  return (
    <div className="msg msg-assistant">
      <Alert
        tone="danger"
        title="Nanvi couldn't complete that request"
        actions={
          <Button
            size="sm"
            variant="secondary"
            icon={RefreshCw}
            disabled={wait > 0}
            onClick={() => onRetry(message.id)}
          >
            {wait > 0 ? `Retry in ${wait}s` : "Retry request"}
          </Button>
        }
      >
        {message.text}
      </Alert>
    </div>
  );
}

function extractKeyMetrics(text: string): ContextMetric[] {
  const metrics: ContextMetric[] = [];
  // Match currency values e.g. $120,450
  const currencyMatches = text.match(/(\$|€|£|₹)\s?[\d,]+(\.\d+)?(\s?[MKmk]|\s?million|\s?billion)?/g);
  if (currencyMatches && currencyMatches.length > 0) {
    const uniqueCurrencies = Array.from(new Set(currencyMatches)).slice(0, 2);
    uniqueCurrencies.forEach((val, idx) => {
      metrics.push({
        id: `m-cur-${idx}`,
        label: idx === 0 ? "Total / Value" : "Related Amount",
        value: val,
        tone: "primary",
      });
    });
  }

  // Match percentages
  const pctMatches = text.match(/\b\d+(\.\d+)?%/g);
  if (pctMatches && pctMatches.length > 0) {
    metrics.push({
      id: "m-pct",
      label: "Rate / Variance",
      value: pctMatches[0],
      tone: "accent",
    });
  }

  return metrics;
}

function MessageItemBase({ message, onOpenSource, onDownload, onRetry, onFollowup }: Props) {
  const notify = useToast();
  const [copied, setCopied] = useState(false);

  // Extract key figures for Bento highlight if present
  const metrics = useMemo(() => {
    if (message.role !== "assistant" || message.error) return [];
    return extractKeyMetrics(message.text);
  }, [message]);

  if (message.role === "user") {
    const copyUser = async () => {
      const ok = await copyText(message.text);
      if (ok) notify("Question copied to clipboard.", "success");
    };

    return (
      <div className="msg msg-user">
        <div className="user-bubble" title="Click to copy prompt" onClick={copyUser}>
          {message.text}
        </div>
        <time className="msg-time" dateTime={new Date(message.createdAt).toISOString()}>
          {formatTime(message.createdAt)}
        </time>
      </div>
    );
  }

  if (message.error) return <ErrorMessage message={message} onRetry={onRetry} />;

  const copy = async () => {
    const ok = await copyText(message.text);
    if (ok) {
      setCopied(true);
      notify("Answer copied to clipboard.", "success");
      setTimeout(() => setCopied(false), 2000);
    } else {
      notify("Couldn't copy the answer.", "danger");
    }
  };

  return (
    <article className="msg msg-assistant" aria-label="Answer from Nanvi">
      <AssistantHead time={message.createdAt} capability={message.capability} />

      {/* Render Bento Metrics Strip if key figures are detected */}
      {metrics.length > 1 && (
        <BentoMetrics metrics={metrics} title="Key Figures Detected" className="msg-bento-metrics" />
      )}

      {/* Render Markdown & Interactive Tables */}
      <MarkdownContent text={message.text} />

      {/* Render Interactive Source Cards */}
      {message.sources && message.sources.length > 0 && (
        <SourceList sources={message.sources} onOpen={onOpenSource} />
      )}

      {/* Render Backend Trace Disclosure */}
      {message.trace && message.trace.length > 0 && <TraceDisclosure steps={message.trace} />}

      {/* Interactive Actions Bar */}
      <div className="msg-actions">
        <Button
          variant="ghost"
          size="sm"
          icon={copied ? Check : Copy}
          onClick={() => void copy()}
        >
          {copied ? "Copied" : "Copy answer"}
        </Button>

        <Button
          variant="ghost"
          size="sm"
          icon={RefreshCw}
          onClick={() => onRetry(message.id)}
          title="Regenerate this response"
        >
          Regenerate
        </Button>

        {message.reportId && (
          <Button
            variant="secondary"
            size="sm"
            icon={Download}
            onClick={() => onDownload(message.reportId!)}
          >
            Download report
          </Button>
        )}

        {onFollowup && (
          <>
            <Button
              variant="ghost"
              size="sm"
              icon={Sparkles}
              onClick={() => onFollowup("Can you explain the key details and implications of this answer?")}
            >
              Explain more
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onFollowup("Summarize this into a 3-bullet executive summary.")}
            >
              Summarize
            </Button>
          </>
        )}
      </div>
    </article>
  );
}

export const MessageItem = memo(MessageItemBase);
