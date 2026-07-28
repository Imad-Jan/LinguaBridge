"use client";

import {
  FormEvent,
  ReactElement,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type Provider = "gemini" | "soniox";
type Direction = "caller_to_callee" | "callee_to_caller";
type View = "settings" | "dialer" | "dashboard";

type Check = {
  configured: boolean;
  valid: boolean | null;
  message: string;
};

type ConfigResult = {
  config_id: string;
  twilio: Check;
  gemini: Check;
  soniox: Check;
  numbers: string[];
};

type FeedItem = {
  id: string;
  direction: Direction;
  stage: "source" | "translation";
  text: string;
  language?: string;
  at: number;
};

type EventItem = {
  id: string;
  text: string;
  tone: "info" | "good" | "warn";
  at: number;
};

const languages = [
  ["en", "English"],
  ["ur", "Urdu"],
  ["ar", "Arabic"],
  ["es", "Spanish"],
  ["fr", "French"],
  ["de", "German"],
  ["hi", "Hindi"],
  ["pa", "Punjabi"],
  ["fa", "Persian"],
  ["tr", "Turkish"],
  ["it", "Italian"],
  ["pt-BR", "Portuguese (Brazil)"],
  ["zh-Hans", "Chinese (Simplified)"],
  ["ja", "Japanese"],
  ["ko", "Korean"],
];

const voices = [
  "Maya",
  "Adrian",
  "Priya",
  "Arjun",
  "Claire",
  "Daniel",
  "Emma",
  "Noah",
];

const keypadKeys: Array<{ digit: string; sub: string }> = [
  { digit: "1", sub: "" },
  { digit: "2", sub: "ABC" },
  { digit: "3", sub: "DEF" },
  { digit: "4", sub: "GHI" },
  { digit: "5", sub: "JKL" },
  { digit: "6", sub: "MNO" },
  { digit: "7", sub: "PQRS" },
  { digit: "8", sub: "TUV" },
  { digit: "9", sub: "WXYZ" },
  { digit: "+", sub: "" },
  { digit: "0", sub: "" },
  { digit: "#", sub: "" },
];

const emptyChecks = {
  twilio: null,
  gemini: null,
  soniox: null,
} as Record<"twilio" | "gemini" | "soniox", Check | null>;

const STORAGE_KEY = "linguabridge.config.v1";

type PersistedConfig = {
  apiBase: string;
  publicUrl: string;
  accountSid: string;
  authToken: string;
  geminiKey: string;
  sonioxKey: string;
  provider: Provider;
  fromNumber: string;
  toNumber: string;
  callerLanguage: string;
  calleeLanguage: string;
  callerVoice: string;
  calleeVoice: string;
  echoTarget: boolean;
  context: string;
};

function cls(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

/* ---------------------------------------------------------------------- */
/* Icons — hand-rolled inline SVGs (no external icon package required)     */
/* ---------------------------------------------------------------------- */

type IconProps = { className?: string };

function SettingsIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M19.4 13.6a1.7 1.7 0 0 0 .34 1.87l.06.06a2.06 2.06 0 1 1-2.92 2.92l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V20a2.06 2.06 0 1 1-4.12 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2.06 2.06 0 1 1-2.92-2.92l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H4a2.06 2.06 0 1 1 0-4.12h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2.06 2.06 0 1 1 2.92-2.92l.06.06a1.7 1.7 0 0 0 1.87.34H10.2a1.7 1.7 0 0 0 1.03-1.56V4a2.06 2.06 0 1 1 4.12 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2.06 2.06 0 1 1 2.92 2.92l-.06.06a1.7 1.7 0 0 0-.34 1.87V10.2a1.7 1.7 0 0 0 1.56 1.03H20a2.06 2.06 0 1 1 0 4.12h-.09a1.7 1.7 0 0 0-1.56 1.03Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DialpadIcon({ className }: IconProps) {
  const dots = [
    [5, 5],
    [12, 5],
    [19, 5],
    [5, 12],
    [12, 12],
    [19, 12],
    [5, 19],
    [12, 19],
    [19, 19],
  ];
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      {dots.map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2" fill="currentColor" />
      ))}
    </svg>
  );
}

function ChartIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 19V9m6 10V5m6 14v-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M3 19h18"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function PhoneIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6.6 10.8c1.4 2.8 3.8 5.2 6.6 6.6l2.2-2.2c.3-.3.7-.4 1.1-.3 1.2.4 2.5.6 3.8.6.6 0 1 .5 1 1V20c0 .6-.4 1-1 1C10.5 21 3 13.5 3 4.7c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.6.6 3.8.1.4 0 .8-.3 1.1L6.6 10.8Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PhoneEndIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2.5 13.5c5.6-4.4 13.4-4.4 19 0"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M8.6 15.9c2.2-1.4 4.6-1.4 6.8 0"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="12" cy="18.4" r="1.3" fill="currentColor" />
    </svg>
  );
}

function MicIcon({ className, off }: IconProps & { off?: boolean }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      {off && (
        <path
          d="M4 4l16 16"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

function BackspaceIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 4h10a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H9l-6.4-7.2a1.2 1.2 0 0 1 0-1.6L9 4Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="m12 9 6 6m0-6-6 6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m5 12.5 4.5 4.5L19 7.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PulseIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2.5 12h4l2-6 4 12 2-9 1.5 3h5.5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TranslateIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 5h9M8.5 3v2M3 8.5c1.7 3 4 5 8 6M12.5 8c-1 2.4-3.4 5-8 6.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="m15 21 3.5-9 3.5 9M16 18h5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SpeakerIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 9v6h4l5 4V5L8 9H4Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M17 8.5a5 5 0 0 1 0 7M19.5 6a8.5 8.5 0 0 1 0 12"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ---------------------------------------------------------------------- */
/* Small presentational components                                        */
/* ---------------------------------------------------------------------- */

function CheckBadge({ label, check }: { label: string; check: Check | null }) {
  const tone =
    check?.valid === true ? "ok" : check?.valid === false ? "bad" : "idle";
  return (
    <div className={cls("check-badge", tone)}>
      <span className="status-dot" />
      <span>
        <strong>{label}</strong>
        <small>{check?.message ?? "Not checked"}</small>
      </span>
    </div>
  );
}

function LanguageSelect({
  value,
  onChange,
  id,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  id: string;
  disabled?: boolean;
}) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {languages.map(([code, name]) => (
        <option key={code} value={code}>
          {name} · {code}
        </option>
      ))}
    </select>
  );
}

function LevelMeter({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: "cyan" | "violet";
}) {
  const percent = Math.max(2, Math.min(100, ((value + 70) / 60) * 100));
  return (
    <div className="level-meter">
      <div>
        <span>{label}</span>
        <small>{Math.round(value)} dB</small>
      </div>
      <div className="level-track">
        <span
          className={color}
          style={{ width: `${percent}%` }}
          aria-label={`${label} level ${Math.round(value)} decibels`}
        />
      </div>
    </div>
  );
}

function TranscriptPanel({
  title,
  subtitle,
  items,
  accent,
}: {
  title: string;
  subtitle: string;
  items: FeedItem[];
  accent: "cyan" | "violet";
}) {
  return (
    <div className={cls("panel transcript-panel", accent)}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{subtitle}</span>
          <h2>{title}</h2>
        </div>
        <span className="token-count">{items.length} events</span>
      </div>
      <div className="transcript-scroll">
        {!items.length && (
          <div className="empty-state">
            Source and translated text will stream here.
          </div>
        )}
        {items.map((item) => (
          <div className={cls("transcript-line", item.stage)} key={item.id}>
            <span>{item.stage === "source" ? "Original" : "Translation"}</span>
            <p>{item.text}</p>
            <small>{item.language ?? "auto"}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function LatencyChart({ values }: { values: number[] }) {
  const width = 560;
  const height = 160;
  const padding = 8;

  if (!values.length) {
    return (
      <div className="chart-empty">
        Latency samples will appear once the call is live.
      </div>
    );
  }

  const max = Math.max(...values, 200);
  const min = 0;
  const span = Math.max(1, max - min);
  const stepX = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;

  const points = values.map((value, index) => {
    const x = padding + index * stepX;
    const y = height - padding - ((value - min) / span) * (height - padding * 2);
    return [x, y] as const;
  });

  const linePath = points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${height - padding} L${points[0][0].toFixed(1)},${height - padding} Z`;

  const current = values[values.length - 1];
  const avg = Math.round(values.reduce((a, b) => a + b, 0) / values.length);
  const best = Math.min(...values);
  const worst = Math.max(...values);

  return (
    <div className="chart-card-body">
      <svg
        className="chart-svg"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Round-trip latency chart, current ${current} milliseconds, average ${avg} milliseconds`}
      >
        <defs>
          <linearGradient id="latencyFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(50, 214, 237, 0.45)" />
            <stop offset="100%" stopColor="rgba(50, 214, 237, 0)" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((fraction) => (
          <line
            key={fraction}
            x1={padding}
            x2={width - padding}
            y1={height - padding - fraction * (height - padding * 2)}
            y2={height - padding - fraction * (height - padding * 2)}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="1"
          />
        ))}
        <path d={areaPath} fill="url(#latencyFill)" stroke="none" />
        <path d={linePath} fill="none" stroke="#32d6ed" strokeWidth="2" />
        {points.length > 0 && (
          <circle
            cx={points[points.length - 1][0]}
            cy={points[points.length - 1][1]}
            r="4"
            fill="#32d6ed"
          />
        )}
      </svg>
      <div className="chart-stats">
        <div>
          <small>Current</small>
          <strong>{current} ms</strong>
        </div>
        <div>
          <small>Average</small>
          <strong>{avg} ms</strong>
        </div>
        <div>
          <small>Best</small>
          <strong>{best} ms</strong>
        </div>
        <div>
          <small>Worst</small>
          <strong>{worst} ms</strong>
        </div>
      </div>
    </div>
  );
}

function LatencyPipeline({ averageMs }: { averageMs: number | null }) {
  const steps: Array<{ icon: (props: IconProps) => ReactElement; label: string }> = [
    { icon: MicIcon, label: "Microphone" },
    { icon: PulseIcon, label: "Speech recognition" },
    { icon: TranslateIcon, label: "Translation" },
    { icon: SpeakerIcon, label: "Voice synthesis" },
    { icon: PhoneIcon, label: "Delivered" },
  ];
  return (
    <div className="pipeline">
      {steps.map((step, index) => (
        <div className="pipeline-step" key={step.label}>
          <div className="pipeline-icon">
            <step.icon className="icon" />
          </div>
          <span>{step.label}</span>
          {index < steps.length - 1 && <div className="pipeline-arrow" />}
        </div>
      ))}
      <div className="pipeline-total">
        <small>End-to-end round trip</small>
        <strong>{averageMs ? `${averageMs} ms` : "—"}</strong>
        <p>
          This is the measured mic-to-speaker round trip. The backend reports a
          single combined figure, not a per-stage split.
        </p>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Page                                                                    */
/* ---------------------------------------------------------------------- */

export default function Home() {
  const [view, setView] = useState<View>("settings");
  const [hydrated, setHydrated] = useState(false);

  const [apiBase, setApiBase] = useState("http://localhost:8000");
  const [publicUrl, setPublicUrl] = useState("");
  const [accountSid, setAccountSid] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [sonioxKey, setSonioxKey] = useState("");
  const [checks, setChecks] = useState(emptyChecks);
  const [configId, setConfigId] = useState("");
  const [numbers, setNumbers] = useState<string[]>([]);
  const [configBusy, setConfigBusy] = useState(false);

  const [provider, setProvider] = useState<Provider>("gemini");
  const [fromNumber, setFromNumber] = useState("");
  const [toNumber, setToNumber] = useState("");
  const [callerLanguage, setCallerLanguage] = useState("ur");
  const [calleeLanguage, setCalleeLanguage] = useState("en");
  const [callerVoice, setCallerVoice] = useState("Maya");
  const [calleeVoice, setCalleeVoice] = useState("Adrian");
  const [echoTarget, setEchoTarget] = useState(true);
  const [context, setContext] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [status, setStatus] = useState("Idle");
  const [statusDetail, setStatusDetail] = useState(
    "Configure your providers, then start a call.",
  );
  const [callId, setCallId] = useState("");
  const [twilioSid, setTwilioSid] = useState("");
  const [live, setLive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [levels, setLevels] = useState<Record<Direction, number>>({
    caller_to_callee: -90,
    callee_to_caller: -90,
  });
  const [latencies, setLatencies] = useState<number[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [error, setError] = useState("");

  const socketRef = useRef<WebSocket | null>(null);
  const mediaRef = useRef<{
    stream: MediaStream;
    context: AudioContext;
    source: MediaStreamAudioSourceNode;
    processor: ScriptProcessorNode;
    silent: GainNode;
  } | null>(null);
  const outputContextRef = useRef<AudioContext | null>(null);
  const nextPlaybackRef = useRef(0);
  const streamingRef = useRef(false);
  const mutedRef = useRef(false);
  const dialStartedRef = useRef(false);

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [live]);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
      stopMicrophone();
    };
  }, []);

  // Restore saved configuration from the browser on first load. localStorage
  // is unavailable during SSR, so this must patch state in after mount
  // rather than during render, to avoid a hydration mismatch.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Partial<PersistedConfig>;
        if (saved.apiBase) setApiBase(saved.apiBase);
        if (saved.publicUrl) setPublicUrl(saved.publicUrl);
        if (saved.accountSid) setAccountSid(saved.accountSid);
        if (saved.authToken) setAuthToken(saved.authToken);
        if (saved.geminiKey) setGeminiKey(saved.geminiKey);
        if (saved.sonioxKey) setSonioxKey(saved.sonioxKey);
        if (saved.provider) setProvider(saved.provider);
        if (saved.fromNumber) setFromNumber(saved.fromNumber);
        if (saved.toNumber) setToNumber(saved.toNumber);
        if (saved.callerLanguage) setCallerLanguage(saved.callerLanguage);
        if (saved.calleeLanguage) setCalleeLanguage(saved.calleeLanguage);
        if (saved.callerVoice) setCallerVoice(saved.callerVoice);
        if (saved.calleeVoice) setCalleeVoice(saved.calleeVoice);
        if (typeof saved.echoTarget === "boolean") setEchoTarget(saved.echoTarget);
        if (saved.context) setContext(saved.context);
      }
    } catch {
      // Ignore malformed/unavailable local storage.
    } finally {
      setHydrated(true);
    }
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Persist configuration to the browser whenever it changes.
  useEffect(() => {
    if (!hydrated) return;
    const payload: PersistedConfig = {
      apiBase,
      publicUrl,
      accountSid,
      authToken,
      geminiKey,
      sonioxKey,
      provider,
      fromNumber,
      toNumber,
      callerLanguage,
      calleeLanguage,
      callerVoice,
      calleeVoice,
      echoTarget,
      context,
    };
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // Storage may be unavailable (private browsing, quota); ignore.
    }
  }, [
    hydrated,
    apiBase,
    publicUrl,
    accountSid,
    authToken,
    geminiKey,
    sonioxKey,
    provider,
    fromNumber,
    toNumber,
    callerLanguage,
    calleeLanguage,
    callerVoice,
    calleeVoice,
    echoTarget,
    context,
  ]);

  const averageLatency = useMemo(() => {
    if (!latencies.length) return null;
    return Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length);
  }, [latencies]);

  const addEvent = (text: string, tone: EventItem["tone"] = "info") => {
    setEvents((items) =>
      [
        { id: crypto.randomUUID(), text, tone, at: Date.now() },
        ...items,
      ].slice(0, 30),
    );
  };

  async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${apiBase.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail ?? `Request failed (${response.status})`);
    }
    return data as T;
  }

  async function saveConfiguration(
    event?: FormEvent,
    validate = true,
  ): Promise<ConfigResult | null> {
    event?.preventDefault();
    setConfigBusy(true);
    setError("");
    try {
      const data = await jsonRequest<ConfigResult>("/api/config", {
        method: "POST",
        body: JSON.stringify({
          public_base_url: publicUrl,
          twilio_account_sid: accountSid,
          twilio_auth_token: authToken,
          gemini_api_key: geminiKey || null,
          soniox_api_key: sonioxKey || null,
          validate_credentials: validate,
        }),
      });
      setConfigId(data.config_id);
      setChecks({
        twilio: data.twilio,
        gemini: data.gemini,
        soniox: data.soniox,
      });
      setNumbers(data.numbers);
      if (!fromNumber && data.numbers[0]) setFromNumber(data.numbers[0]);
      addEvent(
        validate ? "Configuration preflight completed" : "Configuration saved",
        data.twilio.valid === false ? "warn" : "good",
      );
      return data;
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Configuration failed",
      );
      return null;
    } finally {
      setConfigBusy(false);
    }
  }

  function stopMicrophone() {
    const current = mediaRef.current;
    if (!current) return;
    current.processor.disconnect();
    current.source.disconnect();
    current.silent.disconnect();
    current.stream.getTracks().forEach((track) => track.stop());
    void current.context.close();
    mediaRef.current = null;
  }

  function resampleTo16k(input: Float32Array, inputRate: number) {
    const ratio = inputRate / 16000;
    const outputLength = Math.max(1, Math.round(input.length / ratio));
    const output = new Int16Array(outputLength);
    for (let index = 0; index < outputLength; index += 1) {
      const sourcePosition = index * ratio;
      const lower = Math.floor(sourcePosition);
      const upper = Math.min(lower + 1, input.length - 1);
      const mix = sourcePosition - lower;
      const sample = input[lower] * (1 - mix) + input[upper] * mix;
      output[index] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
    }
    return output.buffer;
  }

  async function startMicrophone(socket: WebSocket) {
    stopMicrophone();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const context = new AudioContext();
    await context.resume();
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const silent = context.createGain();
    silent.gain.value = 0;
    processor.onaudioprocess = (event) => {
      if (
        !streamingRef.current ||
        mutedRef.current ||
        socket.readyState !== WebSocket.OPEN
      )
        return;
      const pcm = resampleTo16k(
        event.inputBuffer.getChannelData(0),
        context.sampleRate,
      );
      socket.send(pcm);
    };
    source.connect(processor);
    processor.connect(silent);
    silent.connect(context.destination);
    mediaRef.current = { stream, context, source, processor, silent };
  }

  async function playPcm24k(buffer: ArrayBuffer) {
    if (!buffer.byteLength) return;
    let context = outputContextRef.current;
    if (!context || context.state === "closed") {
      context = new AudioContext();
      outputContextRef.current = context;
    }
    if (context.state === "suspended") await context.resume();
    const samples = new Int16Array(buffer);
    const audioBuffer = context.createBuffer(1, samples.length, 24000);
    const channel = audioBuffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      channel[index] = samples[index] / 32768;
    }
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    const now = context.currentTime;
    const startAt = Math.max(now + 0.02, nextPlaybackRef.current);
    source.start(startAt);
    nextPlaybackRef.current = startAt + audioBuffer.duration;
  }

  function handleDashboardMessage(message: Record<string, unknown>) {
    const type = String(message.type ?? "");
    if (type === "providers_ready") {
      setStatus("Ready");
      setStatusDetail(String(message.message ?? "Translation provider ready"));
      addEvent(String(message.message ?? "Translation provider ready"), "good");
      if (!dialStartedRef.current) {
        dialStartedRef.current = true;
        void dialCurrentCall();
      }
    } else if (type === "twilio_connected") {
      streamingRef.current = true;
      setLive(true);
      setStarting(false);
      setStatus("Live");
      setStatusDetail("Both directions are translating in real time.");
      addEvent("Callee answered — translation is live", "good");
    } else if (type === "call_status") {
      const callStatus = String(message.status ?? "updating");
      setStatus(callStatus.replaceAll("-", " "));
      setStatusDetail(String(message.message ?? callStatus));
      if (
        ["completed", "failed", "busy", "no-answer", "canceled"].includes(
          callStatus,
        )
      ) {
        streamingRef.current = false;
        setLive(false);
        setStarting(false);
      }
      addEvent(String(message.message ?? callStatus));
    } else if (type === "provider_status") {
      addEvent(String(message.message ?? "Provider ready"), "good");
    } else if (type === "audio_level") {
      const direction = message.direction as Direction;
      if (direction) {
        setLevels((current) => ({
          ...current,
          [direction]: Number(message.value ?? -90),
        }));
      }
    } else if (type === "latency") {
      const value = Number(message.value);
      if (Number.isFinite(value)) {
        setLatencies((items) => [...items.slice(-59), value]);
      }
    } else if (type === "transcript") {
      const text = String(message.text ?? "");
      if (text) {
        setFeed((items) =>
          [
            ...items,
            {
              id: crypto.randomUUID(),
              direction: message.direction as Direction,
              stage: message.stage as "source" | "translation",
              text,
              language: message.language
                ? String(message.language)
                : undefined,
              at: Date.now(),
            },
          ].slice(-180),
        );
      }
    } else if (type === "error") {
      const text = String(message.message ?? "Call pipeline error");
      setError(text);
      addEvent(text, "warn");
      setStarting(false);
    }
  }

  const callIdRef = useRef("");
  useEffect(() => {
    callIdRef.current = callId;
  }, [callId]);

  async function dialCurrentCall() {
    const activeCallId = callIdRef.current;
    if (!activeCallId) return;
    try {
      const data = await jsonRequest<{
        twilio_call_sid: string;
        status: string;
      }>(`/api/calls/${activeCallId}/dial`, { method: "POST" });
      setTwilioSid(data.twilio_call_sid);
      setStatus("Dialing");
      setStatusDetail("Twilio is calling the destination.");
    } catch (dialError) {
      setError(dialError instanceof Error ? dialError.message : "Dial failed");
      setStarting(false);
      streamingRef.current = false;
      stopMicrophone();
      socketRef.current?.close();
    }
  }

  async function startCall() {
    if (starting || live) return;
    setError("");
    setFeed([]);
    setEvents([]);
    setLatencies([]);
    setElapsed(0);
    setTwilioSid("");
    setStarting(true);
    setStatus("Preparing");
    setStatusDetail("Opening secure audio channels.");
    dialStartedRef.current = false;
    setView("dashboard");

    let activeConfigId = configId;
    if (!activeConfigId) {
      const saved = await saveConfiguration(undefined, false);
      if (!saved) {
        setStarting(false);
        return;
      }
      activeConfigId = saved.config_id;
    }

    try {
      const prepared = await jsonRequest<{
        call_id: string;
        browser_token: string;
        websocket_path: string;
      }>("/api/calls/prepare", {
        method: "POST",
        body: JSON.stringify({
          config_id: activeConfigId,
          provider,
          from_number: fromNumber,
          to_number: toNumber,
          caller_language: callerLanguage,
          callee_language: calleeLanguage,
          caller_voice: callerVoice,
          callee_voice: calleeVoice,
          echo_target_language: echoTarget,
          soniox_context: context,
        }),
      });
      setCallId(prepared.call_id);
      callIdRef.current = prepared.call_id;
      const wsBase = apiBase.replace(/^http/, "ws").replace(/\/$/, "");
      const socket = new WebSocket(
        `${wsBase}${prepared.websocket_path}?token=${encodeURIComponent(prepared.browser_token)}`,
      );
      socket.binaryType = "arraybuffer";
      socketRef.current = socket;
      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          void playPcm24k(event.data);
        } else {
          handleDashboardMessage(JSON.parse(String(event.data)));
        }
      };
      socket.onerror = () => {
        setError("Browser audio socket failed. Confirm that the backend is running.");
        setStarting(false);
      };
      socket.onclose = () => {
        streamingRef.current = false;
        setLive(false);
      };
      await new Promise<void>((resolve, reject) => {
        socket.onopen = () => resolve();
        const timer = window.setTimeout(
          () => reject(new Error("Browser audio connection timed out")),
          8000,
        );
        socket.addEventListener("open", () => window.clearTimeout(timer), {
          once: true,
        });
      });
      await startMicrophone(socket);
      addEvent("Microphone connected");
    } catch (startError) {
      setError(
        startError instanceof Error ? startError.message : "Could not start call",
      );
      setStarting(false);
      streamingRef.current = false;
      stopMicrophone();
      socketRef.current?.close();
    }
  }

  async function endCall() {
    streamingRef.current = false;
    setLive(false);
    setStarting(false);
    stopMicrophone();
    if (callId) {
      try {
        await jsonRequest(`/api/calls/${callId}/end`, { method: "POST" });
      } catch {
        // The call may already be terminal; local cleanup still proceeds.
      }
    }
    socketRef.current?.close();
    socketRef.current = null;
    setStatus("Completed");
    setStatusDetail("The call and translation sessions are closed.");
  }

  async function clearPlayback() {
    if (!callId) return;
    await jsonRequest(`/api/calls/${callId}/clear`, { method: "POST" });
    nextPlaybackRef.current = 0;
    addEvent("Queued translated audio cleared");
  }

  function pressKey(digit: string) {
    if (live || starting) return;
    setToNumber((current) => {
      if (digit === "+") {
        return current.startsWith("+") ? current : `+${current}`;
      }
      return current + digit;
    });
  }

  function backspaceKey() {
    if (live || starting) return;
    setToNumber((current) => current.slice(0, -1));
  }

  const callerToCallee = feed.filter(
    (item) => item.direction === "caller_to_callee",
  );
  const calleeToCaller = feed.filter(
    (item) => item.direction === "callee_to_caller",
  );

  const canDial = Boolean(fromNumber && toNumber && publicUrl && accountSid);
  const configReady = Boolean(publicUrl && accountSid && authToken);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">LB</div>
          <div>
            <h1>LinguaBridge</h1>
            <p>Real-time interpreted calls</p>
          </div>
        </div>
        <div className="topbar-actions">
          <span className={cls("connection-pill", live && "live")}>
            <span className="pulse-dot" />
            {live ? "Call live" : status}
          </span>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar-nav">
          <button
            type="button"
            className={cls("nav-item", view === "settings" && "active")}
            onClick={() => setView("settings")}
          >
            <SettingsIcon className="icon" />
            <div>
              <strong>Settings</strong>
              <small>Twilio + AI keys</small>
            </div>
            {configReady && <CheckIcon className="nav-check" />}
          </button>
          <button
            type="button"
            className={cls("nav-item", view === "dialer" && "active")}
            onClick={() => setView("dialer")}
          >
            <DialpadIcon className="icon" />
            <div>
              <strong>Dialer</strong>
              <small>Languages + number</small>
            </div>
          </button>
          <button
            type="button"
            className={cls("nav-item", view === "dashboard" && "active")}
            onClick={() => setView("dashboard")}
          >
            <ChartIcon className="icon" />
            <div>
              <strong>Dashboard</strong>
              <small>Latency + transcripts</small>
            </div>
            {(live || starting) && <span className="nav-live-dot" />}
          </button>
          <div className="rail-note">
            <span>Privacy</span>
            <p>
              Credentials are kept in backend memory (lost on backend restart)
              and cached locally in this browser for convenience.
            </p>
          </div>
        </aside>

        <section className="content">
          {view === "settings" && (
            <form className="settings-view" onSubmit={saveConfiguration}>
              <div className="view-heading">
                <div>
                  <span className="eyebrow">Initial setup</span>
                  <h2>Connect the call stack</h2>
                  <p>
                    The public URL must expose backend port 8000 over HTTPS so
                    Twilio can reach the media WebSocket (e.g. an ngrok URL).
                  </p>
                </div>
                <button
                  type="submit"
                  className="primary-button"
                  disabled={configBusy}
                >
                  {configBusy ? "Testing…" : "Save & test all"}
                </button>
              </div>

              <div className="settings-grid">
                <div className="provider-card">
                  <div className="provider-card-heading">
                    <span className="eyebrow">Required</span>
                    <h3>Twilio</h3>
                  </div>
                  <label className="field">
                    <span>Public backend URL</span>
                    <input
                      required
                      value={publicUrl}
                      onChange={(e) => setPublicUrl(e.target.value)}
                      placeholder="https://your-domain.example or ngrok URL"
                    />
                  </label>
                  <label className="field">
                    <span>Account SID</span>
                    <input
                      required
                      value={accountSid}
                      onChange={(e) => setAccountSid(e.target.value)}
                      placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                      autoComplete="off"
                    />
                  </label>
                  <label className="field">
                    <span>Auth token</span>
                    <input
                      required
                      type="password"
                      value={authToken}
                      onChange={(e) => setAuthToken(e.target.value)}
                      placeholder="••••••••••••••••"
                      autoComplete="new-password"
                    />
                  </label>
                  <div className="provider-card-footer">
                    <CheckBadge label="Twilio" check={checks.twilio} />
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={configBusy || !accountSid || !authToken || !publicUrl}
                      onClick={() => saveConfiguration(undefined, true)}
                    >
                      Test connection
                    </button>
                  </div>
                </div>

                <div className="provider-card">
                  <div className="provider-card-heading">
                    <span className="eyebrow">Optional</span>
                    <h3>Gemini</h3>
                  </div>
                  <label className="field">
                    <span>API key</span>
                    <input
                      type="password"
                      value={geminiKey}
                      onChange={(e) => setGeminiKey(e.target.value)}
                      placeholder="Required when Gemini is selected"
                      autoComplete="new-password"
                    />
                  </label>
                  <p className="provider-card-hint">
                    Used for the Gemini Live translation pipeline. Select
                    Gemini as the provider on the Dialer page to use it.
                  </p>
                  <div className="provider-card-footer">
                    <CheckBadge label="Gemini" check={checks.gemini} />
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={configBusy || !geminiKey || !accountSid || !authToken || !publicUrl}
                      onClick={() => saveConfiguration(undefined, true)}
                    >
                      Test connection
                    </button>
                  </div>
                </div>

                <div className="provider-card">
                  <div className="provider-card-heading">
                    <span className="eyebrow">Optional</span>
                    <h3>Soniox</h3>
                  </div>
                  <label className="field">
                    <span>API key</span>
                    <input
                      type="password"
                      value={sonioxKey}
                      onChange={(e) => setSonioxKey(e.target.value)}
                      placeholder="Required when Soniox is selected"
                      autoComplete="new-password"
                    />
                  </label>
                  <p className="provider-card-hint">
                    Used for the Soniox speech-to-speech pipeline with custom
                    voices. Select Soniox as the provider on the Dialer page.
                  </p>
                  <div className="provider-card-footer">
                    <CheckBadge label="Soniox" check={checks.soniox} />
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={configBusy || !sonioxKey || !accountSid || !authToken || !publicUrl}
                      onClick={() => saveConfiguration(undefined, true)}
                    >
                      Test connection
                    </button>
                  </div>
                </div>
              </div>

              <details className="runtime-details">
                <summary>Frontend runtime (advanced)</summary>
                <label className="field">
                  <span>Backend address used by this browser</span>
                  <input
                    value={apiBase}
                    onChange={(e) => setApiBase(e.target.value)}
                    placeholder="http://localhost:8000"
                  />
                </label>
              </details>

              {error && <div className="error-box">{error}</div>}
            </form>
          )}

          {view === "dialer" && (
            <div className="dialer-view">
              <div className="view-heading">
                <div>
                  <span className="eyebrow">Call console</span>
                  <h2>Place an interpreted call</h2>
                </div>
                <div className="provider-toggle" aria-label="Translation provider">
                  <button
                    type="button"
                    className={provider === "gemini" ? "selected" : ""}
                    onClick={() => setProvider("gemini")}
                    disabled={live || starting}
                  >
                    Gemini
                  </button>
                  <button
                    type="button"
                    className={provider === "soniox" ? "selected" : ""}
                    onClick={() => setProvider("soniox")}
                    disabled={live || starting}
                  >
                    Soniox
                  </button>
                </div>
              </div>

              <div className="dialer-columns">
                <div className="panel phone-shell">
                  <div className="phone-screen">
                    <div className="phone-from">
                      <span>Calling from</span>
                      <select
                        value={fromNumber}
                        onChange={(e) => setFromNumber(e.target.value)}
                        disabled={live || starting}
                      >
                        <option value="" disabled>
                          Select a Twilio number
                        </option>
                        {numbers.map((number) => (
                          <option key={number} value={number}>
                            {number}
                          </option>
                        ))}
                        {fromNumber && !numbers.includes(fromNumber) && (
                          <option value={fromNumber}>{fromNumber}</option>
                        )}
                      </select>
                    </div>
                    <input
                      className="phone-display"
                      value={toNumber}
                      onChange={(e) => setToNumber(e.target.value)}
                      placeholder="Enter a number"
                      disabled={live || starting}
                      inputMode="tel"
                    />
                  </div>

                  <div className="keypad">
                    {keypadKeys.map((key) => (
                      <button
                        type="button"
                        key={key.digit}
                        className="keypad-btn"
                        disabled={live || starting}
                        onClick={() => pressKey(key.digit)}
                      >
                        <strong>{key.digit}</strong>
                        {key.sub && <small>{key.sub}</small>}
                      </button>
                    ))}
                  </div>

                  <div className="phone-actions">
                    <button
                      type="button"
                      className="icon-button"
                      disabled={!toNumber || live || starting}
                      onClick={backspaceKey}
                      aria-label="Delete last digit"
                    >
                      <BackspaceIcon className="icon" />
                    </button>

                    {!live && !starting ? (
                      <button
                        type="button"
                        className="call-button round"
                        onClick={startCall}
                        disabled={!canDial}
                        aria-label="Start interpreted call"
                      >
                        <PhoneIcon className="icon" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="end-button round"
                        onClick={endCall}
                        aria-label="End call"
                      >
                        <PhoneEndIcon className="icon" />
                      </button>
                    )}

                    <button
                      type="button"
                      className={cls("icon-button", muted && "active")}
                      onClick={() => setMuted(!muted)}
                      disabled={!live && !starting}
                      aria-label={muted ? "Unmute microphone" : "Mute microphone"}
                    >
                      <MicIcon className="icon" off={muted} />
                    </button>
                  </div>

                  {!canDial && (
                    <p className="phone-hint">
                      Add a public URL, Twilio SID/token in Settings, choose a
                      &ldquo;Calling from&rdquo; number, and enter a number to
                      dial.
                    </p>
                  )}
                </div>

                <div className="panel call-options">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">Route</span>
                      <h2>Languages</h2>
                    </div>
                  </div>
                  <div className="route-map">
                    <div className="person-card">
                      <span className="avatar caller">A</span>
                      <div>
                        <small>Browser caller</small>
                        <strong>Person A</strong>
                      </div>
                      <LanguageSelect
                        id="caller-language"
                        value={callerLanguage}
                        onChange={setCallerLanguage}
                        disabled={live || starting}
                      />
                    </div>
                    <div className="route-line">
                      <TranslateIcon className="icon" />
                      <small>{provider === "gemini" ? "Gemini Live" : "Soniox STS"}</small>
                    </div>
                    <div className="person-card">
                      <span className="avatar callee">B</span>
                      <div>
                        <small>Ordinary phone</small>
                        <strong>Person B</strong>
                      </div>
                      <LanguageSelect
                        id="callee-language"
                        value={calleeLanguage}
                        onChange={setCalleeLanguage}
                        disabled={live || starting}
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    className="ghost-button full-width"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                  >
                    {showAdvanced ? "Hide advanced options" : "Advanced options"}
                  </button>

                  {showAdvanced &&
                    (provider === "soniox" ? (
                      <div className="advanced-grid">
                        <label className="field">
                          <span>Voice heard by Person A</span>
                          <select
                            value={callerVoice}
                            onChange={(e) => setCallerVoice(e.target.value)}
                          >
                            {voices.map((voice) => (
                              <option key={voice}>{voice}</option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          <span>Voice heard by Person B</span>
                          <select
                            value={calleeVoice}
                            onChange={(e) => setCalleeVoice(e.target.value)}
                          >
                            {voices.map((voice) => (
                              <option key={voice}>{voice}</option>
                            ))}
                          </select>
                        </label>
                        <label className="field span-2">
                          <span>Names and domain context (optional)</span>
                          <textarea
                            value={context}
                            onChange={(e) => setContext(e.target.value)}
                            placeholder="Client names, company names, products and technical terms"
                            rows={2}
                          />
                        </label>
                      </div>
                    ) : (
                      <label className="switch-row">
                        <span>
                          <strong>Echo target-language speech</strong>
                          <small>
                            Repeat words already spoken in the listener&apos;s
                            language.
                          </small>
                        </span>
                        <input
                          type="checkbox"
                          checked={echoTarget}
                          onChange={(e) => setEchoTarget(e.target.checked)}
                        />
                      </label>
                    ))}

                  {error && <div className="error-box">{error}</div>}
                </div>
              </div>
            </div>
          )}

          {view === "dashboard" && (
            <div className="dashboard-view">
              <div className="view-heading">
                <div>
                  <span className="eyebrow">Live monitoring</span>
                  <h2>Call dashboard</h2>
                </div>
                <div className="dashboard-actions">
                  <button
                    type="button"
                    className={cls("secondary-button", muted && "active")}
                    onClick={() => setMuted(!muted)}
                    disabled={!live && !starting}
                  >
                    {muted ? "Unmute" : "Mute"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={clearPlayback}
                    disabled={!live && !starting}
                  >
                    Clear audio
                  </button>
                  {(live || starting) && (
                    <button type="button" className="end-button" onClick={endCall}>
                      End call
                    </button>
                  )}
                </div>
              </div>

              <div className="dashboard-grid">
                <div className="dashboard-main">
                  <div className="panel status-card">
                    <div className="status-card-top">
                      <span className={cls("live-orb", live && "active")} />
                      <div>
                        <small>Session status</small>
                        <h3>{starting ? "Connecting…" : status}</h3>
                      </div>
                      <span className="timer">{formatDuration(elapsed)}</span>
                    </div>
                    <p>{statusDetail}</p>
                    <div className="metric-grid">
                      <div>
                        <small>Provider</small>
                        <strong>
                          {provider === "gemini" ? "Gemini Live" : "Soniox STS"}
                        </strong>
                      </div>
                      <div>
                        <small>Mean live response</small>
                        <strong>
                          {averageLatency ? `${averageLatency} ms` : "—"}
                        </strong>
                      </div>
                      <div>
                        <small>Translation events</small>
                        <strong>
                          {feed.filter((item) => item.stage === "translation").length}
                        </strong>
                      </div>
                      <div>
                        <small>Twilio call</small>
                        <strong>
                          {twilioSid ? `${twilioSid.slice(0, 8)}…` : "Pending"}
                        </strong>
                      </div>
                    </div>
                    <div className="level-block">
                      <LevelMeter
                        label="Person A microphone"
                        value={levels.caller_to_callee}
                        color="cyan"
                      />
                      <LevelMeter
                        label="Person B phone"
                        value={levels.callee_to_caller}
                        color="violet"
                      />
                    </div>
                  </div>

                  <div className="panel chart-card">
                    <div className="panel-heading">
                      <div>
                        <span className="eyebrow">Latency</span>
                        <h2>Round-trip response time</h2>
                      </div>
                    </div>
                    <LatencyPipeline averageMs={averageLatency} />
                    <LatencyChart values={latencies} />
                  </div>
                </div>

                <div className="dashboard-side">
                  <TranscriptPanel
                    title="Person A → Person B"
                    subtitle={`${callerLanguage} into ${calleeLanguage}`}
                    items={callerToCallee}
                    accent="cyan"
                  />
                  <TranscriptPanel
                    title="Person B → Person A"
                    subtitle={`${calleeLanguage} into ${callerLanguage}`}
                    items={calleeToCaller}
                    accent="violet"
                  />
                  <div className="panel event-panel">
                    <div className="panel-heading">
                      <div>
                        <span className="eyebrow">Telemetry</span>
                        <h2>Call events</h2>
                      </div>
                    </div>
                    <div className="event-list">
                      {!events.length && (
                        <div className="empty-state">
                          Events will appear during a call.
                        </div>
                      )}
                      {events.map((item) => (
                        <div className={cls("event-row", item.tone)} key={item.id}>
                          <span />
                          <p>{item.text}</p>
                          <time>
                            {new Date(item.at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                              second: "2-digit",
                            })}
                          </time>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
