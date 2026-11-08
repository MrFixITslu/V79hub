import { useEffect, useRef, useState } from "react";

type Credential = { credential?: string };
type GoogleIdentity = {
  accounts: {
    id: {
      initialize: (options: {
        client_id: string;
        nonce: string;
        auto_select: boolean;
        callback: (response: Credential) => void;
      }) => void;
      renderButton: (target: HTMLElement, options: {
        theme: string;
        size: string;
        text: string;
        shape: string;
        width: number;
      }) => void;
    };
  };
};

function googleIdentity(): GoogleIdentity | undefined {
  return (window as Window & { google?: GoogleIdentity }).google;
}

let sdkPromise: Promise<void> | null = null;
function loadGoogleIdentity(): Promise<void> {
  if (googleIdentity()?.accounts?.id) return Promise.resolve();
  if (!sdkPromise) {
    sdkPromise = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.crossOrigin = "anonymous";
      script.onload = () => googleIdentity()?.accounts?.id
        ? resolve()
        : reject(new Error("Google sign-in is unavailable."));
      script.onerror = () => reject(new Error("Google sign-in could not load."));
      document.head.appendChild(script);
    }).catch(error => {
      sdkPromise = null;
      throw error;
    });
  }
  return sdkPromise;
}

export function GoogleSignIn({ organizationId, onCredential }: {
  organizationId: string;
  onCredential: (credential: string, nonce: string, organizationId: string) => Promise<void>;
}) {
  const button = useRef<HTMLDivElement>(null);
  const handler = useRef(onCredential);
  const [version, setVersion] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "submitting" | "off" | "error">("loading");
  const [message, setMessage] = useState("");
  useEffect(() => { handler.current = onCredential; }, [onCredential]);

  useEffect(() => {
    let cancelled = false;
    let expireTimer: number | undefined;
    const initialise = async () => {
      setStatus("loading");
      setMessage("");
      if (button.current) button.current.replaceChildren();
      try {
        // The live Hub server decides whether Google login is available.
        // Never use a hard-coded OAuth client ID in a release build.
        const configResponse = await fetch("/api/auth/google/config", {
          credentials: "same-origin", cache: "no-store",
        });
        if (!configResponse.ok) throw new Error("Google configuration is unavailable.");
        const config = await configResponse.json();
        if (cancelled) return;
        if (config?.enabled !== true || typeof config.clientId !== "string" ||
            !config.clientId || config.clientId.length > 512) {
          setStatus("off");
          return;
        }

        await loadGoogleIdentity();
        if (cancelled) return;
        // A fresh server nonce is consumed exactly once. The ID token never
        // enters localStorage, a URL, analytics, or the page's rendered text.
        const challengeResponse = await fetch("/api/auth/google/challenge", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
          headers: { "content-type": "application/json" },
          body: "{}",
        });
        const challenge = await challengeResponse.json().catch(() => ({}));
        if (!challengeResponse.ok ||
            typeof challenge.nonce !== "string" ||
            !/^[A-Za-z0-9_-]{16,128}$/.test(challenge.nonce)) {
          throw new Error("Google sign-in could not start safely.");
        }
        if (cancelled || !button.current) return;

        const nonce = challenge.nonce;
        googleIdentity()!.accounts.id.initialize({
          client_id: config.clientId,
          nonce,
          auto_select: false,
          callback: async response => {
            if (cancelled) return;
            if (typeof response.credential !== "string" || !response.credential) {
              setStatus("error");
              setMessage("Google did not provide a valid sign-in response.");
              return;
            }
            setStatus("submitting");
            try {
              await handler.current(response.credential, nonce, organizationId);
            } catch {
              // The parent owns user-safe authentication error messaging.
            } finally {
              // A nonce cannot be reused after a server-side login attempt.
              if (!cancelled) setVersion(value => value + 1);
            }
          },
        });
        button.current.replaceChildren();
        googleIdentity()!.accounts.id.renderButton(button.current, {
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: 300,
        });
        setStatus("ready");
        // Refresh even if someone leaves the login page open for 15 minutes.
        expireTimer = window.setTimeout(() => {
          if (!cancelled) setVersion(value => value + 1);
        }, 12 * 60_000);
      } catch {
        if (!cancelled) {
          setStatus("error");
          setMessage("Google sign-in is temporarily unavailable. You can still sign in with your password.");
        }
      }
    };
    void initialise();
    return () => {
      cancelled = true;
      if (expireTimer !== undefined) window.clearTimeout(expireTimer);
    };
  }, [organizationId, version]);

  if (status === "off") return null;
  return (
    <div className="hub-login-google mt-4 space-y-2" aria-label="Google account sign-in">
      <div ref={button} className={status === "ready" ? "flex min-h-11 justify-center" : "hidden"} />
      {status === "loading" && <p role="status" className="text-center text-xs text-slate-400">Preparing secure Google sign-in…</p>}
      {status === "submitting" && <p role="status" className="text-center text-xs text-slate-400">Verifying your Google account…</p>}
      {status === "error" && (
        <div className="text-center text-xs text-slate-400">
          <p role="status">{message}</p>
          <button type="button" onClick={() => setVersion(value => value + 1)}
            className="mt-2 rounded-lg border border-slate-500 px-3 py-2 text-slate-200 hover:text-white">
            Retry Google sign-in
          </button>
        </div>
      )}
      <p className="text-center text-[11px] text-slate-400">
        Google sign-in uses your existing Hub account and the same MFA requirements.
      </p>
    </div>
  );
}
