"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel } from "../page";

type Props = {
  panels: Panel[];
  isGenerating: boolean;
  isGeneratingMore?: boolean;
  selectedPanels: number[];
  onSelectPanels: (panels: number[]) => void;
  onGenerateMore?: () => void;
  styleName: string;
  storyTitle: string;
  characterImage?: string;
  userStory?: string;
};

const PANEL_GRADIENTS = [
  "linear-gradient(160deg, #e8e4dc, #ddd8ce)",
  "linear-gradient(160deg, #e4e4ec, #d8d8e8)",
  "linear-gradient(160deg, #ece8e0, #e4dcd0)",
  "linear-gradient(160deg, #e0e8e8, #d4e0e0)",
  "linear-gradient(160deg, #ece4ec, #e4d8e8)",
  "linear-gradient(160deg, #e4e4ec, #dcdce8)",
  "linear-gradient(160deg, #ece4e4, #e8d8d8)",
  "linear-gradient(160deg, #e4ece4, #d8e4d8)",
  "linear-gradient(160deg, #e8e4ec, #dcd4e4)",
  "linear-gradient(160deg, #e4e8ec, #d8dce4)",
  "linear-gradient(160deg, #ece8e0, #e4dcd0)",
  "linear-gradient(160deg, #e4e8ec, #d8dce4)",
];

function getShotGroup(panelNumber: number): number {
  return Math.ceil(panelNumber / 6);
}

function LoadingState({ userStory }: { userStory?: string }) {
  const [loadingStep, setLoadingStep] = useState(0);
  useEffect(() => {
    const t1 = setTimeout(() => setLoadingStep(1), 3000);
    const t2 = setTimeout(() => setLoadingStep(2), 8000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  return (
    <div className="loading-state fade-in">
      <div className="loading-orb">
        <div className="loading-orb-ring" />
        <div className="loading-orb-ring" />
        <div className="loading-orb-ring" />
        <div className="loading-orb-center" />
      </div>
      {userStory && (
        <div
          style={{
            fontFamily: "var(--font-body)",
            fontSize: "13px",
            color: "var(--dim)",
            textAlign: "center",
            maxWidth: 320,
            lineHeight: 1.5,
            fontStyle: "italic",
          }}
        >
          &ldquo;
          {userStory.length > 80 ? userStory.slice(0, 80).trimEnd() + "..." : userStory}
          &rdquo;
        </div>
      )}
      <div className="loading-title">상품 사진을 촬영하고 있어요</div>
      <div className="loading-subtitle">약 30초 정도 소요됩니다</div>
      <div className="loading-steps">
        <div className={`loading-step ${loadingStep === 0 ? "active" : "done"}`}>
          <div className="loading-step-dot" />
          {loadingStep > 0 ? "상품 분석 완료" : "상품을 분석하고 있어요"}
        </div>
        <div
          className={`loading-step ${
            loadingStep === 1 ? "active" : loadingStep > 1 ? "done" : ""
          }`}
        >
          <div className="loading-step-dot" />
          {loadingStep > 1 ? "촬영 계획 완료" : "촬영 계획을 세우고 있어요"}
        </div>
        <div className={`loading-step ${loadingStep === 2 ? "active" : ""}`}>
          <div className="loading-step-dot" />
          상품 사진을 생성하고 있어요
        </div>
      </div>
    </div>
  );
}

export default function PhotoViewer({
  panels,
  isGenerating,
  isGeneratingMore,
  selectedPanels,
  onSelectPanels,
  onGenerateMore,
  styleName,
  storyTitle,
  characterImage,
  userStory,
}: Props) {
  const [viewMode, setViewMode] = useState<"grid" | "scroll">("grid");
  const [zoomedPanel, setZoomedPanel] = useState<Panel | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  }, []);

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const donePanels = panels.filter((p) => p.status === "done").length;
  const donePanelsList = panels.filter((p) => p.status === "done");

  const zoomedIdx = zoomedPanel
    ? donePanelsList.findIndex((p) => p.panel_number === zoomedPanel.panel_number)
    : -1;

  const goLightboxPrev = useCallback(() => {
    if (zoomedIdx > 0) setZoomedPanel(donePanelsList[zoomedIdx - 1]);
  }, [zoomedIdx, donePanelsList]);

  const goLightboxNext = useCallback(() => {
    if (zoomedIdx < donePanelsList.length - 1)
      setZoomedPanel(donePanelsList[zoomedIdx + 1]);
  }, [zoomedIdx, donePanelsList]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (zoomedPanel) {
          setZoomedPanel(null);
          if (document.fullscreenElement) document.exitFullscreen();
        }
      }
      if (zoomedPanel) {
        if (e.key === "ArrowLeft") goLightboxPrev();
        if (e.key === "ArrowRight") goLightboxNext();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [zoomedPanel, goLightboxPrev, goLightboxNext]);

  const handlePanelClick = (panelNumber: number, shiftKey: boolean) => {
    if (shiftKey) {
      const isSelected = selectedPanels.includes(panelNumber);
      if (isSelected) {
        onSelectPanels(selectedPanels.filter((n) => n !== panelNumber));
      } else {
        onSelectPanels([...selectedPanels, panelNumber].sort((a, b) => a - b));
      }
    } else {
      if (selectedPanels.length === 1 && selectedPanels[0] === panelNumber) {
        onSelectPanels([]);
      } else {
        onSelectPanels([panelNumber]);
      }
    }
  };

  const handlePanelDoubleClick = (panel: Panel) => {
    if (panel.status === "done" && panel.image_url) {
      setZoomedPanel(panel);
    }
  };

  const renderPanelCard = (panel: Panel, idx: number) => {
    const isSelected = selectedPanels.includes(panel.panel_number);
    return (
      <div
        className={`panel-card ${
          panel.status === "done"
            ? "panel-card-done"
            : panel.status === "gen"
            ? "panel-card-gen"
            : "panel-card-wait"
        } ${isSelected ? "selected" : ""}`}
        style={{
          background:
            panel.status === "done" && panel.image_url
              ? undefined
              : PANEL_GRADIENTS[idx % PANEL_GRADIENTS.length],
          outline: isSelected
            ? selectedPanels.length > 1
              ? "2px solid var(--gold)"
              : "2px solid var(--red)"
            : undefined,
          outlineOffset: isSelected ? "2px" : undefined,
          boxShadow: isSelected
            ? selectedPanels.length > 1
              ? "0 0 14px rgba(255, 214, 10, 0.18)"
              : "0 0 14px rgba(255, 45, 85, 0.2)"
            : undefined,
        }}
        onClick={(e) => {
          if (panel.status === "done") {
            handlePanelClick(panel.panel_number, e.shiftKey);
          }
        }}
        onDoubleClick={() => handlePanelDoubleClick(panel)}
        title={
          panel.status === "done"
            ? `Shot #${panel.panel_number}${
                panel.narration ? ` · ${panel.narration}` : ""
              }\n더블클릭으로 확대 · ${
                selectedPanels.length > 0
                  ? "Shift+클릭으로 추가 선택"
                  : "클릭으로 선택 · Shift+클릭으로 다중 선택"
              }`
            : undefined
        }
      >
        <div className="panel-badge">{panel.panel_number}</div>

        {panel.status === "done" && panel.image_url ? (
          <>
            <img
              src={panel.image_url}
              alt={`Shot ${panel.panel_number}`}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
              draggable={false}
            />
            {isSelected && selectedPanels.length > 1 && (
              <div
                style={{
                  position: "absolute",
                  top: 5,
                  left: 5,
                  width: 16,
                  height: 16,
                  borderRadius: "50%",
                  background: "var(--gold)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  zIndex: 10,
                  fontSize: 9,
                  fontWeight: 700,
                  color: "#000",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {selectedPanels.indexOf(panel.panel_number) + 1}
              </div>
            )}
            <div className="panel-zoom-hint">⤢</div>
          </>
        ) : panel.status === "gen" ? (
          <div className="panel-gen-content">
            <div className="panel-gen-icon" />
            <div className="panel-gen-text">촬영 중</div>
            {panel.narration && (
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "7px",
                  color: "rgba(17,17,17,0.25)",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  marginTop: 2,
                }}
              >
                {panel.narration}
              </div>
            )}
            {panel.dialogue?.[0] && (
              <div
                style={{
                  fontFamily: "var(--font-body)",
                  fontSize: "9px",
                  color: "rgba(17,17,17,0.3)",
                  textAlign: "center",
                  padding: "0 12px",
                  lineHeight: 1.4,
                  maxWidth: "90%",
                  marginTop: 4,
                }}
              >
                &ldquo;{panel.dialogue[0]}&rdquo;
              </div>
            )}
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                color: "rgba(17,17,17,0.15)",
                letterSpacing: "0.06em",
              }}
            >
              {panel.panel_number}
            </span>
          </div>
        )}
      </div>
    );
  };

  const showLoadingState = isGenerating && panels.length === 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="panel-grid-header">
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div className="panel-grid-label">Product Shots · {styleName || "Photo"}</div>
          {panels.length > 0 && (
            <span className="panel-grid-count" style={{ margin: 0 }}>
              {donePanels}/{panels.length}
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {selectedPanels.length > 0 && (
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "9px",
                color: "var(--red)",
                letterSpacing: "0.06em",
              }}
            >
              {selectedPanels.length === 1
                ? `#${selectedPanels[0]} 선택됨`
                : `${selectedPanels.length}장 선택됨`}
            </div>
          )}
          {panels.length > 0 && (
            <div className="view-toggle">
              <button
                className={`view-toggle-btn ${viewMode === "grid" ? "active" : ""}`}
                onClick={() => setViewMode("grid")}
                title="Grid view"
              >
                ⊞
              </button>
              <button
                className={`view-toggle-btn ${
                  viewMode === "scroll" ? "active" : ""
                }`}
                onClick={() => setViewMode("scroll")}
                title="Scroll view"
              >
                ☰
              </button>
            </div>
          )}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {showLoadingState && (
          <LoadingState userStory={userStory} />
        )}
        {storyTitle && storyTitle !== "Generating..." && (
          <div
            style={{
              padding: "16px 20px 4px",
              fontFamily: "var(--font-display)",
              fontSize: "18px",
              color: "var(--text)",
              lineHeight: 1.2,
              textAlign: "center",
            }}
          >
            {storyTitle}
          </div>
        )}

        {characterImage && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              padding: "12px 16px 4px",
            }}
          >
            <div
              style={{
                position: "relative",
                width: 120,
                height: 120,
                borderRadius: 12,
                overflow: "hidden",
                border: "1px solid var(--border)",
                flexShrink: 0,
              }}
            >
              <img
                src={characterImage}
                alt="Product reference"
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
                draggable={false}
              />
              <div
                style={{
                  position: "absolute",
                  bottom: 0,
                  left: 0,
                  right: 0,
                  padding: "2px 6px",
                  background: "rgba(0,0,0,0.65)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "8px",
                  color: "rgba(255,255,255,0.7)",
                  letterSpacing: "0.06em",
                  textAlign: "center",
                }}
              >
                PRODUCT REF
              </div>
            </div>
          </div>
        )}

        {viewMode === "grid" && (
          <div className="panel-grid">
            {panels.map((panel, idx) => {
              const group = getShotGroup(panel.panel_number);
              const prevGroup =
                idx > 0 ? getShotGroup(panels[idx - 1].panel_number) : 0;
              const showDivider = group !== prevGroup;

              return (
                <div key={panel.panel_number} style={{ display: "contents" }}>
                  {showDivider && (
                    <div className="chapter-divider">Set {group}</div>
                  )}
                  {renderPanelCard(panel, idx)}
                </div>
              );
            })}
          </div>
        )}

        {viewMode === "scroll" && (
          <div className="panel-scroll">
            {panels.map((panel, idx) => {
              const group = getShotGroup(panel.panel_number);
              const prevGroup =
                idx > 0 ? getShotGroup(panels[idx - 1].panel_number) : 0;
              const showDivider = group !== prevGroup;

              return (
                <div key={panel.panel_number}>
                  {showDivider && (
                    <div className="scroll-chapter-divider">Set {group}</div>
                  )}
                  <div className="panel-scroll-item">
                    {renderPanelCard(panel, idx)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {panels.some((p) => p.status === "done") && !isGenerating && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: "16px 0" }}>
            {onGenerateMore && (
              <button
                className="btn-cta"
                onClick={onGenerateMore}
                disabled={isGeneratingMore}
                style={{
                  padding: "10px 24px",
                  fontSize: "13px",
                  opacity: isGeneratingMore ? 0.6 : 1,
                }}
              >
                {isGeneratingMore ? "생성 중..." : "+ 4장 더 생성"}
              </button>
            )}
            <div className="multiselect-hint">
              더블클릭으로 확대 · Shift+클릭으로 다중 선택
            </div>
          </div>
        )}
      </div>

      {(isGenerating || (donePanels < panels.length && panels.length > 0)) && (
        <div className="gen-progress-bar">
          <div className="gen-progress-track">
            <div
              className="gen-progress-fill"
              style={{
                width: `${
                  panels.length > 0 ? (donePanels / panels.length) * 100 : 0
                }%`,
              }}
            />
          </div>
          <span className="gen-progress-text">
            {donePanels}/{panels.length}
          </span>
        </div>
      )}

      {zoomedPanel && (
        <div className="lightbox-overlay" onClick={() => setZoomedPanel(null)}>
          <div className="lightbox-inner" onClick={(e) => e.stopPropagation()}>
            <button className="lightbox-close" onClick={() => setZoomedPanel(null)}>
              ✕
            </button>
            <button
              className="lightbox-fullscreen"
              onClick={toggleFullscreen}
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? "⊡" : "⛶"}
            </button>

            <div className="lightbox-meta">
              <span className="lightbox-num">#{zoomedPanel.panel_number}</span>
              {zoomedPanel.narration && (
                <span className="lightbox-act">{zoomedPanel.narration}</span>
              )}
              <span className="lightbox-counter">
                {zoomedIdx + 1} / {donePanelsList.length}
              </span>
            </div>

            {zoomedIdx > 0 && (
              <button className="lightbox-nav lightbox-nav-prev" onClick={goLightboxPrev}>
                ‹
              </button>
            )}

            <img
              src={zoomedPanel.image_url}
              alt={`Shot ${zoomedPanel.panel_number}`}
              className="lightbox-image"
              draggable={false}
            />

            {zoomedIdx < donePanelsList.length - 1 && (
              <button className="lightbox-nav lightbox-nav-next" onClick={goLightboxNext}>
                ›
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
