"use client";

import { useEffect, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import PhotoViewer from "./components/PhotoViewer";

export type Panel = {
  panel_number: number;
  image_url: string;
  dialogue: string[];
  narration: string;
  image_prompt: string;
  scene_description?: string;
  face_description?: string;
  character_name?: string;
  outfit?: string;
  character_expression?: string;
  camera_angle?: string;
  mood?: string;
  session_id?: string;
  loading?: boolean;
  status?: "done" | "gen" | "wait";
};

export type Phase = 0 | 1 | 2;

export type Style = {
  id: string;
  emoji: string;
  title: string;
  desc: string;
};

export const STYLES: Style[] = [
  { id: "studio", emoji: "\uD83D\uDCF8", title: "Studio", desc: "\uD074\uB9B0\uD55C \uC2A4\uD29C\uB514\uC624 \uCD2C\uC601" },
  { id: "lifestyle", emoji: "\uD83C\uDF3F", title: "Lifestyle", desc: "\uAC10\uC131\uC801\uC778 \uB77C\uC774\uD504\uC2A4\uD0C0\uC77C \uC5F0\uCD9C" },
  { id: "flat-lay", emoji: "\uD83C\uDFA8", title: "Flat Lay", desc: "\uD0D1\uBDF0 \uD50C\uB7AB\uB808\uC774 \uAD6C\uC131" },
  { id: "cinematic", emoji: "\uD83C\uDFAC", title: "Cinematic", desc: "\uC2DC\uB124\uB9C8\uD2F1 \uBB34\uB4DC \uCD2C\uC601" },
];

const STORY_SUGGESTIONS = [
  "\uBBF8\uB2C8\uBA40\uD55C \uAC00\uC8FD \uC9C0\uAC11, 20\uB300 \uB0A8\uC131 \uD0C0\uAC9F, \uACE0\uAE09\uC2A4\uB7EC\uC6B4 \uB290\uB08C",
  "\uC218\uC81C \uC544\uB85C\uB9C8 \uCE94\uB4E4, \uC778\uC2A4\uD0C0\uADF8\uB7A8 \uAC10\uC131, \uB530\uB73B\uD55C \uBD84\uC704\uAE30",
  "\uBB34\uC120 \uBE14\uB8E8\uD22C\uC2A4 \uC774\uC5B4\uD3F0, \uD14C\uD06C \uAC10\uC131, \uAE54\uB054\uD55C \uC81C\uD488\uCEF7",
  "\uD578\uB4DC\uBA54\uC774\uB4DC \uB3C4\uC790\uAE30 \uBA38\uADF8\uCEF5, \uCE74\uD398 \uBD84\uC704\uAE30, \uB0B4\uCD94\uB7F4\uD55C \uC5F0\uCD9C",
];

export default function Home() {
  const [phase, setPhase] = useState<Phase>(0);
  const [selectedStyle, setSelectedStyle] = useState<Style | null>(null);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [characterDescription, setCharacterDescription] = useState("");
  const [characterImage, setCharacterImage] = useState("");
  const [selectedPanels, setSelectedPanels] = useState<number[]>([]);
  const [genProgress, setGenProgress] = useState({ current: 0, total: 0 });
  const [storyTitle, setStoryTitle] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [isGeneratingMore, setIsGeneratingMore] = useState(false);

  // Story input state (lifted here so it persists across phases)
  const [story, setStory] = useState("");
  const [selfieFile, setSelfieFile] = useState<File[]>([]);
  const [selfiePreview, setSelfiePreview] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  // Refs to avoid stale closures in handleEdit
  const panelsRef = useRef<Panel[]>([]);
  const sessionIdRef = useRef("");
  useEffect(() => { panelsRef.current = panels; }, [panels]);
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  const handleSelectStyle = (style: Style) => {
    setSelectedStyle(style);
    setPhase(1);
  };

  // addMsg callback ref — ChatPanel registers its addMsg function here
  const addMsgRef = useRef<
    | ((
        text: string,
        type?: "sys" | "progress" | "ai" | "storyboard" | "tool-call" | "tool-result",
        data?: unknown
      ) => void)
    | null
  >(null);

  // Pending generate — set true to kick off fetch after ChatPanel mounts
  const [pendingGenerate, setPendingGenerate] = useState(false);
  // Capture story/style/selfie at trigger time so the effect closure is stable
  const pendingFormRef = useRef<FormData | null>(null);

  const handleGenerate = () => {
    if (!story.trim() && selfieFile.length === 0) return;
    const formData = new FormData();
    formData.append("story", story.trim() || "상품 사진 촬영");
    if (selectedStyle) formData.append("style", selectedStyle.id);
    selfieFile.forEach((f) => formData.append("photos", f));
    pendingFormRef.current = formData;

    setPhase(2);
    setIsGenerating(true);
    setStoryTitle("Generating...");
    setPanels([]);
    setGenProgress({ current: 0, total: 0 });
    setPendingGenerate(true); // fires useEffect AFTER ChatPanel has mounted + registered addMsg
  };

  // Actual SSE fetch — runs after ChatPanel has mounted and registered addMsgRef.current
  useEffect(() => {
    if (!pendingGenerate) return;
    setPendingGenerate(false);
    const formData = pendingFormRef.current;
    if (!formData) return;

    const addMsg = (...args: Parameters<NonNullable<typeof addMsgRef.current>>) => addMsgRef.current?.(...args);
    const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

    const run = async () => {
      let panelsDoneCount = 0;
      let panelsTotalCount = 0;
      try {
      const res = await fetch(`${BACKEND}/generate/stream`, { method: "POST", body: formData });
      if (!res.body) throw new Error("No response body");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          if (!chunk.startsWith("data: ")) continue;
          const event = JSON.parse(chunk.slice(6));
          if (event.type === "status") {
            addMsg?.(event.message, "sys");
          } else if (event.type === "thought") {
            addMsg?.(`💭 ${event.content}`, "progress");
          } else if (event.type === "text") {
            if (event.content?.trim()) addMsg?.(event.content.trim(), "ai");
          } else if (event.type === "tool_call") {
            addMsg?.(event.name, "tool-call", { name: event.name, args: event.args ?? {} });
          } else if (event.type === "tool_result") {
            addMsg?.(event.name, "tool-result", { name: event.name, status: event.status, preview: event.preview ?? {} });
          } else if (event.type === "character") {
            setCharacterDescription(event.face_description ?? "");
            let refImg = event.face_ref_image ?? "";
            if (refImg && refImg.startsWith("/")) refImg = `${BACKEND}${refImg}`;
            setCharacterImage(refImg);
            addMsg?.("Product photos analyzed", "progress");
          } else if (event.type === "storyboard") {
            setStoryTitle(event.title ?? "");
            setSessionId(event.session_id ?? "");
            if (!characterDescription && event.character_description) {
              setCharacterDescription(event.character_description);
            }
            const count = event.panel_count as number;
            const panelsMeta = event.panels_meta as Array<{
              panel_number: number;
              act?: string;
              dialogue?: string;
              character_names?: string[];
            }> | undefined;
            setPanels(Array.from({ length: count }, (_, i) => ({
              panel_number: i + 1,
              image_url: "",
              dialogue: panelsMeta?.[i]?.dialogue ? [panelsMeta[i].dialogue as string] : [],
              narration: panelsMeta?.[i]?.act ?? "",
              image_prompt: "",
              status: "gen" as const,
            })));
            panelsTotalCount = count;
            panelsDoneCount = 0;
            setGenProgress({ current: 0, total: count });
            addMsg?.("storyboard", "storyboard", {
              title: event.title,
              characters: event.characters ?? [],
              panels_meta: (event.panels_meta ?? []).map((p: { panel_number: number; act?: string; dialogue?: string; character_names?: string[] }) => ({
                panel_number: p.panel_number,
                act: p.act ?? "",
                dialogue: p.dialogue ?? "",
                character_names: p.character_names ?? [],
              })),
              panel_count: count,
            });
          } else if (event.type === "panel") {
            const p = event.panel as Panel;
            // Prefix backend URL for relative image paths
            if (p.image_url && p.image_url.startsWith("/")) {
              p.image_url = `${BACKEND}${p.image_url}`;
            }
            setPanels((prev) =>
              prev.map((x) =>
                x.panel_number === p.panel_number ? { ...p, status: "done" as const } : x
              )
            );
            // Track count outside updater to avoid React strict mode double-fire
            panelsDoneCount++;
            const next = panelsDoneCount;
            const total = panelsTotalCount;
            if (next === 1) {
              addMsg?.(`First panel ready \u2014 ${total - 1} more rendering...`, "progress");
            } else if (next === total) {
              addMsg?.(`All ${total} panels rendered`, "progress");
            } else if (next % 5 === 0) {
              addMsg?.(`${next}/${total} panels done`, "progress");
            }
            setGenProgress({ current: next, total });
          } else if (event.type === "error") {
            addMsg?.(event.message ?? "Generation failed", "sys");
            setIsGenerating(false);
          } else if (event.type === "done") {
            setSessionId(event.session_id ?? sessionId);
            // Don't set isGenerating=false here — the finally block after the loop handles it.
            // Setting it here causes a race: React batches this with panel updates,
            // so the completion effect sees 0 done panels.
          }
        }
      }
    } catch (err) {
      console.error("SSE stream error:", err);
      addMsg?.(`생성 중 오류 발생: ${err}`, "sys");
    }

    setIsGenerating(false);
    }; // end run

    run();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingGenerate]);

  const handleEdit = async (panelNumber: number, instruction: string) => {
    setPanels((prev) =>
      prev.map((p) =>
        p.panel_number === panelNumber ? { ...p, status: "gen" as const, loading: true } : p
      )
    );

    try {
      const panel = panelsRef.current.find((p) => p.panel_number === panelNumber);
      const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
      const res = await fetch(`${BACKEND}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          panel_number: panelNumber,
          instruction,
          session_id: panel?.session_id ?? sessionIdRef.current,
          scene_description: panel?.scene_description ?? "",
          face_description: panel?.face_description ?? characterDescription,
          outfit: panel?.outfit ?? "",
          character_expression: panel?.character_expression ?? "",
          camera_angle: panel?.camera_angle ?? "",
          mood: panel?.mood ?? "",
          dialogue: panel?.dialogue?.[0] ?? "",
          style: selectedStyle?.id ?? "studio",
        }),
      });
      const data = await res.json();

      let newUrl = data.image_url || "";
      if (newUrl && newUrl.startsWith("/")) {
        newUrl = `${BACKEND}${newUrl}`;
      }
      if (newUrl && !newUrl.startsWith("data:")) {
        newUrl += (newUrl.includes("?") ? "&" : "?") + `t=${Date.now()}`;
      }

      setPanels((prev) =>
        prev.map((p) =>
          p.panel_number === panelNumber
            ? { ...p, image_url: newUrl, loading: false, status: "done" as const }
            : p
        )
      );
    } catch {
      setPanels((prev) =>
        prev.map((p) =>
          p.panel_number === panelNumber ? { ...p, loading: false, status: "done" as const } : p
        )
      );
    }
  };

  const handleGenerateMore = async () => {
    if (!sessionId || isGeneratingMore) return;
    const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
    setIsGeneratingMore(true);

    // Add 4 placeholder panels
    const existingCount = panels.length;
    const placeholders: Panel[] = Array.from({ length: 4 }, (_, i) => ({
      panel_number: existingCount + 1 + i,
      image_url: "",
      dialogue: [],
      narration: "",
      image_prompt: "",
      status: "gen" as const,
    }));
    setPanels((prev) => [...prev, ...placeholders]);

    try {
      const res = await fetch(`${BACKEND}/generate/more`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          story: story,
          style: selectedStyle?.id ?? "studio",
          face_description: characterDescription,
          count: 4,
          existing_count: existingCount,
        }),
      });
      const data = await res.json();
      const newPanels = (data.panels ?? []) as Panel[];

      // Prefix backend URL and mark as done
      for (const p of newPanels) {
        if (p.image_url && p.image_url.startsWith("/")) {
          p.image_url = `${BACKEND}${p.image_url}`;
        }
      }

      setPanels((prev) => {
        // Replace placeholders with real panels
        const existing = prev.slice(0, existingCount);
        const done = newPanels.map((p) => ({ ...p, status: "done" as const }));
        return [...existing, ...done];
      });
    } catch {
      // Remove placeholders on error
      setPanels((prev) => prev.slice(0, existingCount));
    }
    setIsGeneratingMore(false);
  };

  const handleReset = () => {
    setPhase(0);
    setSelectedStyle(null);
    setPanels([]);
    setIsGenerating(false);
    setIsGeneratingMore(false);
    setCharacterDescription("");
    setCharacterImage("");
    setSelectedPanels([]);
    setGenProgress({ current: 0, total: 0 });
    setStoryTitle("");
    setSessionId("");
    setStory("");
    setSelfieFile([]);
    setSelfiePreview([]);
  };

  const handleSelfie = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const selected = Array.from(files).slice(0, 4);
    setSelfieFile(selected);
    setSelfiePreview(selected.map((f) => URL.createObjectURL(f)));
  };

  const donePanels = panels.filter((p) => p.status === "done").length;

  return (
    <main style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--bg)" }}>
      {/* Top Bar */}
      <div className="topbar">
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <span className="topbar-logo" style={{ cursor: "pointer" }} onClick={handleReset}>
            Shot<span>Craft</span>
          </span>
          {phase === 0 && (
            <span className="topbar-sub">AI Product Photography</span>
          )}
        </div>
        <div className="topbar-right">
          {selectedStyle && (
            <span className="badge badge-style">{selectedStyle.title}</span>
          )}
          {panels.length > 0 && genProgress.total > 0 && (
            <span className="badge badge-progress">
              {donePanels}/{genProgress.total}
            </span>
          )}
          {phase > 0 && (
            <button className="btn-reset" onClick={handleReset}>Reset</button>
          )}
        </div>
      </div>

      {/* Phase 0: Hero Landing */}
      {phase === 0 && (
        <div className="hero-page fade-in">
          <div>
            <div className="hero-title">Shot<span>Craft</span></div>
            <div className="hero-subtitle">{"\uC0C1\uD488 \uC0AC\uC9C4, AI\uAC00 \uC5F0\uCD9C\uD569\uB2C8\uB2E4"}</div>
          </div>
          <div className="hero-styles">
            {STYLES.map((s) => (
              <div
                key={s.id}
                className="hero-style-card"
                onClick={() => handleSelectStyle(s)}
              >
                <span className="hero-style-flag">{s.emoji}</span>
                <span className="hero-style-title">{s.title}</span>
                <span className="hero-style-desc">{s.desc}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Phase 1: Story Input */}
      {phase === 1 && (
        <div className="story-page fade-in">
          <div className="story-container">
            <button className="story-back" onClick={() => { setPhase(0); setSelectedStyle(null); }}>
              &larr; Back to styles
            </button>

            <div className="story-heading">
              {"\uC0C1\uD488\uC5D0 \uB300\uD574"} <span>{"\uC124\uBA85\uD574\uC8FC\uC138\uC694"}</span>
            </div>

            <textarea
              className="story-textarea"
              rows={4}
              placeholder={"\uC0C1\uD488 \uC124\uBA85\uC744 \uC785\uB825\uD574\uC8FC\uC138\uC694...\ne.g. \uBBF8\uB2C8\uBA40\uD55C \uAC00\uC8FD \uC9C0\uAC11, \uACE0\uAE09\uC2A4\uB7EC\uC6B4 \uB290\uB08C, \uB0A8\uC131 \uD0C0\uAC9F"}
              value={story}
              onChange={(e) => setStory(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  handleGenerate();
                }
              }}
              autoFocus
            />

            {/* Story suggestions */}
            <div className="story-suggestions">
              {STORY_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="story-chip"
                  onClick={() => setStory(s)}
                >
                  {s.length > 100 ? s.slice(0, 100).trimEnd() + "..." : s}
                </button>
              ))}
            </div>

            {/* Product photo upload */}
            <div className="selfie-upload">
              <button
                className={`selfie-btn ${selfiePreview.length > 0 ? "has-image" : ""}`}
                onClick={() => fileRef.current?.click()}
              >
                {selfiePreview.length > 0 ? (
                  <div style={{ display: "grid", gridTemplateColumns: selfiePreview.length > 1 ? "1fr 1fr" : "1fr", width: "100%", height: "100%", gap: 2 }}>
                    {selfiePreview.map((src, i) => (
                      <img
                        key={i}
                        src={src}
                        alt={`product-${i + 1}`}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />
                    ))}
                  </div>
                ) : (
                  <span>{"\uD83D\uDCF8"}</span>
                )}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                multiple
                style={{ display: "none" }}
                onChange={handleSelfie}
              />
              <div>
                <div
                  style={{
                    fontFamily: "var(--font-body)",
                    fontSize: "14px",
                    color: selfieFile.length > 0 ? "var(--green)" : "rgba(17, 17, 17, 0.5)",
                    letterSpacing: "0.01em",
                  }}
                >
                  {selfieFile.length > 0 ? `${selfieFile.length}\uC7A5 \uC5C5\uB85C\uB4DC \uC644\uB8CC \u2713` : "\uC0C1\uD488 \uC0AC\uC9C4 \uC5C5\uB85C\uB4DC (1~4\uC7A5)"}
                </div>
                {selfieFile.length > 0 && (
                  <button
                    onClick={() => { setSelfieFile([]); setSelfiePreview([]); }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--dim)",
                      fontSize: "10px",
                      cursor: "pointer",
                      padding: 0,
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {"\u2715"} Remove
                  </button>
                )}
              </div>
            </div>

            {/* Generate button */}
            <button
              className="btn-cta btn-cta-primary"
              disabled={!story.trim() && selfieFile.length === 0}
              onClick={handleGenerate}
            >
              Generate Shots
            </button>
          </div>
        </div>
      )}

      {/* Phase 2+: Split Layout */}
      {phase === 2 && (
        <div className="split-layout fade-in">
          <ChatPanel
            panels={panels}
            isGenerating={isGenerating}
            selectedPanels={selectedPanels}
            userStory={story}
            genProgress={genProgress}
            onEdit={handleEdit}
            onSelectPanels={setSelectedPanels}
            addMsgRef={addMsgRef}
          />

          <div className="preview-panel">
            <PhotoViewer
              panels={panels}
              isGenerating={isGenerating}
              isGeneratingMore={isGeneratingMore}
              selectedPanels={selectedPanels}
              onSelectPanels={setSelectedPanels}
              onGenerateMore={handleGenerateMore}
              styleName={selectedStyle?.title ?? ""}
              storyTitle={storyTitle}
              characterImage={characterImage}
              userStory={story}
            />
          </div>
        </div>
      )}
    </main>
  );
}
