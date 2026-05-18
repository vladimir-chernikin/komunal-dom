import React from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  ChevronRight,
  CircleAlert,
  Clock3,
  Copy,
  FileAudio,
  Image as ImageIcon,
  Lock,
  MapPin,
  Mic,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import "./styles.css";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const APP_BUILD = "2026-05-14-external-recorder-primary-status-fix-v1";
const PENDING_VOICE_SESSION_KEY = "maxWebappPendingVoiceSession";
const PENDING_VOICE_SESSION_TTL_MS = 20 * 60 * 1000;
const AUDIO_CAPTURE_ACCEPT = "audio/*";
const AUDIO_CAPTURE_MODE = "user";

function getWebApp() {
  return window.WebApp || null;
}

function maskSensitive(value) {
  const text = String(value || "");
  return text.length > 16 ? `${text.slice(0, 8)}...${text.slice(-8)}` : "***";
}

function parseInitData(initData) {
  const result = {};
  if (!initData) {
    return result;
  }
  const params = new URLSearchParams(initData);
  params.forEach((value, key) => {
    if (key === "hash") {
      result[key] = maskSensitive(value);
      return;
    }
    if (key === "user") {
      try {
        result[key] = JSON.parse(value);
      } catch {
        result[key] = value;
      }
      return;
    }
    result[key] = value;
  });
  return result;
}

function buildFrontendLaunchDebug(webApp, initData) {
  return {
    source: "frontend_webapp",
    build: APP_BUILD,
    url: window.location.href,
    origin: window.location.origin,
    secureContext: window.isSecureContext,
    userAgent: window.navigator.userAgent,
    initDataLength: initData?.length || 0,
    initDataUnsafe: webApp?.initDataUnsafe || null,
    initDataParsed: parseInitData(initData),
    webApp: webApp
      ? {
          version: webApp.version,
          platform: webApp.platform,
          colorScheme: webApp.colorScheme,
          themeParams: webApp.themeParams,
          viewportHeight: webApp.viewportHeight,
          viewportStableHeight: webApp.viewportStableHeight,
          isExpanded: webApp.isExpanded,
        }
      : null,
  };
}

function loadPendingVoiceSession() {
  try {
    const raw = window.localStorage?.getItem(PENDING_VOICE_SESSION_KEY);
    if (!raw) {
      return null;
    }
    const pending = JSON.parse(raw);
    if (!pending?.sessionId || !pending?.orderId || Date.now() - Number(pending.createdAt || 0) > PENDING_VOICE_SESSION_TTL_MS) {
      window.localStorage?.removeItem(PENDING_VOICE_SESSION_KEY);
      return null;
    }
    return pending;
  } catch {
    return null;
  }
}

function savePendingVoiceSession(pending) {
  try {
    window.localStorage?.setItem(PENDING_VOICE_SESSION_KEY, JSON.stringify(pending));
  } catch {
    // localStorage may be unavailable in some embedded browsers.
  }
}

function clearPendingVoiceSession(sessionId = null) {
  try {
    const pending = loadPendingVoiceSession();
    if (!sessionId || pending?.sessionId === sessionId) {
      window.localStorage?.removeItem(PENDING_VOICE_SESSION_KEY);
    }
  } catch {
    // No-op.
  }
}

function formatDate(value) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function normalize(value) {
  return String(value || "").toLocaleLowerCase("ru-RU");
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.max(0, Math.floor(Math.abs(milliseconds) / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const time = [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
  return days ? `${days} д ${time}` : time;
}

function getSlaText(row, now) {
  if (row.text) {
    return row.text;
  }
  const dueAt = row.due_at ? new Date(row.due_at) : null;
  const stoppedAt = row.stopped_at ? new Date(row.stopped_at) : null;
  if (!dueAt) {
    return "норматив не задан";
  }
  if (stoppedAt) {
    const delta = stoppedAt.getTime() - dueAt.getTime();
    return delta > 0 || row.state === "overdue"
      ? `просрочено на ${formatDuration(delta)}`
      : "выполнено в срок";
  }
  const delta = dueAt.getTime() - now.getTime();
  return delta >= 0 ? `осталось ${formatDuration(delta)}` : `просрочено на ${formatDuration(delta)}`;
}

function getSlaClass(row, now) {
  if (row.state === "missing") {
    return "sla-muted";
  }
  const dueAt = row.due_at ? new Date(row.due_at) : null;
  const stoppedAt = row.stopped_at ? new Date(row.stopped_at) : null;
  if (stoppedAt) {
    return stoppedAt.getTime() > dueAt?.getTime() || row.state === "overdue" ? "sla-danger" : "sla-success";
  }
  if (dueAt && dueAt.getTime() < now.getTime()) {
    return "sla-danger";
  }
  return "sla-active";
}

function friendlyHttpError(status, rawText) {
  if (status === 413) {
    return "Фото слишком большое. Попробуйте выбрать другое фото.";
  }
  if (status === 502 || status === 504) {
    return "Сервер временно недоступен. Повторите действие позже.";
  }
  if (rawText?.trim().startsWith("<")) {
    return "Сервер вернул техническую ошибку вместо JSON.";
  }
  return "Запрос не выполнен.";
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

async function prepareImageFile(file) {
  if (!file.type.startsWith("image/")) {
    return file;
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await loadImage(objectUrl);
    const maxSide = 1600;
    const scale = Math.min(1, maxSide / Math.max(image.width, image.height));

    if (scale === 1 && file.size <= 900 * 1024) {
      return file;
    }

    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
    if (!blob || blob.size >= file.size) {
      return file;
    }

    const fileName = file.name.replace(/\.[^.]+$/, "") || "photo";
    return new File([blob], `${fileName}.jpg`, {
      type: "image/jpeg",
      lastModified: Date.now(),
    });
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function StatusPill({ order }) {
  return (
    <span className={`status status-${order.status.code}`}>
      {order.isEmergency && <CircleAlert size={14} strokeWidth={2.4} />}
      {order.status.name}
    </span>
  );
}

function EmptyState({ icon: Icon, title, text }) {
  return (
    <section className="empty-state">
      <Icon size={34} strokeWidth={1.8} />
      <h2>{title}</h2>
      <p>{text}</p>
    </section>
  );
}

function Field({ icon: Icon, label, value }) {
  return (
    <div className="detail-field">
      <div className="field-label">
        <Icon size={15} />
        <span>{label}</span>
      </div>
      <div className="field-value">{value || "Не задано"}</div>
    </div>
  );
}

function App() {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [query, setQuery] = React.useState("");
  const [status, setStatus] = React.useState("all");
  const [selectedId, setSelectedId] = React.useState(null);
  const [detail, setDetail] = React.useState(null);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [detailError, setDetailError] = React.useState("");
  const [formState, setFormState] = React.useState({ resolution: "", responsibleUserId: "" });
  const [saving, setSaving] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [recognizingAudio, setRecognizingAudio] = React.useState(false);
  const [uploadPreviews, setUploadPreviews] = React.useState([]);
  const [listening, setListening] = React.useState(false);
  const [notice, setNotice] = React.useState("");
  const [speechNote, setSpeechNote] = React.useState("");
  const [micDebug, setMicDebug] = React.useState([]);
  const [now, setNow] = React.useState(() => new Date());
  const fileInputRef = React.useRef(null);
  const audioInputRef = React.useRef(null);
  const voicePollTimerRef = React.useRef(null);
  const voiceSessionIdRef = React.useRef(null);

  const webApp = getWebApp();
  const initData = webApp?.initData || "";
  const frontendLaunchDebug = React.useMemo(
    () => buildFrontendLaunchDebug(webApp, initData),
    [initData, webApp],
  );

  const showNotice = React.useCallback((message) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 3600);
  }, []);

  const copyText = React.useCallback(
    async (text) => {
      try {
        await copyTextToClipboard(text);
        showNotice("Лог скопирован в буфер.");
      } catch (copyError) {
        showNotice(`Не удалось скопировать: ${copyError.message}`);
      }
    },
    [showNotice],
  );

  const addMicDebug = React.useCallback((message, details = null) => {
    const time = new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date());
    const detailsText = details ? ` ${JSON.stringify(details)}` : "";
    console.debug(`[MAX mic] ${message}`, details || "");
    setMicDebug((current) => [`${time} ${message}${detailsText}`, ...current].slice(0, 8));
  }, []);

  const requestJson = React.useCallback(
    async (url, options = {}) => {
      if (!initData) {
        throw new Error("Откройте мини-приложение из MAX.");
      }
      const response = await fetch(url, {
        ...options,
        cache: "no-store",
        headers: {
          ...(options.headers || {}),
          "X-Max-Init-Data": initData,
        },
      });
      const rawText = await response.text();
      let payload = null;
      try {
        payload = rawText ? JSON.parse(rawText) : null;
      } catch {
        payload = null;
      }
      if (!response.ok || !payload.ok) {
        const requestError = new Error(payload?.error || friendlyHttpError(response.status, rawText));
        requestError.code = payload?.code;
        requestError.status = response.status;
        throw requestError;
      }
      return payload;
    },
    [initData],
  );

  const loadOrders = React.useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) {
        setLoading(true);
      }
      setError("");
      try {
        const payload = await requestJson("/api/max-webapp/work-orders/");
        setData(payload);
      } catch (loadError) {
        setError(loadError.message);
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [requestJson],
  );

  const openOrder = React.useCallback(
    async (orderId) => {
      setSelectedId(orderId);
      setDetail(null);
      setDetailError("");
      setDetailLoading(true);
      try {
        const payload = await requestJson(`/api/max-webapp/work-orders/${orderId}/`);
        setDetail(payload.order);
        setFormState({
          resolution: payload.order.resolution || "",
          responsibleUserId: payload.order.responsibleUser?.id ? String(payload.order.responsibleUser.id) : "",
        });
      } catch (openError) {
        setDetailError(openError.message);
      } finally {
        setDetailLoading(false);
      }
    },
    [requestJson],
  );

  React.useEffect(() => {
    webApp?.BackButton?.hide?.();
    console.info("[MAX launch]", frontendLaunchDebug);
    loadOrders();
  }, [frontendLaunchDebug, loadOrders, webApp]);

  React.useEffect(() => {
    if (!selectedId) {
      webApp?.BackButton?.hide?.();
      return undefined;
    }
    const handler = () => closeDetail();
    webApp?.BackButton?.show?.();
    webApp?.BackButton?.onClick?.(handler);
    return () => webApp?.BackButton?.offClick?.(handler);
  }, [selectedId, webApp]);

  React.useEffect(() => {
    if (!selectedId) {
      return undefined;
    }
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, [selectedId]);

  React.useEffect(() => {
    return () => {
      uploadPreviews.forEach((preview) => URL.revokeObjectURL(preview.url));
    };
  }, [uploadPreviews]);

  React.useEffect(() => {
    return () => {
      window.clearTimeout(voicePollTimerRef.current);
    };
  }, []);

  function closeDetail() {
    setSelectedId(null);
    setDetail(null);
    setDetailError("");
    setUploadPreviews([]);
    window.clearTimeout(voicePollTimerRef.current);
    voiceSessionIdRef.current = null;
    setListening(false);
  }

  const orders = data?.orders || [];
  const statuses = React.useMemo(
    () => Array.from(new Set(orders.map((order) => order.status.name))),
    [orders],
  );
  const filteredOrders = React.useMemo(() => {
    const searchText = normalize(query);
    return orders.filter((order) => {
      const matchesStatus = status === "all" || order.status.name === status;
      const haystack = normalize(
        [
          order.number,
          order.text,
          order.service.name,
          order.service.category,
          order.object.address,
          order.department,
          order.responsible,
        ].join(" "),
      );
      return matchesStatus && (!searchText || haystack.includes(searchText));
    });
  }, [orders, query, status]);
  const interfaceInfo = data?.interface || null;
  const launchLogText = React.useMemo(
    () =>
      JSON.stringify(
        {
          backend: data?.maxLaunch || null,
          frontend: frontendLaunchDebug,
        },
        null,
        2,
    ),
    [data?.maxLaunch, frontendLaunchDebug],
  );

  async function saveAndReturn() {
    if (!detail) {
      return;
    }
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append("resolution_text", formState.resolution || "");
      if (detail.assignment.editable && formState.responsibleUserId) {
        formData.append("responsible_user_id", formState.responsibleUserId);
      }
      await requestJson(`/api/max-webapp/work-orders/${detail.id}/save/`, {
        method: "POST",
        body: formData,
      });
      closeDetail();
      await loadOrders();
    } catch (saveError) {
      showNotice(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function runStatusAction(forceWithoutPhoto = false) {
    if (!detail?.activeAction) {
      return;
    }
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append("action", detail.activeAction.code);
      formData.append("resolution_text", formState.resolution || "");
      if (detail.assignment.editable && formState.responsibleUserId) {
        formData.append("responsible_user_id", formState.responsibleUserId);
      }
      if (forceWithoutPhoto) {
        formData.append("force_without_photo", "1");
      }
      const payload = await requestJson(`/api/max-webapp/work-orders/${detail.id}/action/`, {
        method: "POST",
        body: formData,
      });
      setDetail(payload.order);
      setFormState({
        resolution: payload.order.resolution || "",
        responsibleUserId: payload.order.responsibleUser?.id ? String(payload.order.responsibleUser.id) : "",
      });
      await loadOrders({ silent: true });
    } catch (actionError) {
      if (actionError.code === "photo_confirmation_required") {
        const confirmed = window.confirm("ФОТО НЕ ПРИВЯЗАНЫ.\nВы точно хотите изменить статус заявки?");
        if (confirmed) {
          await runStatusAction(true);
        }
        return;
      }
      showNotice(actionError.message);
    } finally {
      setSaving(false);
    }
  }

  async function uploadPhotos(files) {
    if (!detail || !files.length) {
      return;
    }
    const previews = files.map((file) => ({ name: file.name, url: URL.createObjectURL(file) }));
    setUploadPreviews((current) => [...current, ...previews]);
    setUploading(true);
    try {
      const preparedFiles = await Promise.all(files.map((file) => prepareImageFile(file)));
      const oversized = preparedFiles.find((file) => file.size > MAX_UPLOAD_BYTES);
      if (oversized) {
        throw new Error("Размер одного фото не должен превышать 20 МБ.");
      }
      const formData = new FormData();
      preparedFiles.forEach((file) => formData.append("photo", file));
      const payload = await requestJson(`/api/max-webapp/work-orders/${detail.id}/photos/`, {
        method: "POST",
        body: formData,
      });
      setDetail(payload.order);
      await loadOrders({ silent: true });
    } catch (uploadError) {
      showNotice(uploadError.message);
    } finally {
      setUploading(false);
      setUploadPreviews([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function uploadAudioForRecognition(file) {
    if (!file) {
      setSpeechNote("");
      return;
    }
    setRecognizingAudio(true);
    setSpeechNote("Отправляю аудиозапись на распознавание...");
    addMicDebug("Uploading system recorder audio", {
      name: file.name,
      type: file.type,
      size: file.size,
    });
    try {
      const formData = new FormData();
      formData.append("audio", file, file.name || "voice-recording");
      const payload = await requestJson("/api/max-webapp/speech-to-text/", {
        method: "POST",
        body: formData,
      });
      const transcript = (payload.text || "").trim();
      addMicDebug("System recorder STT response", { chars: transcript.length });
      if (!transcript) {
        setSpeechNote("Речь не распознана. Попробуйте записать фразу еще раз.");
        return;
      }
      setFormState((current) => ({
        ...current,
        resolution: [current.resolution.trim(), transcript].filter(Boolean).join("\n"),
      }));
      setSpeechNote("Текст добавлен к решению.");
    } catch (audioError) {
      addMicDebug("System recorder STT failed", { message: audioError.message, code: audioError.code });
      setSpeechNote(audioError.message || "Аудиозапись не распознана.");
    } finally {
      setRecognizingAudio(false);
      if (audioInputRef.current) {
        audioInputRef.current.value = "";
      }
    }
  }

  function startSystemRecording(event) {
    event?.preventDefault?.();
    if (recognizingAudio) {
      return;
    }
    addMicDebug("Opening system recorder", {
      capture: AUDIO_CAPTURE_MODE,
      accept: AUDIO_CAPTURE_ACCEPT,
      build: APP_BUILD,
    });
    setSpeechNote("Пробую открыть встроенный диктофон. Если MAX снова покажет только «Файл», используйте запасной вариант ниже.");
    audioInputRef.current?.click();
  }

  const pollVoiceSession = React.useCallback(
    (sessionId, pending = null) => {
      window.clearTimeout(voicePollTimerRef.current);
      const tick = async () => {
        if (voiceSessionIdRef.current !== sessionId) {
          return;
        }
        try {
          const payload = await requestJson(`/api/max-webapp/voice-sessions/${sessionId}/`);
          const session = payload.session;
          addMicDebug("External recorder status", { status: session.status });

          if (session.status === "done") {
            voiceSessionIdRef.current = null;
            setListening(false);
            clearPendingVoiceSession(sessionId);
            if (session.text?.trim()) {
              const orderId = pending?.orderId || session.workOrderId || null;
              if (orderId && Number(selectedId) !== Number(orderId)) {
                await openOrder(orderId);
              }
              setFormState((current) => ({
                ...current,
                resolution: [current.resolution.trim(), session.text.trim()].filter(Boolean).join("\n"),
              }));
              setSpeechNote("Текст из внешней записи добавлен к решению.");
            } else {
              setSpeechNote("Внешняя запись завершена, но речь не распознана.");
            }
            return;
          }

          if (session.status === "error") {
            voiceSessionIdRef.current = null;
            setListening(false);
            clearPendingVoiceSession(sessionId);
            setSpeechNote(session.error || "Внешняя запись завершилась ошибкой.");
            return;
          }

          voicePollTimerRef.current = window.setTimeout(tick, 2000);
        } catch (pollError) {
          addMicDebug("External recorder polling failed", { message: pollError.message });
          voicePollTimerRef.current = window.setTimeout(tick, 3000);
        }
      };
      voicePollTimerRef.current = window.setTimeout(tick, 2000);
    },
    [addMicDebug, openOrder, requestJson, selectedId],
  );

  const resumePendingVoiceSession = React.useCallback(() => {
    const pending = loadPendingVoiceSession();
    if (!pending || voiceSessionIdRef.current === pending.sessionId) {
      return;
    }
    voiceSessionIdRef.current = pending.sessionId;
    setListening(true);
    setSpeechNote("Проверяю результат внешней записи и возвращаю карточку обращения.");
    addMicDebug("Resuming pending external recorder session", {
      sessionId: pending.sessionId,
      orderId: pending.orderId,
    });
    openOrder(pending.orderId);
    pollVoiceSession(pending.sessionId, pending);
  }, [addMicDebug, openOrder, pollVoiceSession]);

  React.useEffect(() => {
    resumePendingVoiceSession();
    const handleFocus = () => resumePendingVoiceSession();
    const handleVisibility = () => {
      if (!document.hidden) {
        resumePendingVoiceSession();
      }
    };
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [resumePendingVoiceSession]);

  async function startExternalDictation(event) {
    event?.preventDefault?.();
    if (listening || voiceSessionIdRef.current) {
      addMicDebug("External recorder already active");
      return;
    }
    if (!detail?.id) {
      setSpeechNote("Откройте карточку обращения перед записью.");
      return;
    }
    try {
      setListening(true);
      addMicDebug("Opening external recorder", {
        build: APP_BUILD,
        openLinkAvailable: Boolean(webApp?.openLink),
      });
      setSpeechNote("Открываю запись во внешнем браузере. После отправки текста вернитесь в MAX.");
      const payload = await requestJson("/api/max-webapp/voice-sessions/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workOrderId: detail.id }),
      });
      const sessionId = payload.session.id;
      const pending = {
        sessionId,
        orderId: detail.id,
        createdAt: Date.now(),
      };
      voiceSessionIdRef.current = sessionId;
      savePendingVoiceSession(pending);
      addMicDebug("External recorder session created", {
        sessionId,
        orderId: detail.id,
        expiresAt: payload.session.expiresAt,
      });

      if (webApp?.openLink) {
        webApp.openLink(payload.recordUrl);
        addMicDebug("Opened external recorder via WebApp.openLink");
      } else {
        window.open(payload.recordUrl, "_blank", "noopener,noreferrer");
        addMicDebug("Opened external recorder via window.open");
      }
      pollVoiceSession(sessionId, pending);
    } catch (dictationError) {
      setListening(false);
      voiceSessionIdRef.current = null;
      clearPendingVoiceSession();
      addMicDebug("External recorder failed to open", { message: dictationError.message });
      setSpeechNote(dictationError.message || "Не удалось открыть внешний браузер для записи.");
    }
  }

  if (!loading && error) {
    const isAuthError = error.includes("MAX") || error.includes("Доступ");
    return (
      <main className="app-shell">
        <EmptyState
          icon={isAuthError ? Lock : AlertTriangle}
          title={isAuthError ? "Доступ ограничен" : "Ошибка загрузки"}
          text={error}
        />
      </main>
    );
  }

  if (selectedId) {
    return (
      <DetailView
        detail={detail}
        detailError={detailError}
        detailLoading={detailLoading}
        formState={formState}
        listening={listening}
        micDebug={micDebug}
        now={now}
        onBack={closeDetail}
        onDictateStart={startExternalDictation}
        onSystemRecordStart={startSystemRecording}
        onAudioFileSelect={uploadAudioForRecognition}
        onCopyMicLog={() => copyText(micDebug.join("\n"))}
        onFormChange={setFormState}
        onPhotoSelect={(files) => uploadPhotos(files)}
        onSave={saveAndReturn}
        onStatusAction={() => runStatusAction(false)}
        notice={notice}
        onNoticeClose={() => setNotice("")}
        saving={saving}
        recognizingAudio={recognizingAudio}
        speechNote={speechNote}
        uploading={uploading}
        uploadPreviews={uploadPreviews}
        fileInputRef={fileInputRef}
        audioInputRef={audioInputRef}
      />
    );
  }

  return (
    <main className="app-shell">
      {notice && <Toast message={notice} onClose={() => setNotice("")} />}
      <header className="topbar">
        <div>
          <p className="eyebrow">УК АСПЕКТ</p>
          <h1>Обращения</h1>
          <div className="user-line">
            <ShieldCheck size={15} />
            <span>
              {data?.user?.name || "MAX"}
              {interfaceInfo?.label ? ` · ${interfaceInfo.label}` : ""}
            </span>
          </div>
        </div>
        <button className="icon-button" type="button" onClick={() => loadOrders()} disabled={loading} aria-label="Обновить">
          <RefreshCw size={20} className={loading ? "spin" : ""} />
        </button>
      </header>

      <section className="summary-grid">
        <div className="metric">
          <span>Всего</span>
          <strong>{data?.summary?.total ?? "..."}</strong>
        </div>
        <div className="metric">
          <span>Аварийные</span>
          <strong>{data?.summary?.emergency ?? "..."}</strong>
        </div>
        <div className="metric wide">
          <span>Обновлено</span>
          <strong>{data?.summary?.updatedAt ? formatDate(data.summary.updatedAt) : "..."}</strong>
        </div>
      </section>

      {interfaceInfo?.type === "uk_user" && (
        <section className="create-request-panel">
          <button type="button" onClick={() => showNotice("Создание заявки будет подключено на следующем этапе.")}>
            Оставить заявку
          </button>
        </section>
      )}

      {interfaceInfo?.type === "boss" && (
        <details className="launch-debug">
          <summary>
            <span>MAX launch log</span>
            <button
              className="copy-log-button"
              type="button"
              onClick={(event) => {
                event.preventDefault();
                copyText(launchLogText);
              }}
              aria-label="Скопировать MAX launch log"
            >
              <Copy size={15} />
            </button>
          </summary>
          <pre>{launchLogText}</pre>
        </details>
      )}

      <section className="filters">
        <label className="search-box">
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Номер, адрес, текст"
          />
        </label>
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Статус">
          <option value="all">Все статусы</option>
          {statuses.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </section>

      <section className="status-strip">
        {Object.entries(data?.summary?.statuses || {}).map(([name, count]) => (
          <button
            type="button"
            className={status === name ? "status-filter active" : "status-filter"}
            key={name}
            onClick={() => setStatus(status === name ? "all" : name)}
          >
            <span>{name}</span>
            <strong>{count}</strong>
          </button>
        ))}
      </section>

      <section className="orders-list" aria-live="polite">
        {loading && <EmptyState icon={Clock3} title="Загрузка" text="Получаю обращения АСПЕКТ." />}
        {!loading && filteredOrders.length === 0 && (
          <EmptyState icon={Search} title="Ничего не найдено" text="Измените фильтр или поисковую строку." />
        )}
        {!loading &&
          filteredOrders.map((order) => (
            <button className="order-card" type="button" key={order.id} onClick={() => openOrder(order.id)}>
              <div className="order-head">
                <div>
                  <strong>#{order.number}</strong>
                  <time>{formatDate(order.createdAt)}</time>
                </div>
                <StatusPill order={order} />
              </div>
              <p className="order-text">{order.text}</p>
              <dl className="order-meta">
                <div>
                  <dt>Адрес</dt>
                  <dd>{order.object.address}</dd>
                </div>
                <div>
                  <dt>Услуга</dt>
                  <dd>{order.service.name}</dd>
                </div>
                <div>
                  <dt>Отдел</dt>
                  <dd>{order.department || "Не назначен"}</dd>
                </div>
                <div>
                  <dt>Исполнитель</dt>
                  <dd>{order.responsible || "Не назначен"}</dd>
                </div>
              </dl>
              <ChevronRight className="order-chevron" size={20} />
            </button>
          ))}
      </section>
    </main>
  );
}

function DetailView({
  audioInputRef,
  detail,
  detailError,
  detailLoading,
  fileInputRef,
  formState,
  listening,
  micDebug,
  now,
  onBack,
  onAudioFileSelect,
  onCopyMicLog,
  onDictateStart,
  onSystemRecordStart,
  onFormChange,
  onPhotoSelect,
  notice,
  onNoticeClose,
  onSave,
  onStatusAction,
  saving,
  recognizingAudio,
  speechNote,
  uploading,
  uploadPreviews,
}) {
  if (detailLoading) {
    return (
      <main className="app-shell">
        <button className="back-link" type="button" onClick={onBack}>
          <ArrowLeft size={18} />
          <span>Назад</span>
        </button>
        <EmptyState icon={Clock3} title="Загрузка карточки" text="Получаю данные обращения." />
      </main>
    );
  }

  if (detailError || !detail) {
    return (
      <main className="app-shell">
        <button className="back-link" type="button" onClick={onBack}>
          <ArrowLeft size={18} />
          <span>Назад</span>
        </button>
        <EmptyState icon={AlertTriangle} title="Карточка недоступна" text={detailError || "Не удалось открыть обращение."} />
      </main>
    );
  }

  const action = detail.activeAction;
  const canEdit = detail.interface?.canEdit ?? true;
  const actionLabels = {
    assign: "Установить ответственного",
    start: "Взять в работу",
    localize: "Локализовать",
    complete: "Выполнить",
    close: "Завершить",
  };
  const actionLabel = action ? actionLabels[action.code] || action.label : "Смена статуса недоступна";
  const actionDisabled = !action || saving || (action.requiresResponsible && !formState.responsibleUserId);
  const allPhotos = [
    ...detail.photos.map((photo) => ({ id: photo.id, name: photo.fileName, url: photo.dataUrl, saved: true })),
    ...uploadPreviews.map((preview, index) => ({ id: `preview-${index}`, name: preview.name, url: preview.url, saved: false })),
  ];

  return (
    <main className="app-shell detail-shell">
      {notice && <Toast message={notice} onClose={onNoticeClose} />}
      <header className="detail-topbar">
        <button className="back-link" type="button" onClick={onBack}>
          <ArrowLeft size={18} />
          <span>Назад</span>
        </button>
        <StatusPill order={detail} />
      </header>

      <section className="detail-title">
        <p className="eyebrow">Карточка обращения</p>
        <h1>#{detail.number}</h1>
        <time>{formatDate(detail.createdAt)}</time>
      </section>

      <section className="sla-panel">
        {detail.sla.map((row) => (
          <div className={`sla-row ${getSlaClass(row, now)}`} key={row.label}>
            <span>{row.label}</span>
            <strong>{getSlaText(row, now)}</strong>
          </div>
        ))}
      </section>

      <section className="detail-grid">
        <Field icon={MapPin} label="Адрес" value={detail.object.address} />
        <Field icon={Wrench} label="Наименование услуги" value={detail.service.name} />
        <Field icon={UserRound} label="Отдел" value={detail.department} />
        <Field icon={UserRound} label="Исполнитель" value={detail.responsibleUser.name || "Не назначен"} />
      </section>

      <section className="request-text-block">
        <div className="field-label">
          <Clock3 size={15} />
          <span>Текст обращения</span>
        </div>
        <p>{detail.text}</p>
      </section>

      {!canEdit && (
        <section className="readonly-panel">
          <div>
            <strong>Решение</strong>
            <p>{detail.resolution || "Решение пока не указано."}</p>
          </div>
          <button className="close-button" type="button" onClick={onBack}>
            <X size={18} />
            <span>Закрыть</span>
          </button>
        </section>
      )}

      {canEdit && (
      <section className="edit-panel">
        {detail.assignment.editable && (
          <label className="form-field">
            <span>Исполнитель</span>
            <select
              value={formState.responsibleUserId}
              onChange={(event) =>
                onFormChange((current) => ({ ...current, responsibleUserId: event.target.value }))
              }
            >
              <option value="">Выберите сотрудника отдела</option>
              {detail.assignment.candidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </option>
              ))}
            </select>
            {detail.assignment.candidates.length === 0 && (
              <small className="form-note">В этом отделе нет активных исполнителей.</small>
            )}
          </label>
        )}

        <label className="form-field">
          <span>Решение</span>
          <div className="resolution-row">
            <textarea
              value={formState.resolution}
              onChange={(event) =>
                onFormChange((current) => ({ ...current, resolution: event.target.value }))
              }
              placeholder="Опишите решение, локализацию или выполненные работы"
            />
            <button
              className={listening ? "mic-button active" : "mic-button"}
              type="button"
              onClick={onDictateStart}
              onContextMenu={(event) => event.preventDefault()}
              disabled={listening}
              aria-label="Открыть запись с микрофона"
            >
              <Mic size={24} />
            </button>
          </div>
          {speechNote && <small className="form-note">{speechNote}</small>}
          {micDebug.length > 0 && (
            <div className="mic-log-block">
              <div className="log-head">
                <span>Лог записи</span>
                <button
                  className="copy-log-button"
                  type="button"
                  onClick={onCopyMicLog}
                  aria-label="Скопировать лог записи"
                >
                  <Copy size={15} />
                </button>
              </div>
              <div className="mic-debug" aria-label="Отладка записи">
                {micDebug.map((line, index) => (
                  <code key={`${index}-${line}`}>{line}</code>
                ))}
              </div>
            </div>
          )}
          <button
            className="audio-fallback-button"
            type="button"
            onClick={onSystemRecordStart}
            disabled={recognizingAudio}
          >
            <FileAudio size={17} />
            <span>{recognizingAudio ? "Распознаю аудио" : "Попробовать системный диктофон"}</span>
          </button>
          <input
            ref={audioInputRef}
            type="file"
            accept={AUDIO_CAPTURE_ACCEPT}
            capture={AUDIO_CAPTURE_MODE}
            hidden
            onChange={(event) => onAudioFileSelect(event.target.files?.[0] || null)}
            onCancel={() => onAudioFileSelect(null)}
          />
        </label>
        <div className="resident-warning">Все написанное тут уйдет пользователю.</div>

        <div className="photos-block">
          <div className="photos-head">
            <div>
              <span>Фото</span>
              <small>{detail.photoCount + uploadPreviews.length} добавлено</small>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Camera size={18} />
              <span>{uploading ? "Загрузка" : "Добавить фото"}</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              multiple
              hidden
              onChange={(event) => onPhotoSelect(Array.from(event.target.files || []))}
            />
          </div>
          <div className="photo-grid">
            {allPhotos.length === 0 && (
              <div className="photo-empty">
                <ImageIcon size={22} />
                <span>Фото пока не добавлены</span>
              </div>
            )}
            {allPhotos.map((photo) => (
              <div className="photo-thumb" key={photo.id} title={photo.name}>
                {photo.url ? <img src={photo.url} alt={photo.name} /> : <ImageIcon size={28} />}
                {!photo.saved && <span>загрузка</span>}
              </div>
            ))}
          </div>
        </div>

        <div className="detail-actions">
          <button className="status-action-button" type="button" onClick={onStatusAction} disabled={actionDisabled}>
            {saving ? "Сохраняю" : actionLabel}
          </button>
          <button className="save-button" type="button" onClick={onSave} disabled={saving || uploading}>
            <Save size={18} />
            <span>Сохранить</span>
          </button>
          <button className="close-button" type="button" onClick={onBack} disabled={saving}>
            <X size={18} />
            <span>Закрыть</span>
          </button>
        </div>
      </section>
      )}
    </main>
  );
}

function Toast({ message, onClose }) {
  return (
    <button className="toast-message" type="button" onClick={onClose}>
      {message}
    </button>
  );
}

createRoot(document.getElementById("root")).render(<App />);
