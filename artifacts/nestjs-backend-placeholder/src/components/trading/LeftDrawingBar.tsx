import { useState, useRef, useEffect } from "react";
import type { DrawingTool } from "./ChartPanel";

// ─── SVG icon helpers ─────────────────────────────────────────────────────────
const Svg = ({ children, size = 16 }: { children: React.ReactNode; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);

const ICONS = {
  cursor:         <Svg><path d="M5 3l14 9-7 1-4 7z"/></Svg>,
  trendline:      <Svg><line x1="4" y1="20" x2="20" y2="4"/><circle cx="4" cy="20" r="1.5" fill="currentColor" stroke="none"/><circle cx="20" cy="4" r="1.5" fill="currentColor" stroke="none"/></Svg>,
  ray:            <Svg><line x1="4" y1="20" x2="22" y2="4"/><circle cx="4" cy="20" r="1.5" fill="currentColor" stroke="none"/></Svg>,
  infoline:       <Svg><line x1="4" y1="20" x2="20" y2="4"/><circle cx="4" cy="20" r="1.5" fill="currentColor" stroke="none"/><circle cx="20" cy="4" r="1.5" fill="currentColor" stroke="none"/><text x="14" y="15" fontSize="7" fill="currentColor" stroke="none">i</text></Svg>,
  extendedline:   <Svg><line x1="2" y1="20" x2="22" y2="4"/></Svg>,
  trendangle:     <Svg><line x1="4" y1="20" x2="20" y2="20"/><line x1="4" y1="20" x2="18" y2="6"/><path d="M8 20 A5 5 0 0 1 7.5 16" fill="none"/></Svg>,
  hline:          <Svg><line x1="2" y1="12" x2="22" y2="12"/><circle cx="2"  cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="22" cy="12" r="1.5" fill="currentColor" stroke="none"/></Svg>,
  hray:           <Svg><line x1="4" y1="12" x2="22" y2="12"/><circle cx="4" cy="12" r="1.5" fill="currentColor" stroke="none"/></Svg>,
  vline:          <Svg><line x1="12" y1="2" x2="12" y2="22"/><circle cx="12" cy="2"  r="1.5" fill="currentColor" stroke="none"/><circle cx="12" cy="22" r="1.5" fill="currentColor" stroke="none"/></Svg>,
  crossline:      <Svg><line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/></Svg>,
  parallelch:     <Svg><line x1="3" y1="18" x2="15" y2="6"/><line x1="9" y1="18" x2="21" y2="6"/></Svg>,
  regtrend:       <Svg><line x1="4" y1="19" x2="20" y2="5"/><line x1="4" y1="15" x2="20" y2="9" strokeDasharray="2 2"/><line x1="4" y1="23" x2="20" y2="1" strokeDasharray="2 2" strokeOpacity="0.5"/></Svg>,
  flattop:        <Svg><line x1="3" y1="8" x2="21" y2="8"/><line x1="3" y1="16" x2="21" y2="16"/><path d="M8 8 L12 16"/><path d="M12 16 L16 8"/></Svg>,
  disjointch:     <Svg><line x1="3" y1="18" x2="11" y2="6"/><line x1="13" y1="18" x2="21" y2="6"/></Svg>,
  pitchfork:      <Svg><path d="M12 20 L12 10 L6 4 M12 10 L18 4 M12 10 L12 4"/></Svg>,
  schiffpitch:    <Svg><path d="M12 20 L12 12 L7 5 M12 12 L17 5 M12 15 L9.5 8.5"/></Svg>,
  fibonacci:      <Svg><line x1="3" y1="20" x2="21" y2="20"/><line x1="3" y1="14" x2="21" y2="14"/><line x1="3" y1="9"  x2="21" y2="9"/><line x1="3" y1="5"  x2="21" y2="5"/><line x1="3" y1="3"  x2="21" y2="3"/><line x1="3" y1="5"  x2="3"  y2="20"/><line x1="21" y1="5" x2="21" y2="20"/></Svg>,
  fibextension:   <Svg><line x1="3" y1="20" x2="21" y2="20"/><line x1="3" y1="13" x2="21" y2="13"/><line x1="3" y1="3"  x2="21" y2="3"/><path d="M3 20 L12 3"/></Svg>,
  fibchannel:     <Svg><line x1="3" y1="19" x2="15" y2="5"/><line x1="9" y1="19" x2="21" y2="5"/><line x1="6" y1="19" x2="18" y2="5" strokeDasharray="2 2"/></Svg>,
  fibtimezone:    <Svg><line x1="5"  y1="4" x2="5"  y2="20"/><line x1="9"  y1="4" x2="9"  y2="20"/><line x1="14" y1="4" x2="14" y2="20"/><line x1="21" y1="4" x2="21" y2="20"/><line x1="3"  y1="12" x2="22" y2="12" strokeOpacity="0.4"/></Svg>,
  gannbox:        <Svg><rect x="4" y="4" width="16" height="16" rx="1"/><line x1="4" y1="4" x2="20" y2="20"/><line x1="4" y1="20" x2="20" y2="4"/></Svg>,
  gannsquare:     <Svg><rect x="4" y="4" width="16" height="16" rx="1"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="12" y1="4" x2="12" y2="20"/><line x1="4" y1="4" x2="20" y2="20"/></Svg>,
  gannfan:        <Svg><path d="M4 20 L20 4 M4 20 L20 10 M4 20 L20 16 M4 20 L20 20 M4 20 L14 4 M4 20 L8 4"/></Svg>,
  abcd:           <Svg><path d="M4 18 L10 6 L14 14 L20 4"/><circle cx="4" cy="18" r="1.5" fill="currentColor" stroke="none"/><circle cx="10" cy="6"  r="1.5" fill="currentColor" stroke="none"/><circle cx="14" cy="14" r="1.5" fill="currentColor" stroke="none"/><circle cx="20" cy="4"  r="1.5" fill="currentColor" stroke="none"/></Svg>,
  headshoulders:  <Svg><path d="M2 18 L5 14 L8 17 L12 8 L16 17 L19 14 L22 18"/></Svg>,
  triangle:       <Svg><path d="M4 18 L12 6 L20 18 Z"/></Svg>,
  elliott:        <Svg><path d="M3 18 L7 8 L11 15 L15 5 L19 12"/><circle cx="3"  cy="18" r="1" fill="currentColor" stroke="none"/><circle cx="7"  cy="8"  r="1" fill="currentColor" stroke="none"/><circle cx="11" cy="15" r="1" fill="currentColor" stroke="none"/><circle cx="15" cy="5"  r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></Svg>,
  cycliclines:    <Svg><line x1="4"  y1="4" x2="4"  y2="20"/><line x1="10" y1="4" x2="10" y2="20"/><line x1="16" y1="4" x2="16" y2="20"/><line x1="22" y1="4" x2="22" y2="20"/></Svg>,
  sineline:       <Svg><path d="M2 12 C4 6 6 6 8 12 S12 18 14 12 S18 6 20 12 S22 18 22 12"/></Svg>,
  longposition:   <Svg><line x1="3" y1="16" x2="21" y2="16"/><line x1="3" y1="10" x2="21" y2="10"/><path d="M7 10 L7 16 M17 10 L17 16"/><path d="M12 10 L12 3 L8 7 M12 3 L16 7" strokeWidth="1.5"/></Svg>,
  shortposition:  <Svg><line x1="3" y1="8"  x2="21" y2="8"/><line x1="3" y1="14" x2="21" y2="14"/><path d="M7 8 L7 14 M17 8 L17 14"/><path d="M12 14 L12 21 L8 17 M12 21 L16 17" strokeWidth="1.5"/></Svg>,
  anchoredvwap:   <Svg><path d="M4 18 L8 14 L11 16 L14 10 L18 12 L21 8"/><line x1="4" y1="8" x2="4" y2="20" strokeDasharray="2 2"/></Svg>,
  pricerange:     <Svg><line x1="5" y1="6"  x2="19" y2="6"/><line x1="5" y1="18" x2="19" y2="18"/><line x1="12" y1="6" x2="12" y2="18"/><line x1="8"  y1="6"  x2="8"  y2="8"/><line x1="16" y1="6"  x2="16" y2="8"/><line x1="8"  y1="18" x2="8"  y2="16"/><line x1="16" y1="18" x2="16" y2="16"/></Svg>,
  brush:          <Svg><path d="M9.5 3 L14.5 8 L7 16 C5 18 3 18 3 16 C3 14 5 14 7 12 Z"/><path d="M14.5 8 L17 5.5 L18.5 7 L16 9.5 Z"/></Svg>,
  highlighter:    <Svg><path d="M3 17 L14 6 L19 11 L8 22 Z" strokeWidth="3" strokeOpacity="0.5"/><line x1="14" y1="6" x2="19" y2="11"/></Svg>,
  arrowmarker:    <Svg><path d="M5 12 L19 12 M14 7 L19 12 L14 17"/></Svg>,
  arrowmarkup:    <Svg><path d="M12 19 L12 5 M7 10 L12 5 L17 10"/><path d="M9 22 L15 22" strokeOpacity="0.5"/></Svg>,
  arrowmarkdown:  <Svg><path d="M12 5 L12 19 M7 14 L12 19 L17 14"/><path d="M9 2 L15 2" strokeOpacity="0.5"/></Svg>,
  rectangle:      <Svg><rect x="4" y="6" width="16" height="12" rx="1"/></Svg>,
  circle:         <Svg><circle cx="12" cy="12" r="8"/></Svg>,
  ellipse:        <Svg><ellipse cx="12" cy="12" rx="9" ry="6"/></Svg>,
  polyline:       <Svg><path d="M3 18 L8 10 L13 15 L18 7"/><circle cx="3"  cy="18" r="1.5" fill="currentColor" stroke="none"/><circle cx="8"  cy="10" r="1.5" fill="currentColor" stroke="none"/><circle cx="13" cy="15" r="1.5" fill="currentColor" stroke="none"/><circle cx="18" cy="7"  r="1.5" fill="currentColor" stroke="none"/></Svg>,
  arc:            <Svg><path d="M4 18 C6 6 18 6 20 18"/></Svg>,
  curve:          <Svg><path d="M3 17 C5 8 10 16 12 12 S19 6 21 8"/></Svg>,
  text:           <Svg><path d="M4 6 L20 6 M12 6 L12 18 M8 18 L16 18" strokeWidth="2"/></Svg>,
  note:           <Svg><rect x="4" y="4" width="16" height="14" rx="2"/><line x1="8" y1="9"  x2="16" y2="9"/><line x1="8" y1="12" x2="14" y2="12"/><path d="M4 18 L4 22 L8 18 Z" fill="currentColor" stroke="none"/></Svg>,
  pricenote:      <Svg><rect x="4" y="6" width="14" height="12" rx="2"/><text x="7" y="16" fontSize="8" fill="currentColor" stroke="none">$</text><line x1="18" y1="12" x2="22" y2="12"/></Svg>,
  pin:            <Svg><circle cx="12" cy="8" r="4"/><line x1="12" y1="12" x2="12" y2="20"/></Svg>,
  callout:        <Svg><rect x="4" y="4" width="16" height="12" rx="2"/><path d="M8 16 L6 20 L12 16"/></Svg>,
  flag:           <Svg><line x1="6" y1="4" x2="6" y2="20"/><path d="M6 4 L20 6 L6 12 Z" fill="currentColor" stroke="none" fillOpacity="0.3"/><path d="M6 4 L20 6 L6 12"/></Svg>,
  measure:        <Svg><rect x="3" y="9" width="18" height="6" rx="1"/><line x1="7"  y1="9" x2="7"  y2="12"/><line x1="12" y1="9" x2="12" y2="12"/><line x1="17" y1="9" x2="17" y2="12"/></Svg>,
  eraser:         <Svg><path d="M20 20 L8 20 L4 14 L14 4 L22 12 Z"/><line x1="4" y1="14" x2="14" y2="24" strokeOpacity="0.3"/></Svg>,
  zoom:           <Svg><circle cx="10" cy="10" r="7"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="7" y1="10" x2="13" y2="10"/><line x1="10" y1="7" x2="10" y2="13"/></Svg>,
};

// ─── Tool catalogue ───────────────────────────────────────────────────────────
export interface SidebarTool { tool: DrawingTool | string; label: string; shortcut?: string; icon: React.ReactNode }
interface ToolGroup {
  id: string;
  categoryIcon: React.ReactNode;
  categoryLabel: string;
  single?: boolean;
  tools: SidebarTool[];
}

const TOOL_GROUPS: ToolGroup[] = [
  {
    id: "cursor", categoryIcon: ICONS.cursor, categoryLabel: "Cursor", single: true,
    tools: [{ tool: "none", label: "Cursor", shortcut: "Esc", icon: ICONS.cursor }],
  },
  {
    id: "lines", categoryIcon: ICONS.trendline, categoryLabel: "Lines",
    tools: [
      { tool: "trendline",   label: "Trendline",       shortcut: "Alt+T", icon: ICONS.trendline },
      { tool: "ray",         label: "Ray",                                 icon: ICONS.ray },
      { tool: "infoline",    label: "Info line",                           icon: ICONS.infoline },
      { tool: "extendedline",label: "Extended line",                       icon: ICONS.extendedline },
      { tool: "trendangle",  label: "Trend angle",                         icon: ICONS.trendangle },
      { tool: "hline",       label: "Horizontal line", shortcut: "Alt+H", icon: ICONS.hline },
      { tool: "hray",        label: "Horizontal ray",  shortcut: "Alt+J", icon: ICONS.hray },
      { tool: "vline",       label: "Vertical line",   shortcut: "Alt+V", icon: ICONS.vline },
      { tool: "crossline",   label: "Cross line",      shortcut: "Alt+C", icon: ICONS.crossline },
    ],
  },
  {
    id: "channels", categoryIcon: ICONS.parallelch, categoryLabel: "Channels",
    tools: [
      { tool: "parallelch",  label: "Parallel channel",    icon: ICONS.parallelch },
      { tool: "regtrend",    label: "Regression trend",    icon: ICONS.regtrend },
      { tool: "flattop",     label: "Flat top / bottom",   icon: ICONS.flattop },
      { tool: "disjointch",  label: "Disjoint channel",    icon: ICONS.disjointch },
    ],
  },
  {
    id: "pitchforks", categoryIcon: ICONS.pitchfork, categoryLabel: "Pitchforks",
    tools: [
      { tool: "pitchfork",   label: "Pitchfork",        icon: ICONS.pitchfork },
      { tool: "schiffpitch", label: "Schiff pitchfork", icon: ICONS.schiffpitch },
    ],
  },
  {
    id: "fibonacci", categoryIcon: ICONS.fibonacci, categoryLabel: "Fibonacci",
    tools: [
      { tool: "fibretracement",  label: "Fib retracement",            shortcut: "Alt+F", icon: ICONS.fibonacci },
      { tool: "fibextension",    label: "Trend-based fib extension",                     icon: ICONS.fibextension },
      { tool: "fibchannel",      label: "Fib channel",                                   icon: ICONS.fibchannel },
      { tool: "fibtimezone",     label: "Fib time zone",                                 icon: ICONS.fibtimezone },
      { tool: "fibfan",          label: "Fib speed resistance fan",                      icon: ICONS.gannfan },
      { tool: "fibcircles",      label: "Fib circles",                                   icon: ICONS.circle },
      { tool: "fibspiral",       label: "Fib spiral",                                    icon: ICONS.arc },
      { tool: "fibwedge",        label: "Fib wedge",                                     icon: ICONS.flattop },
      { tool: "pitchfan",        label: "Pitchfan",                                      icon: ICONS.pitchfork },
    ],
  },
  {
    id: "gann", categoryIcon: ICONS.gannbox, categoryLabel: "Gann",
    tools: [
      { tool: "gannbox",         label: "Gann box",          icon: ICONS.gannbox },
      { tool: "gannsquarefixed", label: "Gann square fixed", icon: ICONS.gannsquare },
      { tool: "gannsquare",      label: "Gann square",       icon: ICONS.gannsquare },
      { tool: "gannfan",         label: "Gann fan",          icon: ICONS.gannfan },
    ],
  },
  {
    id: "patterns", categoryIcon: ICONS.headshoulders, categoryLabel: "Chart Patterns",
    tools: [
      { tool: "abcd",           label: "ABCD pattern",        icon: ICONS.abcd },
      { tool: "cypher",         label: "Cypher pattern",      icon: ICONS.abcd },
      { tool: "headshoulders",  label: "Head and shoulders",  icon: ICONS.headshoulders },
      { tool: "trianglepat",    label: "Triangle pattern",    icon: ICONS.triangle },
      { tool: "threedrives",    label: "Three drives pattern",icon: ICONS.elliott },
    ],
  },
  {
    id: "elliott", categoryIcon: ICONS.elliott, categoryLabel: "Elliott Waves",
    tools: [
      { tool: "elliottimpulse",   label: "Elliott impulse wave (1·2·3·4·5)",        icon: ICONS.elliott },
      { tool: "elliottcorrection",label: "Elliott correction wave (A·B·C)",          icon: ICONS.elliott },
      { tool: "elliotttriangle",  label: "Elliott triangle wave (A·B·C·D·E)",       icon: ICONS.elliott },
      { tool: "elliottdouble",    label: "Elliott double combo wave (W·X·Y)",        icon: ICONS.sineline },
      { tool: "elliotttriple",    label: "Elliott triple combo wave (W·X·Y·X·Z)",   icon: ICONS.sineline },
    ],
  },
  {
    id: "cycles", categoryIcon: ICONS.cycliclines, categoryLabel: "Cycles",
    tools: [
      { tool: "cycliclines", label: "Cyclic lines", icon: ICONS.cycliclines },
      { tool: "timecycles",  label: "Time cycles",  icon: ICONS.cycliclines },
      { tool: "sineline",    label: "Sine line",    icon: ICONS.sineline },
    ],
  },
  {
    id: "forecast", categoryIcon: ICONS.longposition, categoryLabel: "Forecasting",
    tools: [
      { tool: "longposition",     label: "Long position",     icon: ICONS.longposition },
      { tool: "shortposition",    label: "Short position",    icon: ICONS.shortposition },
      { tool: "positionforecast", label: "Position forecast", icon: ICONS.longposition },
      { tool: "barpattern",       label: "Bar pattern",       icon: ICONS.elliott },
      { tool: "sector",           label: "Sector",            icon: ICONS.arc },
    ],
  },
  {
    id: "volume", categoryIcon: ICONS.anchoredvwap, categoryLabel: "Volume",
    tools: [
      { tool: "anchoredvwap",      label: "Anchored VWAP",                icon: ICONS.anchoredvwap },
      { tool: "fixedrangevolume",  label: "Fixed range volume profile",   icon: ICONS.pricerange },
      { tool: "anchoredvolume",    label: "Anchored volume profile",      icon: ICONS.pricerange },
    ],
  },
  {
    id: "brushes", categoryIcon: ICONS.brush, categoryLabel: "Brushes",
    tools: [
      { tool: "brush",       label: "Brush",       icon: ICONS.brush },
      { tool: "highlighter", label: "Highlighter", icon: ICONS.highlighter },
    ],
  },
  {
    id: "arrows", categoryIcon: ICONS.arrowmarker, categoryLabel: "Arrows",
    tools: [
      { tool: "arrowmarker",   label: "Arrow marker",    icon: ICONS.arrowmarker },
      { tool: "arrow",         label: "Arrow",           icon: ICONS.arrowmarker },
      { tool: "arrowmarkup",   label: "Arrow mark up",   icon: ICONS.arrowmarkup },
      { tool: "arrowmarkdown", label: "Arrow mark down", icon: ICONS.arrowmarkdown },
    ],
  },
  {
    id: "shapes", categoryIcon: ICONS.rectangle, categoryLabel: "Shapes",
    tools: [
      { tool: "rectangle",        label: "Rectangle",          shortcut: "Alt+Shift+R", icon: ICONS.rectangle },
      { tool: "rotatedrectangle", label: "Rotated rectangle",                           icon: ICONS.rectangle },
      { tool: "path",             label: "Path",                                         icon: ICONS.polyline },
      { tool: "circle",           label: "Circle",                                       icon: ICONS.circle },
      { tool: "ellipse",          label: "Ellipse",                                      icon: ICONS.ellipse },
      { tool: "polyline",         label: "Polyline",                                     icon: ICONS.polyline },
      { tool: "triangleshape",    label: "Triangle",                                     icon: ICONS.triangle },
      { tool: "arc",              label: "Arc",                                          icon: ICONS.arc },
      { tool: "curve",            label: "Curve",                                        icon: ICONS.curve },
    ],
  },
  {
    id: "text", categoryIcon: ICONS.text, categoryLabel: "Text & Notes",
    tools: [
      { tool: "text",         label: "Text",         icon: ICONS.text },
      { tool: "note",         label: "Note",         icon: ICONS.note },
      { tool: "pricenote",    label: "Price note",   icon: ICONS.pricenote },
      { tool: "pin",          label: "Pin",          icon: ICONS.pin },
      { tool: "callout",      label: "Callout",      icon: ICONS.callout },
      { tool: "pricelabel",   label: "Price label",  icon: ICONS.pricenote },
      { tool: "flag",         label: "Flag mark",    icon: ICONS.flag },
    ],
  },
  {
    id: "measure", categoryIcon: ICONS.measure, categoryLabel: "Measure",
    tools: [
      { tool: "pricerange",      label: "Price range",          icon: ICONS.pricerange },
      { tool: "daterange",       label: "Date range",           icon: ICONS.measure },
      { tool: "datepricerange",  label: "Date and price range", icon: ICONS.measure },
    ],
  },
  {
    id: "zoom", categoryIcon: ICONS.zoom, categoryLabel: "Zoom", single: true,
    tools: [{ tool: "zoom", label: "Zoom in", icon: ICONS.zoom }],
  },
];

// ─── Props ────────────────────────────────────────────────────────────────────
interface Props {
  activeTool: string;
  onToolSelect: (tool: string) => void;
  onClearDrawings: () => void;
  hasDrawings: boolean;
  isDark: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function LeftDrawingBar({ activeTool, onToolSelect, onClearDrawings, hasDrawings, isDark }: Props) {
  const [openGroupId, setOpenGroupId] = useState<string | null>(null);
  const barRef = useRef<HTMLDivElement>(null);

  const bg        = isDark ? "#131722" : "#ffffff";
  const border    = isDark ? "rgba(255,255,255,0.07)" : "#e2e8f0";
  const iconColor = isDark ? "#9ca3af" : "#475569";
  const flyoutBg  = isDark ? "#1e2130" : "#ffffff";
  const flyoutBor = isDark ? "#374151" : "#e2e8f0";
  const hoverBg   = isDark ? "rgba(99,102,241,0.08)" : "rgba(99,102,241,0.06)";
  const labelColor= isDark ? "#d1d5db" : "#1e293b";
  const shortcutColor = isDark ? "#6b7280" : "#94a3b8";

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setOpenGroupId(null);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleGroupClick(group: ToolGroup) {
    if (group.single) {
      onToolSelect(group.tools[0].tool as string);
      setOpenGroupId(null);
    } else {
      setOpenGroupId(id => id === group.id ? null : group.id);
    }
  }

  function handleToolSelect(tool: string) {
    onToolSelect(tool);
    setOpenGroupId(null);
  }

  function isGroupActive(group: ToolGroup) {
    return group.tools.some(t => t.tool === activeTool);
  }

  return (
    <div
      ref={barRef}
      className="relative flex flex-col shrink-0 z-30"
      style={{ width: 40, background: bg, borderRight: `1px solid ${border}` }}
    >
      {/* ── Tool groups ───────────────────────────────────────────────── */}
      <div className="flex flex-col items-center py-2 gap-0.5 flex-1">
        {TOOL_GROUPS.map((group, gi) => {
          const active = isGroupActive(group);
          const open   = openGroupId === group.id;

          return (
            <div key={group.id}>
              {/* Divider before certain groups */}
              {(gi === 1 || gi === 5 || gi === 11 || gi === 14 || gi === 15) && (
                <div className="w-6 h-px mx-auto my-1" style={{ background: border }} />
              )}

              <button
                title={group.categoryLabel}
                onClick={() => handleGroupClick(group)}
                className="w-8 h-8 flex items-center justify-center rounded transition-all relative"
                style={
                  active || open
                    ? { background: "#6366f1", color: "#ffffff" }
                    : { color: iconColor }
                }
              >
                {group.categoryIcon}
                {/* Small arrow indicator for groups with sub-tools */}
                {!group.single && (
                  <span
                    className="absolute bottom-0.5 right-0.5 w-1 h-1 rounded-sm"
                    style={{ background: active ? "rgba(255,255,255,0.7)" : open ? "rgba(255,255,255,0.5)" : iconColor, opacity: 0.6 }}
                  />
                )}
              </button>

              {/* Flyout panel */}
              {open && (
                <div
                  className="absolute left-full top-0 ml-0.5 rounded shadow-2xl overflow-hidden"
                  style={{
                    minWidth: 220,
                    background: flyoutBg,
                    border: `1px solid ${flyoutBor}`,
                    top: `${gi * 36 + 8}px`,
                    maxHeight: "calc(100vh - 80px)",
                    overflowY: "auto",
                  }}
                >
                  {/* Category header */}
                  <div
                    className="px-3 py-2 text-[11px] font-semibold tracking-wider uppercase"
                    style={{ color: shortcutColor, borderBottom: `1px solid ${flyoutBor}` }}
                  >
                    {group.categoryLabel}
                  </div>

                  {/* Tool items */}
                  {group.tools.map(item => {
                    const isActive = activeTool === item.tool;
                    return (
                      <button
                        key={item.tool as string}
                        onClick={() => handleToolSelect(item.tool as string)}
                        className="w-full flex items-center gap-3 px-3 py-2 transition-colors text-left"
                        style={isActive
                          ? { background: "rgba(99,102,241,0.15)", color: "#818cf8" }
                          : { color: labelColor }}
                        onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLButtonElement).style.background = hoverBg; }}
                        onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLButtonElement).style.background = ""; }}
                      >
                        <span className="shrink-0 opacity-70">{item.icon}</span>
                        <span className="flex-1 text-sm">{item.label}</span>
                        {item.shortcut && (
                          <span className="text-[10px] shrink-0" style={{ color: shortcutColor }}>{item.shortcut}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Eraser (bottom) ───────────────────────────────────────────── */}
      <div className="flex flex-col items-center pb-2 gap-0.5">
        <div className="w-6 h-px mx-auto mb-1" style={{ background: border }} />
        <button
          title="Eraser"
          onClick={() => { onToolSelect("eraser"); setOpenGroupId(null); }}
          className="w-8 h-8 flex items-center justify-center rounded transition-all"
          style={activeTool === "eraser"
            ? { background: "#6366f1", color: "#ffffff" }
            : { color: iconColor }}
        >
          {ICONS.eraser}
        </button>
        <button
          title={hasDrawings ? "Clear all drawings" : "No drawings to clear"}
          onClick={onClearDrawings}
          disabled={!hasDrawings}
          className="w-8 h-8 flex items-center justify-center rounded transition-all"
          style={{ color: hasDrawings ? "#f87171" : isDark ? "#374151" : "#cbd5e1", cursor: hasDrawings ? "pointer" : "not-allowed" }}
        >
          <Svg size={14}>
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
          </Svg>
        </button>
      </div>
    </div>
  );
}
